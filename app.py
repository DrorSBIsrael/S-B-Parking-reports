from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_mail import Mail, Message
from supabase import create_client, Client
import os
import random
import string
import re
import html
# הייבואים החדשים לעיבוד מיילים
import imaplib
import email as email_lib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import io
import csv
from datetime import datetime, timedelta
import pandas as pd
from apscheduler.schedulers.background import BackgroundScheduler
import atexit

print("🔥 WORKING VERSION - NOW WITH EMAIL AND SECURITY!")

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'

# Supabase configuration
SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_ANON_KEY')
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# הגדרות מייל עם Gmail + Environment Variables
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
app.config['MAIL_USE_SSL'] = os.environ.get('MAIL_USE_SSL', 'False').lower() == 'true'
app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'True').lower() == 'true'
app.config['MAIL_USERNAME'] = os.environ.get('GMAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('GMAIL_APP_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('GMAIL_USERNAME')
app.config['MAIL_SUPPRESS_SEND'] = False
app.config['MAIL_DEBUG'] = True

# הגדרות נוספות לעיבוד מיילים
app.config['REPORTS_EMAIL'] = os.environ.get('GMAIL_USERNAME')  # משתמש בנתונים הקיימים
app.config['REPORTS_EMAIL_PASSWORD'] = os.environ.get('GMAIL_APP_PASSWORD')  # משתמש בנתונים הקיימים
app.config['SENDER_EMAIL'] = 'Report@sbparking.co.il'

# בדיקה שהמשתנים קיימים
if not app.config['MAIL_USERNAME'] or not app.config['MAIL_PASSWORD']:
    print("⚠️  WARNING: Gmail credentials not found in environment variables!")

mail = Mail(app)

# הגנות אבטחה
def validate_input(input_text, input_type="general"):
    """אימות קלט מפני SQL Injection ותקיפות אחרות"""
    
    if not input_text:
        return False, "שדה ריק"
    
    # הגנה בסיסית - הסרת תווים מסוכנים
    input_text = html.escape(input_text.strip())
    
    # רשימת מילים מסוכנות (SQL Injection)
    dangerous_words = [
        'select', 'insert', 'update', 'delete', 'drop', 'create', 'alter',
        'union', 'join', 'exec', 'execute', 'script', 'declare', 'cast',
        'convert', 'begin', 'end', 'if', 'else', 'while', 'waitfor',
        'shutdown', 'sp_', 'xp_', 'cmdshell', 'openrowset', 'opendatasource'
    ]
    
    # בדיקת מילים מסוכנות
    lower_input = input_text.lower()
    for word in dangerous_words:
        if word in lower_input:
            print(f"🚨 Security threat detected: '{word}' in input")
            return False, f"קלט לא חוקי - מכיל מילה אסורה: {word}"
    
    # בדיקת תווים מסוכנים
    dangerous_chars = ["'", '"', ';', '--', '/*', '*/', '<', '>', '&', '|', '`']
    for char in dangerous_chars:
        if char in input_text:
            print(f"🚨 Security threat detected: '{char}' character in input")
            return False, f"קלט לא חוקי - מכיל תו אסור: {char}"
    
    # אימות לפי סוג הקלט
    if input_type == "username":
        # שם משתמש: רק אותיות באנגלית, מספרים, נקודה וקו תחתון
        if not re.match(r'^[a-zA-Z0-9._]+$', input_text):
            return False, "שם משתמש יכול להכיל רק אותיות באנגלית, מספרים, נקודה וקו תחתון"
        if len(input_text) < 3 or len(input_text) > 50:
            return False, "שם משתמש חייב להיות בין 3-50 תווים"
    
    elif input_type == "password":
        # סיסמה: בדיקות בסיסיות
        if len(input_text) < 4 or len(input_text) > 100:
            return False, "סיסמה חייבת להיות בין 4-100 תווים"
    
    elif input_type == "email":
        # אימות אימייל בסיסי
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, input_text):
            return False, "כתובת אימייל לא תקינה"
    
    elif input_type == "verification_code":
        # קוד אימות: רק 6 ספרות
        if not re.match(r'^[0-9]{6}$', input_text):
            return False, "קוד אימות חייב להיות 6 ספרות בלבד"
    
    return True, input_text

def rate_limit_check(identifier, max_attempts=5, time_window=300):
    """בדיקת הגבלת קצב - מונע התקפות brute force"""
    # פשוט לעכשיו - בפרויקט אמיתי נשתמש ב-Redis או מסד נתונים
    # כרגע רק נדפיס אזהרה
    print(f"🔍 Rate limit check for: {identifier}")
    return True

def generate_verification_code():
    """יצירת קוד אימות של 6 ספרות"""
    return ''.join(random.choices(string.digits, k=6))

def store_verification_code(email, code):
    """שמירת קוד אימות בטבלת user_parkings הקיימת"""
    try:
        # אימות אימייל לפני שמירה
        is_valid, validated_email = validate_input(email, "email")
        if not is_valid:
            print(f"❌ Invalid email format: {email}")
            return False
        
        # חישוב זמן תפוגה (10 דקות מעכשיו)
        expires_at = datetime.now() + timedelta(minutes=10)
        expires_str = expires_at.strftime('%Y-%m-%d %H:%M:%S')
        
        print(f"🔄 Updating user_parkings for {validated_email} with code {code}")
        
        # שימוש ב-Supabase עם פרמטרים בטוחים
        result = supabase.table('user_parkings').update({
            'verification_code': code,
            'code_expires_at': expires_str
        }).eq('email', validated_email).execute()
        
        print(f"✅ Update result: {result.data}")
        print(f"✅ Code saved: {code} expires at {expires_str}")
        return True
        
    except Exception as e:
        print(f"❌ Failed to save code: {str(e)}")
        return False

def send_verification_email(email, code):
    """שליחת מייל עם Gmail + App Password מ-Environment Variables"""
    
    # אימות אימייל
    is_valid, validated_email = validate_input(email, "email")
    if not is_valid:
        print(f"❌ Invalid email format: {email}")
        return False
    
    # בדיקה שיש נתונים
    if not app.config['MAIL_USERNAME'] or not app.config['MAIL_PASSWORD']:
        print(f"❌ Gmail credentials missing in environment variables")
        print(f"📱 BACKUP CODE for {validated_email}: {code}")
        return False
    
    try:
        print(f"🚀 Starting Gmail send to {validated_email}...")
        
        msg = Message(
            subject='קוד אימות - S&B Parking',
            recipients=[validated_email],
            html=f"""
            <div style="font-family: Arial, sans-serif; direction: rtl; text-align: right;">
                <h2 style="color: #667eea;">שיידט את בכמן ישראל</h2>
                <h3>קוד האימות שלך:</h3>
                <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; text-align: center; margin: 20px 0;">
                    <span style="font-size: 32px; font-weight: bold; color: #667eea; letter-spacing: 5px;">{code}</span>
                </div>
                <p>הקוד תקף ל-10 דקות בלבד.</p>
                <p>אם לא ביקשת קוד זה, התעלם מהודעה זו.</p>
                <hr>
                <p style="color: #666; font-size: 12px;">S&B Parking - מערכת דוחות חניות      דרור פריץ</p>
            </div>
            """,
            sender=app.config['MAIL_USERNAME']
        )
        
        print(f"🔄 Sending via Gmail...")
        mail.send(msg)
        
        print(f"✅ Gmail email sent successfully to {validated_email}")
        return True
        
    except Exception as e:
        print(f"❌ Gmail error: {str(e)}")
        print(f"📱 BACKUP CODE for {validated_email}: {code}")
        return False

def verify_code_from_database(email, code):
    """בדיקת קוד אימות מטבלת user_parkings"""
    try:
        # אימות קלט
        is_valid_email, validated_email = validate_input(email, "email")
        is_valid_code, validated_code = validate_input(code, "verification_code")
        
        if not is_valid_email:
            print(f"❌ Invalid email format: {email}")
            return False
            
        if not is_valid_code:
            print(f"❌ Invalid code format: {code}")
            return False
        
        # חיפוש משתמש עם הקוד - שימוש ב-Supabase עם פרמטרים בטוחים
        result = supabase.table('user_parkings').select('verification_code, code_expires_at').eq('email', validated_email).execute()
        
        if not result.data:
            print(f"❌ No user found for {validated_email}")
            return False
            
        user_data = result.data[0]
        stored_code = user_data.get('verification_code')
        expires_at_str = user_data.get('code_expires_at')
        
        print(f"🔍 Code verification attempt for {validated_email}")
        
        if not stored_code or stored_code != validated_code:
            print(f"❌ Code mismatch")
            return False
            
        # בדיקת תוקף
        if expires_at_str:
            expires_at = datetime.fromisoformat(expires_at_str.replace('Z', '').replace('+00:00', ''))
            if datetime.now() > expires_at:
                print(f"❌ Code expired")
                return False
        
        # מחיקת הקוד אחרי שימוש מוצלח
        supabase.table('user_parkings').update({
            'verification_code': None,
            'code_expires_at': None
        }).eq('email', validated_email).execute()
        
        print(f"✅ Code verified and cleared for {validated_email}")
        return True
        
    except Exception as e:
        print(f"❌ Database verification failed: {str(e)}")
        return False

# פונקציות עיבוד מיילים חדשות
def connect_to_email():
    """התחברות לתיבת הדואר לקריאת מיילים"""
    try:
        # התחברות ל-Gmail IMAP
        mail = imaplib.IMAP4_SSL('imap.gmail.com')
        mail.login(app.config['REPORTS_EMAIL'], app.config['REPORTS_EMAIL_PASSWORD'])
        return mail
    except Exception as e:
        print(f"❌ Failed to connect to email: {str(e)}")
        return None

def extract_csv_from_email(msg):
    """חילוץ קובץ CSV מהמייל"""
    csv_files = []
    
    for part in msg.walk():
        if part.get_content_disposition() == 'attachment':
            filename = part.get_filename()
            if filename and filename.lower().endswith('.csv'):
                csv_content = part.get_payload(decode=True)
                csv_files.append({
                    'filename': filename,
                    'content': csv_content.decode('utf-8-sig')
                })
                print(f"📎 Found CSV file: {filename}")
    
    return csv_files

def parse_parking_csv(csv_content):
    """פירוק קובץ CSV של נתוני חניונים"""
    try:
        csv_reader = csv.reader(io.StringIO(csv_content))
        rows = list(csv_reader)
        
        print(f"📊 CSV has {len(rows)} rows")
        
        parsed_data = []
        for i, row in enumerate(rows):
            if i == 0 and any(field.isalpha() for field in row):
                continue
                
            try:
                if len(row) >= 35:
                    parking_data = {
                        'project_number': int(row[0]),
                        'lglobalref': int(row[1]), 
                        'scomputer': int(row[2]),
                        'sshiftid': int(row[3]),
                        'ttcret': row[4],
                        'ttendt': row[5],
                        'ctext': row[6],
                        'scash': int(float(row[7])) if row[7] else 0,
                        'scredit': int(float(row[8])) if row[8] else 0,
                        'stotcacr': int(float(row[9])) if row[9] else 0,
                        'spango': int(float(row[10])) if row[10] else 0,
                        'scelo': int(float(row[11])) if row[11] else 0,
                        'sencoder1': int(row[12]) if row[12] else 0,
                        'sencoder2': int(row[13]) if row[13] else 0,
                        'sencoder3': int(row[14]) if row[14] else 0,
                        'sencodertot': int(row[15]) if row[15] else 0,
                        'topenb': int(row[16]) if row[16] else 0,
                        'tentrys': int(row[17]) if row[17] else 0,
                        'tentryp': int(row[18]) if row[18] else 0,
                        'tentrytot': int(row[19]) if row[19] else 0,
                        'teeits': int(row[20]) if row[20] else 0,
                        'teeitp': int(row[21]) if row[21] else 0,
                        'teeittot': int(row[22]) if row[22] else 0,
                        'tentryap': int(row[23]) if row[23] else 0,
                        'teeitap': int(row[24]) if row[24] else 0,
                        'tsper1': int(row[25]) if row[25] else 0,
                        'tsper2': int(row[26]) if row[26] else 0,
                        'stay015': int(row[27]) if row[27] else 0,
                        'stay030': int(row[28]) if row[28] else 0,
                        'stay045': int(row[29]) if row[29] else 0,
                        'stay060': int(row[30]) if row[30] else 0,
                        'stay2': int(row[31]) if row[31] else 0,
                        'stay3': int(row[32]) if row[32] else 0,
                        'stay4': int(row[33]) if row[33] else 0,
                        'stay5': int(row[34]) if row[34] else 0,
                        'stay6': int(row[35]) if len(row) > 35 and row[35] else 0,
                        'stay724': int(row[36]) if len(row) > 36 and row[36] else 0,
                        'tsper3': int(row[37]) if len(row) > 37 and row[37] else 0,
                        'tsper4': int(row[38]) if len(row) > 38 and row[38] else 0,
                        'tsper5': int(row[39]) if len(row) > 39 and row[39] else 0,
                        'tsper6': int(row[40]) if len(row) > 40 and row[40] else 0,
                        'sexp': int(row[41]) if len(row) > 41 and row[41] else 0
                    }
                    parsed_data.append(parking_data)
                    
            except (ValueError, IndexError) as e:
                print(f"⚠️ Error parsing row {i}: {str(e)}")
                continue
        
        print(f"✅ Successfully parsed {len(parsed_data)} data rows")
        return parsed_data
        
    except Exception as e:
        print(f"❌ Error parsing CSV: {str(e)}")
        return []

def insert_parking_data_to_db(parking_data_list):
    """הכנסת נתוני חניונים למסד הנתונים"""
    success_count = 0
    error_count = 0
    
    for data in parking_data_list:
        try:
            # קריאה לפונקציה import_single_parking_data
            result = supabase.rpc('import_single_parking_data', {
                'p_project_number': data['project_number'],
                'p_lglobalref': data['lglobalref'],
                'p_scomputer': data['scomputer'], 
                'p_sshiftid': data['sshiftid'],
                'p_ttcret': data['ttcret'],
                'p_ttendt': data['ttendt'],
                'p_ctext': data['ctext'],
                'p_scash': data['scash'],
                'p_scredit': data['scredit'],
                'p_stotcacr': data['stotcacr'],
                'p_spango': data['spango'],
                'p_scelo': data['scelo'],
                'p_sencoder1': data['sencoder1'],
                'p_sencoder2': data['sencoder2'],
                'p_sencoder3': data['sencoder3'],
                'p_sencodertot': data['sencodertot'],
                'p_topenb': data['topenb'],
                'p_tentrys': data['tentrys'],
                'p_tentryp': data['tentryp'],
                'p_tentrytot': data['tentrytot'],
                'p_teeits': data['teeits'],
                'p_teeitp': data['teeitp'],
                'p_teeittot': data['teeittot'],
                'p_tentryap': data['tentryap'],
                'p_teeitap': data['teeitap'],
                'p_tsper1': data['tsper1'],
                'p_tsper2': data['tsper2'],
                'p_stay015': data['stay015'],
                'p_stay030': data['stay030'],
                'p_stay045': data['stay045'],
                'p_stay060': data['stay060'],
                'p_stay2': data['stay2'],
                'p_stay3': data['stay3'],
                'p_stay4': data['stay4'],
                'p_stay5': data['stay5'],
                'p_stay6': data['stay6'],
                'p_stay724': data['stay724'],
                'p_tsper3': data['tsper3'],
                'p_tsper4': data['tsper4'],
                'p_tsper5': data['tsper5'],
                'p_tsper6': data['tsper6'],
                'p_sexp': data['sexp']
            }).execute()
            
            success_count += 1
            print(f"✅ Inserted data for project {data['project_number']}")
            
        except Exception as e:
            error_count += 1
            print(f"❌ Failed to insert data for project {data.get('project_number', 'unknown')}: {str(e)}")
    
    return success_count, error_count

def check_and_process_emails():
    """פונקציה ראשית לבדיקת ועיבוד מיילים"""
    try:
        print("🔍 Checking for new parking data emails...")
        
        # התחברות לאימייל
        mail = connect_to_email()
        if not mail:
            return {"success": False, "message": "Failed to connect to email"}
        
        # בחירת תיבת הדואר הנכנס
        mail.select('inbox')
        
        # חיפוש מיילים חדשים מהשולח הרצוי
        search_criteria = f'(FROM "{app.config["SENDER_EMAIL"]}" UNSEEN)'
        result, message_ids = mail.search(None, search_criteria)
        
        if result != 'OK':
            print("❌ Failed to search emails")
            mail.logout()
            return {"success": False, "message": "Failed to search emails"}
        
        message_ids = message_ids[0].split()
        print(f"📬 Found {len(message_ids)} unread emails from {app.config['SENDER_EMAIL']}")
        
        total_processed = 0
        total_errors = 0
        processed_files = []
        
        # עיבוד כל מייל
        for msg_id in message_ids:
            try:
                # קבלת המייל
                result, msg_data = mail.fetch(msg_id, '(RFC822)')
                if result != 'OK':
                    continue
                
                # פירוק המייל
                email_body = msg_data[0][1]
                msg = email_lib.message_from_bytes(email_body)
                
                print(f"📧 Processing email: {msg.get('Subject', 'No Subject')}")
                
                # חילוץ קבצי CSV
                csv_files = extract_csv_from_email(msg)
                
                # עיבוד כל קובץ CSV
                for csv_file in csv_files:
                    print(f"🔄 Processing file: {csv_file['filename']}")
                    
                    # פירוק הנתונים
                    parking_data = parse_parking_csv(csv_file['content'])
                    
                    if parking_data:
                        # הכנסה למסד נתונים
                        success, errors = insert_parking_data_to_db(parking_data)
                        total_processed += success
                        total_errors += errors
                        
                        processed_files.append({
                            'filename': csv_file['filename'],
                            'rows_processed': success,
                            'errors': errors
                        })
                        
                        print(f"📊 File {csv_file['filename']}: {success} rows processed, {errors} errors")
                
                # סימון המייל כנקרא
                mail.store(msg_id, '+FLAGS', '\\Seen')
                
            except Exception as e:
                print(f"❌ Error processing email {msg_id}: {str(e)}")
                total_errors += 1
        
        # סגירת החיבור
        mail.logout()
        
        result_message = f"✅ Processing complete: {total_processed} rows processed, {total_errors} errors"
        print(result_message)
        
        return {
            "success": True,
            "message": result_message,
            "total_processed": total_processed,
            "total_errors": total_errors,
            "processed_files": processed_files
        }
        
    except Exception as e:
        print(f"❌ Email processing error: {str(e)}")
        return {"success": False, "message": f"Error: {str(e)}"}

def automated_email_check():
    """פונקציה לבדיקה אוטומטית של מיילים - רק בשעות 03:00-08:00"""
    try:
        current_hour = datetime.now().hour
        
        # בדיקה שאנחנו בשעות הנכונות (03:00-08:00)
        if 3 <= current_hour <= 8:
            print(f"🕐 {datetime.now().strftime('%H:%M:%S')} - Running automated email check...")
            result = check_and_process_emails()
            
            if result['success']:
                print(f"✅ Automated processing: {result['total_processed']} rows processed, {result['total_errors']} errors")
            else:
                print(f"❌ Automated processing failed: {result['message']}")
        else:
            print(f"🕐 {datetime.now().strftime('%H:%M:%S')} - Outside processing hours (03:00-08:00), skipping...")
    except Exception as e:
        print(f"❌ Automated email check error: {str(e)}")

# הגדרת Scheduler לעיבוד אוטומטי
scheduler = BackgroundScheduler()
scheduler.add_job(
    func=automated_email_check,
    trigger="interval",
    minutes=5,  # כל 5 דקות
    id='email_check_job'
)

# הפעלת ה-Scheduler
scheduler.start()

# סגירת ה-Scheduler כשהאפליקציה נסגרת
atexit.register(lambda: scheduler.shutdown())

@app.route('/')
def index():
    return redirect(url_for('login_page'))

@app.route('/login')
def login_page():
    return render_template('login.html')

@app.route('/verify')
def verify_page():
    if 'pending_email' not in session:
        return redirect(url_for('login_page'))
    return render_template('verify.html')

@app.route('/dashboard')
def dashboard():
    """דף הדשבורד הראשי"""
    if 'user_email' not in session:
        return redirect(url_for('login_page'))
    return render_template('dashboard.html')

@app.route('/api/user-info', methods=['GET'])
def get_user_info():
    """קבלת נתוני המשתמש המחובר"""
    try:
        if 'user_email' not in session:
            return jsonify({'success': False, 'message': 'לא מחובר'}), 401
        
        email = session['user_email']
        
        # קבלת נתוני המשתמש
        user_result = supabase.table('user_parkings').select(
            'username, email, role, project_number, parking_name, company_type, access_level'
        ).eq('email', email).execute()
        
        if not user_result.data:
            return jsonify({'success': False, 'message': 'משתמש לא נמצא'})
        
        user_data = user_result.data[0]
        
        return jsonify({
            'success': True,
            'user': user_data
        })
        
    except Exception as e:
        print(f"❌ Error getting user info: {str(e)}")
        return jsonify({'success': False, 'message': 'שגיאה בקבלת נתוני משתמש'})

@app.route('/api/user-parkings', methods=['GET'])
def get_user_parkings():
    """קבלת רשימת החניונים עבור מנהל קבוצה"""
    try:
        if 'user_email' not in session:
            return jsonify({'success': False, 'message': 'לא מחובר'}), 401
        
        email = session['user_email']
        
        # בדיקת הרשאות משתמש
        user_result = supabase.table('user_parkings').select(
            'access_level, company_type'
        ).eq('email', email).execute()
        
        if not user_result.data:
            return jsonify({'success': False, 'message': 'משתמש לא נמצא'})
        
        user_data = user_result.data[0]
        
        if user_data['access_level'] != 'group_manager':
            return jsonify({'success': False, 'message': 'אין הרשאה לצפייה בחניונים מרובים'})
        
        # קבלת כל החניונים של החברה
        parkings_result = supabase.table('user_parkings').select(
            'project_number, parking_name'
        ).eq('company_type', user_data['company_type']).execute()
        
        # הסרת כפילויות
        unique_parkings = {}
        for parking in parkings_result.data:
            if parking['project_number'] not in unique_parkings:
                unique_parkings[parking['project_number']] = parking
        
        parkings_list = list(unique_parkings.values())
        
        return jsonify({
            'success': True,
            'parkings': parkings_list
        })
        
    except Exception as e:
        print(f"❌ Error getting user parkings: {str(e)}")
        return jsonify({'success': False, 'message': 'שגיאה בקבלת רשימת חניונים'})

@app.route('/api/parking-data', methods=['GET'])
def get_parking_data():
    """קבלת נתוני החניון לפי תאריכים והרשאות"""
    try:
        if 'user_email' not in session:
            return jsonify({'success': False, 'message': 'לא מחובר'}), 401
        
        # קבלת פרמטרים
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        parking_id = request.args.get('parking_id')  # אופציונלי - למנהלי קבוצה
        
        if not start_date or not end_date:
            return jsonify({'success': False, 'message': 'חסרים תאריכים'})
        
        # אימות תאריכים
        is_valid_start, validated_start = validate_input(start_date, "general")
        is_valid_end, validated_end = validate_input(end_date, "general")
        
        if not is_valid_start or not is_valid_end:
            return jsonify({'success': False, 'message': 'תאריכים לא תקינים'})
        
        email = session['user_email']
        
        # קבלת נתוני המשתמש
        user_result = supabase.table('user_parkings').select(
            'access_level, project_number, company_type'
        ).eq('email', email).execute()
        
        if not user_result.data:
            return jsonify({'success': False, 'message': 'משתמש לא נמצא'})
        
        user_data = user_result.data[0]
        
        # בניית שאילתה בהתאם להרשאות
        query = supabase.table('parking_data').select('*')
        
        # הגבלת תאריכים
        query = query.gte('report_date', validated_start).lte('report_date', validated_end)
        
        # הגבלת חניונים לפי הרשאות
        if user_data['access_level'] == 'single_parking':
            # משתמש חניון בודד - רק החניון שלו
            query = query.eq('project_number', user_data['project_number'])
            
        elif user_data['access_level'] == 'group_manager':
            # מנהל קבוצה
            if parking_id:
                # אימות שהחניון שייך לחברה שלו
                parking_check = supabase.table('user_parkings').select('project_number').eq(
                    'project_number', parking_id
                ).eq('company_type', user_data['company_type']).execute()
                
                if not parking_check.data:
                    return jsonify({'success': False, 'message': 'אין הרשאה לחניון זה'})
                
                query = query.eq('project_number', parking_id)
            else:
                # כל החניונים של החברה
                company_parkings = supabase.table('user_parkings').select('project_number').eq(
                    'company_type', user_data['company_type']
                ).execute()
                
                parking_numbers = [p['project_number'] for p in company_parkings.data]
                
                if parking_numbers:
                    query = query.in_('project_number', parking_numbers)
                else:
                    return jsonify({'success': True, 'data': []})
        else:
            return jsonify({'success': False, 'message': 'רמת הרשאה לא מוכרת'})
        
        # הגבלת כמות התוצאות (אבטחה)
        query = query.limit(10000)
        
        # ביצוע השאילתה
        result = query.execute()
        
        # עיבוד הנתונים
        processed_data = []
        for row in result.data:
            # וידוא שכל השדות הנדרשים קיימים
            processed_row = {
                'id': row.get('id'),
                'parking_id': row.get('parking_id'),
                'report_date': row.get('report_date'),
                'project_number': row.get('project_number'),
                'total_revenue_shekels': float(row.get('total_revenue_shekels', 0)),
                'net_revenue_shekels': float(row.get('net_revenue_shekels', 0)),
                's_cash_shekels': float(row.get('s_cash_shekels', 0)),
                's_credit_shekels': float(row.get('s_credit_shekels', 0)),
                's_pango_shekels': float(row.get('s_pango_shekels', 0)),
                's_celo_shekels': float(row.get('s_celo_shekels', 0)),
                't_entry_tot': int(row.get('t_entry_tot', 0)),
                't_exit_tot': int(row.get('t_exit_tot', 0)),
                't_entry_s': int(row.get('t_entry_s', 0)),  # מנויים
                't_entry_p': int(row.get('t_entry_p', 0)),  # מזדמנים
                't_entry_ap': int(row.get('t_entry_ap', 0)),  # אפליקציה
                't_open_b': int(row.get('t_open_b', 0)),  # פתיחות מחסום
                'stay_015': int(row.get('stay_015', 0)),
                'stay_030': int(row.get('stay_030', 0)),
                'stay_045': int(row.get('stay_045', 0)),
                'stay_060': int(row.get('stay_060', 0)),
                'stay_2': int(row.get('stay_2', 0)),
                'stay_3': int(row.get('stay_3', 0)),
                'stay_4': int(row.get('stay_4', 0)),
                'stay_5': int(row.get('stay_5', 0)),
                'stay_6': int(row.get('stay_6', 0)),
                'stay_724': int(row.get('stay_724', 0))
            }
            processed_data.append(processed_row)
        
        print(f"✅ Retrieved {len(processed_data)} parking records for user {email}")
        
        return jsonify({
            'success': True,
            'data': processed_data,
            'total_records': len(processed_data)
        })
        
    except Exception as e:
        print(f"❌ Error getting parking data: {str(e)}")
        return jsonify({'success': False, 'message': 'שגיאה בקבלת נתוני חניון'})

def validate_date_format(date_string):
    """בדיקת תקפות פורמט תאריך YYYY-MM-DD"""
    try:
        datetime.strptime(date_string, '%Y-%m-%d')
        return True
    except ValueError:
        return False

@app.route('/api/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        username = data.get('username', '').strip()
        password = data.get('password', '').strip()
        
        # אימות קלט
        is_valid_username, validated_username = validate_input(username, "username")
        is_valid_password, validated_password = validate_input(password, "password")
        
        if not is_valid_username:
            print(f"🚨 Invalid username attempt: {username}")
            return jsonify({'success': False, 'message': is_valid_username})
        
        if not is_valid_password:
            print(f"🚨 Invalid password attempt from user: {validated_username}")
            return jsonify({'success': False, 'message': is_valid_password})
        
        # בדיקת rate limiting
        client_ip = request.environ.get('HTTP_X_REAL_IP', request.remote_addr)
        if not rate_limit_check(f"login_{client_ip}_{validated_username}"):
            print(f"🚨 Rate limit exceeded for {client_ip}")
            return jsonify({'success': False, 'message': 'יותר מדי ניסיונות. נסה שוב מאוחר יותר'})
        
        print(f"🔑 Login attempt: {validated_username}")
        
        # Check user credentials עם פרמטרים בטוחים
        auth_result = supabase.rpc('user_login', {
            'p_username': validated_username,
            'p_password': validated_password
        }).execute()
        
        print(f"🔐 Auth result: {auth_result.data}")
        
        if auth_result.data == True:
            # Get user email עם פרמטרים בטוחים
            user_result = supabase.table('user_parkings').select('email').eq('username', validated_username).execute()
            
            if user_result.data and len(user_result.data) > 0:
                email = user_result.data[0]['email']
                print(f"✅ Email found: {email}")
                
                # יצירת קוד אימות חדש
                verification_code = generate_verification_code()
                print(f"🎯 Generated code: {verification_code}")
                
                # שמירה במסד נתונים
                if store_verification_code(email, verification_code):
                    # שליחת מייל
                    print(f"🚀 Attempting to send email to {email}...")
                    email_sent = send_verification_email(email, verification_code)
                    print(f"📧 Email send result: {email_sent}")
                    
                    # שמירה ב-session
                    session['pending_email'] = email
                    print(f"📧 Code ready for {email}: {verification_code}")
                    return jsonify({'success': True, 'redirect': '/verify'})
                else:
                    return jsonify({'success': False, 'message': 'שגיאה בשמירת הקוד'})
            else:
                return jsonify({'success': False, 'message': 'משתמש לא נמצא'})
        else:
            print(f"❌ Authentication failed for: {validated_username}")
            return jsonify({'success': False, 'message': 'שם משתמש או סיסמה שגויים'})
            
    except Exception as e:
        print(f"❌ Login error: {str(e)}")
        return jsonify({'success': False, 'message': 'שגיאה במערכת'})

@app.route('/api/verify-code', methods=['POST'])
def verify_code():
    try:
        data = request.get_json()
        code = data.get('code', '').strip()
        email = session.get('pending_email')
        
        # אימות קוד
        is_valid_code, validated_code = validate_input(code, "verification_code")
        if not is_valid_code:
            print(f"🚨 Invalid verification code format: {code}")
            return jsonify({'success': False, 'message': 'קוד לא תקין'})
        
        if not email:
            print(f"🚨 No pending email in session")
            return jsonify({'success': False, 'message': 'אין בקשה לאימות'})
        
        # בדיקת rate limiting
        client_ip = request.environ.get('HTTP_X_REAL_IP', request.remote_addr)
        if not rate_limit_check(f"verify_{client_ip}_{email}"):
            return jsonify({'success': False, 'message': 'יותר מדי ניסיונות. נסה שוב מאוחר יותר'})
        
        print(f"🔍 Verify attempt: code={validated_code}, email={email}")
        
        # בדיקת הקוד מהמסד נתונים
        if verify_code_from_database(email, validated_code):
            session['user_email'] = email
            session.pop('pending_email', None)
            print(f"✅ SUCCESS - Redirecting to dashboard")
            return jsonify({'success': True, 'redirect': '/dashboard'})
        else:
            print(f"❌ FAILED - Invalid or expired code")
            return jsonify({'success': False, 'message': 'קוד שגוי או פג תוקף'})
            
    except Exception as e:
        print(f"❌ Verify error: {str(e)}")
        return jsonify({'success': False, 'message': 'שגיאה במערכת'})

# API endpoints לניטור ובדיקה
@app.route('/api/email-status', methods=['GET'])
def get_email_status():
    """קבלת סטטוס תכונת המיילים והשעות הפעילות"""
    try:
        if 'user_email' not in session:
            return jsonify({'success': False, 'message': 'לא מחובר'}), 401
        
        current_hour = datetime.now().hour
        is_active_hours = 3 <= current_hour <= 8
        
        # בדיקה שיש את כל הנתונים הנדרשים
        has_email_config = bool(
            app.config.get('REPORTS_EMAIL') and 
            app.config.get('REPORTS_EMAIL_PASSWORD')
        )
        
        return jsonify({
            'success': True,
            'email_configured': has_email_config,
            'reports_email': app.config.get('REPORTS_EMAIL', 'Not configured'),
            'sender_email': app.config.get('SENDER_EMAIL', 'Not configured'),
            'current_hour': current_hour,
            'is_active_hours': is_active_hours,
            'active_hours': '03:00-08:00',
            'check_interval': '5 minutes',
            'scheduler_running': scheduler.running if 'scheduler' in globals() else False
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/manual-email-check', methods=['POST'])
def manual_email_check():
    """בדיקה ידנית של מיילים - רק למנהלים ורק למטרות בדיקה"""
    try:
        if 'user_email' not in session:
            return jsonify({'success': False, 'message': 'לא מחובר'}), 401
        
        # בדיקת הרשאות - רק מנהלים יכולים להפעיל
        user_result = supabase.table('user_parkings').select('access_level').eq('email', session['user_email']).execute()
        
        if not user_result.data or user_result.data[0]['access_level'] != 'group_manager':
            return jsonify({'success': False, 'message': 'אין הרשאה לעיבוד מיילים'}), 403
        
        # הפעלת עיבוד המיילים
        result = check_and_process_emails()
        
        return jsonify(result)
        
    except Exception as e:
        print(f"❌ Manual email processing error: {str(e)}")
        return jsonify({'success': False, 'message': 'שגיאה בעיבוד מיילים'})

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login_page'))

if __name__ == '__main__':
    app.run(debug=True)
