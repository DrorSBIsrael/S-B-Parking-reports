from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_mail import Mail, Message
from supabase.client import create_client, Client
import os
import random
import string
import requests
import re
import html
import bcrypt
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

ERROR_EMAILS_DISABLED = True
# הגדרות מיילים אוטומטיים - להוסיף אחרי ההגדרות הקיימות:
if EMAIL_MONITORING_AVAILABLE:
    EMAIL_CHECK_INTERVAL = 5  # בדיקה כל 5 דקות
    PROCESSED_EMAILS_LIMIT = 100  # מקסימום מיילים לזכור
    processed_email_ids = []  # רשימה לזכור מיילים שכבר עובדו
    last_cache_reset = None

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
    """פרסור CSV עם זיהוי קידוד אוטומטי לעברית ואימות תקינות"""
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
        
        # ⚠️ בדיקת תקינות CSV - אם זה קובץ SQL או לא תקין
        if any(sql_keyword in first_line.lower() for sql_keyword in ['connect', 'insert', 'select', 'values', 'create']):
            print("🚫 INVALID FILE: This appears to be a SQL file, not a CSV file!")
            print(f"🚫 First line contains SQL keywords: {first_line}")
            return None
        
        # בדיקה שיש כותרות CSV תקינות
        if 'ProjectNumber' not in first_line:
            print("🚫 INVALID CSV: Missing expected header 'ProjectNumber'")
            print(f"🚫 First line: {first_line}")
            return None
        
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
                
                # בדיקה נוספת - אם השורה הראשונה ריקה או לא תקינה
                if not rows or not any(rows[0].values()):
                    print("🚫 INVALID CSV: First data row is empty or invalid")
                    return None
                
                # בדיקה אם יש עברית בנתונים
                for i, row in enumerate(rows[:3]):  # בדיקת 3 שורות ראשונות
                    for key, value in row.items():
                        if value and any('\u0590' <= char <= '\u05FF' for char in str(value)):
                            print(f"🇮🇱 Hebrew text found in row {i+1}, column '{key}': {value}")
                            break
                
                return rows
        except Exception as e:
            print(f"❌ Comma parsing failed: {e}")
        
        # אם הגענו לכאן, הקובץ לא תקין
        print("🚫 INVALID CSV: Could not parse as valid CSV file")
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
    """העברה מ csv_import_shekels ל parking_data - עם תיקונים"""
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
        
        # עיבוד הנתונים להעברה - עם בדיקות כפילות משופרות
        successful_transfers = 0
        failed_transfers = 0
        skipped_duplicates = 0
        
        for i, row in enumerate(csv_result.data):
            try:
                project_number = int(row.get('project_number', 0))
                report_date = str(row.get('report_date', ''))
                l_global_ref = int(row.get('l_global_ref', 0))
                s_computer = int(row.get('s_computer', 0))
                s_shift_id = int(row.get('s_shift_id', 0))
                
                if project_number <= 0:
                    print(f"⚠️ Row {i+1}: Skipping - invalid project_number")
                    failed_transfers += 1
                    continue
                
                parking_id = get_parking_id(project_number)
                
                # תיקון c_text
                ctext_value = str(row.get('ctext', '')).strip()
                if ctext_value in ["' '", "'  '", "''", ""]:
                    ctext_value = ""
                
                # יצירת שורה חדשה
                transfer_row = {
                    'parking_id': parking_id,
                    'project_number': project_number,
                    'report_date': report_date,
                    'report_start_time': str(row.get('report_start_time', '')),
                    'report_end_time': str(row.get('report_end_time', '')),
                    'l_global_ref': l_global_ref,
                    's_computer': s_computer,
                    's_shift_id': s_shift_id,
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
                
                # 🆕 בדיקה משופרת עם 3 שדות מזהים (במקום 5)
                try:
                    print(f"🔄 Checking row {i+1}/{len(csv_result.data)}: project {project_number}, date {report_date}, text: '{ctext_value}'")
                    
                    # בדיקה עם שילוב שדות - כמו constraint במסד הנתונים
                    existing_check = supabase.table('parking_data').select('id').eq(
                        'parking_id', parking_id
                    ).eq(
                        'report_date', report_date
                    ).eq(
                        's_shift_id', s_shift_id
                    ).execute()
                    
                    if existing_check.data:
                        print(f"🔄 Row {i+1}: DUPLICATE DETECTED (constraint match) - skipping completely")
                        skipped_duplicates += 1
                        continue
                    
                    # רק אם לא קיים - הכנס חדש
                    result = supabase.table('parking_data').insert([transfer_row]).execute()
                    
                    if result.data:
                        successful_transfers += 1
                        print(f"✅ Row {i+1}: Successfully inserted as NEW record")
                    else:
                        failed_transfers += 1
                        print(f"❌ Row {i+1}: Insert failed - no data returned")
                        
                except Exception as single_error:
                    # טיפול בשגיאת constraint
                    if "duplicate key value violates unique constraint" in str(single_error):
                        print(f"🔄 Row {i+1}: DUPLICATE DETECTED (database constraint) - skipping")
                        skipped_duplicates += 1
                        continue
                    else:
                        failed_transfers += 1
                        print(f"❌ Row {i+1}: Error during processing: {str(single_error)}")
                        continue
                    
            except Exception as row_error:
                failed_transfers += 1
                print(f"❌ Row {i+1}: Error processing row: {str(row_error)}")
                continue
        
        # דוח סיכום מפורט
        total_processed = successful_transfers + skipped_duplicates + failed_transfers
        print(f"\n📊 Transfer Summary:")
        print(f"   ✅ Successfully transferred: {successful_transfers} NEW records")
        print(f"   🔄 Skipped duplicates: {skipped_duplicates} existing records")
        print(f"   ❌ Failed: {failed_transfers} records")
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

def process_single_email(mail, email_id):
    """עיבוד מייל יחיד - עם שליחת מיילי הודעות מתוקן"""
    sender = None  # נגדיר את המשתנה מלכתחילה
    
    try:
        _, msg_data = mail.fetch(email_id, '(RFC822)')
        
        # בדיקה שיש נתונים
        if not msg_data or len(msg_data) == 0:
            print(f"❌ No data for email ID: {email_id}")
            return False
            
        email_body = msg_data[0][1]
        
        # בדיקה שיש body
        if not email_body:
            print(f"❌ Empty email body for ID: {email_id}")
            return False
            
        email_message = email.message_from_bytes(email_body)
        
        # קבלת פרטי השולח
        sender = email_message.get('From', 'unknown@unknown.com')
        subject = email_message.get('Subject', 'No Subject') or 'No Subject'
        date = email_message.get('Date', 'No Date') or 'No Date'
        
        print(f"\n📧 Processing email from: {sender}")
        print(f"   Subject: {subject}")
        print(f"   Date: {date}")
        
        # בדיקה שהשולח תקין
        if sender == 'unknown@unknown.com' or '@' not in sender:
            print(f"❌ Invalid sender address: {sender}")
            return False
        
        # בדיקת שולח מורשה
        if not is_authorized_sender(sender):
            print(f"🚫 UNAUTHORIZED SENDER: {sender}")
            print(f"✅ Authorized senders: {AUTHORIZED_SENDERS}")
            print(f"⏭️ Skipping email from unauthorized sender")
            
            # 🆕 סימון המייל כדי לא לבדוק אותו שוב
            try:
                print(f"🏷️ Marking unauthorized email as processed (ID: {email_id})...")
                mail.store(email_id, '+FLAGS', '\\Seen \\Flagged')
                print(f"✅ Unauthorized email marked as processed")
            except Exception as mark_error:
                print(f"⚠️ Could not mark unauthorized email: {str(mark_error)}")
            
            print(f"📝 UNAUTHORIZED ACCESS LOGGED: {sender} tried to send data files")
            return False
        
        print(f"✅ AUTHORIZED SENDER: {sender}")
        
        csv_files = download_csv_from_email(email_message)
        
        if not csv_files:
            print("⚠️ No CSV files found in email")
            # 🆕 שליחת מייל על חוסר קבצים
            send_error_notification(sender, 
                "לא נמצאו קבצי CSV במייל. אנא ודא שצירפת קבצי נתונים תקינים.")
            return False
        
        all_converted_data = []
        processed_files = []
        
        for csv_file in csv_files:
            print(f"\n🔄 Processing file: {csv_file['filename']}")
            
            # פרסור CSV
            csv_rows = parse_csv_content(csv_file['data'])
            if csv_rows is None:
                print(f"❌ Failed to parse file: {csv_file['filename']}")
                continue
            
            # המרה לפורמט שלנו
            converted_data = convert_to_csv_import_format(csv_rows)
            if not converted_data:
                print(f"❌ Failed to convert file: {csv_file['filename']}")
                continue
            
            all_converted_data.extend(converted_data)
            processed_files.append({
                'name': csv_file['filename'],
                'rows': len(converted_data)
            })
            
            print(f"✅ File {csv_file['filename']}: {len(converted_data)} rows converted")
        
        # בדיקה שיש נתונים תקינים
        if not all_converted_data:
            error_msg = "לא נמצאו נתונים תקינים בקבצים. אנא בדוק את פורמט הקבצים."
            print(f"❌ {error_msg}")
            send_error_notification(sender, error_msg)
            return False
        
        print(f"📊 Total converted data: {len(all_converted_data)} rows")
        
        # הכנסה לטבלת הביניים
        inserted_count = insert_to_csv_import_shekels(all_converted_data)
        if inserted_count == 0:
            error_msg = "שגיאה בהכנסת הנתונים למסד הנתונים."
            print(f"❌ {error_msg}")
            send_error_notification(sender, error_msg)
            return False
        
        print(f"✅ Inserted to csv_import_shekels: {inserted_count} rows")
        
        # העברה לטבלה הסופית
        transferred_count = transfer_to_parking_data()
        
        # 🆕 תמיד שליחת מייל הצלחה - גם אם הכל כפילויות
        total_processed = len(all_converted_data)
        files_summary = ', '.join([f['name'] for f in processed_files])
        
        if transferred_count > 0:
            success_msg = f"עובדו {transferred_count} רשומות חדשות מתוך {total_processed} רשומות כולל"
            print(f"🎉 Email processed successfully: {success_msg}")
        else:
            success_msg = f"כל {total_processed} הרשומות כבר קיימות במערכת (כפילויות)"
            print(f"🎉 Email processed successfully: {success_msg}")
        
        # 🆕 שליחת מייל הצלחה עם פרטים מלאים
        send_success_notification(sender, processed_files, transferred_count, total_processed)
        
# 🏷️ סימון המייל כמעובד במקום מחיקה
        try:
            print(f"🏷️ Marking email as processed (ID: {email_id})...")
            mail.store(email_id, '+FLAGS', '\\Seen \\Flagged')
            print(f"✅ Email marked as processed successfully")
            
        except Exception as mark_error:
            print(f"⚠️ Could not mark email as processed: {str(mark_error)}")
            # לא מפסיקים את התהליך בגלל זה
        
        return True
        
    except Exception as e:
        error_msg = f"שגיאה טכנית בעיבוד המייל: {str(e)}"
        print(f"❌ Error processing email: {error_msg}")
        
        # 🆕 שליחת מייל שגיאה עם פרטים
        if sender and sender != 'unknown@unknown.com':
            send_error_notification(sender, error_msg)
        else:
            print(f"❌ Could not send error notification - unknown sender")
            
        return False

def send_success_notification(sender_email, processed_files, new_rows, total_rows):
    """שליחת התראת הצלחה - גרסה מתוקנת עם פרטים מלאים"""
    
    # בדיקת מגבלה יומית
    if not hasattr(send_success_notification, 'daily_count'):
        send_success_notification.daily_count = 0
        send_success_notification.last_reset = datetime.now().date()
    
    # איפוס יומי
    if send_success_notification.last_reset != datetime.now().date():
        send_success_notification.daily_count = 0
        send_success_notification.last_reset = datetime.now().date()
    
    # הגבלה ל-100 מיילי הצלחה ביום
    if send_success_notification.daily_count >= 100:
        files_summary = ', '.join([f['name'] for f in processed_files])
        print(f"⚠️ Daily success email limit reached (100/day) - logging only: {new_rows} new, {total_rows} total from {files_summary}")
        return
    
    # בדיקת נתונים
    gmail_user = os.environ.get('GMAIL_USERNAME')
    gmail_password = os.environ.get('GMAIL_APP_PASSWORD')
    
    if not gmail_user or not gmail_password:
        print(f"❌ Missing Gmail credentials for success notification")
        files_summary = ', '.join([f['name'] for f in processed_files])
        print(f"📝 Success logged: {new_rows} new, {total_rows} total from {files_summary}")
        return
        
    try:
        print(f"📧 Sending success notification to {sender_email}...")
        
        msg = MIMEMultipart()
        msg['From'] = gmail_user
        msg['To'] = sender_email
        msg['Subject'] = '✅ קבצי הנתונים עובדו בהצלחה - S&B Parking'
        
        files_list = '\n'.join([f"• {file['name']} - {file['rows']:,} שורות" for file in processed_files])
        
        # 🆕 הודעה מפורטת יותר
        if new_rows > 0:
            status_message = f"נוספו {new_rows:,} רשומות חדשות למסד הנתונים"
            if new_rows < total_rows:
                status_message += f" (מתוך {total_rows:,} רשומות כולל - יתר הרשומות כבר קיימות)"
        else:
            status_message = f"כל {total_rows:,} הרשומות כבר קיימות במערכת (לא נוספו רשומות חדשות)"
        
        body = f"""
שלום,

קבצי הנתונים שלך עובדו בהצלחה במערכת S&B Parking:

📁 קבצים שעובדו:
{files_list}

📊 תוצאות העיבוד:
{status_message}

💡 הערה: אם הרשומות כבר קיימות, זה אומר שהנתונים כבר הועלו קודם לכן.

🔍 הנתונים זמינים כעת בדשבורד לצפייה ודוחות.

בברכה,
מערכת S&B Parking (דוח אוטומטי)
נשלח מ: {gmail_user}
        """
        
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(gmail_user, gmail_password)
        server.send_message(msg)
        server.quit()
        
        send_success_notification.daily_count += 1
        print(f"✅ Success notification sent to {sender_email} ({send_success_notification.daily_count}/100 today)")
        
    except Exception as e:
        error_str = str(e)
        if "sending limit exceeded" in error_str.lower():
            print(f"🚫 Gmail daily limit exceeded - switching to log-only mode")
            send_success_notification.daily_count = 99
        else:
            print(f"❌ Failed to send success notification: {str(e)}")
            files_summary = ', '.join([f['name'] for f in processed_files])
            print(f"📝 Success logged: {new_rows} new, {total_rows} total from {files_summary}")

def send_error_notification(sender_email, error_message):
    """שליחת התראת שגיאה - מושבת, רק לוג"""
    
    # בדיקה אם מיילי שגיאה מושבתים
    if ERROR_EMAILS_DISABLED:
        print(f"🚫 Error email DISABLED - logging only")
        print(f"📝 Error for {sender_email}: {error_message}")
        return
    
    # אם לא מושבת, רק לוג (ללא שליחת מייל)
    print(f"📝 ERROR LOGGED (no email sent): {sender_email} - {error_message}")
            
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
    """הפעלת מעקב מיילים עם לוגים מפורטים - ללא כפילות"""
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
                    time.sleep(150)  # 300 שניות = 5 דקות
                    
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
        
        # בדיקה ראשונית מעוכבת למניעת כפילות
        print("🚀 Running initial email check in 15 seconds...")
        def delayed_initial_check():
            time.sleep(15)  # המתנה של 15 שניות
            with app.app_context():
                check_for_new_emails()
        threading.Thread(target=delayed_initial_check, daemon=True).start()
        
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
            print("📧 About to start email monitoring with logs...")  # 🆕 הוסף דיבוג
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
    """בדיקת מיילים חדשים - תיקון תאריכים"""
    global processed_email_ids, last_cache_reset
    
    # 🆕 איפוס זיכרון אחת לשעה
    if last_cache_reset is None or (datetime.now() - last_cache_reset).seconds > 3600:
        processed_email_ids = []
        last_cache_reset = datetime.now()
        print(f"🔄 Hourly cache reset completed")
    
    # ניקוי זיכרון אם יש יותר מדי
    if len(processed_email_ids) > 50:
        processed_email_ids = processed_email_ids[-20:]
        print(f"🧹 Email cache cleaned - kept last 20 emails")
    
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
        
        # תיקון תאריכים - מחפש מהיומיים האחרונים
        today = datetime.now().strftime('%d-%b-%Y')
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%d-%b-%Y')
        
        # חיפוש מיילים מהיומיים האחרונים
        search_criteria = f'OR SINCE {yesterday} SINCE {today}'
        
        print(f"🔍 Search criteria: {search_criteria}")
        print(f"📅 Today: {today}, Yesterday: {yesterday}")
        
        _, message_ids = mail.search(None, f'({search_criteria}) UNFLAGGED')
        
        if not message_ids[0]:
            print("📭 No emails found from the last 2 days")
            print(f"📊 Processed emails cache: {len(processed_email_ids)} emails")
            mail.logout()
            return
        
        email_ids = message_ids[0].split()
        print(f"📧 Found {len(email_ids)} emails from the last 2 days")
        
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
            
            # 🔧 תיקון: הוסף לרשימה רק אם הצליח!
            if success:
                processed_email_ids.append(email_id_str)
                print(f"✅ Email {email_id_str} added to processed cache")
            else:
                # לא מוסיפים לרשימה - ננסה שוב בפעם הבאה
                print(f"❌ Email {email_id_str} NOT added to cache - will retry next time")
            
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
    """פונקציה לשמירה על השירות ערני - גרסה מתוקנת"""
    def ping_self():
        print("🏓 Keep-alive service started")
        
        # קבלת URL של השרת מהמשתנה שהגדרנו
        app_url = os.environ.get('RENDER_EXTERNAL_URL', 'https://s-b-parking-reports.onrender.com')
        
        while True:
            try:
                # שליחת בקשה לעצמנו כל 10 דקות
                print(f"🏓 Sending keep-alive ping to {app_url}")
                response = requests.get(f'{app_url}/ping', timeout=30000)
                print(f"🏓 Keep-alive ping successful: {response.status_code}")
                
            except requests.exceptions.RequestException as e:
                print(f"⚠️ Keep-alive ping failed: {str(e)}")
                # ממשיכים גם במקרה של שגיאה
                
            except Exception as e:
                print(f"⚠️ Unexpected error in keep-alive: {str(e)}")
            
            # המתנה של 10 דקות (600 שניות)
            time.sleep(600)
    
    # הרצת הפונקציה ברקע
    ping_thread = threading.Thread(target=ping_self, daemon=True)
    ping_thread.start()
    print("🏓 Keep-alive service initialized")

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
                't_exit_s': int(row.get('t_exit_s', 0)),
                't_exit_p': int(row.get('t_exit_p', 0)),
                't_entry_s': int(row.get('t_entry_s', 0)),  # מזדמנים
                't_entry_p': int(row.get('t_entry_p', 0)),  # מנויים
                't_entry_ap': int(row.get('t_entry_ap', 0)),  # אפליקציה
                't_open_b': int(row.get('t_open_b', 0)),  # פתיחות מחסום
                'ts_per1': int(row.get('ts_per1', 0)),
                'ts_per2': int(row.get('ts_per2', 0)),
                'ts_per3': int(row.get('ts_per3', 0)),
                'ts_per4': int(row.get('ts_per4', 0)),
                'ts_per5': int(row.get('ts_per5', 0)),
                'ts_per6': int(row.get('ts_per6', 0)),
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
    print("🔍 === LOGIN FUNCTION STARTED ===")
    try:
        print("🔍 Step 1: Checking supabase...")
        if not supabase:
            return jsonify({'success': False, 'message': 'מסד הנתונים לא זמין'})
            
        print("🔍 Step 2: Getting JSON data...")
        data = request.get_json()
        username = data.get('username', '').strip()
        password = data.get('password', '').strip()
        
        print("🔍 Step 3: Validating input...")
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
        print("🔍 About to call RPC function...")
        
# קריאה לפונקציה עם טיפול פשוט  
        try:
            result = supabase.rpc('user_login', {
                'p_username': validated_username,
                'p_password': validated_password
            }).execute()
            auth_result = result.data
            print(f"🔐 Normal result: {auth_result}")
            
        except Exception as rpc_error:
            print(f"🔍 RPC Exception: {rpc_error}")
            # ניקח את התוצאה מהשגיאה
            if hasattr(rpc_error, 'args') and rpc_error.args:
                auth_result = rpc_error.args[0]
                print(f"🔐 From exception: {auth_result}")
                print(f"🔐 Type: {type(auth_result)}")
                
                # בדיקת סוג הנתונים
                if isinstance(auth_result, dict):
                    print(f"🔐 It's already a dict!")
                elif isinstance(auth_result, str):
                    print(f"🔍 Raw string: {repr(auth_result)}")
                    # זה כנראה string שנראה כמו dict - ננסה eval
                    try:
                        import ast
                        auth_result = ast.literal_eval(auth_result)
                        print(f"🔐 Converted with literal_eval: {auth_result}")
                    except:
                        try:
                            import json
                            auth_result = json.loads(auth_result)
                            print(f"🔐 Converted with json: {auth_result}")
                        except:
                            print("🔍 Could not parse - treating as error message")
                            return jsonify({'success': False, 'message': auth_result})
                else:
                    print(f"🔍 Unknown type: {type(auth_result)}")
                    raise rpc_error
            else:
                raise rpc_error
        
        print(f"🔍 Final result: {auth_result}")
        
        # עיבוד התוצאה
        if auth_result and auth_result.get('success'):
            # בדיקה אם נדרש לשנות סיסמה
            if auth_result.get('require_password_change'):
                session['change_password_user'] = validated_username
                print("🔍 Redirecting to password change")
                return jsonify({
                    'success': True,
                    'require_password_change': True,
                    'message': auth_result.get('message'),
                    'redirect': '/change-password'
                })
            
            # התחברות רגילה - קבלת האימייל
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
            error_msg = auth_result.get('message', 'שם משתמש או סיסמה שגויים') if auth_result else 'שגיאה בהתחברות'
            print(f"❌ Authentication failed: {error_msg}")
            return jsonify({'success': False, 'message': error_msg})
            
    except Exception as e:
        print(f"❌ OUTER EXCEPTION: {type(e)}")
        print(f"❌ OUTER EXCEPTION MESSAGE: {str(e)}")
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
            
            # 🆕 קבלת נתוני המשתמש לקביעת ההפניה
            try:
                user_result = supabase.table('user_parkings').select(
                    'code_type, access_level, role'
                ).eq('email', email).execute()
                
                if user_result.data and len(user_result.data) > 0:
                    user_data = user_result.data[0]
                    code_type = user_data.get('code_type', 'dashboard')
                    
                    print(f"✅ SUCCESS - User type: {code_type}")
                    
                    # קביעת הפניה לפי סוג המשתמש
                    redirect_url = '/dashboard'  # ברירת מחדל
                    
                    if code_type == 'master':
                        redirect_url = '/master-users'
                        print(f"🔧 Redirecting MASTER to: {redirect_url}")
                    elif code_type == 'parking_manager':
                        redirect_url = '/parking-manager-users'
                        print(f"🅿️ Redirecting PARKING MANAGER to: {redirect_url}")
                    else:
                        # dashboard משתמשים רגילים
                        redirect_url = '/dashboard'
                        print(f"📊 Redirecting REGULAR USER to: {redirect_url}")
                    
                    return jsonify({
                        'success': True, 
                        'redirect': redirect_url,
                        'user_type': code_type
                    })
                else:
                    print(f"⚠️ User data not found, redirecting to dashboard")
                    return jsonify({'success': True, 'redirect': '/dashboard'})
                    
            except Exception as e:
                print(f"❌ Error getting user data: {str(e)}")
                # במקרה של שגיאה, נפנה לדשבורד רגיל
                return jsonify({'success': True, 'redirect': '/dashboard'})
        else:
            print(f"❌ FAILED - Invalid or expired code")
            return jsonify({'success': False, 'message': 'קוד שגוי או פג תוקף'})
            
    except Exception as e:
        print(f"❌ Verify error: {str(e)}")
        return jsonify({'success': False, 'message': 'שגיאה במערכת'})

# 🆕 הוסף גם פונקציה לבדיקת הרשאות מוקדמת (אופציונלית)
def get_user_redirect_url(email):
    """קבלת URL להפניה לפי סוג המשתמש"""
    try:
        if not supabase:
            return '/dashboard'
            
        user_result = supabase.table('user_parkings').select(
            'code_type, access_level, role'
        ).eq('email', email).execute()
        
        if user_result.data and len(user_result.data) > 0:
            code_type = user_result.data[0].get('code_type', 'dashboard')
            
            if code_type == 'master':
                return '/master-users'
            elif code_type == 'parking_manager':
                return '/parking-manager-users'
            else:
                return '/dashboard'
        else:
            return '/dashboard'
            
    except Exception as e:
        print(f"❌ Error in get_user_redirect_url: {str(e)}")
        return '/dashboard'

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login_page'))

@app.route('/ping')
def ping():
    current_time = datetime.now()
    print(f"🏓 Ping received at {current_time}")
    print(f"🔋 Service status: Active and responsive")
    
    return jsonify({
        'status': 'pong',
        'timestamp': current_time.isoformat(),
        'message': 'Service is alive',
        'uptime': 'Active'
    }), 200

@app.route('/status')
def status():
    """בדיקת סטטוס מפורטת"""
    try:
        return jsonify({
            'service': 'S&B Parking Reports',
            'status': 'running',
            'timestamp': datetime.now().isoformat(),
            'email_monitoring': EMAIL_MONITORING_AVAILABLE,
            'supabase_connected': supabase is not None,
            'version': '1.0',
            'environment': os.environ.get('FLASK_ENV', 'production')
        }), 200
    except Exception as e:
        return jsonify({
            'service': 'S&B Parking Reports',
            'status': 'error',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500

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

# Route לדף שינוי סיסמה
@app.route('/change-password')
def change_password_page():
    if 'change_password_user' not in session:
        return redirect(url_for('login_page'))
    return render_template('change-password.html')

# API לשינוי סיסמה
@app.route('/api/change-password', methods=['POST'])
def change_password():
    try:
        if not supabase:
            return jsonify({'success': False, 'message': 'מסד הנתונים לא זמין'})
        
        if 'change_password_user' not in session:
            return jsonify({'success': False, 'message': 'אין הרשאה לשינוי סיסמה'})
        
        data = request.get_json()
        old_password = data.get('old_password', '').strip()
        new_password = data.get('new_password', '').strip()
        confirm_password = data.get('confirm_password', '').strip()
        
        # אימות קלט
        if not old_password or not new_password or not confirm_password:
            return jsonify({'success': False, 'message': 'יש למלא את כל השדות'})
        
        if new_password != confirm_password:
            return jsonify({'success': False, 'message': 'סיסמאות לא תואמות'})
        
        if len(new_password) < 6:
            return jsonify({'success': False, 'message': 'סיסמה חייבת להיות לפחות 6 תווים'})
        
        username = session['change_password_user']
        
# שינוי הסיסמה עם טיפול בAPIError
        try:
            result = supabase.rpc('change_user_password', {
                'p_username': username,
                'p_old_password': old_password,
                'p_new_password': new_password
            }).execute()
            change_result = result.data
        except Exception as rpc_error:
            # טיפול באותה בעיה
            if hasattr(rpc_error, 'args') and rpc_error.args:
                try:
                    import ast
                    change_result = ast.literal_eval(str(rpc_error.args[0]))
                except:
                    change_result = rpc_error.args[0]
            else:
                raise rpc_error
        
        if change_result and change_result.get('success'):
            # מחיקת המשתמש מהסשן וחזרה להתחברות
            session.pop('change_password_user', None)
            return jsonify({
                'success': True,
                'message': 'סיסמה שונתה בהצלחה. אנא התחבר מחדש',
                'redirect': '/login'
            })
        else:
            error_msg = result.data.get('message', 'שגיאה בשינוי סיסמה') if result.data else 'שגיאה בשינוי סיסמה'
            return jsonify({'success': False, 'message': error_msg})
        
    except Exception as e:
        print(f"❌ Change password error: {str(e)}")
        return jsonify({'success': False, 'message': 'שגיאה במערכת'})

# API ליצירת משתמש חדש (למאסטר)
@app.route('/api/create-user', methods=['POST'])
def create_user():
    try:
        if not supabase:
            return jsonify({'success': False, 'message': 'מסד הנתונים לא זמין'})
        
        # בדיקת הרשאות - כרגע נחזור לזה אחר כך
        if 'user_email' not in session:
            return jsonify({'success': False, 'message': 'לא מחובר'})
        
        data = request.get_json()
        username = data.get('username', '').strip()
        email = data.get('email', '').strip()
        project_number = data.get('project_number')
        code_type = data.get('code_type', 'dashboard').strip()
        company_list = data.get('company_list', '').strip() or None
        
        # אימות קלט בסיסי
        if not username or not email or not project_number:
            return jsonify({'success': False, 'message': 'יש למלא את כל השדות הנדרשים'})
        
        # יצירת המשתמש
        result = supabase.rpc('create_user_with_temp_password', {
            'p_username': username,
            'p_email': email,
            'p_project_number': int(project_number),
            'p_code_type': code_type,
            'p_created_by': session['user_email'],
            'p_company_list': company_list
        }).execute()
        
        if result.data and result.data.get('success'):
            # שליחת מייל למשתמש החדש
            user_data = result.data
            send_new_user_email(
                user_data.get('email'),
                user_data.get('username'),
                user_data.get('temp_password'),
                user_data.get('login_url')
            )
            
            return jsonify({
                'success': True,
                'message': f'משתמש נוצר בהצלחה. מייל נשלח ל-{email}',
                'user_data': {
                    'username': username,
                    'email': email,
                    'temp_password': user_data.get('temp_password')
                }
            })
        else:
            error_msg = result.data.get('message', 'שגיאה ביצירת משתמש') if result.data else 'שגיאה ביצירת משתמש'
            return jsonify({'success': False, 'message': error_msg})
        
    except Exception as e:
        print(f"❌ Create user error: {str(e)}")
        return jsonify({'success': False, 'message': 'שגיאה במערכת'})

def send_new_user_email(email, username, temp_password, login_url):
    """שליחת מייל למשתמש חדש עם פרטי התחברות"""
    
    if not mail:
        print(f"❌ Mail system not available")
        print(f"📱 NEW USER DETAILS for {email}:")
        print(f"   Username: {username}")
        print(f"   Password: {temp_password}")
        print(f"   URL: {login_url}")
        return False
    
    try:
        print(f"🚀 Sending new user email to {email}...")
        
        msg = Message(
            subject='חשבון חדש - S&B Parking',
            recipients=[email],
            html=f"""
            <div style="font-family: Arial, sans-serif; direction: rtl; text-align: right;">
                <h2 style="color: #667eea;">שיידט את בכמן ישראל</h2>
                <h3>חשבון חדש נוצר עבורך במערכת דוחות החניות</h3>
                
                <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0;">
                    <p><strong>שם משתמש:</strong> {username}</p>
                    <p><strong>סיסמה זמנית:</strong> <span style="font-family: monospace; background: #e9ecef; padding: 2px 6px;">{temp_password}</span></p>
                    <p><strong>קישור להתחברות:</strong></p>
                    <a href="{login_url}" style="color: #667eea; text-decoration: none; font-weight: bold;">{login_url}</a>
                </div>
                
                <div style="background: #fff3cd; border: 1px solid #ffeaa7; padding: 15px; border-radius: 8px; margin: 20px 0;">
                    <p style="margin: 0; color: #856404;"><strong>חשוב:</strong></p>
                    <p style="margin: 5px 0 0 0; color: #856404;">
                        • הסיסמה הזמנית תפוג ב-01/01/2025<br>
                        • בכניסה הראשונה תתבקש לשנות את הסיסמה<br>
                        • לאחר שינוי הסיסמה תוכל להתחבר למערכת
                    </p>
                </div>
                
                <p>אם יש לך שאלות, צור קשר עם מנהל המערכת.</p>
                
                <hr>
                <p style="color: #666; font-size: 12px;">S&B Parking - מערכת דוחות חניות</p>
            </div>
            """,
            sender=app.config['MAIL_USERNAME']
        )
        
        mail.send(msg)
        print(f"✅ New user email sent successfully to {email}")
        return True
        
    except Exception as e:
        print(f"❌ New user email error: {str(e)}")
        print(f"📱 BACKUP - NEW USER DETAILS for {email}:")
        print(f"   Username: {username}")
        print(f"   Password: {temp_password}")
        print(f"   URL: {login_url}")
        return False

@app.route('/master-users')
def master_users_page():
    """דף ניהול משתמשים למאסטר"""
    if 'user_email' not in session:
        return redirect(url_for('login_page'))
    
    # בדיקת הרשאות מאסטר
    try:
        user_result = supabase.table('user_parkings').select('code_type, access_level').eq('email', session['user_email']).execute()
        if not user_result.data or user_result.data[0].get('code_type') != 'master':
            print(f"⚠️ Unauthorized access attempt to master-users by {session['user_email']}")
            return redirect(url_for('dashboard'))
    except Exception as e:
        print(f"❌ Error checking master permissions: {str(e)}")
        return redirect(url_for('dashboard'))
    
    return render_template('master_users.html')

@app.route('/parking-manager-users')
def parking_manager_users_page():
    """דף ניהול משתמשים למנהל חניון"""
    if 'user_email' not in session:
        return redirect(url_for('login_page'))
    
    # בדיקת הרשאות מנהל חניון
    try:
        user_result = supabase.table('user_parkings').select('code_type, project_number, access_level').eq('email', session['user_email']).execute()
        if not user_result.data or user_result.data[0].get('code_type') != 'parking_manager':
            print(f"⚠️ Unauthorized access attempt to parking-manager-users by {session['user_email']}")
            return redirect(url_for('dashboard'))
    except Exception as e:
        print(f"❌ Error checking parking manager permissions: {str(e)}")
        return redirect(url_for('dashboard'))
    
    return render_template('parking_manager_users.html')

# ========== API למאסטר ==========

@app.route('/api/master/get-all-users', methods=['GET'])
def master_get_all_users():
    """קבלת כל המשתמשים - למאסטר בלבד"""
    try:
        if 'user_email' not in session:
            return jsonify({'success': False, 'message': 'לא מחובר'}), 401
        
        # בדיקת הרשאות מאסטר
        user_result = supabase.table('user_parkings').select('code_type').eq('email', session['user_email']).execute()
        if not user_result.data or user_result.data[0].get('code_type') != 'master':
            return jsonify({'success': False, 'message': 'אין הרשאה'}), 403
        
        # קבלת כל המשתמשים
        users_result = supabase.table('user_parkings').select(
            'user_id, username, email, role, project_number, parking_name, company_type, access_level, code_type, created_at, password_changed_at, is_temp_password'
        ).order('created_at', desc=True).execute()
        
        return jsonify({
            'success': True,
            'users': users_result.data
        })
        
    except Exception as e:
        print(f"❌ Error getting all users: {str(e)}")
        return jsonify({'success': False, 'message': 'שגיאה בקבלת רשימת משתמשים'})

@app.route('/api/master/create-user', methods=['POST'])
def master_create_user():
    """יצירת משתמש חדש - למאסטר בלבד - גרסה מתוקנת"""
    try:
        if 'user_email' not in session:
            return jsonify({'success': False, 'message': 'לא מחובר'}), 401
        
        # בדיקת הרשאות מאסטר
        user_result = supabase.table('user_parkings').select('code_type').eq('email', session['user_email']).execute()
        if not user_result.data or user_result.data[0].get('code_type') != 'master':
            return jsonify({'success': False, 'message': 'אין הרשאה'}), 403
        
        data = request.get_json()
        username = data.get('username', '').strip()
        email = data.get('email', '').strip()
        project_number = data.get('project_number')
        code_type = data.get('code_type', 'dashboard').strip()
        role = data.get('role', 'user').strip()
        access_level = data.get('access_level', 'single_parking').strip()
        company_type = data.get('company_type', '').strip()
        parking_name = data.get('parking_name', '').strip()
        
        print(f"🆕 Creating new user: {username} ({email})")
        
        # אימות קלט בסיסי
        if not username or not email:
            return jsonify({'success': False, 'message': 'יש למלא שם משתמש ואימייל'})
        
        # אימות אימייל
        is_valid_email, validated_email = validate_input(email, "email")
        if not is_valid_email:
            return jsonify({'success': False, 'message': 'כתובת אימייל לא תקינה'})
        
        # בדיקה אם המשתמש כבר קיים - גרסה מתוקנת לSupabase
        existing_username = supabase.table('user_parkings').select('username').eq('username', username).execute()
        existing_email = supabase.table('user_parkings').select('email').eq('email', validated_email).execute()
        
        if existing_username.data:
            return jsonify({'success': False, 'message': f'שם משתמש "{username}" כבר קיים במערכת'})
        
        if existing_email.data:
            return jsonify({'success': False, 'message': f'כתובת אימייל "{validated_email}" כבר קיימת במערכת'})
        
        # יצירת hash לסיסמה
        password_hash = bcrypt.hashpw('Dd123456'.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
        # הכנת הנתונים להוספה
        new_user_data = {
            'username': username,
            'email': validated_email,
            'password_hash': password_hash,
            'role': role,
            'project_number': int(project_number) if project_number else 0,
            'parking_name': parking_name if parking_name else 'לא צוין',
            'company_type': company_type if company_type else 'לא צוין',
            'access_level': access_level,
            'code_type': code_type,
            'is_temp_password': True,  # סיסמה זמנית שיש לשנות
            'verification_code': None,
            'code_expires_at': None
        }
        
        print(f"💾 Inserting user data: {new_user_data}")
        
        # הוספת המשתמש למסד הנתונים
        result = supabase.table('user_parkings').insert(new_user_data).execute()
        
        if result.data:
            print(f"✅ User created successfully: {username}")
            
            # שליחת מייל למשתמש החדש
            email_sent = send_new_user_welcome_email(
                validated_email,
                username,
                'Dd123456',
                'https://s-b-parking-reports.onrender.com'
            )
            
            if email_sent:
                message = f'משתמש {username} נוצר בהצלחה! מייל נשלח ל-{validated_email}'
            else:
                message = f'משתמש {username} נוצר בהצלחה, אך לא ניתן לשלוח מייל. הסיסמה הראשונית: Dd123456'
            
            return jsonify({
                'success': True,
                'message': message,
                'user_data': {
                    'username': username,
                    'email': validated_email,
                    'temp_password': 'Dd123456'
                }
            })
        else:
            print(f"❌ Failed to insert user to database")
            return jsonify({'success': False, 'message': 'שגיאה ביצירת המשתמש במסד הנתונים'})
        
    except Exception as e:
        print(f"❌ Master create user error: {str(e)}")
        return jsonify({'success': False, 'message': f'שגיאה במערכת: {str(e)}'})

@app.route('/api/master/reset-password', methods=['POST'])
def master_reset_password():
    """איפוס סיסמה - למאסטר בלבד"""
    try:
        if 'user_email' not in session:
            return jsonify({'success': False, 'message': 'לא מחובר'}), 401
        
        # בדיקת הרשאות מאסטר
        user_result = supabase.table('user_parkings').select('code_type').eq('email', session['user_email']).execute()
        if not user_result.data or user_result.data[0].get('code_type') != 'master':
            return jsonify({'success': False, 'message': 'אין הרשאה'}), 403
        
        data = request.get_json()
        target_username = data.get('username', '').strip()
        
        if not target_username:
            return jsonify({'success': False, 'message': 'יש לציין שם משתמש'})
        
        # איפוס הסיסמה ל-Dd123456
        try:
            result = supabase.rpc('master_reset_password', {
                'p_username': target_username,
                'p_new_password': 'Dd123456',
                'p_reset_by': session['user_email']
            }).execute()
        except Exception as rpc_error:
            # טיפול בAPIError
            if hasattr(rpc_error, 'args') and rpc_error.args:
                try:
                    import ast
                    result_data = ast.literal_eval(str(rpc_error.args[0]))
                except:
                    result_data = {'success': False, 'message': str(rpc_error)}
            else:
                result_data = {'success': False, 'message': str(rpc_error)}
        else:
            result_data = result.data
        
        if result_data and result_data.get('success'):
            # קבלת כתובת המייל של המשתמש
            user_info = supabase.table('user_parkings').select('email').eq('username', target_username).execute()
            if user_info.data:
                user_email = user_info.data[0]['email']
                send_password_reset_email(user_email, target_username, 'Dd123456')
            
            return jsonify({
                'success': True,
                'message': f'סיסמה אופסה בהצלחה עבור {target_username}'
            })
        else:
            error_msg = result_data.get('message', 'שגיאה באיפוס סיסמה') if result_data else 'שגיאה באיפוס סיסמה'
            return jsonify({'success': False, 'message': error_msg})
        
    except Exception as e:
        print(f"❌ Master reset password error: {str(e)}")
        return jsonify({'success': False, 'message': 'שגיאה במערכת'})

# ========== API למנהל חניון ==========

@app.route('/api/parking-manager/get-parking-info', methods=['GET'])
def parking_manager_get_info():
    """קבלת נתוני החניון של המנהל"""
    try:
        if 'user_email' not in session:
            return jsonify({'success': False, 'message': 'לא מחובר'}), 401
        
        # בדיקת הרשאות מנהל חניון
        user_result = supabase.table('user_parkings').select(
            'code_type, project_number, parking_name, company_type'
        ).eq('email', session['user_email']).execute()
        
        if not user_result.data or user_result.data[0].get('code_type') != 'parking_manager':
            return jsonify({'success': False, 'message': 'אין הרשאה'}), 403
        
        user_data = user_result.data[0]
        
        # קבלת משתמשי החניון
        parking_users = supabase.table('user_parkings').select(
            'user_id, username, email, role, access_level, created_at, password_changed_at, is_temp_password'
        ).eq('project_number', user_data['project_number']).order('created_at', desc=True).execute()
        
        return jsonify({
            'success': True,
            'parking_info': {
                'project_number': user_data['project_number'],
                'parking_name': user_data['parking_name'],
                'company_type': user_data['company_type']
            },
            'users': parking_users.data
        })
        
    except Exception as e:
        print(f"❌ Error getting parking manager info: {str(e)}")
        return jsonify({'success': False, 'message': 'שגיאה בקבלת נתוני חניון'})

@app.route('/api/parking-manager/create-user', methods=['POST'])
def parking_manager_create_user():
    """יצירת משתמש חדש לחניון - למנהל חניון בלבד - גרסה מתוקנת"""
    try:
        if 'user_email' not in session:
            return jsonify({'success': False, 'message': 'לא מחובר'}), 401
        
        # בדיקת הרשאות מנהל חניון
        manager_result = supabase.table('user_parkings').select(
            'code_type, project_number, parking_name, company_type'
        ).eq('email', session['user_email']).execute()
        
        if not manager_result.data or manager_result.data[0].get('code_type') != 'parking_manager':
            return jsonify({'success': False, 'message': 'אין הרשאה'}), 403
        
        manager_data = manager_result.data[0]
        
        data = request.get_json()
        username = data.get('username', '').strip()
        email = data.get('email', '').strip()
        access_level = data.get('access_level', 'single_parking').strip()
        
        print(f"🅿️ Parking manager creating user: {username} for parking {manager_data['project_number']}")
        
        # אימות קלט בסיסי
        if not username or not email:
            return jsonify({'success': False, 'message': 'יש למלא שם משתמש ואימייל'})
        
        # אימות אימייל
        is_valid_email, validated_email = validate_input(email, "email")
        if not is_valid_email:
            return jsonify({'success': False, 'message': 'כתובת אימייל לא תקינה'})
        
        # בדיקה אם המשתמש כבר קיים - גרסה מתוקנת לSupabase
        existing_username = supabase.table('user_parkings').select('username').eq('username', username).execute()
        existing_email = supabase.table('user_parkings').select('email').eq('email', validated_email).execute()
        
        if existing_username.data:
            return jsonify({'success': False, 'message': f'שם משתמש "{username}" כבר קיים במערכת'})
        
        if existing_email.data:
            return jsonify({'success': False, 'message': f'כתובת אימייל "{validated_email}" כבר קיימת במערכת'})
        
        # יצירת hash לסיסמה
        password_hash = bcrypt.hashpw('Dd123456'.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
        # הכנת הנתונים להוספה
        new_user_data = {
            'username': username,
            'email': validated_email,
            'password_hash': password_hash,
            'role': 'user',  # משתמש רגיל בחניון
            'project_number': manager_data['project_number'],
            'parking_name': manager_data['parking_name'],
            'company_type': manager_data['company_type'],
            'access_level': access_level,
            'code_type': 'dashboard',  # משתמש רגיל
            'is_temp_password': True,  # סיסמה זמנית שיש לשנות
            'verification_code': None,
            'code_expires_at': None
        }
        
        print(f"💾 Inserting parking user data: {new_user_data}")
        
        # הוספת המשתמש למסד הנתונים
        result = supabase.table('user_parkings').insert(new_user_data).execute()
        
        if result.data:
            print(f"✅ Parking user created successfully: {username}")
            
            # שליחת מייל למשתמש החדש
            email_sent = send_new_user_welcome_email(
                validated_email,
                username,
                'Dd123456',
                'https://s-b-parking-reports.onrender.com'
            )
            
            if email_sent:
                message = f'משתמש {username} נוסף בהצלחה לחניון {manager_data["parking_name"]}! מייל נשלח ל-{validated_email}'
            else:
                message = f'משתמש {username} נוסף בהצלחה לחניון {manager_data["parking_name"]}, אך לא ניתן לשלוח מייל. הסיסמה הראשונית: Dd123456'
            
            return jsonify({
                'success': True,
                'message': message,
                'user_data': {
                    'username': username,
                    'email': validated_email,
                    'parking_name': manager_data['parking_name'],
                    'temp_password': 'Dd123456'
                }
            })
        else:
            print(f"❌ Failed to insert parking user to database")
            return jsonify({'success': False, 'message': 'שגיאה ביצירת המשתמש במסד הנתונים'})
        
    except Exception as e:
        print(f"❌ Parking manager create user error: {str(e)}")
        return jsonify({'success': False, 'message': f'שגיאה במערכת: {str(e)}'})
# ========== פונקציות מיילים ==========

def send_new_user_welcome_email(email, username, password, login_url):
    """שליחת מייל ברוכים הבאים למשתמש חדש"""
    
    if not mail:
        print(f"❌ Mail system not available")
        print(f"📱 NEW USER DETAILS for {email}:")
        print(f"   Username: {username}")
        print(f"   Password: {password}")
        print(f"   URL: {login_url}")
        return False
    
    try:
        print(f"🚀 Sending welcome email to {email}...")
        
        msg = Message(
            subject='ברוכים הבאים למערכת S&B Parking',
            recipients=[email],
            html=f"""
            <div style="font-family: Arial, sans-serif; direction: rtl; text-align: right;">
                <h2 style="color: #667eea;">ברוכים הבאים למערכת S&B Parking</h2>
                <h3>חשבון חדש נוצר עבורך במערכת דוחות החניות</h3>
                
                <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0;">
                    <p><strong>שם משתמש:</strong> {username}</p>
                    <p><strong>סיסמה ראשונית:</strong> <span style="font-family: monospace; background: #e9ecef; padding: 2px 6px; color: #d63384; font-weight: bold;">Dd123456</span></p>
                    <p><strong>קישור להתחברות:</strong></p>
                    <a href="{login_url}" style="color: #667eea; text-decoration: none; font-weight: bold;">{login_url}</a>
                </div>
                
                <div style="background: #fff3cd; border: 1px solid #ffeaa7; padding: 15px; border-radius: 8px; margin: 20px 0;">
                    <p style="margin: 0; color: #856404;"><strong>חשוב - הוראות בטיחות:</strong></p>
                    <p style="margin: 5px 0 0 0; color: #856404;">
                        • בכניסה הראשונה תתבקש לשנות את הסיסמה<br>
                        • אנא שנה את הסיסמה לסיסמה אישית וחזקה<br>
                        • שמור על פרטי ההתחברות שלך במקום בטוח<br>
                        • אל תשתף את פרטי ההתחברות עם אחרים
                    </p>
                </div>
                
                <p>אם יש לך שאלות או בעיות בהתחברות, צור קשר עם מנהל המערכת.</p>
                
                <hr>
                <p style="color: #666; font-size: 12px;">
                    S&B Parking - מערכת ניהול דוחות חניות<br>
                    מייל אוטומטי - אנא אל תענה למייל זה
                </p>
            </div>
            """,
            sender=app.config['MAIL_USERNAME']
        )
        
        mail.send(msg)
        print(f"✅ Welcome email sent successfully to {email}")
        return True
        
    except Exception as e:
        print(f"❌ Welcome email error: {str(e)}")
        print(f"📱 BACKUP - NEW USER DETAILS for {email}:")
        print(f"   Username: {username}")
        print(f"   Password: {password}")
        print(f"   URL: {login_url}")
        return False

def send_password_reset_email(email, username, new_password):
    """שליחת מייל על איפוס סיסמה"""
    
    if not mail:
        print(f"❌ Mail system not available")
        print(f"📱 PASSWORD RESET for {username}: {new_password}")
        return False
    
    try:
        print(f"🚀 Sending password reset email to {email}...")
        
        msg = Message(
            subject='איפוס סיסמה - S&B Parking',
            recipients=[email],
            html=f"""
            <div style="font-family: Arial, sans-serif; direction: rtl; text-align: right;">
                <h2 style="color: #667eea;">איפוס סיסמה - S&B Parking</h2>
                <h3>הסיסמה שלך אופסה על ידי מנהל המערכת</h3>
                
                <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0;">
                    <p><strong>שם משתמש:</strong> {username}</p>
                    <p><strong>סיסמה חדשה:</strong> <span style="font-family: monospace; background: #e9ecef; padding: 2px 6px; color: #d63384; font-weight: bold;">Dd123456</span></p>
                    <p><strong>קישור להתחברות:</strong></p>
                    <a href="https://s-b-parking-reports.onrender.com" style="color: #667eea; text-decoration: none; font-weight: bold;">https://s-b-parking-reports.onrender.com</a>
                </div>
                
                <div style="background: #f8d7da; border: 1px solid #f5c6cb; padding: 15px; border-radius: 8px; margin: 20px 0;">
                    <p style="margin: 0; color: #721c24;"><strong>חשוב:</strong></p>
                    <p style="margin: 5px 0 0 0; color: #721c24;">
                        • בכניסה הבאה תתבקש לשנות את הסיסמה<br>
                        • שנה את הסיסמה מיד לסיסמה אישית וחזקה<br>
                        • אל תשתף את הסיסמה עם אחרים
                    </p>
                </div>
                
                <p>אם לא ביקשת איפוס סיסמה, צור קשר עם מנהל המערכת מיד.</p>
                
                <hr>
                <p style="color: #666; font-size: 12px;">
                    S&B Parking - מערכת ניהול דוחות חניות<br>
                    מייל אוטומטי - אנא אל תענה למייל זה
                </p>
            </div>
            """,
            sender=app.config['MAIL_USERNAME']
        )
        
        mail.send(msg)
        print(f"✅ Password reset email sent successfully to {email}")
        return True
        
    except Exception as e:
        print(f"❌ Password reset email error: {str(e)}")
        print(f"📱 BACKUP - PASSWORD RESET for {username}: {new_password}")
        return False 
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
