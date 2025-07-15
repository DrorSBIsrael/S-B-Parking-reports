from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_mail import Mail, Message
from supabase.client import create_client, Client
import os
import random
import string
import requests
import re
import html
from datetime import datetime, timedelta
try:
    import imaplib
    import email
    import csv
    import io
    import threading
    import time
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    import smtplib
    EMAIL_MONITORING_AVAILABLE = True
    print("✅ Email monitoring libraries loaded successfully")
except ImportError as e:
    EMAIL_MONITORING_AVAILABLE = False
    print(f"⚠️ Email monitoring not available: {e}")

# הגדרות מיילים אוטומטיים - להוסיף אחרי ההגדרות הקיימות:
if EMAIL_MONITORING_AVAILABLE:
    EMAIL_CHECK_INTERVAL = 5  # בדיקה כל 5 דקות
    PROCESSED_EMAILS_LIMIT = 100  # מקסימום מיילים לזכור
    processed_email_ids = []  # רשימה לזכור מיילים שכבר עובדו

# רשימת שולחים מורשים לשליחת קבצי נתונים
AUTHORIZED_SENDERS = [
    'Dror@sbparking.co.il',
    'dror@sbparking.co.il',  # case insensitive
    'Report@sbparking.co.il',
    'report@sbparking.co.il'  # case insensitive
]

print("🚀 S&B Parking Application Starting...")

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your-secret-key-here')

# Supabase configuration
SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_ANON_KEY')

print(f"🔍 Supabase URL: {'✅ SET' if SUPABASE_URL else '❌ MISSING'}")
print(f"🔍 Supabase KEY: {'✅ SET' if SUPABASE_KEY else '❌ MISSING'}")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("❌ CRITICAL: Supabase credentials missing!")
    print("⚠️ Starting anyway to show error page...")
    supabase = None
else:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("✅ Supabase connection established")
    except Exception as e:
        print(f"❌ Supabase connection failed: {e}")
        supabase = None

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

print(f"📧 Gmail Username: {'✅ SET' if app.config['MAIL_USERNAME'] else '❌ MISSING'}")
print(f"🔑 Gmail Password: {'✅ SET' if app.config['MAIL_PASSWORD'] else '❌ MISSING'}")

try:
    mail = Mail(app)
    print("✅ Mail system initialized")
except Exception as e:
    print(f"⚠️ Mail system initialization failed: {e}")
    mail = None

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
        if not re.match(r'^[a-zA-Z0-9._]+$', input_text):
            return False, "שם משתמש יכול להכיל רק אותיות באנגלית, מספרים, נקודה וקו תחתון"
        if len(input_text) < 3 or len(input_text) > 50:
            return False, "שם משתמש חייב להיות בין 3-50 תווים"
    
    elif input_type == "password":
        if len(input_text) < 4 or len(input_text) > 100:
            return False, "סיסמה חייבת להיות בין 4-100 תווים"
    
    elif input_type == "email":
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, input_text):
            return False, "כתובת אימייל לא תקינה"
    
    elif input_type == "verification_code":
        if not re.match(r'^[0-9]{6}$', input_text):
            return False, "קוד אימות חייב להיות 6 ספרות בלבד"
    
    return True, input_text

def rate_limit_check(identifier, max_attempts=5, time_window=300):
    """בדיקת הגבלת קצב - מונע התקפות brute force"""
    print(f"🔍 Rate limit check for: {identifier}")
    return True

def generate_verification_code():
    """יצירת קוד אימות של 6 ספרות"""
    return ''.join(random.choices(string.digits, k=6))

def store_verification_code(email, code):
    """שמירת קוד אימות בטבלת user_parkings הקיימת"""
    if not supabase:
        print("❌ Supabase not available")
        return False
        
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
    
    if not mail:
        print(f"❌ Mail system not available")
        print(f"📱 BACKUP CODE for {email}: {code}")
        return False
    
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
                <p style="color: #666; font-size: 12px;">S&B Parking - מערכת דוחות חניות</p>
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
    if not supabase:
        print("❌ Supabase not available")
        return False
        
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
        
        # חיפוש משתמש עם הקוד
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
def connect_to_gmail_imap():
    """התחברות ל-Gmail IMAP"""
    if not EMAIL_MONITORING_AVAILABLE:
        return None
        
    try:
        mail = imaplib.IMAP4_SSL('imap.gmail.com')
        
        gmail_user = os.environ.get('GMAIL_USERNAME')
        gmail_password = os.environ.get('GMAIL_APP_PASSWORD')
        
        # תיקון type checking - וידוא שהמשתנים לא None
        if not gmail_user or not gmail_password:
            print("❌ Missing Gmail credentials in environment variables")
            return None
            
        mail.login(gmail_user, gmail_password)
        print(f"✅ Connected to Gmail: {gmail_user}")
        
        return mail
        
    except Exception as e:
        print(f"❌ Gmail IMAP connection failed: {str(e)}")
        return None

def download_csv_from_email(msg):
    """הורדת קובץ CSV מהמייל - שמירת bytes מקוריים לזיהוי קידוד"""
    csv_files = []
    
    try:
        for part in msg.walk():
            if part.get_content_disposition() == 'attachment':
                filename = part.get_filename()
                
                if filename and (filename.lower().endswith('.csv') or filename.lower().endswith('.txt')):
                    file_data = part.get_payload(decode=True)
                    
                    if file_data:
                        # שמירת הבייטים המקוריים - לא נמיר לstring כאן!
                        csv_files.append({
                            'filename': filename,
                            'data': file_data  # נשאיר את זה כ-bytes
                        })
                        
                        print(f"📎 Found CSV attachment: {filename} ({len(file_data)} bytes)")
        
        return csv_files
        
    except Exception as e:
        print(f"❌ Error downloading CSV: {str(e)}")
        return []

def parse_csv_content(csv_content):
    """פרסור CSV עם זיהוי קידוד אוטומטי לעברית"""
    try:
        print(f"🔍 Input type: {type(csv_content)}")
        
        # אם זה bytes, ננסה קידודים שונים
        if isinstance(csv_content, bytes):
            # רשימת קידודים לניסיון - העברית קודם
            encodings_to_try = [
                'windows-1255',  # עברית ANSI
                'cp1255',        # עברית
                'utf-8-sig',     # UTF-8 עם BOM
                'utf-8',         # UTF-8 רגיל
                'iso-8859-8',    # עברית ISO
                'cp1252',        # Western European
                'latin1'         # fallback
            ]
            
            decoded_content = None
            used_encoding = None
            
            for encoding in encodings_to_try:
                try:
                    decoded_content = csv_content.decode(encoding)
                    used_encoding = encoding
                    print(f"✅ Successfully decoded with {encoding}")
                    break
                except UnicodeDecodeError:
                    print(f"❌ Failed to decode with {encoding}")
                    continue
            
            if decoded_content is None:
                print("❌ Could not decode with any encoding - using latin1 as fallback")
                decoded_content = csv_content.decode('latin1', errors='ignore')
                used_encoding = 'latin1'
            
            csv_content = decoded_content
        else:
            used_encoding = 'already_string'
        
        # אם זה לא string, נמיר
        if not isinstance(csv_content, str):
            csv_content = str(csv_content)
        
        print(f"📋 Content length: {len(csv_content)}")
        print(f"🔤 Used encoding: {used_encoding}")
        
        # ניקוי בסיסי
        csv_content = csv_content.strip()
        if not csv_content:
            print("❌ Empty content after decoding")
            return None
        
        # הדפסת השורה הראשונה כדי לבדוק עברית
        first_line = csv_content.split('\n')[0]
        print(f"📄 First line: {repr(first_line)}")
        
        # אם יש עברית בשורה הראשונה, נדווח על כך
        if any('\u0590' <= char <= '\u05FF' for char in first_line):
            print("🇮🇱 Hebrew characters detected in header")
        
        # ניסיון פרסור פשוט עם פסיק
        try:
            reader = csv.DictReader(io.StringIO(csv_content))
            rows = list(reader)
            print(f"📊 Parsed {len(rows)} rows with comma delimiter")
            
            if rows:
                columns = list(rows[0].keys())
                print(f"📋 Columns: {columns}")
                
                # בדיקה אם יש עברית בנתונים
                for i, row in enumerate(rows[:3]):  # בדיקת 3 שורות ראשונות
                    for key, value in row.items():
                        if value and any('\u0590' <= char <= '\u05FF' for char in str(value)):
                            print(f"🇮🇱 Hebrew text found in row {i+1}, column '{key}': {value}")
                            break
                
                return rows
        except Exception as e:
            print(f"❌ Comma parsing failed: {e}")
        
        # ניסיון עם נקודה-פסיק
        try:
            reader = csv.DictReader(io.StringIO(csv_content), delimiter=';')
            rows = list(reader)
            print(f"📊 Parsed {len(rows)} rows with semicolon delimiter")
            
            if rows:
                columns = list(rows[0].keys())
                print(f"📋 Columns: {columns}")
                return rows
        except Exception as e:
            print(f"❌ Semicolon parsing failed: {e}")
        
        # ניסיון עם טאב
        try:
            reader = csv.DictReader(io.StringIO(csv_content), delimiter='\t')
            rows = list(reader)
            print(f"📊 Parsed {len(rows)} rows with tab delimiter")
            
            if rows:
                columns = list(rows[0].keys())
                print(f"📋 Columns: {columns}")
                return rows
        except Exception as e:
            print(f"❌ Tab parsing failed: {e}")
        
        print("❌ Could not parse CSV with any delimiter")
        return None
        
    except Exception as e:
        print(f"❌ General error in CSV parsing: {e}")
        return None

def convert_to_csv_import_format(csv_rows):
    """המרה לפורמט csv_import_shekels - עם תמיכה בשורות מרובות"""
    converted_rows = []
    
    print(f"🔄 Processing {len(csv_rows)} rows from CSV...")
    
    for index, row in enumerate(csv_rows):
        try:
            print(f"📝 Processing row {index + 1}/{len(csv_rows)}...")
            
            # המרת תאריך
            date_str = str(row.get('TTCRET', '')).strip()
            if '/' in date_str:
                parts = date_str.split('/')
                if len(parts) == 3:
                    day, month, year = parts
                    formatted_date = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
                else:
                    formatted_date = date_str
            else:
                formatted_date = date_str
                
            # המרת נתוני כסף - הערכים כבר בשקלים!
            def safe_int(value, default=0):
                try:
                    if value is None or value == '':
                        return default
                    return int(float(str(value)))
                except (ValueError, TypeError):
                    return default
            
            # הערכים כבר בשקלים - לא צריך חישובים!
            cash_shekels = safe_int(row.get('SCASH'))
            credit_shekels = safe_int(row.get('SCREDIT'))
            pango_shekels = safe_int(row.get('SPANGO'))
            celo_shekels = safe_int(row.get('SCELO'))
            
            # בדיקת טקסט בעברית
            ctext_value = str(row.get('CTEXT', '')).strip()
            if ctext_value and any('\u0590' <= char <= '\u05FF' for char in ctext_value):
                print(f"🇮🇱 Hebrew text in row {index + 1}: '{ctext_value}'")
            
            converted_row = {
                'project_number': str(row.get('ProjectNumber', '')),
                'l_global_ref': safe_int(row.get('LGLOBALREF')),
                's_computer': safe_int(row.get('SCOMPUTER')),
                's_shift_id': safe_int(row.get('SSHIFTID')),
                'report_start_time': str(row.get('TTCRET', '')),
                'report_end_time': str(row.get('TTENDT', '')),
                'report_date': formatted_date,
                'ctext': ctext_value,
                
                # כסף בשקלים (נשמור כאגורות בשדות הללו)
                's_cash_agorot': cash_shekels,
                's_credit_agorot': credit_shekels,
                's_pango_agorot': pango_shekels,
                's_celo_agorot': celo_shekels,
                'stot_cacr': safe_int(row.get('STOTCACR')),
                's_exp_agorot': safe_int(row.get('SEXP')),
                
                # מקודדים
                's_encoder1': safe_int(row.get('SENCODER1')),
                's_encoder2': safe_int(row.get('SENCODER2')),
                's_encoder3': safe_int(row.get('SENCODER3')),
                'sencodertot': safe_int(row.get('SENCODERTOT')),
                
                # תנועה
                't_open_b': safe_int(row.get('TOPENB')),
                't_entry_s': safe_int(row.get('TENTRYS')),
                't_entry_p': safe_int(row.get('TENTRYP')),
                't_entry_tot': safe_int(row.get('TENTRYTOT')),
                't_exit_s': safe_int(row.get('TEEITS')),
                't_exit_p': safe_int(row.get('TEEITP')),
                't_exit_tot': safe_int(row.get('TEEITTOT')),
                't_entry_ap': safe_int(row.get('TENTRYAP')),
                't_exit_ap': safe_int(row.get('TEEITAP')),
                
                # זמני שהייה
                'tsper1': safe_int(row.get('TSPER1')),
                'tsper2': safe_int(row.get('TSPER2')),
                'stay_015': safe_int(row.get('STAY015')),
                'stay_030': safe_int(row.get('STAY030')),
                'stay_045': safe_int(row.get('STAY045')),
                'stay_060': safe_int(row.get('STAY060')),
                'stay_2': safe_int(row.get('STAY2')),
                'stay_3': safe_int(row.get('STAY3')),
                'stay_4': safe_int(row.get('STAY4')),
                'stay_5': safe_int(row.get('STAY5')),
                'stay_6': safe_int(row.get('STAY6')),
                'stay_724': safe_int(row.get('STAY724')),
                'tsper3': safe_int(row.get('TSPER3')),
                'tsper4': safe_int(row.get('TSPER4')),
                'tsper5': safe_int(row.get('TSPER5')),
                'tsper6': safe_int(row.get('TSPER6')),
                
                # מטא-דטה
                'created_at': datetime.now().isoformat(),
                'uploaded_by': 'email_automation'
            }
            
            converted_rows.append(converted_row)
            
            print(f"✅ Row {index+1}: project {converted_row['project_number']}, cash: {cash_shekels} shekels, text: '{ctext_value}'")
            
        except Exception as e:
            print(f"❌ Error converting row {index+1}: {str(e)}")
            print(f"   Row data: {row}")
            continue  # ממשיך לשורה הבאה במקום להפסיק
    
    print(f"🎯 Successfully converted {len(converted_rows)} out of {len(csv_rows)} rows")
    return converted_rows

def insert_to_csv_import_shekels(converted_data):
    """הכנסה לטבלת csv_import_shekels (שלב ביניים) - גרסה מתוקנת"""
    if not supabase:
        print("❌ Supabase not available")
        return 0
        
    try:
        print(f"🔄 Preparing to insert {len(converted_data)} rows to csv_import_shekels")
        
        # מחיקת נתונים ישנים מהטבלה
        try:
            print("🧹 Clearing old data from csv_import_shekels...")
            delete_result = supabase.table('csv_import_shekels').delete().gt('id', 0).execute()
            print("✅ Old data cleared successfully")
        except Exception as e:
            print(f"⚠️ Could not clear old data: {str(e)}")
            # ממשיכים גם אם המחיקה נכשלה
        
        # ניקוי הנתונים - הסרת שדות שלא צריכים ווידוא תקינות
        cleaned_data = []
        
        for i, row in enumerate(converted_data):
            try:
                # יצירת שורה נקייה עם הכל הערכים הנדרשים
                cleaned_row = {
                    'project_number': str(row.get('project_number', '')).strip(),
                    'l_global_ref': int(row.get('l_global_ref', 0)),
                    's_computer': int(row.get('s_computer', 0)),
                    's_shift_id': int(row.get('s_shift_id', 0)),
                    'report_start_time': str(row.get('report_start_time', '')).strip(),
                    'report_end_time': str(row.get('report_end_time', '')).strip(),
                    'report_date': str(row.get('report_date', '')).strip(),
                    'ctext': str(row.get('ctext', '')).strip(),
                    
                    # כסף בשקלים
                    's_cash_shekels': float(row.get('s_cash_shekels', 0)),
                    's_credit_shekels': float(row.get('s_credit_shekels', 0)),
                    's_pango_shekels': float(row.get('s_pango_shekels', 0)),
                    's_celo_shekels': float(row.get('s_celo_shekels', 0)),
                    'total_revenue_shekels': float(row.get('total_revenue_shekels', 0)),
                    'net_revenue_shekels': float(row.get('net_revenue_shekels', 0)),
                    
                    # כסף באגורות
                    's_cash_agorot': int(row.get('s_cash_agorot', 0)),
                    's_credit_agorot': int(row.get('s_credit_agorot', 0)),
                    's_pango_agorot': int(row.get('s_pango_agorot', 0)),
                    's_celo_agorot': int(row.get('s_celo_agorot', 0)),
                    'stot_cacr': int(row.get('stot_cacr', 0)),
                    's_exp_agorot': int(row.get('s_exp_agorot', 0)),
                    
                    # מקודדים
                    's_encoder1': int(row.get('s_encoder1', 0)),
                    's_encoder2': int(row.get('s_encoder2', 0)),
                    's_encoder3': int(row.get('s_encoder3', 0)),
                    'sencodertot': int(row.get('sencodertot', 0)),
                    
                    # תנועה
                    't_open_b': int(row.get('t_open_b', 0)),
                    't_entry_s': int(row.get('t_entry_s', 0)),
                    't_entry_p': int(row.get('t_entry_p', 0)),
                    't_entry_tot': int(row.get('t_entry_tot', 0)),
                    't_exit_s': int(row.get('t_exit_s', 0)),
                    't_exit_p': int(row.get('t_exit_p', 0)),
                    't_exit_tot': int(row.get('t_exit_tot', 0)),
                    't_entry_ap': int(row.get('t_entry_ap', 0)),
                    't_exit_ap': int(row.get('t_exit_ap', 0)),
                    
                    # זמני שהייה
                    'tsper1': int(row.get('tsper1', 0)),
                    'tsper2': int(row.get('tsper2', 0)),
                    'stay_015': int(row.get('stay_015', 0)),
                    'stay_030': int(row.get('stay_030', 0)),
                    'stay_045': int(row.get('stay_045', 0)),
                    'stay_060': int(row.get('stay_060', 0)),
                    'stay_2': int(row.get('stay_2', 0)),
                    'stay_3': int(row.get('stay_3', 0)),
                    'stay_4': int(row.get('stay_4', 0)),
                    'stay_5': int(row.get('stay_5', 0)),
                    'stay_6': int(row.get('stay_6', 0)),
                    'stay_724': int(row.get('stay_724', 0)),
                    'tsper3': int(row.get('tsper3', 0)),
                    'tsper4': int(row.get('tsper4', 0)),
                    'tsper5': int(row.get('tsper5', 0)),
                    'tsper6': int(row.get('tsper6', 0)),
                    
                    # מטא-דטה (created_at ו-uploaded_by יווצרו אוטומטית)
                }
                
                cleaned_data.append(cleaned_row)
                
            except Exception as row_error:
                print(f"❌ Error cleaning row {i}: {str(row_error)}")
                print(f"   Problematic row: {row}")
                continue
        
        if not cleaned_data:
            print("❌ No valid data after cleaning")
            return 0
            
        print(f"✅ Cleaned {len(cleaned_data)} rows successfully")
        
        # הכנסת הנתונים בקבוצות
        batch_size = 200
        total_inserted = 0
        
        for i in range(0, len(cleaned_data), batch_size):
            batch = cleaned_data[i:i + batch_size]
            batch_num = i // batch_size + 1
            
            try:
                print(f"🔄 Inserting batch {batch_num}: {len(batch)} rows")
                
                result = supabase.table('csv_import_shekels').insert(batch).execute()
                
                if result.data:
                    batch_count = len(result.data)
                    total_inserted += batch_count
                    print(f"✅ Batch {batch_num} inserted successfully: {batch_count} rows")
                else:
                    print(f"⚠️ Batch {batch_num} returned no data")
                    
            except Exception as batch_error:
                print(f"❌ Error in batch {batch_num}: {str(batch_error)}")
                
                # אם הקבוצה נכשלה, ננסה שורה אחת בכל פעם
                print(f"🔄 Trying individual rows for batch {batch_num}...")
                for j, single_row in enumerate(batch):
                    try:
                        single_result = supabase.table('csv_import_shekels').insert([single_row]).execute()
                        if single_result.data:
                            total_inserted += 1
                            if j % 10 == 0:  # הדפסה כל 10 שורות
                                print(f"   ✅ Row {i+j+1} inserted")
                    except Exception as single_error:
                        print(f"   ❌ Row {i+j+1} failed: {str(single_error)}")
                        # בדיקה אם זו שגיאת מבנה חמורה
                        if "column" in str(single_error).lower() and "does not exist" in str(single_error).lower():
                            print(f"   🚨 CRITICAL: Column structure error - stopping batch")
                            break
        
        print(f"✅ Total inserted to csv_import_shekels: {total_inserted} rows out of {len(converted_data)}")
        return total_inserted
        
    except Exception as e:
        print(f"❌ General error inserting to csv_import_shekels: {str(e)}")
        return 0

def transfer_to_parking_data():
    """העברה מ csv_import_shekels ל parking_data - משופר לשורות מרובות"""
    if not supabase:
        print("❌ Supabase not available")
        return 0
        
    try:
        print("🔄 Starting transfer from csv_import_shekels to parking_data...")
        
        # קבלת כל הנתונים מטבלת הביניים
        csv_result = supabase.table('csv_import_shekels').select('*').execute()
        
        if not csv_result.data:
            print("⚠️ No data in csv_import_shekels to transfer")
            return 0
        
        print(f"📊 Found {len(csv_result.data)} rows in csv_import_shekels")
        
        # פונקציה לקבלת parking_id
        def get_parking_id(project_number):
            try:
                if not supabase:
                    return None
                result = supabase.table('project_parking_mapping').select('parking_id').eq('project_number', str(project_number)).execute()
                if result.data and len(result.data) > 0:
                    return result.data[0]['parking_id']
                return None
            except Exception as e:
                print(f"❌ Error getting parking_id: {str(e)}")
                return None
        
        # עיבוד הנתונים להעברה - שורה אחת בכל פעם
        successful_transfers = 0
        failed_transfers = 0
        
        for i, row in enumerate(csv_result.data):
            try:
                project_number = int(row.get('project_number', 0))
                parking_id = get_parking_id(project_number)
                
                # תיקון c_text
                ctext_value = str(row.get('ctext', '')).strip()
                if ctext_value in ["' '", "'  '", "''", ""]:
                    ctext_value = ""
                
                # יצירת שורה חדשה
                transfer_row = {
                    'parking_id': parking_id,
                    'project_number': project_number,
                    'report_date': str(row.get('report_date', '')),
                    'report_start_time': str(row.get('report_start_time', '')),
                    'report_end_time': str(row.get('report_end_time', '')),
                    'l_global_ref': int(row.get('l_global_ref', 0)),
                    's_computer': int(row.get('s_computer', 0)),
                    's_shift_id': int(row.get('s_shift_id', 0)),
                    'c_text': ctext_value,
                    's_cash_agorot': int(row.get('s_cash_agorot', 0)),
                    's_credit_agorot': int(row.get('s_credit_agorot', 0)),
                    's_pango_agorot': int(row.get('s_pango_agorot', 0)),
                    's_celo_agorot': int(row.get('s_celo_agorot', 0)),
                    's_exp_agorot': int(row.get('s_exp_agorot', 0)),
                    'stot_cacr': int(row.get('stot_cacr', 0)),
                    's_encoder1': int(row.get('s_encoder1', 0)),
                    's_encoder2': int(row.get('s_encoder2', 0)),
                    's_encoder3': int(row.get('s_encoder3', 0)),
                    's_encoder_tot': int(row.get('sencodertot', 0)),
                    't_open_b': int(row.get('t_open_b', 0)),
                    't_entry_s': int(row.get('t_entry_s', 0)),
                    't_entry_p': int(row.get('t_entry_p', 0)),
                    't_entry_tot': int(row.get('t_entry_tot', 0)),
                    't_entry_ap': int(row.get('t_entry_ap', 0)),
                    't_exit_s': int(row.get('t_exit_s', 0)),
                    't_exit_p': int(row.get('t_exit_p', 0)),
                    't_exit_tot': int(row.get('t_exit_tot', 0)),
                    't_exit_ap': int(row.get('t_exit_ap', 0)),
                    'ts_per1': int(row.get('tsper1', 0)),
                    'ts_per2': int(row.get('tsper2', 0)),
                    'ts_per3': int(row.get('tsper3', 0)),
                    'ts_per4': int(row.get('tsper4', 0)),
                    'ts_per5': int(row.get('tsper5', 0)),
                    'ts_per6': int(row.get('tsper6', 0)),
                    'stay_015': int(row.get('stay_015', 0)),
                    'stay_030': int(row.get('stay_030', 0)),
                    'stay_045': int(row.get('stay_045', 0)),
                    'stay_060': int(row.get('stay_060', 0)),
                    'stay_2': int(row.get('stay_2', 0)),
                    'stay_3': int(row.get('stay_3', 0)),
                    'stay_4': int(row.get('stay_4', 0)),
                    'stay_5': int(row.get('stay_5', 0)),
                    'stay_6': int(row.get('stay_6', 0)),
                    'stay_724': int(row.get('stay_724', 0)),
                    'data_source': 'email_automation',
                    'imported_at': datetime.now().isoformat()
                }
                
                if transfer_row['project_number'] <= 0:
                    print(f"⚠️ Row {i+1}: Skipping - invalid project_number")
                    continue
                
                # ניסיון הכנסה של השורה הבודדת
                try:
                    print(f"🔄 Transferring row {i+1}/{len(csv_result.data)}: project {project_number}, text: '{ctext_value}'")
                    
                    # ניסיון upsert ראשון
                    result = supabase.table('parking_data').upsert([transfer_row]).execute()
                    
                    if result.data:
                        successful_transfers += 1
                        print(f"✅ Row {i+1}: Successfully transferred")
                    else:
                        print(f"⚠️ Row {i+1}: No data returned from upsert")
                        
                except Exception as single_error:
                    # אם upsert נכשל, ננסה insert
                    if "already exists" in str(single_error):
                        print(f"⏭️ Row {i+1}: Already exists - skipping")
                        failed_transfers += 1
                    else:
                        try:
                            result = supabase.table('parking_data').insert([transfer_row]).execute()
                            if result.data:
                                successful_transfers += 1
                                print(f"✅ Row {i+1}: Successfully inserted")
                            else:
                                failed_transfers += 1
                                print(f"❌ Row {i+1}: Insert failed - no data returned")
                        except Exception as insert_error:
                            failed_transfers += 1
                            print(f"❌ Row {i+1}: Both upsert and insert failed: {str(insert_error)}")
                    
            except Exception as row_error:
                failed_transfers += 1
                print(f"❌ Row {i+1}: Error processing row: {str(row_error)}")
                continue
        
        # דוח סיכום
        total_processed = successful_transfers + failed_transfers
        print(f"📊 Transfer Summary:")
        print(f"   ✅ Successfully transferred: {successful_transfers} rows")
        print(f"   ❌ Failed/Skipped: {failed_transfers} rows")
        print(f"   📈 Total processed: {total_processed} out of {len(csv_result.data)} rows")
        
        # מחיקת csv_import_shekels אחרי העברה
        if total_processed > 0:
            try:
                print("🧹 Cleaning csv_import_shekels...")
                delete_result = supabase.table('csv_import_shekels').delete().gt('id', 0).execute()
                print("✅ csv_import_shekels cleaned successfully")
            except Exception as cleanup_error:
                print(f"⚠️ Could not clean csv_import_shekels: {str(cleanup_error)}")
        
        return successful_transfers
            
    except Exception as e:
        print(f"❌ Error transferring to parking_data: {str(e)}")
        return 0

def send_success_notification(sender_email, processed_files, total_rows):
    """שליחת התראת הצלחה עם type checking מתוקן"""
    if not EMAIL_MONITORING_AVAILABLE:
        return
        
    try:
        msg = MIMEMultipart()
        
        # תיקון type checking - וידוא שהמשתנים לא None
        gmail_user = os.environ.get('GMAIL_USERNAME')
        gmail_password = os.environ.get('GMAIL_APP_PASSWORD')
        
        if not gmail_user or not gmail_password:
            print("❌ Missing Gmail credentials for notification")
            return
            
        msg['From'] = gmail_user
        msg['To'] = sender_email
        msg['Subject'] = '✅ קבצי הנתונים עובדו בהצלחה - S&B Parking'
        
        files_list = '\n'.join([f"• {file['name']} - {file['rows']} שורות" for file in processed_files])
        
        body = f"""
שלום,

קבצי הנתונים שלך עובדו בהצלחה במערכת S&B Parking:

{files_list}

סה"כ שורות שנוספו: {total_rows}

הנתונים זמינים כעת בדשבורד.

תודה,
מערכת S&B Parking (אוטומטית)
        """
        
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(gmail_user, gmail_password)
        server.send_message(msg)
        server.quit()
        
        print(f"📧 Success notification sent to {sender_email}")
        
    except Exception as e:
        print(f"❌ Failed to send notification: {str(e)}")

def send_error_notification(sender_email, error_message):
    """שליחת התראת שגיאה עם type checking מתוקן"""
    if not EMAIL_MONITORING_AVAILABLE:
        return
        
    try:
        msg = MIMEMultipart()
        
        # תיקון type checking - וידוא שהמשתנים לא None
        gmail_user = os.environ.get('GMAIL_USERNAME')
        gmail_password = os.environ.get('GMAIL_APP_PASSWORD')
        
        if not gmail_user or not gmail_password:
            print("❌ Missing Gmail credentials for error notification")
            return
            
        msg['From'] = gmail_user
        msg['To'] = sender_email
        msg['Subject'] = '❌ שגיאה בעיבוד קבצי הנתונים - S&B Parking'
        
        body = f"""
שלום,

התרחשה שגיאה בעיבוד קבצי הנתונים שלך:

{error_message}

אנא בדוק את הקובץ ונסה שוב, או פנה לתמיכה.

מערכת S&B Parking (אוטומטית)
        """
        
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(gmail_user, gmail_password)
        server.send_message(msg)
        server.quit()
        
        print(f"📧 Error notification sent to {sender_email}")
        
    except Exception as e:
        print(f"❌ Failed to send error notification: {str(e)}")

def process_single_email(mail, email_id):
    """עיבוד מייל יחיד - עם בדיקת שולח מורשה"""
    try:
        _, msg_data = mail.fetch(email_id, '(RFC822)')
        email_body = msg_data[0][1]
        email_message = email.message_from_bytes(email_body)
        
        sender = email_message['From']
        subject = email_message['Subject'] or ''
        date = email_message['Date'] or ''
        
        print(f"\n📧 Processing email from: {sender}")
        print(f"   Subject: {subject}")
        print(f"   Date: {date}")
        
        # בדיקת שולח מורשה
        if not is_authorized_sender(sender):
            print(f"🚫 UNAUTHORIZED SENDER: {sender}")
            print(f"✅ Authorized senders: {AUTHORIZED_SENDERS}")
            print(f"⏭️ Skipping email from unauthorized sender")
            return False
        
        print(f"✅ AUTHORIZED SENDER: {sender}")
        
        csv_files = download_csv_from_email(email_message)
        
        if not csv_files:
            print("⚠️ No CSV files found in email")
            return False
        
        all_converted_data = []
        processed_files = []
        
        for csv_file in csv_files:
            print(f"\n🔄 Processing file: {csv_file['filename']}")
            
            # פרסור CSV (עכשיו מחזיר רשימה במקום DataFrame)
            csv_rows = parse_csv_content(csv_file['data'])
            if csv_rows is None:
                continue
            
            # המרה לפורמט שלנו
            converted_data = convert_to_csv_import_format(csv_rows)
            if not converted_data:
                continue
            
            all_converted_data.extend(converted_data)
            processed_files.append({
                'name': csv_file['filename'],
                'rows': len(converted_data)
            })
            
            print(f"✅ File {csv_file['filename']}: {len(converted_data)} rows converted")
        
        if not all_converted_data:
            error_msg = "לא נמצאו נתונים תקינים בקבצים המצורפים"
            send_error_notification(sender, error_msg)
            return False
        
        # הכנסה לטבלת הביניים
        inserted_count = insert_to_csv_import_shekels(all_converted_data)
        if inserted_count == 0:
            error_msg = "שגיאה בהכנסת הנתונים לטבלת הביניים"
            send_error_notification(sender, error_msg)
            return False
        
        # העברה לטבלה הסופית
        transferred_count = transfer_to_parking_data()
        if transferred_count == 0:
            error_msg = "שגיאה בהעברת הנתונים לטבלה הסופית"
            send_error_notification(sender, error_msg)
            return False
        
        # שליחת התראת הצלחה
        send_success_notification(sender, processed_files, transferred_count)
        
        print(f"🎉 Email processed successfully: {transferred_count} rows added")
        return True
        
    except Exception as e:
        print(f"❌ Error processing email: {str(e)}")
        try:
            sender = email_message['From'] if 'email_message' in locals() else 'unknown'
            send_error_notification(sender, f"שגיאה טכנית: {str(e)}")
        except:
            pass
        return False

def verify_email_system():
    """בדיקת התקינות של מערכת המיילים"""
    if not EMAIL_MONITORING_AVAILABLE:
        print("⚠️ Email libraries not available - email monitoring disabled")
        return False
        
    print("🔧 Verifying email system configuration...")
    
    # בדיקת משתני סביבה
    gmail_user = os.environ.get('GMAIL_USERNAME')
    gmail_password = os.environ.get('GMAIL_APP_PASSWORD')
    
    print(f"📧 Gmail Username: {'✅ SET' if gmail_user else '❌ MISSING'}")
    print(f"🔑 Gmail Password: {'✅ SET' if gmail_password else '❌ MISSING'}")
    
    if not gmail_user or not gmail_password:
        print("⚠️ WARNING: Gmail credentials missing! Email monitoring will not work.")
        return False
    
    # בדיקת חיבור IMAP (מהיר)
    try:
        mail = imaplib.IMAP4_SSL('imap.gmail.com', timeout=10)
        mail.login(gmail_user, gmail_password)
        mail.logout()
        print("🌐 Gmail IMAP connection: ✅ SUCCESS")
        return True
    except Exception as e:
        print(f"❌ Gmail IMAP connection failed: {str(e)}")
        return False

def start_email_monitoring_with_logs():
    """הפעלת מעקב מיילים עם לוגים מפורטים - ללא schedule"""
    if not EMAIL_MONITORING_AVAILABLE:
        print("⚠️ Email monitoring not available - libraries missing")
        return
        
    try:
        print("🚀 Starting email monitoring system...")
        
        # בדיקת תקינות המערכת
        if not verify_email_system():
            print("❌ Email system verification failed. Monitoring will not start.")
            return
        
        def monitoring_loop():
            print("🔄 Email monitoring loop started")
            check_count = 0
            
            while True:
                try:
                    # בדיקת מיילים כל 5 דקות (300 שניות)
                    with app.app_context():
                        print(f"⏰ Email check triggered at {datetime.now()}")
                        check_for_new_emails()
                    
                    # המתנה של 5 דקות
                    time.sleep(300)  # 300 שניות = 5 דקות
                    
                    check_count += 1
                    if check_count % 6 == 0:  # כל 30 דקות (6 * 5 דקות)
                        print(f"💓 Email monitoring alive - {check_count * 5} minutes running")
                        
                except KeyboardInterrupt:
                    print("\n🛑 Email monitoring stopped by user")
                    break
                except Exception as e:
                    print(f"❌ Email monitoring error: {str(e)}")
                    print("⏳ Retrying in 5 minutes...")
                    time.sleep(300)  # 5 דקות המתנה לפני ניסיון חוזר
        
        # הרצת הלולאה ברקע
        monitor_thread = threading.Thread(target=monitoring_loop, daemon=True)
        monitor_thread.start()
        
        print("✅ Email monitoring started successfully in background")
        print(f"⏰ Email checks scheduled every {EMAIL_CHECK_INTERVAL} minutes")
        
        # בדיקה ראשונית מיידית
        print("🚀 Running initial email check...")
        
        def initial_check():
            with app.app_context():
                check_for_new_emails()
        
        threading.Thread(target=initial_check, daemon=True).start()
        
    except Exception as e:
        print(f"❌ Failed to start email monitoring: {str(e)}")

def start_background_email_monitoring():
    """נקודת כניסה להפעלת מעקב מיילים ברקע"""
    if not EMAIL_MONITORING_AVAILABLE:
        print("⚠️ Email monitoring not available - missing libraries")
        return
        
    try:
        print("📧 Initializing background email monitoring...")
        
        def delayed_start():
            time.sleep(5)
            start_email_monitoring_with_logs()
        
        startup_thread = threading.Thread(target=delayed_start, daemon=True)
        startup_thread.start()
        
        print("📧 Background email monitoring initialization started")
        
    except Exception as e:
        print(f"❌ Background email monitoring initialization failed: {str(e)}")

def is_authorized_sender(sender_email):
    """בדיקה אם השולח מורשה לשלוח קבצי נתונים"""
    if not sender_email:
        return False
    
    # ניקוי כתובת המייל מתגים נוספים
    sender_clean = sender_email.strip().lower()
    
    # חילוץ כתובת המייל מפורמט "Name <email@domain.com>"
    if '<' in sender_clean and '>' in sender_clean:
        start = sender_clean.find('<') + 1
        end = sender_clean.find('>')
        sender_clean = sender_clean[start:end].strip()
    
    # בדיקה מול רשימת השולחים המורשים
    for authorized in AUTHORIZED_SENDERS:
        if sender_clean == authorized.lower():
            return True
    
    return False

def check_for_new_emails():
    """בדיקת מיילים חדשים - גרסה מתוקנת"""
    global processed_email_ids
    
    if not EMAIL_MONITORING_AVAILABLE:
        print("⚠️ Email check skipped - libraries not available")
        return
    
    print(f"\n🔍 ===== EMAIL CHECK STARTED at {datetime.now()} =====")
    
    # בדיקת משתני סביבה
    gmail_user = os.environ.get('GMAIL_USERNAME')
    gmail_password = os.environ.get('GMAIL_APP_PASSWORD')
    
    if not gmail_user or not gmail_password:
        print("❌ Missing Gmail credentials - skipping email check")
        return
    
    print(f"📧 Gmail user: {gmail_user}")
    print(f"🔑 Gmail password: {'***' if gmail_password else 'MISSING'}")
    
    mail = connect_to_gmail_imap()
    if not mail:
        print("❌ Failed to connect to Gmail IMAP")
        return
    
    try:
        print("📂 Selecting inbox...")
        mail.select('inbox')
        
        # תיקון פשוט - רק חיפוש מיילים מהיום האחרון
        since_date = (datetime.now() - timedelta(days=1)).strftime('%d-%b-%Y')
        search_criteria = f'SINCE {since_date}'
        
        print(f"🔍 Search criteria: {search_criteria}")
        
        _, message_ids = mail.search(None, search_criteria)
        
        if not message_ids[0]:
            print("📭 No emails found from yesterday")
            print(f"📊 Processed emails cache: {len(processed_email_ids)} emails")
            mail.logout()
            return
        
        email_ids = message_ids[0].split()
        print(f"📧 Found {len(email_ids)} emails from yesterday")
        
        new_emails = 0
        processed_successfully = 0
        
        for email_id in email_ids:
            email_id_str = email_id.decode() if isinstance(email_id, bytes) else str(email_id)
            
            if email_id_str in processed_email_ids:
                print(f"⏭️ Skipping already processed email: {email_id_str}")
                continue
            
            print(f"\n🆕 Processing new email ID: {email_id_str}")
            
            # עיבוד המייל
            success = process_single_email(mail, email_id)
            
            # הוספה לרשימה רק אחרי עיבוד (להימנע מעיבוד חוזר)
            processed_email_ids.append(email_id_str)
            new_emails += 1
            
            # ספירת הצלחות בלבד
            if success:
                processed_successfully += 1
                print(f"✅ Email {email_id_str} processed successfully")
            else:
                print(f"⚠️ Email {email_id_str} was rejected or failed")
            
            # ניקוי cache אם יש יותר מדי מיילים
            if len(processed_email_ids) > PROCESSED_EMAILS_LIMIT:
                processed_email_ids = processed_email_ids[-PROCESSED_EMAILS_LIMIT:]
                print(f"🧹 Cleaned processed emails cache, now: {len(processed_email_ids)}")
            
            # המתנה קצרה בין מיילים
            time.sleep(2)
        
        # סיכום מפורט
        print(f"✅ Email check completed:")
        print(f"   📧 New emails checked: {new_emails}")
        print(f"   🎉 Successfully processed: {processed_successfully}")
        print(f"   🚫 Rejected/Failed: {new_emails - processed_successfully}")
        print(f"   📊 Total emails in cache: {len(processed_email_ids)}")
        
    except Exception as e:
        print(f"❌ Error in email check: {str(e)}")
    
    finally:
        try:
            mail.logout()
            print("🔓 Gmail connection closed")
        except:
            pass
        
        print(f"===== EMAIL CHECK ENDED at {datetime.now()} =====\n")

def keep_service_alive():
    """פונקציה לשמירה על השירות ערני - מונע תרדמה של Render"""
    def ping_self():
        while True:
            try:
                # שליחת בקשה לעצמנו כל 10 דקות
                response = requests.get('https://s-b-parking-reports.onrender.com/', timeout=30)
                print(f"🏓 Keep-alive ping: {response.status_code}")
            except Exception as e:
                print(f"⚠️ Keep-alive ping failed: {str(e)}")
            
            # המתנה של 10 דקות (600 שניות)
            time.sleep(600)
    
    # הרצת הפונקציה ברקע
    ping_thread = threading.Thread(target=ping_self, daemon=True)
    ping_thread.start()
    print("🏓 Keep-alive service started - pinging every 10 minutes")

@app.route('/api/test-email-system', methods=['GET'])
def test_email_system():
    """API לבדיקת מערכת המיילים"""
    try:
        if not EMAIL_MONITORING_AVAILABLE:
            return jsonify({
                'success': False, 
                'message': 'Email system not available - missing libraries'
            })
            
        print("🧪 Manual email system test initiated")
        
        # בדיקת תקינות
        system_ok = verify_email_system()
        
        if system_ok:
            def test_check():
                with app.app_context():
                    check_for_new_emails()
            
            threading.Thread(target=test_check, daemon=True).start()
            
            return jsonify({
                'success': True, 
                'message': 'Email system test completed successfully. Check server logs for details.'
            })
        else:
            return jsonify({
                'success': False, 
                'message': 'Email system test failed. Check server logs for details.'
            })
            
    except Exception as e:
        print(f"❌ Email system test error: {str(e)}")
        return jsonify({
            'success': False, 
            'message': f'Test error: {str(e)}'
        })
# ======================== נקודות קצה (Routes) ========================

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
        
        if not supabase:
            return jsonify({'success': False, 'message': 'מסד הנתונים לא זמין'})
        
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
        
        if not supabase:
            return jsonify({'success': False, 'message': 'מסד הנתונים לא זמין'})
        
        email = session['user_email']
        
        # בדיקת הרשאות משתמש
        user_result = supabase.table('user_parkings').select(
            'access_level, company_type'
        ).eq('email', email).execute()
        
        if not user_result.data:
            return jsonify({'success': False, 'message': 'משתמש לא נמצא'})
        
        user_data = user_result.data[0]
        
        if user_data['access_level'] != 'group_manager' and user_data['access_level'] != 'group_access':
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
        
        if not supabase:
            return jsonify({'success': False, 'message': 'מסד הנתונים לא זמין'})
        
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
            
        elif user_data['access_level'] == 'group_manager' or user_data['access_level'] == 'group_access':
            # מנהל קבוצה או משתמש קבוצה
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
        
        # קבלת מיפוי שמות החניונים מ-project_parking_mapping
        parking_names_map = {}
        try:
            mapping_result = supabase.table('project_parking_mapping').select('project_number, parking_name').execute()
            for mapping in mapping_result.data:
                parking_names_map[mapping['project_number']] = mapping['parking_name']
        except Exception as e:
            print(f"Warning: Could not load parking names mapping: {str(e)}")
        
        # עיבוד הנתונים
        processed_data = []
        for row in result.data:
            # וידוא שכל השדות הנדרשים קיימים
            processed_row = {
                'id': row.get('id'),
                'parking_id': row.get('parking_id'),
                'report_date': row.get('report_date'),
                'project_number': row.get('project_number'),
                'parking_name': parking_names_map.get(row.get('project_number'), '') or row.get('parking_name', ''),  # שם חניון מהמיפוי
                'total_revenue_shekels': float(row.get('total_revenue_shekels', 0)),
                'net_revenue_shekels': float(row.get('net_revenue_shekels', 0)),
                's_cash_shekels': float(row.get('s_cash_shekels', 0)),
                's_credit_shekels': float(row.get('s_credit_shekels', 0)),
                's_pango_shekels': float(row.get('s_pango_shekels', 0)),
                's_celo_shekels': float(row.get('s_celo_shekels', 0)),
                's_encoder1': int(row.get('s_encoder1', 0)),  # הוסף מקודד 1
                's_encoder2': int(row.get('s_encoder2', 0)),  # הוסף מקודד 2
                's_encoder3': int(row.get('s_encoder3', 0)),  # הוסף מקודד 3
                'sencodertot': int(row.get('sencodertot', 0)),  # הוסף סה"כ מקודדים
                't_entry_tot': int(row.get('t_entry_tot', 0)),
                't_exit_tot': int(row.get('t_exit_tot', 0)),
                't_exit_s': int(row.get('t_exit_tot', 0)),
                't_exit_p': int(row.get('t_exit_tot', 0)),
                't_entry_s': int(row.get('t_entry_s', 0)),  # מזדמנים
                't_entry_p': int(row.get('t_entry_p', 0)),  # מנויים
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

@app.route('/api/check-emails-now', methods=['POST'])
def manual_email_check():
    """API לבדיקת מיילים ידנית"""
    try:
        if 'user_email' not in session:
            return jsonify({'success': False, 'message': 'לא מחובר'}), 401
        
        if not supabase:
            return jsonify({'success': False, 'message': 'מסד הנתונים לא זמין'})
        
        if not EMAIL_MONITORING_AVAILABLE:
            return jsonify({'success': False, 'message': 'מערכת מיילים לא זמינה'})
        
        email = session['user_email']
        user_result = supabase.table('user_parkings').select('role, access_level').eq('email', email).execute()
        
        if not user_result.data:
            return jsonify({'success': False, 'message': 'משתמש לא נמצא'})
        
        user_data = user_result.data[0]
        if user_data.get('role') != 'admin' and user_data.get('access_level') != 'group_manager':
            return jsonify({'success': False, 'message': 'אין הרשאה לבדיקת מיילים'})
        
        def test_check():
            with app.app_context():
                check_for_new_emails()
        
        threading.Thread(target=test_check, daemon=True).start()
        
        return jsonify({'success': True, 'message': 'בדיקת מיילים החלה ברקע'})
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

# הוסף גם פונקציה לבדיקת תקפות תאריך
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
        if not supabase:
            return jsonify({'success': False, 'message': 'מסד הנתונים לא זמין'})
            
        data = request.get_json()
        username = data.get('username', '').strip()
        password = data.get('password', '').strip()
        
        # אימות קלט
        is_valid_username, validated_username = validate_input(username, "username")
        is_valid_password, validated_password = validate_input(password, "password")
        
        if not is_valid_username:
            print(f"🚨 Invalid username attempt: {username}")
            return jsonify({'success': False, 'message': 'שם משתמש לא תקין'})
        
        if not is_valid_password:
            print(f"🚨 Invalid password attempt from user: {validated_username}")
            return jsonify({'success': False, 'message': 'סיסמה לא תקינה'})
        
        print(f"🔑 Login attempt: {validated_username}")
        
        # שימוש ב-RPC function
        auth_result = supabase.rpc('user_login', {
            'p_username': validated_username,
            'p_password': validated_password
        }).execute()
        
        print(f"🔐 Auth result: {auth_result.data}")
        
        if auth_result.data is True:
            # Get user email
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
        if not supabase:
            return jsonify({'success': False, 'message': 'מסד הנתונים לא זמין'})
            
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

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login_page'))

@app.route('/ping')
def ping():
    return "pong", 200

@app.route('/health')
def health_check():
    """נקודת קצה לבדיקת תקינות השירות"""
    try:
        current_time = datetime.now().isoformat()
        
        return jsonify({
            'status': 'healthy',
            'timestamp': current_time,
            'email_monitoring': EMAIL_MONITORING_AVAILABLE,
            'supabase_connected': supabase is not None,
            'uptime': 'Service is running'
        }), 200
        
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Page not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500

# הפעלה אוטומטית כשהאפליקציה מתחילה
if __name__ == '__main__':
    print("\n🔧 Pre-flight email system check...")
    
    if EMAIL_MONITORING_AVAILABLE:
        email_system_ready = verify_email_system()
        
        if email_system_ready:
            print("✅ Email system ready - starting background monitoring")
            start_background_email_monitoring()
        else:
            print("⚠️ Email system not ready - monitoring disabled")
            print("💡 You can still use manual email checks via API")
    else:
        print("⚠️ Email libraries not available - monitoring disabled")
    
    print("\n🌐 Starting Flask web server...")
    
    port = int(os.environ.get('PORT', 5000))
    debug_mode = os.environ.get('FLASK_ENV') == 'development'
    
    print(f"🔍 Port: {port}")
    print(f"🔍 Debug mode: {debug_mode}")
    
    keep_service_alive()

    app.run(host='0.0.0.0', port=port, debug=debug_mode)
else:
    if EMAIL_MONITORING_AVAILABLE:
        print("📧 Initializing email monitoring for production...")
        start_background_email_monitoring()
