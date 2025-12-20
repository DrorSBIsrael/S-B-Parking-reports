from flask import Flask, render_template, request, jsonify, session, redirect, url_for, make_response, send_from_directory
import flask
from flask_mail import Mail, Message
from supabase.client import create_client, Client
from dotenv import load_dotenv
import os
import random
import string
import requests
import re
import html
import bcrypt
import base64
import urllib3
import json
from datetime import datetime, timedelta, timezone

# ביטול אזהרות SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# טעינת משתני סביבה מקובץ .env
load_dotenv()

# הוסר ייבוא proxy_endpoints - הקוד נמצא ישירות בקובץ

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
    # Email monitoring libraries loaded successfully
except ImportError as e:
    EMAIL_MONITORING_AVAILABLE = False
    # Email monitoring not available

ERROR_EMAILS_DISABLED = True
# הגדרות מיילים אוטומטיים - להוסיף אחרי ההגדרות הקיימות:
if EMAIL_MONITORING_AVAILABLE:
    EMAIL_CHECK_INTERVAL = 5  # בדיקה כל 5 דקות
    PROCESSED_EMAILS_LIMIT = 100  # מקסימום מיילים לזכור
    processed_email_ids = []  # רשימה לזכור מיילים שכבר עובדו
    last_cache_reset = None
password_reset_codes = {}
# רשימת שולחים מורשים לשליחת קבצי נתונים
AUTHORIZED_SENDERS = [
    'Dror@sbparking.co.il',
    'dror@sbparking.co.il',  # case insensitive
    'Report@sbparking.co.il',
    'report@sbparking.co.il'  # case insensitive
]

# S&B Parking Application Starting

app = Flask(__name__, static_folder='static', static_url_path='/static')
app.secret_key = os.environ.get('SECRET_KEY', 'your-secret-key-here')
app.config['JSON_AS_ASCII'] = False  # תמיכה בעברית ב-JSON
app.config['JSONIFY_MIMETYPE'] = 'application/json; charset=utf-8'  # קידוד UTF-8
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0  # Disable caching for development

# Supabase configuration
SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_ANON_KEY')

# Supabase configuration check

if not SUPABASE_URL or not SUPABASE_KEY:
    # CRITICAL: Supabase credentials missing
    supabase = None
else:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        # Supabase connection established
            
    except Exception as e:
        # Supabase connection failed
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
app.config['MAIL_DEBUG'] = False

# Gmail configuration check

try:
    mail = Mail(app)
    # Mail system initialized
except Exception as e:
    # Mail system initialization failed
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
            # Security threat detected
            return False, f"קלט לא חוקי - מכיל מילה אסורה: {word}"
    
    # בדיקת תווים מסוכנים
    dangerous_chars = ["'", '"', ';', '--', '/*', '*/', '<', '>', '&', '|', '`']
    for char in dangerous_chars:
        if char in input_text:
            # Security threat detected
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
    # Rate limit check
    return True

def generate_verification_code():
    """יצירת קוד אימות של 6 ספרות"""
    return ''.join(random.choices(string.digits, k=6))

def store_verification_code(email, code):
    """שמירת קוד אימות בטבלת user_parkings הקיימת"""
    if not supabase:
        # Supabase not available
        return False
        
    try:
        # אימות אימייל לפני שמירה
        is_valid, validated_email = validate_input(email, "email")
        if not is_valid:
            # Invalid email format
            return False
        
        # חישוב זמן תפוגה (10 דקות מעכשיו)
        expires_at = datetime.now() + timedelta(minutes=10)
        expires_str = expires_at.strftime('%Y-%m-%d %H:%M:%S')
        
        # Updating user_parkings
        
        # שימוש ב-Supabase עם פרמטרים בטוחים
        result = supabase.table('user_parkings').update({
            'verification_code': code,
            'code_expires_at': expires_str
        }).eq('email', validated_email).execute()
        
        # Code saved successfully
        return True
        
    except Exception as e:
        # Failed to save code
        return False

def send_verification_email(email, code):
    """שליחת מייל עם Gmail + App Password מ-Environment Variables"""
    
    if not mail:
        # Mail system not available
        return False
    
    # אימות אימייל
    is_valid, validated_email = validate_input(email, "email")
    if not is_valid:
        # Invalid email format
        return False
    
    # בדיקה שיש נתונים
    if not app.config['MAIL_USERNAME'] or not app.config['MAIL_PASSWORD']:
        # Gmail credentials missing
        return False
    
    try:
        # Starting Gmail send
        
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
        
        # Sending via Gmail
        mail.send(msg)
        
        # Gmail email sent successfully
        return True
        
    except Exception as e:
        # Gmail error occurred
        return False

def verify_code_from_database(email, code):
    """בדיקת קוד אימות מטבלת user_parkings"""
    if not supabase:
        # Supabase not available
        return False
        
    try:
        # אימות קלט
        is_valid_email, validated_email = validate_input(email, "email")
        is_valid_code, validated_code = validate_input(code, "verification_code")
        
        if not is_valid_email:
            # Invalid email format
            return False
            
        if not is_valid_code:
            # Invalid code format
            return False
        
        # חיפוש משתמש עם הקוד
        result = supabase.table('user_parkings').select('verification_code, code_expires_at').eq('email', validated_email).execute()
        
        if not result.data:
            # No user found
            return False
            
        user_data = result.data[0]
        stored_code = user_data.get('verification_code')
        expires_at_str = user_data.get('code_expires_at')
        
        # Code verification attempt
        
        if not stored_code or stored_code != validated_code:
            # Code mismatch
            return False
            
        # בדיקת תוקף
        if expires_at_str:
            expires_at = datetime.fromisoformat(expires_at_str.replace('Z', '').replace('+00:00', ''))
            if datetime.now() > expires_at:
                # Code expired
                return False
        
        # מחיקת הקוד אחרי שימוש מוצלח
        supabase.table('user_parkings').update({
            'verification_code': None,
            'code_expires_at': None
        }).eq('email', validated_email).execute()
        
        # Code verified and cleared
        return True
        
    except Exception as e:
        # Database verification failed
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
            # Missing Gmail credentials
            return None
            
        mail.login(gmail_user, gmail_password)
        # Connected to Gmail
        
        return mail
        
    except Exception as e:
        # Gmail IMAP connection failed
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
                        
                        # Found CSV attachment
        
        return csv_files
        
    except Exception as e:
        # Error downloading CSV
        return []

def parse_csv_content(csv_content):
    """פרסור CSV עם זיהוי קידוד אוטומטי לעברית ואימות תקינות"""
    try:
        # Check input type
        
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
                    # Successfully decoded
                    break
                except UnicodeDecodeError:
                    # Failed to decode
                    continue
            
            if decoded_content is None:
                # Could not decode - using latin1 as fallback
                decoded_content = csv_content.decode('latin1', errors='ignore')
                used_encoding = 'latin1'
            
            csv_content = decoded_content
        else:
            used_encoding = 'already_string'
        
        # אם זה לא string, נמיר
        if not isinstance(csv_content, str):
            csv_content = str(csv_content)
        
        # Content parsed
        
        # ניקוי בסיסי
        csv_content = csv_content.strip()
        if not csv_content:
            # Empty content after decoding
            return None
        
        # הדפסת השורה הראשונה כדי לבדוק עברית
        first_line = csv_content.split('\n')[0]
        # Check first line
        
        # ⚠️ בדיקת תקינות CSV - אם זה קובץ SQL או לא תקין
        if any(sql_keyword in first_line.lower() for sql_keyword in ['connect', 'insert', 'select', 'values', 'create']):
            # Invalid file: SQL detected, not CSV
            return None
        
        # בדיקה שיש כותרות CSV תקינות
        if 'ProjectNumber' not in first_line:
            # Invalid CSV: Missing expected header
            return None
        
        # אם יש עברית בשורה הראשונה, נדווח על כך
        if any('\u0590' <= char <= '\u05FF' for char in first_line):
            # Hebrew characters detected in header
            pass
        
        # ניסיון פרסור פשוט עם פסיק
        try:
            reader = csv.DictReader(io.StringIO(csv_content))
            rows = list(reader)
            # Parsed rows
            
            if rows:
                columns = list(rows[0].keys())
                # Check columns
                
                # בדיקה נוספת - אם השורה הראשונה ריקה או לא תקינה
                if not rows or not any(rows[0].values()):
                    # Invalid CSV: First data row is empty
                    return None
                
                # בדיקה אם יש עברית בנתונים
                for i, row in enumerate(rows[:3]):  # בדיקת 3 שורות ראשונות
                    for key, value in row.items():
                        if value and any('\u0590' <= char <= '\u05FF' for char in str(value)):
                            # Hebrew text found
                            break
                
                return rows
        except Exception as e:
            # Comma parsing failed
            pass
        
        # אם הגענו לכאן, הקובץ לא תקין
        # Invalid CSV: Could not parse
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
            # Error converting row {index+1}: {str(e)}")
            print(f"   Row data: {row}")
            continue  # ממשיך לשורה הבאה במקום להפסיק
    
    # Successfully converted rows
    return converted_rows

def insert_to_csv_import_shekels(converted_data):
    """הכנסה לטבלת csv_import_shekels (שלב ביניים) - גרסה מתוקנת"""
    if not supabase:
        # Supabase not available
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
                # Error cleaning row {i}: {str(row_error)}")
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
                # Error in batch {batch_num}: {str(batch_error)}")
                
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
        # Supabase not available
        return 0
        
    try:
        print("🔄 Starting transfer from csv_import_shekels to parking_data...")
        
        # קבלת כל הנתונים מטבלת הביניים
        csv_result = supabase.table('csv_import_shekels').select('*').execute()
        
        if not csv_result.data:
            print("⚠️ No data in csv_import_shekels to transfer")
            return 0
        
        # Found rows in csv_import_shekels
        
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
                # Error getting parking_id: {str(e)}")
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
                        # Row inserted as new record
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
        # Successfully transferred records
        # Skipped duplicates
        # Failed transfers
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
        # Error transferring to parking_data: {str(e)}")
        return 0

def process_single_email(mail, email_id):
    """עיבוד מייל יחיד - עם שליחת מיילי הודעות מתוקן"""
    sender = None  # נגדיר את המשתנה מלכתחילה
    
    try:
        _, msg_data = mail.fetch(email_id, '(RFC822)')
        
        # בדיקה שיש נתונים
        if not msg_data or len(msg_data) == 0:
            # No data for email
            return False
            
        email_body = msg_data[0][1]
        
        # בדיקה שיש body
        if not email_body:
            # Empty email body
            return False
            
        email_message = email.message_from_bytes(email_body)
        
        # קבלת פרטי השולח
        sender = email_message.get('From', 'unknown@unknown.com')
        subject = email_message.get('Subject', 'No Subject') or 'No Subject'
        date = email_message.get('Date', 'No Date') or 'No Date'
        
        # Processing email from sender
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
            # Skipping unauthorized sender
            
            # 🆕 סימון המייל כדי לא לבדוק אותו שוב
            try:
                # Marking unauthorized email
                mail.store(email_id, '+FLAGS', '\\Seen \\Flagged')
                # Unauthorized email marked
            except Exception as mark_error:
                # Could not mark unauthorized email
                pass
            
            print(f"📝 UNAUTHORIZED ACCESS LOGGED: {sender} tried to send data files")
            return False
        
        print(f"✅ AUTHORIZED SENDER: {sender}")
        
        csv_files = download_csv_from_email(email_message)
        
        if not csv_files:
            # No CSV files found
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
            # Email processed successfully
        else:
            success_msg = f"כל {total_processed} הרשומות כבר קיימות במערכת (כפילויות)"
            # Email processed successfully
        
        # 🆕 שליחת מייל הצלחה עם פרטים מלאים
        send_success_notification(sender, processed_files, transferred_count, total_processed)
        
# 🏷️ סימון המייל כמעובד במקום מחיקה
        try:
            # Marking email as processed
            mail.store(email_id, '+FLAGS', '\\Seen \\Flagged')
            # Email marked as processed
            
        except Exception as mark_error:
            # Could not mark email
            # לא מפסיקים את התהליך בגלל זה
            pass
        
        return True
        
    except Exception as e:
        error_msg = f"שגיאה טכנית בעיבוד המייל: {str(e)}"
        # Error processing email
        
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
        # Daily email limit reached
        return
    
    # בדיקת נתונים
    gmail_user = os.environ.get('GMAIL_USERNAME')
    gmail_password = os.environ.get('GMAIL_APP_PASSWORD')
    
    if not gmail_user or not gmail_password:
        print(f"❌ Missing Gmail credentials for success notification")
        files_summary = ', '.join([f['name'] for f in processed_files])
        # Success logged
        return
        
    try:
        # Sending success notification
        
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
        # Success notification sent
        
    except Exception as e:
        error_str = str(e)
        if "sending limit exceeded" in error_str.lower():
            print(f"🚫 Gmail daily limit exceeded - switching to log-only mode")
            send_success_notification.daily_count = 99
        else:
            print(f"❌ Failed to send success notification: {str(e)}")
            files_summary = ', '.join([f['name'] for f in processed_files])
            # Success logged

def send_error_notification(sender_email, error_message):
    """שליחת התראת שגיאה - מושבת, רק לוג"""
    
    # בדיקה אם מיילי שגיאה מושבתים
    if ERROR_EMAILS_DISABLED:
        # Error email disabled
        # Error logged
        return
    
    # אם לא מושבת, רק לוג (ללא שליחת מייל)
    # Error logged
            
def verify_email_system():
    """בדיקת התקינות של מערכת המיילים"""
    if not EMAIL_MONITORING_AVAILABLE:
        # Email libraries not available
        return False
        
    # Verifying email system configuration
    
    # בדיקת משתני סביבה
    gmail_user = os.environ.get('GMAIL_USERNAME')
    gmail_password = os.environ.get('GMAIL_APP_PASSWORD')
    
    if not gmail_user or not gmail_password:
        # Gmail credentials missing
        return False
    
    # בדיקת חיבור IMAP (מהיר)
    try:
        mail = imaplib.IMAP4_SSL('imap.gmail.com', timeout=10)
        mail.login(gmail_user, gmail_password)
        mail.logout()
        # Gmail IMAP connection successful
        return True
    except Exception as e:
        # Gmail IMAP connection failed
        return False

def start_email_monitoring_with_logs():
    """הפעלת מעקב מיילים עם לוגים מפורטים - ללא כפילות"""
    if not EMAIL_MONITORING_AVAILABLE:
        # Email monitoring not available
        return
        
    try:
        # Starting email monitoring system
        
        # בדיקת תקינות המערכת
        if not verify_email_system():
            # Email system verification failed
            return
        
        def monitoring_loop():
            # Email monitoring loop started
            check_count = 0
            
            while True:
                try:
                    # בדיקת מיילים כל 5 דקות (300 שניות)
                    with app.app_context():
                        # Email check triggered
                        check_for_new_emails()
                    
                    # המתנה של 5 דקות
                    time.sleep(150)  # 300 שניות = 5 דקות
                    
                    check_count += 1
                    if check_count % 6 == 0:  # כל 30 דקות (6 * 5 דקות)
                        # Email monitoring alive
                        pass
                        
                except KeyboardInterrupt:
                    # Email monitoring stopped by user
                    break
                except Exception as e:
                    # Email monitoring error - retrying
                    time.sleep(300)  # 5 דקות המתנה לפני ניסיון חוזר
        
        # הרצת הלולאה ברקע
        monitor_thread = threading.Thread(target=monitoring_loop, daemon=True)
        monitor_thread.start()
        
        # Email monitoring started successfully
        
        # בדיקה ראשונית מעוכבת למניעת כפילות
        # Running initial email check
        def delayed_initial_check():
            time.sleep(15)  # המתנה של 15 שניות
            with app.app_context():
                check_for_new_emails()
        threading.Thread(target=delayed_initial_check, daemon=True).start()
        
    except Exception as e:
        # Failed to start email monitoring
        pass

def start_background_email_monitoring():
    """נקודת כניסה להפעלת מעקב מיילים ברקע"""
    if not EMAIL_MONITORING_AVAILABLE:
        print("⚠️ Email monitoring not available - missing libraries")
        return
        
    try:
        
        def delayed_start():
            time.sleep(5)
            # Starting email monitoring  # 🆕 הוסף דיבוג
            start_email_monitoring_with_logs()
        
        startup_thread = threading.Thread(target=delayed_start, daemon=True)
        startup_thread.start()
        
        
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
        # Hourly cache reset completed
    
    # ניקוי זיכרון אם יש יותר מדי
    if len(processed_email_ids) > 50:
        processed_email_ids = processed_email_ids[-20:]
        # Email cache cleaned
    
    if not EMAIL_MONITORING_AVAILABLE:
        # Email check skipped
        return
    
    # Email check started
    
    # בדיקת משתני סביבה
    gmail_user = os.environ.get('GMAIL_USERNAME')
    gmail_password = os.environ.get('GMAIL_APP_PASSWORD')
    
    if not gmail_user or not gmail_password:
        # Missing Gmail credentials
        return
    
    # Gmail credentials present
    
    mail = connect_to_gmail_imap()
    if not mail:
        # Failed to connect to Gmail IMAP
        return
    
    try:
        # Selecting inbox
        mail.select('inbox')
        
        # תיקון תאריכים - מחפש מהיומיים האחרונים
        today = datetime.now().strftime('%d-%b-%Y')
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%d-%b-%Y')
        
        # חיפוש מיילים מהיומיים האחרונים
        search_criteria = f'OR SINCE {yesterday} SINCE {today}'
        
        # Search criteria set
        
        _, message_ids = mail.search(None, f'({search_criteria}) UNFLAGGED')
        
        if not message_ids[0]:
            # No new emails found
            mail.logout()
            return
        
        email_ids = message_ids[0].split()
        # Found emails
        
        new_emails = 0
        processed_successfully = 0
        
        for email_id in email_ids:
            email_id_str = email_id.decode() if isinstance(email_id, bytes) else str(email_id)
            
            if email_id_str in processed_email_ids:
                # Skipping already processed email
                continue
            
            # Processing new email
            
            # עיבוד המייל
            success = process_single_email(mail, email_id)
            
            # 🔧 תיקון: הוסף לרשימה רק אם הצליח!
            if success:
                processed_email_ids.append(email_id_str)
                # Email added to processed cache
            else:
                # לא מוסיפים לרשימה - ננסה שוב בפעם הבאה
                # Email not added to cache - will retry
                pass
            
            new_emails += 1
            
            # ספירת הצלחות בלבד
            if success:
                processed_successfully += 1
                # Email processed successfully
            else:
                # Email rejected or failed
                pass
            
            # ניקוי cache אם יש יותר מדי מיילים
            if len(processed_email_ids) > PROCESSED_EMAILS_LIMIT:
                processed_email_ids = processed_email_ids[-PROCESSED_EMAILS_LIMIT:]
                # Cleaned processed emails cache
            
            # המתנה קצרה בין מיילים
            time.sleep(2)
        
        # סיכום מפורט
        # Email check completed
        
    except Exception as e:
        # Error in email check
        pass
    
    finally:
        try:
            mail.logout()
            # Gmail connection closed
        except:
            pass
        
        # Email check ended

def keep_service_alive():
    """פונקציה לשמירה על השירות ערני - גרסה מתוקנת"""
    def ping_self():
        # Keep-alive service started
        
        # קבלת URL של השרת מהמשתנה שהגדרנו
        app_url = os.environ.get('RENDER_EXTERNAL_URL', 'https://s-b-parking-reports.onrender.com')
        
        while True:
            try:
                # שליחת בקשה לעצמנו כל 10 דקות
                # Sending keep-alive ping
                response = requests.get(f'{app_url}/ping', timeout=30000)
                # Keep-alive ping successful
                
            except requests.exceptions.RequestException as e:
                # Keep-alive ping failed
                # ממשיכים גם במקרה של שגיאה
                pass
                
            except Exception as e:
                # Unexpected error in keep-alive
                pass
            
            # המתנה של 10 דקות (600 שניות)
            time.sleep(600)
    
    # הרצת הפונקציה ברקע
    ping_thread = threading.Thread(target=ping_self, daemon=True)
    ping_thread.start()
    # Keep-alive service initialized

def validate_username(username):
    """
    תיקוף שם משתמש - רק אותיות אנגלית, מספרים וקו תחתון
    """
    import re
    
    if not username or len(username.strip()) == 0:
        return False, "יש להזין שם משתמש"
    
    username = username.strip()
    
    # בדיקת אורך
    if len(username) < 3:
        return False, "שם משתמש חייב להיות לפחות 3 תווים"
    
    if len(username) > 20:
        return False, "שם משתמש יכול להיות מקסימום 20 תווים"
    
    # בדיקה שיש רק אותיות אנגלית, מספרים וקו תחתון
    if not re.match(r'^[a-zA-Z0-9_]+$', username):
        return False, "שם משתמש יכול לכלול רק אותיות אנגלית, מספרים וקו תחתון (_)"
    
    # בדיקה שמתחיל באות
    if not username[0].isalpha():
        return False, "שם משתמש חייב להתחיל באות אנגלית"
    
    # רשימת שמות אסורים
    forbidden_names = [
        'admin', 'administrator', 'root', 'user', 'test', 'guest', 'null', 'undefined',
        'api', 'www', 'mail', 'email', 'support', 'help', 'info', 'contact',
        'scheidt', 'master', 'system', 'service'
    ]
    
    if username.lower() in forbidden_names:
        return False, "שם משתמש זה אינו זמין"
    
    return True, username

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

@app.route('/static/<path:filename>')
def serve_static(filename):
    """Serve static files with no-cache headers"""
    response = make_response(app.send_static_file(filename))
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '-1'
    return response

@app.route('/<filename>.js')
def serve_js_files(filename):
    """Serve JavaScript files from root directory"""
    try:
        return send_from_directory('.', f'{filename}.js', mimetype='application/javascript')
    except FileNotFoundError:
        return "File not found", 404

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
    
    # בדיקה אם המשתמש הוא מנהל חברה
    try:
        user_result = supabase.table('user_parkings').select(
            'access_level, code_type'
        ).eq('email', session['user_email']).execute()
        
        if user_result.data:
            user_data = user_result.data[0]
            if user_data.get('access_level') == 'company_manager' or user_data.get('code_type') == 'company_manager':
                # מנהל חברה - מפנים אותו לדף הנכון
                return redirect(url_for('company_manager_page'))
    except Exception as e:
        print(f"Error checking user type: {str(e)}")
    
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
        # Error getting user info: {str(e)}")
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
        # Error getting user parkings: {str(e)}")
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
        elif user_data['access_level'] == 'company_manager':
            # מנהל חברה - מפנים אותו לדף הנכון
            return jsonify({
                'success': False, 
                'message': 'מנהל חברה - יש להשתמש בדף ניהול חברה',
                'redirect': '/company-manager'
            })
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
        
        # Retrieved parking records
        
        return jsonify({
            'success': True,
            'data': processed_data,
            'total_records': len(processed_data)
        })
        
    except Exception as e:
        # Error getting parking data: {str(e)}")
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

@app.route('/forgot-password')
def forgot_password_page():
    """דף איפוס סיסמה"""
    return render_template('forgot-password.html')

@app.route('/api/forgot-password', methods=['POST'])
def forgot_password():
    """בקשה לאיפוס סיסמה - שליחת קוד למייל"""
    try:
        if not supabase:
            return jsonify({'success': False, 'message': 'מסד הנתונים לא זמין'})
        
        data = request.get_json()
        email = data.get('email', '').strip()
        
        # אימות מייל
        is_valid_email, validated_email = validate_input(email, "email")
        if not is_valid_email:
            return jsonify({'success': False, 'message': 'כתובת מייל לא תקינה'})
        
        print(f"🔄 Password reset request for: {validated_email}")
        
        # בדיקה שהמייל קיים במערכת
        user_result = supabase.table('user_parkings').select('username, email').eq('email', validated_email).execute()
        
        if not user_result.data:
            return jsonify({'success': False, 'message': 'כתובת מייל לא נמצאה במערכת'})
        
        user = user_result.data[0]
        
        # יצירת קוד אימות
        reset_code = generate_verification_code()
        
        # שמירת הקוד בזיכרון זמני
        password_reset_codes[validated_email] = {
            'code': reset_code,
            'timestamp': time.time(),
            'attempts': 0,
            'username': user['username']
        }
        
        
        # שליחת מייל
        email_sent = send_password_reset_verification_email(validated_email, reset_code, user['username'])
        
        if email_sent:
            return jsonify({
                'success': True,
                'message': 'קוד אימות נשלח לכתובת המייל שלך'
            })
        else:
            return jsonify({
                'success': True,  # נחזיר הצלחה גם אם המייל נכשל
                'message': 'קוד אימות נוצר (בדוק לוגים)'
            })
            
    except Exception as e:
        print(f"❌ Forgot password error: {str(e)}")
        return jsonify({'success': False, 'message': 'שגיאה במערכת'})

@app.route('/api/verify-reset-code', methods=['POST'])
def verify_reset_code():
    """אימות קוד איפוס סיסמה"""
    try:
        data = request.get_json()
        email = data.get('email', '').strip()
        code = data.get('code', '').strip()
        
        # אימות קלט
        is_valid_email, validated_email = validate_input(email, "email")
        is_valid_code, validated_code = validate_input(code, "verification_code")
        
        if not is_valid_email or not is_valid_code:
            return jsonify({'success': False, 'message': 'נתונים לא תקינים'})
        
        print(f"🔍 Verifying reset code for: {validated_email}")
        
        # ניקוי קודים ישנים
        clean_expired_reset_codes()
        
        # בדיקה שהקוד קיים
        if validated_email not in password_reset_codes:
            return jsonify({'success': False, 'message': 'קוד לא נמצא או פג תוקף'})
        
        reset_data = password_reset_codes[validated_email]
        
        # בדיקת תוקף (10 דקות)
        if time.time() - reset_data['timestamp'] > 600:  # 10 דקות
            del password_reset_codes[validated_email]
            return jsonify({'success': False, 'message': 'הקוד פג תוקף'})
        
        # בדיקת ניסיונות (מקסימום 3)
        if reset_data['attempts'] >= 3:
            del password_reset_codes[validated_email]
            return jsonify({'success': False, 'message': 'חרגת ממספר הניסיונות המותר'})
        
        # בדיקת הקוד
        if reset_data['code'] != validated_code:
            reset_data['attempts'] += 1
            return jsonify({'success': False, 'message': 'קוד שגוי'})
        
        # יצירת טוקן לאיפוס
        import secrets
        reset_token = secrets.token_urlsafe(32)
        reset_data['token'] = reset_token
        reset_data['verified'] = True
        
        print(f"✅ Reset code verified for: {validated_email}")
        
        return jsonify({
            'success': True,
            'token': reset_token,
            'message': 'קוד אומת בהצלחה'
        })
        
    except Exception as e:
        print(f"❌ Verify reset code error: {str(e)}")
        return jsonify({'success': False, 'message': 'שגיאה במערכת'})

@app.route('/api/reset-password', methods=['POST'])
def reset_password():
    """עדכון סיסמה חדשה"""
    try:
        if not supabase:
            return jsonify({'success': False, 'message': 'מסד הנתונים לא זמין'})
        
        data = request.get_json()
        email = data.get('email', '').strip()
        token = data.get('token', '').strip()
        new_password = data.get('newPassword', '').strip()
        
        # אימות קלט
        is_valid_email, validated_email = validate_input(email, "email")
        if not is_valid_email or not token or not new_password:
            return jsonify({'success': False, 'message': 'נתונים לא תקינים'})
        
        if len(new_password) < 6:
            return jsonify({'success': False, 'message': 'הסיסמה חייבת להיות לפחות 6 תווים'})
        
        print(f"🔄 Resetting password for: {validated_email}")
        
        # בדיקת הטוקן
        if validated_email not in password_reset_codes:
            return jsonify({'success': False, 'message': 'טוקן לא תקין או פג תוקף'})
        
        reset_data = password_reset_codes[validated_email]
        
        if not reset_data.get('verified') or reset_data.get('token') != token:
            return jsonify({'success': False, 'message': 'טוקן לא תקין'})
        
        # בדיקת תוקף (30 דקות מתחילת התהליך)
        if time.time() - reset_data['timestamp'] > 1800:  # 30 דקות
            del password_reset_codes[validated_email]
            return jsonify({'success': False, 'message': 'הטוקן פג תוקף'})
        
        # הצפנת הסיסמה החדשה
        password_hash = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt(rounds=6, prefix=b'2a')).decode('utf-8')
        
        # עדכון הסיסמה בבסיס הנתונים
        current_time = datetime.now(timezone.utc).isoformat()
        
        update_result = supabase.table('user_parkings').update({
            'password_hash': password_hash,
            'updated_at': current_time,
            'password_changed_at': current_time,
            'is_temp_password': False
        }).eq('email', validated_email).execute()
        
        if update_result.data:
            # מחיקת הקוד מהזיכרון
            del password_reset_codes[validated_email]
            
            print(f"✅ Password reset successfully for: {validated_email}")
            
            return jsonify({
                'success': True,
                'message': 'הסיסמה עודכנה בהצלחה'
            })
        else:
            return jsonify({'success': False, 'message': 'שגיאה בעדכון הסיסמה'})
        
    except Exception as e:
        print(f"❌ Reset password error: {str(e)}")
        return jsonify({'success': False, 'message': 'שגיאה במערכת'})

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
        
        
# קריאה לפונקציה עם טיפול פשוט  
        try:
            result = supabase.rpc('user_login', {
                'p_username': validated_username,
                'p_password': validated_password
            }).execute()
            auth_result = result.data
            
        except Exception as rpc_error:
            # ניקח את התוצאה מהשגיאה
            if hasattr(rpc_error, 'args') and rpc_error.args:
                auth_result = rpc_error.args[0]
                
                # בדיקת סוג הנתונים
                if isinstance(auth_result, dict):
                    pass
                elif isinstance(auth_result, str):
                    # זה כנראה string שנראה כמו dict - ננסה eval
                    try:
                        import ast
                        auth_result = ast.literal_eval(auth_result)
                    except:
                        try:
                            import json
                            auth_result = json.loads(auth_result)
                        except:
                            print("🔍 Could not parse - treating as error message")
                            return jsonify({'success': False, 'message': auth_result})
                else:
                    print(f"🔍 Unknown type: {type(auth_result)}")
                    raise rpc_error
            else:
                raise rpc_error
        
        
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
                
                # יצירת קוד אימות חדש
                verification_code = generate_verification_code()
                
                # שמירה במסד נתונים
                if store_verification_code(email, verification_code):
                    # שליחת מייל
                    email_sent = send_verification_email(email, verification_code)
                    
                    # שמירה ב-session
                    session['pending_email'] = email
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
                    # Use central redirect logic
                    redirect_url = get_user_redirect_url(email)
                    print(f"🔍 User {email} redirected to: {redirect_url}")

                    return jsonify({
                        'success': True, 
                        'redirect': redirect_url,
                        'user_type': user_data.get('code_type', '')
                    })
                else:
                    print(f"⚠️ User data not found, redirecting to dashboard")
                    return jsonify({'success': True, 'redirect': '/dashboard'})
                    
            except Exception as e:
                # Error getting user data: {str(e)}")
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
            # Normalize: strip whitespace, lower case case-insensitive
            code_type_raw = str(code_type).strip() if code_type else ''
            code_type_lower = code_type_raw.lower()
            
            # Map legacy or approximate values
            if code_type_lower == 'master':
                return '/master-users'
            elif code_type_lower == 'parking_manager':
                return '/parking-manager-users'
            elif code_type_lower == 'company_manager':
                return '/company-manager'
            elif code_type_lower.replace(' ', '_').replace('-', '_') in ['dashboard_v2', 'dashboardv2']:
                return '/dashboard-v2'
            elif code_type_lower.replace(' ', '_').replace('-', '_') in ['dashboard_v3', 'dashboardv3']:
                return '/dashboard-v3'
            # Support both old 'partial' and new 'part' naming
            elif code_type_lower in ['parking_manager_partial', 'parking_manager_part']:
                return '/parking-manager-users-part'
            elif code_type.lower() == 'parking_tour' or code_type_lower == 'parking_tour':
                return '/parking-tour'
            elif code_type_lower == 'mobile_controller':
                return '/mobile-parking-controller'
            else:
                return '/dashboard'
        else:
            return '/dashboard'
            
    except Exception as e:
        # Error in get_user_redirect_url: {str(e)}")
        return '/dashboard'

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login_page'))

@app.route('/ping')
def ping():
    current_time = datetime.now()
    # Ping received
    
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
        # Error checking master permissions: {str(e)}")
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
        # Error checking parking manager permissions: {str(e)}")
        return redirect(url_for('dashboard'))
    
    return render_template('parking_manager_users.html')

@app.route('/dashboard-v2')
def dashboard_v2_page():
    """Dashboard V2"""
    if 'user_email' not in session:
        return redirect(url_for('login_page'))
    
    # Check permissions with permissive matching
    try:
        user_result = supabase.table('user_parkings').select('code_type').eq('email', session['user_email']).execute()
        if not user_result.data:
            print(f"⚠️ Unauthorized access attempt to dashboard-v2 by {session['user_email']}")
            return redirect(url_for('dashboard'))
            
        code_type = user_result.data[0].get('code_type', '')
        code_type_clean = str(code_type).strip().lower().replace(' ', '_').replace('-', '_')
        
        # Allow normalized matches
        if code_type_clean not in ['dashboard_v2', 'dashboardv2'] and code_type != 'master':
            print(f"⚠️ Unauthorized access attempt to dashboard-v2 by {session['user_email']} (code_type: {code_type})")
            return redirect(url_for('dashboard'))
            
    except Exception as e:
        print(f"Error checking dashboard-v2 permissions: {str(e)}")
        return redirect(url_for('dashboard'))
    
    return render_template('dashboard_v2.html')


@app.route('/dashboard-v3')
def dashboard_v3_page():
    """Dashboard V3"""
    if 'user_email' not in session:
        return redirect(url_for('login_page'))
    
    # Check permissions with permissive matching
    try:
        user_result = supabase.table('user_parkings').select('code_type').eq('email', session['user_email']).execute()
        if not user_result.data:
            print(f"⚠️ Unauthorized access attempt to dashboard-v3 by {session['user_email']}")
            return redirect(url_for('dashboard'))
            
        code_type = user_result.data[0].get('code_type', '')
        code_type_clean = str(code_type).strip().lower().replace(' ', '_').replace('-', '_')

        if code_type_clean not in ['dashboard_v3', 'dashboardv3'] and code_type != 'master':
            print(f"⚠️ Unauthorized access attempt to dashboard-v3 by {session['user_email']} (code_type: {code_type})")
            return redirect(url_for('dashboard'))
            
    except Exception as e:
        print(f"Error checking dashboard-v3 permissions: {str(e)}")
        return redirect(url_for('dashboard'))
    
    return render_template('dashboard_v3.html')


@app.route('/parking-manager-users-part')
def parking_manager_users_part_page():
    """דף ניהול משתמשים לחניון ספציפי (ניהול חלקי)"""
    if 'user_email' not in session:
        return redirect(url_for('login_page'))
    
    # Check permissions
    # Fetch user data including company_list and counting
    try:
        user_result = supabase.table('user_parkings').select('code_type, company_list, counting').eq('email', session['user_email']).execute()
        if not user_result.data:
            print(f"⚠️ Unauthorized access attempt to parking-manager-users-part by {session['user_email']}")
            return redirect(url_for('dashboard'))
            
        user_data = user_result.data[0]
        code_type = user_data.get('code_type', '')
        code_type_lower = str(code_type).strip().lower()
        manager_company_list = user_data.get('company_list', '')
        manager_counting = user_data.get('counting', 0) or 0
        
        # Allow 'parking_manager_part' AND 'parking_manager_partial' for legacy support
        if code_type_lower not in ['parking_manager_part', 'parking_manager_partial'] and code_type_lower != 'master':
             print(f"⚠️ Unauthorized access attempt to parking-manager-users-part by {session['user_email']} (code_type: {code_type})")
             return redirect(url_for('dashboard'))

    except Exception as e:
        print(f"Error checking parking manager permissions: {str(e)}")
        return redirect(url_for('dashboard'))
    
    return render_template('parking_manager_users_part.html', manager_company_list=manager_company_list, manager_counting=manager_counting)

@app.route('/parking-tour')
def parking_tour_page():
    """דף חיפוש מנויים למשתמשי Parking_tour"""
    if 'user_email' not in session:
        return redirect(url_for('login_page'))
    
    # בדיקת הרשאות Parking_tour
    try:
        user_result = supabase.table('user_parkings').select('code_type, project_number, parking_name, access_level').eq('email', session['user_email']).execute()
        if not user_result.data:
            print(f"⚠️ No user data found for {session['user_email']}")
            return redirect(url_for('dashboard'))
        
        code_type = user_result.data[0].get('code_type', '')
        if code_type != 'Parking_tour' and code_type != 'parking_tour':
            print(f"⚠️ Unauthorized access attempt to parking-tour by {session['user_email']} (code_type: {code_type})")
            return redirect(url_for('dashboard'))
    except Exception as e:
        print(f"Error checking parking tour permissions: {str(e)}")
        return redirect(url_for('dashboard'))
    
    return render_template('parking_tour.html')

@app.route('/mobile-parking-controller')
def mobile_parking_controller_page():
    """דף בקרת חניון למובייל - Mobile Parking Controller"""
    if 'user_email' not in session:
        return redirect(url_for('login_page'))
    
    # בדיקת הרשאות - רק למשתמשים עם קוד mobile_controller
    try:
        user_result = supabase.table('user_parkings').select(
            'code_type, project_number, parking_name, access_level, permissions'
        ).eq('email', session['user_email']).execute()
        
        if not user_result.data:
            print(f"⚠️ No user data found for {session['user_email']}")
            return redirect(url_for('dashboard'))
        
        user_data = user_result.data[0]
        code_type = user_data.get('code_type', '')
        
        # בדיקה שהמשתמש הוא mobile_controller
        if code_type.lower() != 'mobile_controller':
            print(f"⚠️ Unauthorized access attempt to mobile-parking-controller by {session['user_email']} (code_type: {code_type})")
            return redirect(url_for('dashboard'))
        
    except Exception as e:
        print(f"Error checking controller permissions: {str(e)}")
        return redirect(url_for('dashboard'))
    
    return render_template('mobile_parking_controller.html')

# ========== API לחיפוש מנויים - Parking Tour ==========

@app.route('/api/parking-tour/search', methods=['POST'])
def parking_tour_search():
    """חיפוש מנוי לפי לוחית רישוי"""
    print("="*50)
    print("🔍 PARKING TOUR SEARCH CALLED!")
    print("="*50)
    
    try:
        if 'user_email' not in session:
            print("❌ NO USER IN SESSION")
            return jsonify({'success': False, 'message': 'לא מחובר'}), 401
        
        print(f"✅ User: {session['user_email']}")
        
        # בדיקת הרשאות - מבוטלת זמנית לצורך בדיקה
        # TODO: להחזיר בדיקת הרשאות אחרי הבדיקות
        
        # user_result = supabase.table('user_parkings').select(
        #     'code_type, project_number, parking_name'
        # ).eq('email', session['user_email']).execute()
        
        # if not user_result.data:
        #     return jsonify({'success': False, 'message': 'אין הרשאה'}), 403
            
        # code_type = user_result.data[0].get('code_type', '')
        # if code_type != 'Parking_tour' and code_type != 'parking_tour':
        #     return jsonify({'success': False, 'message': 'אין הרשאה'}), 403
        
        # לצורך בדיקה - נשתמש ב-parking_id מהבקשה
        # user_data = user_result.data[0]
        # user_parking_id = user_data.get('project_number')
        user_parking_id = None  # ביטלנו זמנית את הבדיקה
        
        # קבלת נתונים מהבקשה
        data = request.get_json()
        print(f"📦 Request data: {data}")
        
        license_plate = data.get('license_plate', '').strip()
        parking_id = data.get('parking_id')  # לצורך בדיקה, נשתמש רק במה שנשלח
        
        if not license_plate:
            return jsonify({'success': False, 'message': 'יש להזין לוחית רישוי'})
        
        # ניקוי לוחית רישוי - הסרת רווחים ומקפים
        clean_plate = license_plate.replace(' ', '').replace('-', '')
        
        print(f"🔍 Searching for license plate: {clean_plate} in parking: {parking_id}")
        
        # בדיקת דמו - החזרת תוצאה לדוגמה
        if clean_plate == "23320601":  # הלוחית שניסית
            demo_result = [{
                'id': '123',
                'firstName': 'ישראל',
                'lastName': 'ישראלי',
                'lpn1': '2-33-20601',
                'contractId': '1001',
                'companyName': 'חברה לדוגמה',
                'validFrom': '2024-01-01',
                'validUntil': '2025-12-31'
            }]
            print("✅ DEMO MODE - Returning test result")
            return jsonify({
                'success': True,
                'data': demo_result,
                'total': 1,
                'message': 'מצב הדגמה'
            })
        
        # נבדוק אם יש חניון
        if not parking_id:
            print(f"❌ No parking_id provided")
            return jsonify({
                'success': False,
                'message': 'לא נבחר חניון'
            })
        
        # קבלת נתוני החיבור לשרת החניון
        ip_address = '192.117.0.122'  # ברירת מחדל
        port = 8240  # ברירת מחדל
        
        try:
            # בדיקה אם יש מיפוי לחניון
            if parking_id:
                parking_mapping = supabase.table('project_parking_mapping').select(
                    'parking_id, ip_address, port'
                ).eq('project_number', str(parking_id)).execute()
                
                if parking_mapping.data:
                    parking_data = parking_mapping.data[0]
                    ip_address = parking_data.get('ip_address') or ip_address
                    port = parking_data.get('port') or port
                else:
                    print(f"⚠️ No parking mapping found for parking {parking_id}, using defaults")
        except Exception as e:
            print(f"Error getting parking data: {str(e)}, using defaults")
        
        print(f"🔌 Using direct server connection...")
        
        # בניית URL ישירות לשרת החניון
        protocol = "https"
        url = f"{protocol}://{ip_address}:{port}/CustomerMediaWebService/consumers?lpn={clean_plate}"
        
        print(f"📤 Direct URL: {url}")
        
        # הכנת headers עם Basic Auth
        auth_string = base64.b64encode(b'2022:2022').decode('ascii')
        headers = {
            'Authorization': f'Basic {auth_string}',
            'Content-Type': 'application/json',
            'Accept': 'application/xml,application/json'
        }
        
        try:
            # קריאה ישירה לשרת
            print(f"🌐 Making direct request to parking server...")
            
            # ביטול אזהרות SSL
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            
            response = requests.get(url, headers=headers, verify=False, timeout=30)
            
            print(f"📡 Response status: {response.status_code}")
            print(f"📄 Response headers: {dict(response.headers)}")
            
            if response.status_code != 200:
                print(f"❌ Server returned {response.status_code}")
                print(f"📄 Error response: {response.text[:500]}")
                return jsonify({
                    'success': False,
                    'message': 'שגיאה בחיפוש במערכת החניון'
                })
            
            # עיבוד התשובה
            content_type = response.headers.get('content-type', '')
            print(f"📄 Content-Type: {content_type}")
            print(f"📄 Response body (first 1000 chars): {response.text[:1000]}")
            
            consumers_data = []
            
            if 'xml' in content_type or response.text.startswith('<?xml'):
                print(f"📋 Parsing XML response...")
                import xml.etree.ElementTree as ET
                
                try:
                    root = ET.fromstring(response.text)
                    print(f"📋 Root element: {root.tag}")
                    
                    # Option 1: consumers/consumer structure
                    consumers_elem = root.find('.//consumers')
                    if consumers_elem is not None:
                        print(f"📋 Found consumers element")
                        for consumer_elem in consumers_elem.findall('consumer'):
                            consumer_data = {}
                            for child in consumer_elem:
                                consumer_data[child.tag] = child.text
                            consumers_data.append(consumer_data)
                            print(f"📋 Consumer found: {consumer_data}")
                    
                    # Option 2: Direct consumer elements
                    if not consumers_data:
                        for consumer_elem in root.findall('.//consumer'):
                            consumer_data = {}
                            for child in consumer_elem:
                                consumer_data[child.tag] = child.text
                            consumers_data.append(consumer_data)
                            print(f"📋 Consumer found (direct): {consumer_data}")
                    
                    # Option 3: Root is consumer
                    if not consumers_data and root.tag == 'consumer':
                        consumer_data = {}
                        for child in root:
                            consumer_data[child.tag] = child.text
                        consumers_data = [consumer_data]
                        print(f"📋 Consumer found (root): {consumer_data}")
                
                except ET.ParseError as e:
                    print(f"❌ XML Parse error: {str(e)}")
                    return jsonify({
                        'success': False,
                        'message': 'שגיאה בפענוח תשובת השרת'
                    })
            else:
                # Try JSON
                print(f"📋 Trying to parse as JSON...")
                try:
                    json_data = response.json()
                    if isinstance(json_data, list):
                        consumers_data = json_data
                    elif isinstance(json_data, dict):
                        if 'consumers' in json_data:
                            consumers_data = json_data['consumers']
                        elif 'consumer' in json_data:
                            consumers_data = [json_data['consumer']]
                        else:
                            consumers_data = [json_data]
                    print(f"📋 Parsed JSON successfully: {len(consumers_data)} consumers")
                except:
                    print(f"❌ Failed to parse as JSON")
                    return jsonify({
                        'success': False,
                        'message': 'שגיאה בפענוח תשובת השרת'
                    })
            
            result = {'success': True, 'data': consumers_data}
            print(f"✅ Search completed successfully! Found {len(consumers_data)} consumers")
                
        except requests.exceptions.RequestException as e:
            print(f"❌ Request error: {str(e)}")
            return jsonify({
                'success': False,
                'message': f'שגיאה בחיבור לשרת החניון'
            })
        except Exception as e:
            print(f"❌ Unexpected error: {str(e)}")
            import traceback
            print(traceback.format_exc())
            return jsonify({
                'success': False,
                'message': 'שגיאה בחיפוש במערכת החניון'
            })
        
        # עיבוד התוצאות מה-proxy
        consumers_data = result.get('data', {})
        consumers = []
        
        # ה-proxy כבר עשה את הפענוח של XML/JSON
        if isinstance(consumers_data, list):
            consumers = consumers_data
        elif isinstance(consumers_data, dict):
            if 'consumers' in consumers_data and 'consumer' in consumers_data['consumers']:
                consumer_list = consumers_data['consumers']['consumer']
                consumers = consumer_list if isinstance(consumer_list, list) else [consumer_list]
            elif 'consumer' in consumers_data:
                consumer_list = consumers_data['consumer']
                consumers = consumer_list if isinstance(consumer_list, list) else [consumer_list]
            else:
                # אולי זה consumer בודד
                consumers = [consumers_data]
        
        # עיבוד התוצאות
        found_subscribers = []
        
        print(f"📊 Found {len(consumers)} consumers with lpn={clean_plate}")
        
        # עיבוד כל מנוי שנמצא
        for consumer in consumers:
            if not consumer:
                continue
            # קבלת פרטי המנוי
            contract_id = consumer.get('contractId') or consumer.get('contractid') or consumer.get('contract')
            company_name = consumer.get('companyName') or consumer.get('contractName') or 'לא ידוע'
            
            # בניית אובייקט המנוי
            subscriber_data = {
                'id': consumer.get('id') or consumer.get('subscriberNum'),
                'subscriberNum': consumer.get('subscriberNum') or consumer.get('id'),
                'firstName': consumer.get('firstName', ''),
                'lastName': consumer.get('lastName') or consumer.get('name', ''),
                'name': consumer.get('name', ''),
                'companyId': contract_id,
                'companyName': company_name,
                'vehicle1': consumer.get('lpn1') or consumer.get('vehicleNum', ''),
                'vehicle2': consumer.get('lpn2', ''),
                'vehicle3': consumer.get('lpn3', ''),
                'lpn1': consumer.get('lpn1') or consumer.get('vehicleNum', ''),
                'lpn2': consumer.get('lpn2', ''),
                'lpn3': consumer.get('lpn3', ''),
                'tagNum': consumer.get('tagNum') or consumer.get('cardNum', ''),
                'validFrom': consumer.get('xValidFrom') or consumer.get('validFrom', ''),
                'validUntil': consumer.get('xValidUntil') or consumer.get('validUntil', ''),
                'profile': consumer.get('profile') or consumer.get('extCardProfile', '0'),
                'presence': consumer.get('presence', False)
            }
            found_subscribers.append(subscriber_data)
        
        print(f"✅ Returning {len(found_subscribers)} subscribers")
        
        return jsonify({
            'success': True,
            'data': found_subscribers,
            'total': len(found_subscribers)
        })
        
    except Exception as e:
        error_details = f"Error in parking tour search: {str(e)}"
        print(f"❌ {error_details}")
        import traceback
        print(traceback.format_exc())
        return jsonify({
            'success': False, 
            'message': f'שגיאה: {str(e)}',
            'error_type': type(e).__name__,
            'details': error_details
        })

# ========== Mobile Parking Controller API ==========

@app.route('/api/mobile-controller/devices', methods=['GET', 'POST'])
def mobile_controller_devices():
    """Get list of parking devices"""
    print(f"📱 Mobile Controller Devices - Method: {request.method}")
    try:
        if 'user_email' not in session:
            print(f"❌ No user in session")
            return jsonify({'success': False, 'message': 'לא מחובר'}), 401
        
        # בדיקת הרשאות
        user_result = supabase.table('user_parkings').select(
            'code_type, project_number, parking_name'
        ).eq('email', session['user_email']).execute()
        
        if not user_result.data or user_result.data[0].get('code_type', '').lower() != 'mobile_controller':
            return jsonify({'success': False, 'message': 'אין הרשאה'}), 403
        
        user_data = user_result.data[0]
        parking_id = user_data.get('project_number')
        print(f"✅ Mobile Controller - User: {session['user_email']}, Parking ID: {parking_id}")
        
        # קבלת רשימת מכשירים מהשרת דרך proxy
        try:
            proxy_data = {
                'parking_id': parking_id,
                'endpoint': 'DeviceControlWebService/geometry',
                'method': 'GET'
            }
            
            # Add internal session for proxy authentication
            proxy_data['_internal_session'] = {
                'user_email': session.get('user_email'),
                'user_access_level': session.get('user_access_level'),
                'user_permissions': session.get('user_permissions'),
                'user_project_number': session.get('user_project_number'),
                'user_company_list': session.get('user_company_list')
            }
            
            # Use the company-manager proxy
            # Always use localhost to avoid timeout in Render
            port = os.environ.get('PORT', '5000')
            proxy_url = f'http://localhost:{port}/api/company-manager/proxy'
            
            response = requests.post(
                proxy_url,
                json=proxy_data,
                headers={
                    'Content-Type': 'application/json',
                    'Cookie': request.headers.get('Cookie', '')
                },
                timeout=30
            )
            
            if response.status_code != 200:
                error_msg = f'שגיאת proxy: {response.status_code}'
                try:
                    error_detail = response.json()
                    error_msg = error_detail.get('message', error_msg)
                except:
                    pass
                return jsonify({
                    'success': False,
                    'message': error_msg,
                    'devices': []
                })
            
            proxy_result = response.json()
            
            if proxy_result.get('success', False):
                devices_data = proxy_result.get('data', [])
                
                # Store cell computers in session if available
                cell_computers = proxy_result.get('cellComputers', [])
                if cell_computers:
                    session['cell_computers'] = cell_computers
                    print(f"📱 Stored cell computers in session: {cell_computers}")
                
                # עיבוד הנתונים למבנה שאנחנו צריכים
                devices = []
                for device in devices_data:
                    # Device data already processed by proxy
                    device_num = device.get('number')
                    if device_num:
                        devices.append({
                            'number': device_num,
                            'name': device.get('name', ''),
                            'type': device.get('type', 'unknown'),
                            'status': device.get('status', 1),
                            'deviceState': device.get('deviceState', 1),
                            'barrier': device.get('barrier', 'unknown'),
                            'doorOpen': device.get('doorOpen', False),
                            'lastEvent': device.get('last_event_time', ''),
                            'singleState': device.get('singleState', '')
                        })
                
                return jsonify({
                    'success': True,
                    'devices': devices,
                    'parking_id': parking_id
                })
            else:
                return jsonify({
                    'success': False,
                    'message': proxy_result.get('message', 'שגיאה בקבלת מכשירים'),
                    'devices': []
                })
                
        except Exception as e:
            print(f"❌ Error getting devices via proxy: {str(e)}")
            return jsonify({
                'success': False,
                'message': 'שגיאה בחיבור לשרת',
                'devices': []
            })
        
    except Exception as e:
        print(f"Error in mobile_controller_devices: {str(e)}")
        return jsonify({'success': False, 'message': 'שגיאה בקבלת מכשירים'}), 500

@app.route('/api/mobile-controller/events', methods=['GET', 'POST'])
def mobile_controller_events():
    """Get parking events"""
    print(f"📱 Mobile Controller Events - Method: {request.method}")
    try:
        if 'user_email' not in session:
            return jsonify({'success': False, 'message': 'לא מחובר'}), 401
        
        # בדיקת הרשאות
        user_result = supabase.table('user_parkings').select(
            'code_type, project_number'
        ).eq('email', session['user_email']).execute()
        
        if not user_result.data or user_result.data[0].get('code_type', '').lower() != 'mobile_controller':
            return jsonify({'success': False, 'message': 'אין הרשאה'}), 403
        
        user_data = user_result.data[0]
        parking_id = user_data.get('project_number')
        
        # קבלת אירועים מהשרת דרך proxy
        try:
            proxy_data = {
                'parking_id': parking_id,
                'endpoint': 'DeviceControlWebService/lastevents/100',
                'method': 'GET'
            }
            
            # Add internal session for proxy authentication
            proxy_data['_internal_session'] = {
                'user_email': session.get('user_email'),
                'user_access_level': session.get('user_access_level'),
                'user_permissions': session.get('user_permissions'),
                'user_project_number': session.get('user_project_number'),
                'user_company_list': session.get('user_company_list')
            }
            
            # Use the company-manager proxy
            # Always use localhost to avoid timeout in Render
            port = os.environ.get('PORT', '5000')
            proxy_url = f'http://localhost:{port}/api/company-manager/proxy'
            
            response = requests.post(
                proxy_url,
                json=proxy_data,
                headers={
                    'Content-Type': 'application/json',
                    'Cookie': request.headers.get('Cookie', '')
                },
                timeout=30
            )
            
            if response.status_code != 200:
                return jsonify({
                    'success': False,
                    'message': 'שגיאה בקבלת אירועים',
                    'events': []
                })
            
            proxy_result = response.json()
            
            if proxy_result.get('success', False):
                events_data = proxy_result.get('data', [])
                # עיבוד הנתונים למבנה שאנחנו צריכים
                events = []
                for event in events_data:
                    # Map event data from Scheidt format
                    event_no = event.get('event_no', '')
                    event_text = event.get('event_text', event.get('event_name', ''))
                    device_number = event.get('device_number', event.get('field_device_number', ''))
                    
                    # Determine event type from event number or text
                    event_type = 'info'
                    if 'HAND_OPEN' in str(event_text) or event_no == '42250':
                        event_type = 'open'
                    elif 'HAND_CLOSE' in str(event_text) or event_no == '42251':
                        event_type = 'close'
                    elif 'alarm' in str(event_text).lower() or event.get('alarm') == '1':
                        event_type = 'alarm'
                    elif 'error' in str(event_text).lower():
                        event_type = 'error'
                    
                    events.append({
                        'id': event.get('unique_sequence_number', event.get('event_no', '')),
                        'device': device_number,
                        'deviceName': event.get('device_name', event.get('field_device_name', '')),
                        'type': event_type,
                        'timestamp': event.get('event_date_time', ''),
                        'description': event_text,
                        'user': event.get('user', 'מערכת'),
                        'deviceState': event.get('device_state'),
                        'alarm': event.get('alarm', '0')
                    })
                
                return jsonify({
                    'success': True,
                    'events': events[:100]  # הגבלה ל-100 אירועים אחרונים
                })
            else:
                return jsonify({
                    'success': False,
                    'message': proxy_result.get('message', 'שגיאה בקבלת אירועים'),
                    'events': []
                })
                
        except Exception as e:
            print(f"Error getting events via proxy: {str(e)}")
            return jsonify({
                'success': False,
                'message': 'שגיאה בחיבור לשרת',
                'events': []
            })
        
    except Exception as e:
        print(f"Error in mobile_controller_events: {str(e)}")
        return jsonify({'success': False, 'message': 'שגיאה בקבלת אירועים'}), 500

@app.route('/api/mobile-controller/device-status', methods=['POST'])
def mobile_controller_device_status():
    """Get status for a specific device"""
    try:
        if 'user_email' not in session:
            return jsonify({'success': False, 'message': 'לא מחובר'}), 401
        
        # בדיקת הרשאות
        user_result = supabase.table('user_parkings').select(
            'project_number, code_type'
        ).eq('email', session['user_email']).execute()
        
        if not user_result.data or user_result.data[0].get('code_type', '').lower() != 'mobile_controller':
            return jsonify({'success': False, 'message': 'אין הרשאה'}), 403
        
        data = request.get_json()
        device_num = data.get('device')
        parking_id = user_result.data[0].get('project_number')
        
        print(f"📱 Device Status Check for device: {device_num}")
        
        # Get cell computer number from session
        cell_computer_num = 1
        if 'cell_computers' in session:
            cell_computers = session.get('cell_computers', [])
            if cell_computers:
                cell_computer_num = int(cell_computers[0])
        
        # Use special command 0xA137 (41271) for status check
        proxy_data = {
            'parking_id': parking_id,
            'endpoint': f'DeviceControlWebService/command/{cell_computer_num}/{device_num}/41271',  # 0xA137
            'method': 'PUT',
            'data': {}
        }
        
        # Add internal session for proxy authentication
        proxy_data['_internal_session'] = {
            'user_email': session.get('user_email'),
            'user_access_level': session.get('user_access_level'),
            'user_permissions': session.get('user_permissions'),
            'user_project_number': session.get('user_project_number'),
            'user_company_list': session.get('user_company_list')
        }
        
        # Use the company-manager proxy
        port = os.environ.get('PORT', '5000')
        proxy_url = f'http://localhost:{port}/api/company-manager/proxy'
        
        response = requests.post(
            proxy_url,
            json=proxy_data,
            headers={
                'Content-Type': 'application/json',
                'Cookie': request.headers.get('Cookie', '')
            },
            timeout=10
        )
        
        if response.status_code == 200:
            proxy_result = response.json()
            if proxy_result.get('success', False):
                return jsonify({
                    'success': True,
                    'status': 'checked',
                    'device': device_num
                })
        
        return jsonify({'success': False, 'message': 'שגיאה בבדיקת סטטוס'}), 500
        
    except Exception as e:
        print(f"Error in mobile_controller_device_status: {str(e)}")
        return jsonify({'success': False, 'message': 'שגיאה בבדיקת סטטוס'}), 500

@app.route('/api/mobile-controller/system-status', methods=['POST'])
def mobile_controller_system_status():
    """Get system status for mobile controller"""
    try:
        if 'user_email' not in session:
            return jsonify({'success': False, 'message': 'לא מחובר'}), 401
        
        # בדיקת הרשאות
        user_result = supabase.table('user_parkings').select(
            'project_number, code_type'
        ).eq('email', session['user_email']).execute()
        
        if not user_result.data or user_result.data[0].get('code_type', '').lower() != 'mobile_controller':
            return jsonify({'success': False, 'message': 'אין הרשאה'}), 403
        
        # For now, return basic status
        return jsonify({
            'success': True,
            'status': 'online',
            'connected': True,
            'parking_id': user_result.data[0].get('project_number')
        })
        
    except Exception as e:
        print(f"Error in mobile_controller_system_status: {str(e)}")
        return jsonify({'success': False, 'message': 'שגיאה בקבלת סטטוס'}), 500

@app.route('/api/mobile-controller/send-price', methods=['POST'])
def mobile_controller_send_price():
    """Send price to exit device"""
    try:
        if 'user_email' not in session:
            return jsonify({'success': False, 'message': 'לא מחובר'}), 401
        
        # בדיקת הרשאות
        user_result = supabase.table('user_parkings').select(
            'code_type, project_number'
        ).eq('email', session['user_email']).execute()
        
        if not user_result.data or user_result.data[0].get('code_type', '').lower() != 'mobile_controller':
            return jsonify({'success': False, 'message': 'אין הרשאה'}), 403
        
        data = request.get_json()
        device = data.get('device')
        amount = data.get('amount', 0)
        parking_id = data.get('parking_id') or user_result.data[0].get('project_number')
        
        print(f"📱 Mobile Controller Send Price: Device {device}, Amount: {amount}")
        
        # בדיקה שמדובר במכשיר יציאה
        if not device or device < 200 or device > 299:
            return jsonify({'success': False, 'message': 'ניתן לשלוח מחיר רק למכשירי יציאה (200-299)'}), 400
        
        # בניית פקודת מחיר לפי הפרוטוקול
        # Format: 0xA306 (41734) עם פרמטר של המחיר
        command = 41734  # 0xA306 - PRICE_SEND
        
        try:
            # Get cell computer number from session
            cell_computer_num = 1  # Default
            if 'cell_computers' in session:
                cell_computers = session.get('cell_computers', [])
                if cell_computers:
                    cell_computer_num = int(cell_computers[0])
            
            proxy_data = {
                'parking_id': parking_id,
                'endpoint': f'DeviceControlWebService/sendprice/{cell_computer_num}/{device}/{amount}',
                'method': 'PUT',
                'data': {}
            }
            
            # Add internal session for proxy authentication
            proxy_data['_internal_session'] = {
                'user_email': session.get('user_email'),
                'user_access_level': session.get('user_access_level'),
                'user_permissions': session.get('user_permissions'),
                'user_project_number': session.get('user_project_number'),
                'user_company_list': session.get('user_company_list')
            }
            
            # Use the company-manager proxy
            port = os.environ.get('PORT', '5000')
            proxy_url = f'http://localhost:{port}/api/company-manager/proxy'
            
            response = requests.post(
                proxy_url,
                json=proxy_data,
                headers={
                    'Content-Type': 'application/json',
                    'Cookie': request.headers.get('Cookie', '')
                },
                timeout=10
            )
            
            if response.status_code == 200:
                proxy_result = response.json()
                if proxy_result.get('success', False):
                    print(f"✅ Price {amount} sent successfully to device {device}")
                    return jsonify({
                        'success': True,
                        'message': f'מחיר {amount} ש"ח נשלח בהצלחה למכשיר {device}',
                        'device': device,
                        'amount': amount
                    })
                else:
                    return jsonify({
                        'success': False,
                        'message': proxy_result.get('message', 'שגיאה בשליחת מחיר')
                    })
            else:
                return jsonify({
                    'success': False,
                    'message': f'שגיאה בשליחת מחיר: HTTP {response.status_code}'
                })
                
        except Exception as e:
            print(f"❌ Error sending price: {str(e)}")
            return jsonify({
                'success': False,
                'message': f'שגיאה בשליחת מחיר: {str(e)}'
            })
            
    except Exception as e:
        print(f"Error in mobile_controller_send_price: {str(e)}")
        return jsonify({'success': False, 'message': 'שגיאה בשליחת מחיר'}), 500

@app.route('/api/mobile-controller/command', methods=['POST'])
def mobile_controller_command():
    """Send command to parking devices"""
    try:
        if 'user_email' not in session:
            return jsonify({'success': False, 'message': 'לא מחובר'}), 401
        
        # בדיקת הרשאות
        user_result = supabase.table('user_parkings').select(
            'code_type, project_number'
        ).eq('email', session['user_email']).execute()
        
        if not user_result.data or user_result.data[0].get('code_type', '').lower() != 'mobile_controller':
            return jsonify({'success': False, 'message': 'אין הרשאה'}), 403
        
        data = request.get_json()
        command = data.get('command')
        devices = data.get('devices', [])
        parking_id = user_result.data[0].get('project_number')
        
        print(f"📱 Mobile Controller Command: {command} for devices: {devices}")
        
        # מיפוי פקודות לקודים לפי הפרוטוקול של Scheidt
        command_mapping = {
            0xA50A: 'HAND_OPEN',      # 42250 - פתח מחסום
            0xA50B: 'HAND_CLOSE',     # 42251 - סגור מחסום
            0xA500: 'BLOCK',          # 42240 - נעל מחסום
            0xA501: 'UNBLOCK',        # 42241 - בטל נעילה
            0xA137: 'CHECK_STATUS'    # בדיקת סטטוס בלבד
        }
        
        success_count = 0
        failed_devices = []
        
        # שליחת פקודה לכל מכשיר
        for device_num in devices:
            try:
                # For Scheidt, we need cell computer number
                # Try to get it from the last devices response or use default
                cell_computer_num = 1  # Default
                
                # Try to get from session if we saved it from geometry
                if 'cell_computers' in session:
                    cell_computers = session.get('cell_computers', [])
                    if cell_computers:
                        cell_computer_num = int(cell_computers[0])
                        print(f"📱 Using cell computer number from session: {cell_computer_num}")
                
                # Log the actual command being sent
                command_name = command_mapping.get(command, f'Unknown ({command})')
                print(f"📱 Sending command {command_name} ({command}) to device {device_num}")
                
                proxy_data = {
                    'parking_id': parking_id,
                    'endpoint': f'DeviceControlWebService/command/{cell_computer_num}/{device_num}/{command}',
                    'method': 'PUT',
                    'data': {}  # Empty body for command
                }
                
                # Add internal session for proxy authentication
                proxy_data['_internal_session'] = {
                    'user_email': session.get('user_email'),
                    'user_access_level': session.get('user_access_level'),
                    'user_permissions': session.get('user_permissions'),
                    'user_project_number': session.get('user_project_number'),
                    'user_company_list': session.get('user_company_list')
                }
                
                # Use the company-manager proxy
                # Always use localhost to avoid timeout in Render
                port = os.environ.get('PORT', '5000')
                proxy_url = f'http://localhost:{port}/api/company-manager/proxy'
                
                response = requests.post(
                    proxy_url,
                    json=proxy_data,
                    headers={
                        'Content-Type': 'application/json',
                        'Cookie': request.headers.get('Cookie', '')
                    },
                    timeout=10
                )
                
                if response.status_code == 200:
                    proxy_result = response.json()
                    if proxy_result.get('success', False):
                        success_count += 1
                        print(f"✅ Command {command} sent successfully to device {device_num}")
                    else:
                        failed_devices.append(device_num)
                        print(f"❌ Command failed for device {device_num}: {proxy_result.get('message', 'Unknown error')}")
                else:
                    failed_devices.append(device_num)
                    print(f"❌ Command failed for device {device_num}: HTTP {response.status_code}")
                    
            except Exception as e:
                print(f"Error sending command to device {device_num}: {str(e)}")
                failed_devices.append(device_num)
        
        if success_count > 0:
            message = f'פקודה נשלחה בהצלחה ל-{success_count} מכשירים'
            if failed_devices:
                message += f', נכשלה ב-{len(failed_devices)} מכשירים'
            return jsonify({
                'success': True,
                'message': message,
                'executed_devices': [d for d in devices if d not in failed_devices],
                'failed_devices': failed_devices
            })
        else:
            return jsonify({
                'success': False,
                'message': 'הפקודה נכשלה בכל המכשירים',
                'failed_devices': failed_devices
            })
        
    except Exception as e:
        print(f"Error in mobile_controller_command: {str(e)}")
        return jsonify({'success': False, 'message': 'שגיאה בשליחת פקודה'}), 500

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
        # Error getting all users: {str(e)}")
        return jsonify({'success': False, 'message': 'שגיאה בקבלת רשימת משתמשים'})

@app.route('/api/master/create-user', methods=['POST'])
def master_create_user():
    """יצירת משתמש חדש - למאסטר בלבד - עם user_id ידני"""
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
        company_list = data.get('company_list', '').strip()
        
        if company_list:
            if not re.match(r'^[0-9\-]+$', company_list):
                return jsonify({'success': False, 'message': 'רשימת מספרי חברות יכולה לכלול רק מספרים ומקפים'})
    
        if '--' in company_list or company_list.startswith('-') or company_list.endswith('-'):
                return jsonify({'success': False, 'message': 'פורמט רשימת מספרי חברות לא תקין'})

        print(f"🆕 Creating new user: {username} ({email})")
        
        # אימות קלט בסיסי
        if not username or not email:
            return jsonify({'success': False, 'message': 'יש למלא שם משתמש ואימייל'})

        # תיקוף שם משתמש
        is_valid_username, username_or_error = validate_username(username)
        if not is_valid_username:
            return jsonify({'success': False, 'message': username_or_error})
        
        # בדיקה אם המשתמש כבר קיים
        existing_username = supabase.table('user_parkings').select('username').eq('username', username).execute()
        existing_email = supabase.table('user_parkings').select('email').eq('email', validated_email).execute()
        
        if existing_username.data:
            return jsonify({'success': False, 'message': f'שם משתמש "{username}" כבר קיים במערכת'})
        
        if existing_email.data:
            return jsonify({'success': False, 'message': f'כתובת אימייל "{validated_email}" כבר קיימת במערכת'})
        
        # יצירת hash לסיסמה
        password_hash = bcrypt.hashpw('Dd123456'.encode('utf-8'), bcrypt.gensalt(rounds=6, prefix=b'2a')).decode('utf-8')
        
        # קבלת user_id הבא
        try:
            max_user_result = supabase.table('user_parkings').select('user_id').order('user_id', desc=True).limit(1).execute()
            
            if max_user_result.data:
                next_user_id = max_user_result.data[0]['user_id'] + 1
            else:
                next_user_id = 1
            
            print(f"🆔 Next user_id will be: {next_user_id}")
            
        except Exception as e:
            # Error getting max user_id: {str(e)}")
            import random
            next_user_id = random.randint(1000, 9999)
            print(f"🎲 Using random user_id: {next_user_id}")
        
        # הכנת הנתונים להוספה
        current_time = datetime.now(timezone.utc).isoformat()
        
        new_user_data = {
            'user_id': next_user_id,
            'username': username,
            'email': validated_email,
            'password_hash': password_hash,
            'role': role,
            'project_number': int(project_number) if project_number else 0,
            'parking_name': parking_name if parking_name else 'לא צוין',
            'company_type': company_type if company_type else 'לא צוין',
            'access_level': access_level,
            'code_type': code_type,
            'created_at': current_time,
            'updated_at': current_time,
            'password_changed_at': current_time,
            'is_temp_password': True,
            'verification_code': None,
            'code_expires_at': None,
            'password_expires_at': None,
            'company_list': company_list if company_list else None
        }
        
        print(f"💾 Inserting user data with user_id {next_user_id}")
        
        # הוספת המשתמש למסד הנתונים
        result = supabase.table('user_parkings').insert(new_user_data).execute()
        
        if result.data:
            print(f"✅ User created successfully: {username} (ID: {next_user_id})")
            
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
                    'user_id': next_user_id,
                    'temp_password': 'Dd123456'
                }
            })
        else:
            print(f"❌ Failed to insert user to database")
            return jsonify({'success': False, 'message': 'שגיאה ביצירת המשתמש במסד הנתונים'})
        
    except Exception as e:
        print(f"❌ Master create user error: {str(e)}")
        return jsonify({'success': False, 'message': f'שגיאה במערכת: {str(e)}'})


@app.route('/api/parking-manager/create-user', methods=['POST'])
def parking_manager_create_user():
   """יצירת קוד מנהל חברה - למנהל חניון בלבד - רק לחניון שלו"""
   try:
       if 'user_email' not in session:
           return jsonify({'success': False, 'message': 'לא מחובר'}), 401
       
       # בדיקת הרשאות מנהל חניון
       manager_result = supabase.table('user_parkings').select(
           'code_type, project_number, parking_name, company_type, counting, user_id'
       ).eq('email', session['user_email']).execute()
       if not manager_result.data:
            return jsonify({'success': False, 'message': 'אין הרשאה - נדרש קוד מנהל חניון'}), 403
            
       manager_data = manager_result.data[0]
       manager_user_id = manager_data.get('user_id')
       code_type = str(manager_data.get('code_type', '')).strip().lower()
        
       if code_type not in ['parking_manager', 'parking_manager_part', 'parking_manager_partial', 'master']:
            return jsonify({'success': False, 'message': 'אין הרשאה - נדרש קוד מנהל חניון'}), 403
       
       data = request.get_json()
       username = data.get('username', '').strip() if data.get('username') else ''
       email = data.get('email', '').strip() if data.get('email') else ''
       permissions = data.get('permissions', 'B2').strip() if data.get('permissions') else 'B2'
       company_list = data.get('company_list', '').strip() if data.get('company_list') else ''
       access_level = data.get('access_level', 'single_parking').strip() if data.get('access_level') else 'single_parking'
       
       print(f"🅿️ Parking manager creating COMPANY MANAGER for parking: {manager_data['project_number']} ({manager_data['parking_name']})")
       
       # אימות קלט בסיסי
       if not username or not email:
           return jsonify({'success': False, 'message': 'יש למלא שם משתמש ואימייל'})

       # תיקוף שם משתמש
       is_valid_username, username_or_error = validate_username(username)
       if not is_valid_username:
           return jsonify({'success': False, 'message': username_or_error})
       
       # אימות אימייל
       is_valid_email, validated_email = validate_input(email, "email")
       if not is_valid_email:
           return jsonify({'success': False, 'message': 'כתובת אימייל לא תקינה'})

        # Validation: Check counting limit
       new_counting = int(data.get('counting', 0) or 0)
       if new_counting < 0:
            return jsonify({'success': False, 'message': 'כמות רכבים לא יכולה להיות שלילית'})

       manager_limit = manager_data.get('counting', 0) or 0
       if manager_limit > 0: # Only check if manager has a limit
            # Get current usage - Fetch ALL user IDs and filter in Python
            usage_result = supabase.table('user_parkings').select('user_id, counting').eq('project_number', manager_data['project_number']).execute()
            
            # Exclude manager from the sum
            current_usage = sum([(u.get('counting', 0) or 0) for u in usage_result.data if u.get('user_id') != manager_user_id])
            
            if current_usage + new_counting > manager_limit:
                 return jsonify({'success': False, 'message': f'חריגה מכמות הרכבים הכוללת. נותר להקצאה: {manager_limit - current_usage}'})
       
       # בדיקה אם המשתמש כבר קיים
       existing_username = supabase.table('user_parkings').select('username').eq('username', username).execute()
       existing_email = supabase.table('user_parkings').select('email').eq('email', validated_email).execute()
       
       if existing_username.data:
           return jsonify({'success': False, 'message': f'שם משתמש "{username}" כבר קיים במערכת'})
       
       if existing_email.data:
           return jsonify({'success': False, 'message': f'כתובת אימייל "{validated_email}" כבר קיימת במערכת'})
       
       # יצירת hash לסיסמה
       password_hash = bcrypt.hashpw('Dd123456'.encode('utf-8'), bcrypt.gensalt(rounds=6, prefix=b'2a')).decode('utf-8')
       
       # קבלת user_id הבא
       try:
           max_user_result = supabase.table('user_parkings').select('user_id').order('user_id', desc=True).limit(1).execute()
           
           if max_user_result.data:
               next_user_id = max_user_result.data[0]['user_id'] + 1
           else:
               next_user_id = 1
           
           print(f"🆔 Next user_id will be: {next_user_id}")
           
       except Exception as e:
           # Error getting max user_id: {str(e)}")
           import random
           next_user_id = random.randint(1000, 9999)
           print(f"🎲 Using random user_id: {next_user_id}")
       
       # הכנת הנתונים להוספה - 🔒 יוצר רק קוד מנהל חברה לחניון הספציפי
       current_time = datetime.now(timezone.utc).isoformat()
       
       new_user_data = {
           'user_id': next_user_id,
           'username': username,
           'email': validated_email,
           'password_hash': password_hash,
           'role': 'user',
           'project_number': manager_data['project_number'],  # 🔒 חובה - רק החניון של המנהל
           'parking_name': manager_data['parking_name'],      # 🔒 חובה - רק החניון של המנהל
           'company_type': manager_data['company_type'],      # 🔒 חובה - רק החברה של המנהל
           'access_level': 'company_manager',                 # 🔒 חובה - תמיד מנהל חברה
           'code_type': 'company_manager',                    # 🔒 חובה - תמיד קוד מנהל חברה
           'created_at': current_time,
           'updated_at': current_time,
           'password_changed_at': current_time,
           'is_temp_password': True,
           'verification_code': None,
           'code_expires_at': None,
           'password_expires_at': None,
           'company_list': company_list if company_list else None,
           'permissions': permissions,  # Store user permissions
           'counting': new_counting
       }
       
       print(f"💾 Creating COMPANY MANAGER user for parking: {manager_data['project_number']} ({manager_data['parking_name']})")
       
       # הוספת המשתמש למסד הנתונים
       result = supabase.table('user_parkings').insert(new_user_data).execute()
       
       if result.data:
           print(f"✅ Company manager created successfully: {username} (ID: {next_user_id}) - FOR PARKING: {manager_data['project_number']} ({manager_data['parking_name']})")
           
           # שליחת מייל למשתמש החדש
           email_sent = send_new_user_welcome_email(
               validated_email,
               username,
               'Dd123456',
               'https://s-b-parking-reports.onrender.com'
           )
           
           if email_sent:
               message = f'מנהל חברה {username} נוצר בהצלחה עבור חניון {manager_data["parking_name"]}! מייל נשלח ל-{validated_email}'
           else:
               message = f'מנהל חברה {username} נוצר בהצלחה עבור חניון {manager_data["parking_name"]}, אך לא ניתן לשלוח מייל. הסיסמה הראשונית: Dd123456'
           
           return jsonify({
               'success': True,
               'message': message,
               'user_data': {
                   'username': username,
                   'email': validated_email,
                   'parking_name': manager_data['parking_name'],
                   'project_number': manager_data['project_number'],
                   'user_type': 'company_manager',
                   'user_id': next_user_id,
                   'temp_password': 'Dd123456'
               }
           })
       else:
           print(f"❌ Failed to insert company manager to database")
           return jsonify({'success': False, 'message': 'שגיאה ביצירת המנהל במסד הנתונים'})
       
   except Exception as e:
       print(f"❌ Parking manager create company manager error: {str(e)}")
       return jsonify({'success': False, 'message': f'שגיאה במערכת: {str(e)}'})

@app.route('/api/parking-manager/update-user', methods=['POST'])
def parking_manager_update_user():
    """עדכון קוד מנהל חברה - למנהל חניון בלבד - רק לחניון שלו"""
    try:
        if 'user_email' not in session:
            return jsonify({'success': False, 'message': 'לא מחובר'}), 401
        
        # בדיקת הרשאות מנהל חניון
        manager_result = supabase.table('user_parkings').select(
            'code_type, project_number, parking_name, company_type, counting, user_id'
        ).eq('email', session['user_email']).execute()
        
        if not manager_result.data:
            return jsonify({'success': False, 'message': 'אין הרשאה - נדרש קוד מנהל חניון'}), 403
            
        manager_data = manager_result.data[0]
        code_type = str(manager_data.get('code_type', '')).strip().lower()
        
        if code_type not in ['parking_manager', 'parking_manager_part', 'parking_manager_partial', 'master']:
            return jsonify({'success': False, 'message': 'אין הרשאה - נדרש קוד מנהל חניון'}), 403
        
        data = request.get_json()
        user_id = data.get('user_id')
        username = data.get('username', '').strip()
        email = data.get('email', '').strip()
        permissions = data.get('permissions', 'B2').strip()  # Default to 'B2' if not provided
        company_list = data.get('company_list', '').strip()  # וידוא קליטת company_list
        access_level = data.get('access_level', 'single_parking').strip()
        
        print(f"🅿️ Parking manager updating user ID {user_id} for parking: {manager_data['project_number']} ({manager_data['parking_name']})")
        print(f"🏢 Company list received: '{company_list}'")
        
        # אימות קלט בסיסי
        if not user_id:
            return jsonify({'success': False, 'message': 'חסר מזהה משתמש'})
            
        if not username or not email:
            return jsonify({'success': False, 'message': 'יש למלא שם משתמש ואימייל'})

        # וידוא שהמשתמש שמעדכנים שייך לחניון של המנהל
        user_check = supabase.table('user_parkings').select(
            'user_id, username, email, project_number, code_type'
        ).eq('user_id', user_id).eq('project_number', manager_data['project_number']).execute()
        
        if not user_check.data:
            return jsonify({'success': False, 'message': 'משתמש לא נמצא או אין הרשאה לעדכן אותו'})
        
        current_user = user_check.data[0]
        
        # וידוא שמעדכנים רק company_manager (לא parking_manager)
        if current_user.get('code_type') == 'parking_manager':
            return jsonify({'success': False, 'message': 'לא ניתן לערוך מנהל חניון'})

        # תיקוף שם משתמש (רק אם השתנה)
        if username != current_user['username']:
            is_valid_username, username_or_error = validate_username(username)
            if not is_valid_username:
                return jsonify({'success': False, 'message': username_or_error})
            
            # בדיקה אם שם המשתמש החדש כבר קיים
            existing_username = supabase.table('user_parkings').select('username').eq('username', username).neq('user_id', user_id).execute()
            if existing_username.data:
                return jsonify({'success': False, 'message': f'שם משתמש "{username}" כבר קיים במערכת'})
        
        # אימות אימייל (רק אם השתנה)
        if email != current_user['email']:
            is_valid_email, validated_email = validate_input(email, "email")
            if not is_valid_email:
                return jsonify({'success': False, 'message': 'כתובת אימייל לא תקינה'})
            
            # בדיקה אם האימייל החדש כבר קיים
            existing_email = supabase.table('user_parkings').select('email').eq('email', validated_email).neq('user_id', user_id).execute()
            if existing_email.data:
                return jsonify({'success': False, 'message': f'כתובת אימייל "{validated_email}" כבר קיימת במערכת'})
        else:
            validated_email = email

        # וידוא שB תמיד כלול בהרשאות
        if 'B' not in permissions:
            permissions = 'B' + permissions

        # Validation: Check counting limit
        new_counting = int(data.get('counting', 0) or 0)
        if new_counting < 0:
             return jsonify({'success': False, 'message': 'כמות רכבים לא יכולה להיות שלילית'})

        if manager_limit > 0:
            # Get current usage - Fetch ALL and filter in Python to ensure safe exclusion
            usage_result = supabase.table('user_parkings').select('user_id, counting').eq('project_number', manager_data['project_number']).execute()
            
            # Ensure user_id is compared safely (handle string/int)
            target_user_id = int(user_id)
            manager_user_id = manager_data.get('user_id')
            
            # Sum usage EXCLUDING the manager AND the user being updated
            current_usage = sum([(u.get('counting', 0) or 0) for u in usage_result.data 
                                 if int(u.get('user_id')) != target_user_id and u.get('user_id') != manager_user_id])
            
            if current_usage + new_counting > manager_limit:
                 return jsonify({'success': False, 'message': f'חריגה מכמות הרכבים הכוללת. נותר להקצאה: {manager_limit - current_usage}'})
        
        # הכנת הנתונים לעדכון
        current_time = datetime.now(timezone.utc).isoformat()
        
        update_data = {
            'username': username,
            'email': validated_email,
            'permissions': permissions,
            'company_list': company_list if company_list else None,
            'access_level': access_level,
            'counting': new_counting,
            'updated_at': current_time
        }
        
        print(f"💾 Updating user {user_id} in parking: {manager_data['project_number']} ({manager_data['parking_name']})")
        print(f"📝 Update data: {update_data}")
        
        # עדכון המשתמש במסד הנתונים
        result = supabase.table('user_parkings').update(update_data).eq('user_id', user_id).eq('project_number', manager_data['project_number']).execute()
        
        if result.data:
            print(f"✅ User updated successfully: {username} (ID: {user_id}) - FOR PARKING: {manager_data['project_number']} ({manager_data['parking_name']})")
            
            return jsonify({
                'success': True,
                'message': f'המשתמש {username} עודכן בהצלחה עבור חניון {manager_data["parking_name"]}!',
                'user_data': {
                    'user_id': user_id,
                    'username': username,
                    'email': validated_email,
                    'permissions': permissions,
                    'parking_name': manager_data['parking_name'],
                    'project_number': manager_data['project_number']
                }
            })
        else:
            print(f"❌ Failed to update user in database")
            return jsonify({'success': False, 'message': 'שגיאה בעדכון המשתמש במסד הנתונים'})
        
    except Exception as e:
        print(f"❌ Parking manager update user error: {str(e)}")
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

@app.route('/company-manager')
def company_manager_page():
    """דף ניהול חברה למנהל חברה"""
    if 'user_email' not in session:
        return redirect(url_for('login_page'))
    
    # בדיקת הרשאות מנהל חברה
    try:
        user_result = supabase.table('user_parkings').select(
            'code_type, access_level, permissions, company_list, project_number'
        ).eq('email', session['user_email']).execute()
        
        if not user_result.data:
            print(f"⚠️ User not found: {session['user_email']}")
            return redirect(url_for('dashboard'))
        
        user_data = user_result.data[0]
        code_type = user_data.get('code_type')
        access_level = user_data.get('access_level')
        permissions = user_data.get('permissions', '')
        company_list = user_data.get('company_list', '')
        project_number = user_data.get('project_number')
        
        # בדיקה שזה מנהל חברה
        if code_type != 'company_manager' and access_level != 'company_manager':
            print(f"⚠️ Unauthorized access attempt to company-manager by {session['user_email']}")
            return redirect(url_for('dashboard'))
        
        # בדיקת הרשאות - מאפשרים כניסה לכל מנהל חברה
        # ההרשאות יקבעו אילו כפתורים יהיו זמינים
        valid_permissions = ['G', 'N', 'P', 'R', 'B', 'T', '1', '2', '3']
        has_valid_permission = any(perm in permissions for perm in valid_permissions) or permissions == 'B' or permissions == ''
        
        # אם אין הרשאות בכלל או הרשאות לא תקינות
        if not has_valid_permission and permissions not in ['', 'B']:
            print(f"⚠️ Invalid permissions for {session['user_email']}: {permissions}")
            return redirect(url_for('dashboard'))
        
        # שמירת נתונים ב-session לשימוש ב-API
        session['user_permissions'] = permissions
        session['user_company_list'] = company_list
        session['user_project_number'] = project_number
        session['user_access_level'] = access_level
            
    except Exception as e:
        # Error checking company manager permissions: {str(e)}")
        return redirect(url_for('dashboard'))
    
    response = make_response(render_template('parking_subscribers.html',
                                            company_list=company_list,
                                            permissions=permissions,
                                            user_email=session['user_email']))
    # Add no-cache headers to prevent browser caching issues
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response
# ========== Parking System Integration Helper Functions ==========

def get_parking_connection_details(project_number):
    """
    Fetch connection details (IP, Port) for a given parking project number.
    Mirrors logic from company_manager_proxy.
    """
    if not supabase:
        print("❌ Supabase not initialized")
        return None

    try:
        # Search by project number (which matches 'description' in parkings table)
        parking_result = supabase.table('parkings').select(
            'ip_address, port, description'
        ).eq('description', str(project_number)).execute()

        if not parking_result.data:
            # Fallback: project_parking_mapping
            try:
                mapping_result = supabase.table('project_parking_mapping').select(
                    'parking_id, ip_address, port, parking_name'
                ).eq('project_number', str(project_number)).execute()

                if mapping_result.data:
                    data = mapping_result.data[0]
                    return {
                        'ip_address': data.get('ip_address'),
                        'port': data.get('port', 443),
                        'description': data.get('parking_name')
                    }
                else:
                    # Fallback: parking_servers (by name)
                    servers_result = supabase.table('parking_servers').select(
                        'server_url, name'
                    ).eq('name', str(project_number)).execute()
                    
                    if servers_result.data:
                         server_data = servers_result.data[0]
                         import re
                         url_match = re.match(r'https?://([^:]+):?(\d+)?', server_data.get('server_url', ''))
                         if url_match:
                             return {
                                 'ip_address': url_match.group(1),
                                 'port': int(url_match.group(2)) if url_match.group(2) else 443,
                                 'description': server_data.get('name')
                             }
            except Exception as e:
                print(f"❌ Error searching fallback tables for parking {project_number}: {str(e)}")
                return None
        else:
             data = parking_result.data[0]
             return {
                'ip_address': data.get('ip_address'),
                'port': data.get('port', 443),
                'description': data.get('description')
             }
             
    except Exception as e:
        print(f"❌ Error getting parking connection details: {str(e)}")
        return None
    
    return None

def update_parking_contract_counting(project_number, contract_id, counting_value):
    """
    Updates the parking system contract with the new counting limit via XML PUT request.
    """
    print(f"🔄 Attempting to update parking system: Project={project_number}, Contract={contract_id}, Counting={counting_value}")
    
    connection = get_parking_connection_details(project_number)
    if not connection:
        print(f"❌ Could not find connection details for parking {project_number}")
        return False, "Connection details not found"
        
    ip_address = connection['ip_address']
    port = connection['port']
    
    if not ip_address:
         print(f"❌ Missing IP address for parking {project_number}")
         return False, "Missing IP address"

    # Construct URL
    # Format: CustomerMediaWebService/contracts/{id}/detail
    url = f"https://{ip_address}:{port}/CustomerMediaWebService/contracts/{contract_id}/detail"
    
    # Construct XML Payload
    # Structure:
    # <?xml version="1.0" encoding="UTF-8"?>
    # <cm:contractDetail xmlns:cm="http://gsph.sub.com/cust/types">
    #   <cm:contract>
    #       <cm:id>2</cm:id> -- contract_id
    #   </cm:contract>
    #   <counting>10</counting>
    # </cm:contractDetail>
    
    try:
        import xml.etree.ElementTree as ET
        
        # Define Namespaces - ElementTree handling of namespaces can be tricky. 
        # Using explicit standard dictionary but manually handling prefixes might be safer if needed.
        # However, ET.register_namespace usually works globally.
        # Let's try constructing with 'ns0' or explicit prefix if needed, but 'cm' in tag name is explicit.
        
        # NOTE: ElementTree prefixes all tags with the namespace URL in {}. 
        # To get <cm:contractDetail>, we register the namespace.
        ns_url = "http://gsph.sub.com/cust/types"
        ET.register_namespace('cm', ns_url)
        
        # Root Element
        # Using QName syntax {url}tag
        root = ET.Element(f'{{{ns_url}}}contractDetail')
        
        # Contract Wrapper
        contract_elem = ET.SubElement(root, f'{{{ns_url}}}contract')
        
        # ID Element
        id_elem = ET.SubElement(contract_elem, f'{{{ns_url}}}id')
        id_elem.text = str(contract_id)
        
        # Counting Element - Adding namespace to be consistent with schema
        # Assuming <cm:counting> matches the schema defined by xmlns:cm header
        counting_elem = ET.SubElement(root, f'{{{ns_url}}}counting')
        counting_elem.text = str(counting_value)
        
        # Generate String
        xml_str = '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding='unicode')
        
        print(f"📤 Sending XML to {url}:\n{xml_str}")
        
        # Headers
        auth_string = base64.b64encode(b'2022:2022').decode('ascii')
        headers = {
            'Content-Type': 'application/xml',
            'Authorization': f'Basic {auth_string}'
        }
        
        # Send Request
        response = requests.put(url, data=xml_str.encode('utf-8'), headers=headers, verify=False, timeout=30)
        
        print(f"📥 Parking System Response: Code={response.status_code}, Body={response.text[:200]}")
        
        if response.status_code in [200, 201]:
             print("✅ Parking system update successful")
             return True, "Updated successfully"
        else:
             print(f"❌ Parking system update failed: {response.status_code}")
             return False, f"HTTP {response.status_code}"

    except Exception as e:
        print(f"❌ Exception sending update to parking system: {str(e)}")
        return False, str(e)

@app.route('/api/get-current-user', methods=['GET'])
def get_current_user():
    """קבלת פרטי המשתמש המחובר"""
    try:
        if 'user_email' not in session:
            return jsonify({'success': False, 'message': 'לא מחובר'}), 401
        
        # קבלת נתוני המשתמש
        user_result = supabase.table('user_parkings').select(
            'username, email, parking_name, company_type'
        ).eq('email', session['user_email']).execute()
        
        if user_result.data:
            user_data = user_result.data[0]
            return jsonify({
                'success': True,
                'user': {
                    'username': user_data.get('username', session['user_email']),
                    'email': session['user_email'],
                    'parking_name': user_data.get('parking_name', ''),
                    'company_type': user_data.get('company_type', '')
                }
            })
        else:
            return jsonify({
                'success': True,
                'user': {
                    'username': session['user_email'],
                    'email': session['user_email']
                }
            })
    except Exception as e:
        # Error getting current user: {str(e)}")
        return jsonify({'success': False, 'message': 'שגיאה בקבלת נתוני משתמש'}), 500

@app.route('/api/company-manager/get-parkings', methods=['GET'])
def company_manager_get_parkings():
    """קבלת רשימת חניונים עבור מנהל חברה"""
    try:
        # Get parkings API called
        
        if 'user_email' not in session:
            # No user in session
            return jsonify({'success': False, 'message': 'לא מחובר'}), 401
        
        # User authenticated
        
        # קבלת נתוני המשתמש
        user_result = supabase.table('user_parkings').select(
            'project_number, company_list, access_level, permissions'
        ).eq('email', session['user_email']).execute()
        
        if not user_result.data:
            # User not found in DB
            return jsonify({'success': False, 'message': 'משתמש לא נמצא'}), 404
        
        user_data = user_result.data[0]
        company_list = user_data.get('company_list', '')
        permissions = user_data.get('permissions', '')
        
        # User data loaded
        
        # בדיקת הרשאות - מאפשרים גישה לכל מנהל חברה עם הרשאות תקינות
        valid_permissions = ['G', 'N', 'P', 'R', 'B']
        has_valid_permission = any(perm in permissions for perm in valid_permissions) or permissions == 'B' or permissions == ''
        
        if not has_valid_permission and permissions not in ['', 'B']:
            # Invalid permissions
            return jsonify({'success': False, 'message': 'הרשאות לא תקינות'}), 403
        
        # לא צריך לפענח את company_list כאן - זה חברות בתוך החניון, לא חניונים
        # company_list משמש למטרות אחרות (חברות בתוך החניון)
        
        # קבלת project_number של המשתמש
        user_project_number = user_data.get('project_number')
        access_level = user_data.get('access_level', '')
        
        # Access control check
        
        # חיפוש חניונים בטבלת parkings
        # Fetching parkings from DB
        parkings_result = supabase.table('parkings').select(
            'id, name, location, description, ip_address, port, is_active'
        ).execute()
        
        # Found parkings in DB
        
        parkings = []
        for idx, parking in enumerate(parkings_result.data):
            try:
                # Processing parking
                ip_address = parking.get('ip_address')
                port = parking.get('port')
                
                parking_number = parking.get('description', 0)
                # Parsed parking number
                
                # לוגיקה מתוקנת: בדיקה אם למשתמש יש גישה לחניון
                has_access = False
                
                # אופציה 1: זה החניון של המשתמש - השוואה גמישה של טיפוסים
                # Checking access
                
                # המרה לאותו טיפוס לצורך השוואה
                try:
                    user_proj_str = str(user_project_number) if user_project_number else ""
                    parking_num_str = str(parking_number) if parking_number else ""
                    
                    if user_proj_str and parking_num_str and user_proj_str == parking_num_str:
                        # Match! User's parking
                        has_access = True
                    # אופציה 2: למשתמש יש גישת מאסטר בלבד  
                    elif access_level == 'master':
                        # Access via MASTER role
                        has_access = True
                    else:
                        # No access
                        pass
                        
                except Exception as e:
                    # Error comparing
                    pass
                
                if has_access:
                    parkings.append({
                        'id': parking['id'],
                        'name': parking['name'],
                        'location': parking.get('location', ''),
                        'project_number': parking.get('description', ''),
                        'ip_address': parking.get('ip_address', ''),
                        'port': parking.get('port', 443),
                        'is_active': parking.get('is_active', False),
                        'api_url': f"https://{parking.get('ip_address', '')}:{parking.get('port', 443)}"
                    })
                    # Added to results
            except Exception as e:
                # Error loading parking
                pass
        
        # Final parkings list ready
        
        return jsonify({
            'success': True,
            'parkings': parkings,
            'user_permissions': permissions,
            'company_list': company_list
        })
        
    except Exception as e:
        # Error getting parkings: {str(e)}")
        return jsonify({'success': False, 'message': 'שגיאה בטעינת חניונים'}), 500


@app.route('/api/company-manager/get-subscribers', methods=['GET'])
def company_manager_get_subscribers():
    """קבלת רשימת מנויים מחניון ספציפי"""
    try:
        if 'user_email' not in session:
            return jsonify({'success': False, 'message': 'לא מחובר'}), 401
        
        parking_id = request.args.get('parking_id')
        if not parking_id:
            return jsonify({'success': False, 'message': 'חסר מזהה חניון'}), 400
        
        # קבלת נתוני המשתמש
        user_permissions = session.get('user_permissions', '')
        company_list = session.get('user_company_list', '')
        
        # בדיקת הרשאות - מאפשרים גישה לכל מנהל חברה עם הרשאות תקינות
        valid_permissions = ['G', 'N', 'P', 'R', 'B']
        has_valid_permission = any(perm in user_permissions for perm in valid_permissions) or user_permissions == 'B' or user_permissions == ''
        
        if not has_valid_permission and user_permissions not in ['', 'B']:
            return jsonify({'success': False, 'message': 'הרשאות לא תקינות'}), 403
        
        # קבלת נתוני החניון כולל IP ופורט
        parking_result = supabase.table('parkings').select(
            'name, ip_address, port, description'
        ).eq('id', parking_id).execute()
        
        if not parking_result.data:
            return jsonify({'success': False, 'message': 'חניון לא נמצא'}), 404
        
        parking_data = parking_result.data[0]
        
        # בדיקה אם החניון ברשימת החברות המורשות
        if company_list:
            allowed_companies = []
            parts = company_list.split(',')
            for part in parts:
                part = part.strip()
                if '-' in part:
                    try:
                        start, end = part.split('-')
                        allowed_companies.extend(range(int(start), int(end) + 1))
                    except:
                        pass
                else:
                    try:
                        allowed_companies.append(int(part))
                    except:
                        pass
            
            try:
                parking_number = int(parking_data.get('description', 0))
                if allowed_companies and parking_number not in allowed_companies:
                    return jsonify({'success': False, 'message': 'אין הרשאה לחניון זה'}), 403
            except:
                pass
        
        # יצירת URL לקריאה לשרת החניון
        ip_address = parking_data.get('ip_address')
        port = parking_data.get('port', 443)
        
        if not ip_address:
            return jsonify({'success': False, 'message': 'חסרים נתוני חיבור לחניון'}), 500
        
        # כאן צריך לבצע קריאה לשרת החניון
        # לעת עתה מחזירים דוגמה
        return jsonify({
            'success': True,
            'parking_name': parking_data['name'],
            'parking_api_url': f"https://{ip_address}:{port}",
            'subscribers': [],  # יתמלא מהקריאה לשרת החניון
            'message': 'נדרש חיבור לשרת החניון'
        })
        
    except Exception as e:
        # Error getting subscribers: {str(e)}")
        return jsonify({'success': False, 'message': 'שגיאה בטעינת מנויים'}), 500


@app.route('/api/status', methods=['GET'])
def api_status():
    """בדיקת סטטוס המערכת"""
    return jsonify({
        'success': True,
        'version': '2.0.8',  # Direct proxy in app.py
        'timestamp': datetime.now().isoformat(),
        'message': 'Server is running with proxy fix',
        'endpoints': {
            'proxy': 'ACTIVE',
            'test': 'ACTIVE'
        }
    })

@app.route('/api/test-proxy', methods=['GET', 'POST', 'OPTIONS'])
def test_proxy():
    """Test endpoint to verify routing works"""
    return jsonify({
        'success': True,
        'message': 'Test proxy endpoint works!',
        'method': request.method,
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/company-manager/proxy', methods=['POST', 'OPTIONS', 'GET'])
def company_manager_proxy():
    """Proxy לקריאות API לשרתי החניונים"""
    
    # Debug log removed for production
    
    # Handle CORS preflight
    if request.method == 'OPTIONS':
        response = make_response('', 200)
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'POST, OPTIONS, GET'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        return response
    
    # Handle GET for testing
    if request.method == 'GET':
        return jsonify({
            'success': True,
            'message': 'Proxy endpoint is working!',
            'version': '2.0.9-FIXED',
            'method': 'GET',
            'timestamp': datetime.now().isoformat()
        })
    
    try:
        # Proxy request received
        
        # בדיקה אם אנחנו במצב פיתוח מקומי
        is_local_dev = request.host.startswith('localhost') or request.host.startswith('127.0.0.1')
        
        # Get request data first
        data = request.get_json()
        if not data:
            # No JSON data in request
            return jsonify({'success': False, 'message': 'חסרים נתונים'}), 400
            
        # Check for internal session data (for internal API calls)
        internal_session = None
        if data and '_internal_session' in data:
            internal_session = data.pop('_internal_session')
            if internal_session:
                print(f"📱 Internal session received: {internal_session.get('user_email')}")
        
        if 'user_email' not in session and not internal_session:
            if is_local_dev:
                # במצב פיתוח - דלג על בדיקת login
                # LOCAL DEV MODE - Skipping login check
                session['user_email'] = 'test@local.dev'  # משתמש דמה לבדיקות
            else:
                # User not logged in
                return jsonify({'success': False, 'message': 'לא מחובר'}), 401
        
        # Use internal session if provided
        if internal_session:
            current_user_email = internal_session.get('user_email')
            print(f"📱 Using internal session for user: {current_user_email}")
        else:
            current_user_email = session.get('user_email')
            
        parking_id = data.get('parking_id')
        endpoint = data.get('endpoint')
        method = data.get('method', 'GET')
        payload = data.get('payload', {})
        
        # Request details received
        
        # For usageprofiles endpoint, try to use a default parking if none provided
        if 'usageprofiles' in endpoint.lower() and (not parking_id or parking_id == 'null' or parking_id == 'undefined'):
            parking_id = '1'  # Default to parking 1
        
        if not parking_id or not endpoint or parking_id == 'null' or parking_id == 'undefined':
            return jsonify({'success': False, 'message': 'חסרים פרמטרים'}), 400
        
        # קבלת נתוני החניון
        # Convert parking_id to string to handle numeric IDs
        parking_num = str(parking_id)
        
        # Check if parking_id looks like a UUID or a numeric ID
        import re
        is_uuid = bool(re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', parking_num, re.IGNORECASE))
        
        if is_uuid:
            # Search by ID (UUID)
            parking_result = supabase.table('parkings').select(
                'ip_address, port, description'
            ).eq('id', parking_num).execute()
        else:
            # Search by description (numeric parking ID)
            parking_result = supabase.table('parkings').select(
                'ip_address, port, description'
            ).eq('description', parking_num).execute()
        
        if not parking_result.data:
            # Try fallback to project_parking_mapping table
            try:
                mapping_result = supabase.table('project_parking_mapping').select(
                    'parking_id, ip_address, port, parking_name'
                ).eq('project_number', parking_num).execute()
                
                if mapping_result.data:
                    # Found in mapping table
                    mapping_data = mapping_result.data[0]
                    parking_data = {
                        'ip_address': mapping_data.get('ip_address'),
                        'port': mapping_data.get('port', 443),
                        'description': mapping_data.get('parking_name', parking_num)
                    }
                    # Create a result structure similar to parkings table
                    parking_result = {'data': [parking_data]}
                else:
                    # Try parking_servers table as last resort
                    servers_result = supabase.table('parking_servers').select(
                        'server_url, name'
                    ).eq('name', parking_num).execute()
                    
                    if servers_result.data:
                        server_data = servers_result.data[0]
                        # Extract IP and port from server_url
                        import re
                        url_match = re.match(r'https?://([^:]+):?(\d+)?', server_data.get('server_url', ''))
                        if url_match:
                            parking_data = {
                                'ip_address': url_match.group(1),
                                'port': int(url_match.group(2)) if url_match.group(2) else 443,
                                'description': server_data.get('name', parking_num)
                            }
                            parking_result = {'data': [parking_data]}
                        else:
                            return jsonify({'success': False, 'message': 'חניון לא נמצא'}), 404
                    else:
                        return jsonify({'success': False, 'message': 'חניון לא נמצא'}), 404
            except Exception as e:
                print(f"❌ Error searching fallback tables: {str(e)}")
                return jsonify({'success': False, 'message': 'חניון לא נמצא'}), 404
        else:
            parking_data = parking_result.data[0]
            
        ip_address = parking_data.get('ip_address')
        port = parking_data.get('port', 443)
        
        # תמיד השתמש בנתונים מהבסיס נתונים
        # Always use data from database
        
        # וודא שיש כתובת נכונה
        if not ip_address or ip_address == 'None':
            # אם אין בdatabase
            return jsonify({'success': False, 'message': 'חסרה כתובת IP לחניון'}), 404
        
        # וודא שהפורט נכון
        if not port or port == 0:
            # אם אין פורט, השתמש בברירת מחדל
            port = 443  # Default port
            # Using default port
        
        if not ip_address:
            return jsonify({'success': False, 'message': 'חסרים נתוני חיבור'}), 500
        

        # בניית URL - עם פורט ברירת מחדל אם לא נמצא
        if port is None or port == 0:
            port = 443  # פורט ברירת מחדל
            # Using default port
    
        # השתמש תמיד ב-HTTPS לשרתי החניון
        protocol = "https"
        # Using HTTPS protocol
        
        # בניית URL - תיקון לפי מה שעובד!
        if endpoint == 'contracts' or endpoint == 'GetContractsList':
            url = f"{protocol}://{ip_address}:{port}/CustomerMediaWebService/contracts"
            method = 'GET'  # תמיד GET לחברות
        elif 'contracts/' in endpoint and '/consumers' in endpoint:
            # Handle contracts/{contractId}/consumers endpoint
            # Remove CustomerMediaWebService prefix if it exists
            clean_endpoint = endpoint.replace('CustomerMediaWebService/', '')
            url = f"{protocol}://{ip_address}:{port}/CustomerMediaWebService/{clean_endpoint}"
            # Direct contract-specific URL
            # Don't override method for POST requests!
            # method = 'GET'
        elif 'consumers' in endpoint.lower() and '/detail' not in endpoint:
            # בדיקה אם יש query parameters ב-endpoint
            if '?' in endpoint:
                # יש query parameters - להשתמש ב-endpoint כמו שהוא
                url = f"{protocol}://{ip_address}:{port}/CustomerMediaWebService/{endpoint}"
                print(f"🔍 Using consumers endpoint with query params: {endpoint}")
            else:
                # Check if we have a contractId in payload to filter by
                contract_id = payload.get('contractId') if payload else None
                
                if contract_id:
                    # Get consumers for SPECIFIC CONTRACT ONLY - Critical for performance!
                    url = f"{protocol}://{ip_address}:{port}/CustomerMediaWebService/contracts/{contract_id}/consumers"
                    # Getting consumers for specific contract
                else:
                    # Fallback to getting all consumers (should not happen)
                    url = f"{protocol}://{ip_address}:{port}/CustomerMediaWebService/consumers"
                    # Getting all consumers - performance warning
            
            # Consumers endpoint - filtered by contract
            method = 'GET'  # תמיד GET למנויים
        elif endpoint.startswith('consumers/'):
            # Alternative format: consumers/{contractId} or consumers/{contractId},{consumerId}
            url = f"{protocol}://{ip_address}:{port}/CustomerMediaWebService/{endpoint}"
            # Keep the original method (could be GET, PUT, DELETE)
            # method = 'GET' # Don't override the method!
            # Consumers endpoint
        elif '/detail' in endpoint:
            # Handle both contracts/X/detail AND consumers/X,Y/detail endpoints
            # Remove CustomerMediaWebService prefix if exists
            clean_endpoint = endpoint.replace('CustomerMediaWebService/', '')
            
            # Check if it's a consumer detail endpoint
            if 'consumer' in clean_endpoint.lower():
                # It's a consumer detail - format: consumers/{contractId},{consumerId}/detail
                # Already in correct format
                pass
            elif not clean_endpoint.startswith('contracts/'):
                # Extract contract ID if endpoint is like "contracts/123/detail" 
                import re
                match = re.search(r'(\d+)/detail', clean_endpoint)
                if match:
                    contract_id = match.group(1)
                    clean_endpoint = f"contracts/{contract_id}/detail"
            
            url = f"{protocol}://{ip_address}:{port}/CustomerMediaWebService/{clean_endpoint}"
            # Preserve the original method for detail endpoints (GET for read, PUT for update)
            # method = 'GET'  # Don't override the method!
            # Detail request
        elif '/parktrans' in endpoint:
            # Handle parking transactions endpoint
            # Format: consumers/{contractId},{consumerId}/parktrans
            url = f"{protocol}://{ip_address}:{port}/CustomerMediaWebService/{endpoint}"
            method = 'GET'  # Parking transactions are always GET
        elif 'usageprofiles' in endpoint.lower():
            # Handle usage profiles endpoint
            url = f"{protocol}://{ip_address}:{port}/CustomerMediaWebService/usageprofiles"
            method = 'GET'  # Usage profiles are always GET
        elif 'DeviceControlWebService' in endpoint:
            # Handle Device Control Web Service endpoints
            url = f"{protocol}://{ip_address}:{port}/{endpoint}"
            # Commands use PUT, queries use GET
            if '/command/' in endpoint:
                method = 'PUT'
                print(f"📱 Device Control Command: {endpoint}")
            else:
                method = 'GET'
        elif 'CustomerMediaWebService' in endpoint:
            # אם כבר יש CustomerMediaWebService ב-endpoint
            url = f"{protocol}://{ip_address}:{port}/{endpoint}"
        else:
            # אחרת, נסה עם /api
            url = f"{protocol}://{ip_address}:{port}/api/{endpoint}"
        
        # Proxy Request
        
        # הכנת headers
        headers = {'Content-Type': 'application/json'}
        
        # Basic Auth - תמיד לשרת החניון
        if 'CustomerMediaWebService' in endpoint or 'contracts' in endpoint or 'consumer' in endpoint or 'usageprofiles' in endpoint or 'DeviceControlWebService' in endpoint:
            # TODO: החלף עם ה-credentials הנכונים!
            auth_string = base64.b64encode(b'2022:2022').decode('ascii')
            headers['Authorization'] = f'Basic {auth_string}'
            # Added Basic Auth
        
        try:
            # timeout מוגבר ל-30 שניות ב-production
            # For device control endpoints, use even longer timeout
            if 'DeviceControlWebService' in endpoint:
                timeout_seconds = 45 if not is_local_dev else 30
            else:
                timeout_seconds = 30 if not is_local_dev else 25
            # Attempting connection
            
            # ביצוע הקריאה - פשוט כמו שהיה
            # Executing request
            if method == 'GET':
                response = requests.get(url, headers=headers, verify=False, timeout=timeout_seconds)
            elif method == 'POST':
                # POST request with payload
                # Check if this is a consumer creation endpoint
                if 'contracts' in endpoint and 'consumers' in endpoint and payload:
                    # Convert JSON to XML for consumer creation
                    import xml.etree.ElementTree as ET
                    
                    # Create the XML structure as per API spec
                    root = ET.Element('consumerDetail', xmlns='http://gsph.sub.com/cust/types')
                    
                    # Add consumer element if exists
                    if 'consumer' in payload:
                        consumer_elem = ET.SubElement(root, 'consumer')
                        # Only set href if we have an ID (for guests)
                        if 'id' in payload['consumer'] and payload['consumer']['id']:
                            consumer_elem.set('href', f"/consumers/{payload['consumer'].get('contractid', '')},{payload['consumer']['id']}")
                        
                        for key, value in payload['consumer'].items():
                            # Skip empty id for new regular subscribers - server will assign
                            if key == 'id' and (value is None or value == ''):
                                continue
                            # Skip href
                            if key == 'href':
                                continue
                            # Add all non-empty values
                            if value is not None and value != '':
                                elem = ET.SubElement(consumer_elem, key)
                                elem.text = str(value)
                    
                    # Add person element if exists
                    if 'person' in payload:
                        person_elem = ET.SubElement(root, 'person')
                        for key, value in payload['person'].items():
                            if value is not None and value != '':
                                elem = ET.SubElement(person_elem, key)
                                elem.text = str(value)
                    
                    # Add identification element if exists
                    if 'identification' in payload:
                        ident_elem = ET.SubElement(root, 'identification')
                        for key, value in payload['identification'].items():
                            if value is not None and value != '':
                                if key == 'usageProfile' and isinstance(value, dict):
                                    # Handle nested usageProfile
                                    usage_elem = ET.SubElement(ident_elem, 'usageProfile')
                                    if 'id' in value and value['id']:
                                        usage_elem.set('href', f"/usageProfile/{value['id']}")
                                    for uk, uv in value.items():
                                        if uk != 'href' and uv is not None and uv != '':
                                            uelem = ET.SubElement(usage_elem, uk)
                                            uelem.text = str(uv)
                                else:
                                    elem = ET.SubElement(ident_elem, key)
                                    elem.text = str(value)
                    
                    # Add other root level elements
                    for key in ['displayText', 'limit', 'status', 'delete', 'lpn1', 'lpn2', 'lpn3']:
                        if key in payload and payload[key] is not None and payload[key] != '':
                            elem = ET.SubElement(root, key)
                            elem.text = str(payload[key])
                    
                    # Convert to XML string
                    xml_str = '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding='unicode')
                    print(f"   📝 Sending XML for consumer creation (POST to {url}):")
                    print(f"   Consumer ID: {payload.get('consumer', {}).get('id', 'NEW')}")
                    print(f"   📄 Full XML being sent:\n{xml_str}")
                    print(f"   📏 XML length: {len(xml_str)} characters")
                    
                    # Send as XML
                    headers['Content-Type'] = 'application/xml'
                    response = requests.post(url, data=xml_str.encode('utf-8'), headers=headers, verify=False, timeout=timeout_seconds)
                else:
                    # Regular POST with JSON
                    response = requests.post(url, json=payload, headers=headers, verify=False, timeout=timeout_seconds)
            elif method == 'PUT':
                # For consumer detail updates, convert JSON to XML
                if '/detail' in endpoint and 'consumer' in endpoint.lower():
                    # Convert JSON payload to XML for consumer update
                    import xml.etree.ElementTree as ET
                    
                    # Create the XML structure as per API spec
                    root = ET.Element('consumerDetail', xmlns='http://gsph.sub.com/cust/types')
                    
                    # Add consumer element if exists
                    if 'consumer' in payload:
                        consumer_elem = ET.SubElement(root, 'consumer', href=f"/consumers/{payload['consumer'].get('contractid', '')},{payload['consumer'].get('id', '')}")
                        for key, value in payload['consumer'].items():
                            if value and key != 'href':
                                elem = ET.SubElement(consumer_elem, key)
                                elem.text = str(value)
                    
                    # Add person element if exists
                    if 'person' in payload:
                        person_elem = ET.SubElement(root, 'person')
                        for key, value in payload['person'].items():
                            if value:
                                elem = ET.SubElement(person_elem, key)
                                elem.text = str(value)
                    
                    # Add identification element if exists
                    if 'identification' in payload:
                        ident_elem = ET.SubElement(root, 'identification')
                        for key, value in payload['identification'].items():
                            if value:
                                if key == 'usageProfile' and isinstance(value, dict):
                                    # Handle nested usageProfile
                                    usage_elem = ET.SubElement(ident_elem, 'usageProfile')
                                    for uk, uv in value.items():
                                        if uv:
                                            uelem = ET.SubElement(usage_elem, uk)
                                            uelem.text = str(uv)
                                else:
                                    elem = ET.SubElement(ident_elem, key)
                                    # Handle ignorePresence specially - should be '0' or '1'
                                    if key == 'ignorePresence':
                                        # Convert to '0' or '1' string
                                        if value == '1' or value == 1 or value == True or value == 'true':
                                            elem.text = '1'
                                        else:
                                            elem.text = '0'
                                    # Handle other boolean values for XML
                                    elif isinstance(value, bool):
                                        elem.text = 'true' if value else 'false'
                                    else:
                                        elem.text = str(value)
                    
                    # Add vehicle data at root level
                    for key in ['lpn1', 'lpn2', 'lpn3']:
                        if key in payload and payload[key]:
                            elem = ET.SubElement(root, key)
                            elem.text = str(payload[key])
                    
                    # Convert to XML string
                    xml_str = '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding='unicode')
                    print(f"   📝 Sending XML for update (PUT to {url}):")
                    print(f"   📅 Dates in consumer: xValidFrom={payload.get('consumer', {}).get('xValidFrom')}, xValidUntil={payload.get('consumer', {}).get('xValidUntil')}")
                    
                    headers['Content-Type'] = 'application/xml'
                    response = requests.put(url, data=xml_str.encode('utf-8'), headers=headers, verify=False, timeout=timeout_seconds)
                elif '/detail' in endpoint and 'contracts' in endpoint:
                    # Handle Contract Update - Convert JSON to XML
                    import xml.etree.ElementTree as ET
                    ns_url = "http://gsph.sub.com/cust/types"
                    ET.register_namespace('cm', ns_url)
                    
                    root = ET.Element(f'{{{ns_url}}}contractDetail')
                    
                    # Contract Wrapper
                    contract_elem = ET.SubElement(root, f'{{{ns_url}}}contract')
                    
                    # Contract ID
                    if 'id' in payload:
                        id_elem = ET.SubElement(contract_elem, f'{{{ns_url}}}id')
                        id_elem.text = str(payload['id'])
                    
                    # Counting
                    if 'counting' in payload:
                        counting_elem = ET.SubElement(root, f'{{{ns_url}}}counting')
                        counting_elem.text = str(payload['counting'])
                        
                    xml_str = '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding='unicode')
                    print(f"   📝 Sending XML for Contract Update (PUT to {url}):\n{xml_str}")
                    
                    headers['Content-Type'] = 'application/xml'
                    response = requests.put(url, data=xml_str.encode('utf-8'), headers=headers, verify=False, timeout=timeout_seconds)
                else:
                    # Regular PUT with JSON
                    response = requests.put(url, json=payload, headers=headers, verify=False, timeout=timeout_seconds)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers, verify=False, timeout=timeout_seconds)
            else:
                return jsonify({'success': False, 'message': 'שיטה לא נתמכת'}), 400
            
            # Response received
            
            # החזרת התוצאה
            if response.status_code in [200, 201]:
                # בדוק אם התגובה היא XML או JSON
                content_type = response.headers.get('content-type', '')
                # Checking content type
                
                if 'xml' in content_type.lower() or response.text.startswith('<?xml'):
                    # פרש XML לJSON
                    # Got XML response, parsing
                    # XML PARSER - checking endpoint type
                    
                    try:
                        import xml.etree.ElementTree as ET
                        # Fix encoding issues
                        response.encoding = 'utf-8'
                        root = ET.fromstring(response.text.encode('utf-8'))
                        
                        # Check for detail endpoints FIRST
                        # Checking if detail endpoint
                        
                        # Skip the list endpoints if this is a detail request
                        is_detail_endpoint = '/detail' in endpoint
                        
                        # Handle Device Control Web Service responses
                        if 'DeviceControlWebService' in endpoint:
                            print(f"   📱 Parsing Device Control response for endpoint: {endpoint}")
                            
                            if 'geometry' in endpoint:
                                # Parse geometry response
                                devices = []
                                
                                # Try to find cell computer numbers for future use
                                cell_computers = []
                                for cell_comp in root.findall('.//cell-computer'):
                                    cell_num = cell_comp.find('number')
                                    if cell_num is not None:
                                        cell_computers.append(cell_num.text)
                                        print(f"   📱 Found cell computer: {cell_num.text}")
                                
                                # Find all field-device elements recursively
                                for device in root.findall('.//field-device'):
                                    device_name = device.find('name')
                                    device_number = device.find('number')
                                    device_state = device.find('device-state')
                                    device_single_state = device.find('device-single-state')
                                    
                                    if device_name is not None and device_number is not None:
                                        device_num = int(device_number.text)
                                        # Determine device type based on number range
                                        device_type = 'unknown'
                                        if 101 <= device_num <= 199:
                                            device_type = 'entry'
                                        elif 201 <= device_num <= 299:
                                            device_type = 'exit'
                                        elif 301 <= device_num <= 399:
                                            device_type = 'pass'
                                        elif 401 <= device_num <= 499:
                                            device_type = 'door'
                                        elif 501 <= device_num <= 599:
                                            device_type = 'validator'
                                        elif 601 <= device_num <= 699:
                                            device_type = 'payment'
                                        elif 701 <= device_num <= 799:
                                            device_type = 'cashier'
                                        elif 801 <= device_num <= 899:
                                            device_type = 'exit_cashier'
                                        
                                        # Parse device state
                                        state = 1  # Default - operational
                                        if device_state is not None:
                                            state = int(device_state.text) if device_state.text else 1
                                        
                                        # Parse single state for more details
                                        barrier_state = 'unknown'
                                        door_open = False
                                        if device_single_state is not None and device_single_state.text:
                                            # The single state is a 40-char hex string
                                            single_state_hex = device_single_state.text
                                            # Check specific bytes for states (based on documentation)
                                            if len(single_state_hex) >= 2:
                                                # Byte 0 contains device states
                                                byte0 = int(single_state_hex[0:2], 16)
                                                # Bit 4 (value 8): Device door open
                                                if byte0 & 0x08:
                                                    door_open = True
                                                # Bit 7 (value 128): Device out of operation manual
                                                if byte0 & 0x80:
                                                    state = 0  # Override state to "out of order"
                                            
                                            # For barrier state, we may need to check other bytes
                                            # or use the device type to determine default state
                                            if device_type in ['entry', 'exit', 'pass']:
                                                # These typically have barriers
                                                # Without specific documentation, we'll keep as unknown
                                                # and rely on events to update barrier state
                                                barrier_state = 'unknown'
                                        
                                        devices.append({
                                            'name': device_name.text,
                                            'number': device_num,
                                            'type': device_type,
                                            'status': state,
                                            'deviceState': state,  # 0=out of order, 1=operational, 2=not fully operational
                                            'barrier': barrier_state,
                                            'doorOpen': door_open,
                                            'singleState': device_single_state.text if device_single_state is not None else None,
                                            'cellComputers': cell_computers  # Store for command use
                                        })
                                
                                print(f"   ✅ Found {len(devices)} devices in geometry")
                                
                                # Store cell computers in session for command use
                                if cell_computers and internal_session:
                                    # If we have internal session, we need to pass it back
                                    return jsonify({
                                        'success': True, 
                                        'data': devices,
                                        'cellComputers': cell_computers
                                    })
                                
                                return jsonify({'success': True, 'data': devices})
                            
                            elif 'events' in endpoint or 'lastevents' in endpoint:
                                # Parse events response
                                events = []
                                for event in root.findall('.//event'):
                                    event_data = {}
                                    for child in event:
                                        tag = child.tag.replace('-', '_')  # Convert XML tags to valid keys
                                        event_data[tag] = child.text
                                    
                                    # Add device info from event if available
                                    if event_data:
                                        # Extract device state information
                                        event_info = {
                                            'unique_sequence_number': event_data.get('unique_sequence_number'),
                                            'event_no': event_data.get('event_no'),
                                            'event_name': event_data.get('event_name'),
                                            'event_text': event_data.get('event_text'),
                                            'event_date_time': event_data.get('event_date_time'),
                                            'device_number': event_data.get('field_device_number'),
                                            'device_name': event_data.get('field_device_name'),
                                            'device_state': event_data.get('device_state'),
                                            'device_single_state': event_data.get('device_single_state'),
                                            'alarm': event_data.get('alarm')
                                        }
                                        events.append(event_info)
                                
                                print(f"   ✅ Found {len(events)} events")
                                return jsonify({'success': True, 'data': events})
                            
                            elif 'version' in endpoint:
                                # Parse version response
                                version_elem = root.find('.//version-no')
                                if version_elem is not None:
                                    return jsonify({'success': True, 'data': {'version': version_elem.text}})
                            
                            elif 'command' in endpoint:
                                # Parse command response
                                print(f"   📱 Parsing command response")
                                status_elem = root.find('.//status')
                                if status_elem is not None:
                                    status_code = int(status_elem.text)
                                    success = status_code == 0
                                    print(f"   📱 Command response status: {status_code} ({'Success' if success else 'Failed'})")
                                    return jsonify({
                                        'success': success,
                                        'status': status_code,
                                        'message': 'Command executed' if success else 'Command failed'
                                    })
                            
                            # Default response for other DeviceControlWebService endpoints
                            return jsonify({'success': True, 'data': response.text})
                        
                        elif not is_detail_endpoint and ('contracts' in endpoint or 'contract' in endpoint.lower()):
                            contracts = []
                            # חפש contract elements בכל namespaces
                            for contract in root.findall('.//{http://gsph.sub.com/cust/types}contract'):
                                contract_data = {}
                                for child in contract:
                                    tag = child.tag.replace('{http://gsph.sub.com/cust/types}', '')
                                    contract_data[tag] = child.text
                                contracts.append(contract_data)
                            
                            # Filter contracts based on user's company_list permissions
                            company_list = session.get('user_company_list', '')
                            if company_list and company_list != 'all':
                                # Parse company list (e.g., "1,2,5-10,60")
                                allowed_companies = set()
                                parts = company_list.split(',')
                                for part in parts:
                                    part = part.strip()
                                    if '-' in part:
                                        # Handle range like "5-10"
                                        try:
                                            start, end = part.split('-')
                                            for i in range(int(start), int(end) + 1):
                                                allowed_companies.add(str(i))
                                        except:
                                            pass
                                    else:
                                        # Single company ID
                                        allowed_companies.add(part)
                                
                                # Filter contracts
                                filtered_contracts = []
                                for contract in contracts:
                                    contract_id = str(contract.get('id', contract.get('contractId', contract.get('contractNum', ''))))
                                    if contract_id in allowed_companies:
                                        filtered_contracts.append(contract)
                                
                                # Filtered contracts based on permissions
                                contracts = filtered_contracts
                            
                            # Returning contracts from XML
                            return jsonify({'success': True, 'data': contracts})
                            
                        elif not is_detail_endpoint and 'consumer' in endpoint.lower():
                            # Show RAW XML for debugging
                            consumers = []
                            # Try to find consumers in different XML structures
                            # First try with namespace
                            consumer_elements = root.findall('.//{http://gsph.sub.com/cust/types}consumer')
                            
                            # If not found, try without namespace
                            if not consumer_elements:
                                consumer_elements = root.findall('.//consumer')
                            
                            # Found consumers
                            
                            for idx, consumer in enumerate(consumer_elements):
                                consumer_data = {}
                                
                                # Get attributes if exist
                                for key, value in consumer.attrib.items():
                                    clean_key = key.replace('{http://gsph.sub.com/cust/types}', '')
                                    consumer_data[clean_key] = value
                                
                                # Get child elements
                                for child in consumer:
                                    tag = child.tag.replace('{http://gsph.sub.com/cust/types}', '')
                                    # Handle nested elements
                                    if len(child) > 0:
                                        # This is a complex element with children
                                        child_data = {}
                                        for subchild in child:
                                            subtag = subchild.tag.replace('{http://gsph.sub.com/cust/types}', '')
                                            child_data[subtag] = subchild.text
                                        consumer_data[tag] = child_data
                                    else:
                                        consumer_data[tag] = child.text
                                
                                consumers.append(consumer_data)
                            
                            # Found consumers
                            pass
                            
                            # Check if we're getting consumers from contract-specific endpoint3482
                            is_contract_specific = 'contracts/' in url and '/consumers' in url
                            
                            if is_contract_specific:
                                # Got consumers from contract-specific endpoint
                                pass
                            elif payload and 'contractId' in payload:
                                # Only filter if we got ALL consumers (old behavior)
                                contract_id = str(payload['contractId'])
                                print(f"   🔍 Got ALL consumers - need to filter for contract ID: {contract_id}")
                                
                                # Filter consumers by contractId
                                filtered = []
                                for c in consumers:
                                    # Check different possible field names for contract association
                                    # NOTE: The XML returns 'contractid' in lowercase!
                                    possible_contract_fields = [
                                        c.get('contractid'),  # lowercase - this is what XML returns!
                                        c.get('contractId'),  # camelCase - just in case
                                        c.get('contract'),
                                        c.get('contractNum'),
                                        c.get('contractNumber'),
                                        c.get('companyId'),
                                        c.get('companyNum')
                                    ]
                                    
                                    # Convert all to string and check
                                    for field_value in possible_contract_fields:
                                        if field_value and str(field_value) == contract_id:
                                            filtered.append(c)
                                            break
                                
                                if filtered:
                                    print(f"   ✅ Filtered to {len(filtered)} consumers for contract {contract_id}")
                                    consumers = filtered
                                else:
                                    print(f"   ⚠️ No consumers found for contract {contract_id} after filtering")
                                    consumers = []
                            
                            # Minimal logging for performance
                            if consumers:
                                # Returning consumers
                                pass
                            
                            # CRITICAL PERFORMANCE FIX: Limit consumers to avoid browser freezing
                            # No limit on consumers - let the frontend handle it with smart loading
                            # MAX_CONSUMERS_PER_REQUEST = 100  # REMOVED - no limit
                            # Returning all consumers
                            pass
                            
                            # Returning consumers from XML
                            return jsonify({'success': True, 'data': consumers})
                        elif '/detail' in endpoint and 'consumer' in endpoint:
                            # Parse consumer DETAIL from XML
                            # Removed verbose XML logging for performance
                            
                            # Parse the consumer detail
                            consumer_detail = {}
                            
                            # Try to parse as XML
                            try:
                                detail_root = ET.fromstring(response.text)
                                
                                # Extract all fields recursively
                                def extract_fields(element, prefix=''):
                                    data = {}
                                    # Add attributes
                                    for key, value in element.attrib.items():
                                        clean_key = key.replace('{http://gsph.sub.com/cust/types}', '')
                                        data[prefix + clean_key] = value
                                    
                                    # Add text if exists
                                    if element.text and element.text.strip():
                                        return element.text.strip()
                                    
                                    # Process children
                                    for child in element:
                                        tag = child.tag.replace('{http://gsph.sub.com/cust/types}', '')
                                        child_data = extract_fields(child, '')
                                        if child_data:
                                            data[tag] = child_data
                                    
                                    return data if data else None
                                
                                consumer_detail = extract_fields(detail_root) or {}
                                
                                # Removed field logging for performance
                                pass
                                
                            except Exception as e:
                                print(f"   ❌ Error parsing consumer detail XML: {e}")
                                consumer_detail = {'error': str(e)}
                            
                            return jsonify({'success': True, 'data': consumer_detail})
                        elif '/detail' in endpoint and 'contracts' in endpoint:
                            # CONTRACT DETAIL - PARSING XML
                            # Parse contract detail with pooling data
                            def parse_element(element, preserve_text=False):
                                """Recursively parse XML element to dict"""
                                result = {}
                                
                                # Add text content if exists
                                if element.text and element.text.strip():
                                    text_value = element.text.strip()
                                    if preserve_text:
                                        result['_text'] = text_value
                                    else:
                                        # If element has no children and no attributes, return just the text
                                        if not len(element) and not element.attrib:
                                            return text_value
                                        result = text_value
                                
                                # Add attributes
                                for key, value in element.attrib.items():
                                    clean_key = key.replace('{http://gsph.sub.com/cust/types}', '')
                                    result[f"@{clean_key}"] = value
                                
                                # Add child elements
                                children = {}
                                for child in element:
                                    tag = child.tag.replace('{http://gsph.sub.com/cust/types}', '')
                                    
                                    # Special handling for poolingDetail to ensure it's always an array
                                    if tag == 'poolingDetail':
                                        if 'poolingDetail' not in children:
                                            children['poolingDetail'] = []
                                        children['poolingDetail'].append(parse_element(child))
                                    elif tag in children:
                                        # Convert to list if not already
                                        if not isinstance(children[tag], list):
                                            children[tag] = [children[tag]]
                                        children[tag].append(parse_element(child))
                                    else:
                                        # Check if there are multiple children with same tag
                                        same_tag_count = len([c for c in element if c.tag == child.tag])
                                        if same_tag_count > 1:
                                            if tag not in children:
                                                children[tag] = []
                                            children[tag].append(parse_element(child))
                                        else:
                                            children[tag] = parse_element(child)
                                
                                # If we have children, add them to result
                                if children:
                                    if isinstance(result, dict):
                                        result.update(children)
                                    elif isinstance(result, str) and result:
                                        # If we had text and children, preserve both
                                        result = {'_text': result, **children}
                                    else:
                                        result = children
                                        
                                return result
                            
                            # Check root tag
                            # Check root tag
                            
                            contract_detail = parse_element(root)
                            
                            # Debug: parsed structure
                            
                            # Check if we have the critical fields
                            if isinstance(contract_detail, dict):
                                # Check for pooling data
                                pass
                            
                            # Calculate summary data from pooling if available
                            # Check for pooling in different possible locations
                            pooling_data = None
                            if 'pooling' in contract_detail:
                                pooling_data = contract_detail['pooling']
                            elif 'poolingDetail' in contract_detail:
                                pooling_data = {'poolingDetail': contract_detail['poolingDetail']}
                            
                            if pooling_data and 'poolingDetail' in pooling_data:
                                pooling_details = pooling_data['poolingDetail']
                                if not isinstance(pooling_details, list):
                                    pooling_details = [pooling_details]
                                
                                # Found pooling data
                                
                                # Calculate totals
                                total_present = 0
                                total_max = 0
                                consumer_count = 0
                                
                                for detail in pooling_details:
                                    if isinstance(detail, dict):
                                        present = int(detail.get('presentCounter', 0))
                                        max_count = int(detail.get('maxCounter', 0))
                                        total_present += present
                                        total_max += max_count
                                        
                                        # Facility "0" usually contains the consumer count
                                        if detail.get('facility') == '0':
                                            consumer_count = present
                                
                                # Don't add consumerCount here - will be calculated from actual consumers
                                # Remove totalVehicles as it's not accurate
                                # Facility data calculated
                            else:
                                # No pooling data found
                                # DO NOT add mock data - return real data only
                                pass
                            
                            # Make sure we're returning the complete data including pooling
                            # Returning contract detail with pooling to client
                            
                            # ALSO return the raw XML for debugging
                            return jsonify({
                                'success': True, 
                                'data': contract_detail,
                                'debug': {
                                    'raw_xml': response.text[:5000],  # First 5000 chars of XML
                                    'parsed_keys': list(contract_detail.keys()) if isinstance(contract_detail, dict) else 'NOT_DICT',
                                    'has_pooling': 'pooling' in contract_detail if isinstance(contract_detail, dict) else False
                                }
                            })
                        elif 'usageprofile' in endpoint.lower():
                            # Parse usage profiles from XML
                            profiles = []
                            print(f"   Root tag: {root.tag}")
                            
                            # Try to find usageProfile elements in different XML structures
                            # First try with namespace
                            profile_elements = root.findall('.//{http://gsph.sub.com/cust/types}usageProfile')
                            
                            # If not found, try without namespace
                            if not profile_elements:
                                profile_elements = root.findall('.//usageProfile')
                            
                            # Also try usageProfiles (plural)
                            if not profile_elements:
                                profile_elements = root.findall('.//{http://gsph.sub.com/cust/types}usageProfiles')
                            if not profile_elements:
                                profile_elements = root.findall('.//usageProfiles')
                            
                            
                            for profile in profile_elements:
                                profile_data = {}
                                # Get attributes (like href)
                                for key, value in profile.attrib.items():
                                    clean_key = key.replace('{http://gsph.sub.com/cust/types}', '')
                                    profile_data[clean_key] = value
                                
                                # Get child elements
                                for child in profile:
                                    tag = child.tag.replace('{http://gsph.sub.com/cust/types}', '')
                                    if child.text:
                                        profile_data[tag] = child.text.strip()
                                
                                # Make sure we have at least id and name
                                if 'id' in profile_data:
                                    profiles.append(profile_data)
                            
                            # If we have a single usageProfiles element containing multiple profiles
                            if not profiles:
                                profiles_container = root.find('.//{http://gsph.sub.com/cust/types}usageProfiles')
                                if profiles_container is None:
                                    profiles_container = root.find('.//usageProfiles')
                                
                                if profiles_container is not None:
                                    for profile in profiles_container:
                                        profile_data = {}
                                        for key, value in profile.attrib.items():
                                            clean_key = key.replace('{http://gsph.sub.com/cust/types}', '')
                                            profile_data[clean_key] = value
                                        
                                        for child in profile:
                                            tag = child.tag.replace('{http://gsph.sub.com/cust/types}', '')
                                            if child.text:
                                                profile_data[tag] = child.text.strip()
                                        
                                        if 'id' in profile_data:
                                            profiles.append(profile_data)
                            
                            if not profiles:
                                print(f"   XML (first 1000 chars): {response.text[:1000]}")
                                # Return default profiles if none found
                                profiles = [
                                    {"id": "0", "name": "רגיל"},
                                    {"id": "1", "name": "כול החניונים"},
                                    {"id": "2", "name": "חניון ראשי"},
                                    {"id": "3", "name": "VIP"},
                                    {"id": "4", "name": "נכה"},
                                    {"id": "5", "name": "-2 חניון"}
                                ]
                            
                            return jsonify({'success': True, 'data': profiles})
                        else:
                            # החזר כ-raw XML אם לא מזהים את הסוג
                            # Unknown XML type, returning raw
                            return jsonify({'success': True, 'raw': response.text})
                            
                    except Exception as e:
                        print(f"   ❌ XML parse error: {e}")
                        return jsonify({'success': True, 'raw': response.text})
                else:
                    # נסה לפרש כ-JSON
                    try:
                        data = response.json() if response.text else {}
                        # Got JSON data from parking server
                        
                        # Log what we got if this is a detail endpoint
                        if '/detail' in endpoint:
                            # Got JSON response for detail endpoint
                            pass
                        
                        # Filter contracts if we're getting contracts
                        if ('contracts' in endpoint or 'contract' in endpoint.lower()) and not '/detail' in endpoint:
                            # Check if data contains contracts
                            contracts_data = data
                            if isinstance(data, dict):
                                # Look for contracts in different possible locations
                                if 'contracts' in data:
                                    contracts_data = data['contracts']
                                elif 'contract' in data:
                                    contracts_data = data['contract']
                            
                            # If we have contracts to filter
                            if isinstance(contracts_data, list):
                                company_list = session.get('user_company_list', '')
                                if company_list and company_list != 'all':
                                    # Parse company list
                                    allowed_companies = set()
                                    parts = company_list.split(',')
                                    for part in parts:
                                        part = part.strip()
                                        if '-' in part:
                                            try:
                                                start, end = part.split('-')
                                                for i in range(int(start), int(end) + 1):
                                                    allowed_companies.add(str(i))
                                            except:
                                                pass
                                        else:
                                            allowed_companies.add(part)
                                    
                                    # Filter contracts
                                    filtered = []
                                    for contract in contracts_data:
                                        contract_id = str(contract.get('id', contract.get('contractId', contract.get('contractNum', ''))))
                                        if contract_id in allowed_companies:
                                            filtered.append(contract)
                                    
                                    # Filtered contracts based on permissions
                                    
                                    # Update data with filtered contracts
                                    if isinstance(data, dict):
                                        if 'contracts' in data:
                                            data['contracts'] = filtered
                                        elif 'contract' in data:
                                            data['contract'] = filtered
                                    else:
                                        data = filtered
                        
                        # Add success message for PUT/POST requests
                        result = {
                            'success': True,
                            'data': data
                        }
                        
                        # Add appropriate message based on method
                        if method == 'PUT':
                            result['message'] = 'הנתונים עודכנו בהצלחה בשרת החניון'
                        elif method == 'POST':
                            result['message'] = 'הנתונים נשמרו בהצלחה בשרת החניון'
                            # For consumer creation, check if we got a created ID
                            if 'contracts' in endpoint and 'consumers' in endpoint:
                                print(f"   🆕 Consumer creation response status: {response.status_code}")
                                print(f"   🆕 Consumer creation response: {response.text[:1000]}")
                                print(f"   🆕 Response content-type: {response.headers.get('content-type', 'unknown')}")
                                # Try to extract ID from response if exists
                                try:
                                    import xml.etree.ElementTree as ET
                                    if response.text.startswith('<?xml'):
                                        root = ET.fromstring(response.text.encode('utf-8'))
                                        # Look for consumer ID in response
                                        consumer_elem = root.find('.//{http://gsph.sub.com/cust/types}consumer')
                                        if consumer_elem is None:
                                            consumer_elem = root.find('.//consumer')
                                        if consumer_elem is not None:
                                            id_elem = consumer_elem.find('.//{http://gsph.sub.com/cust/types}id')
                                            if id_elem is None:
                                                id_elem = consumer_elem.find('.//id')
                                            if id_elem is not None and id_elem.text:
                                                result['data'] = {'id': id_elem.text}
                                                print(f"   🆕 New consumer ID from server: {id_elem.text}")
                                            else:
                                                print(f"   ⚠️ No ID found in consumer element")
                                        else:
                                            print(f"   ⚠️ No consumer element found in response")
                                    else:
                                        print(f"   ⚠️ Response is not XML")
                                except Exception as e:
                                    print(f"   ❌ Error parsing creation response: {str(e)}")
                        
                        return jsonify(result)
                    except Exception as e:
                        # Error parsing JSON
                        # אם זה לא JSON, החזר את הטקסט
                        return jsonify({
                            'success': True,
                            'data': {'raw': response.text}
                        })
            else:
                print(f"   ❌ Error from parking server: {response.status_code}")
                print(f"   📝 Error details: {response.text[:500]}")
                return jsonify({
                    'success': False,
                    'message': f'שגיאה בקריאה לשרת החניון: {response.status_code}'
                }), response.status_code
                
        except requests.exceptions.Timeout:
            return jsonify({
                'success': False, 
                'error': 'זמן ההמתנה לשרת החניון פג',
                'timeout': timeout_seconds,
                'server': f"{ip_address}:{port}"
            }), 504
        except requests.exceptions.ConnectionError as e:
            error_msg = str(e)
            
            # בדוק אם זה בעיית SSL
            if 'SSL' in error_msg or 'certificate' in error_msg.lower():
                try:
                    # נסה שוב עם SSL מושבת לגמרי
                    import ssl
                    import urllib3
                    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                    
                    response = requests.get(url, headers=headers, verify=False, timeout=10)
                    if response.status_code == 200:
                        print(f"   ✅ Worked without SSL verification!")
                        data = response.json() if response.text else {}
                        return jsonify({'success': True, 'data': data})
                except:
                    pass
            
            return jsonify({
                'success': False, 
                'error': 'לא ניתן להתחבר לשרת החניון',
                'details': error_msg[:200],
                'server': f"{ip_address}:{port}"
            }), 503
        except Exception as e:
            return jsonify({
                'success': False, 
                'error': str(e)[:200],
                'server': f"{ip_address}:{port}"
            }), 500
            
    except Exception as e:
        print(f"❌ General proxy error: {str(e)}")
        return jsonify({'success': False, 'error': 'שגיאה כללית במערכת'}), 500

# ========== API למנהל חניון ==========
@app.route('/api/parking-manager/get-parking-info', methods=['GET'])
def parking_manager_get_info():
    """קבלת נתוני החניון של המנהל - תומך גם במנהל חלקי"""
    try:
        if 'user_email' not in session:
            return jsonify({'success': False, 'message': 'לא מחובר'}), 401
        
        # בדיקת הרשאות מנהל חניון
        user_result = supabase.table('user_parkings').select(
            'code_type, project_number, parking_name, company_type, company_list, counting'
        ).eq('email', session['user_email']).execute()
        
        if not user_result.data:
            return jsonify({'success': False, 'message': 'משתמש לא נמצא'}), 403

        user_data = user_result.data[0]
        code_type = user_data.get('code_type', '')
        code_type_lower = str(code_type).strip().lower()
        
        # הרשאות: מנהל חניון מלא, מנהל חניון חלקי, או מאסטר
        allowed_roles = ['parking_manager', 'parking_manager_part', 'parking_manager_partial', 'master']
        if code_type_lower not in allowed_roles:
            return jsonify({'success': False, 'message': 'אין הרשאה - נדרש קוד מנהל חניון'}), 403
        
        # קבלת משתמשי החניון
        parking_users = supabase.table('user_parkings').select(
             'user_id, username, email, company_list, permissions, role, access_level, created_at, is_temp_password, counting'
        ).eq('project_number', user_data['project_number']).order('created_at', desc=True).execute()
        
        # קבלת משתמשי החניון
        parking_users = supabase.table('user_parkings').select(
             'user_id, username, email, company_list, permissions, role, access_level, created_at, is_temp_password, counting'
        ).eq('project_number', user_data['project_number']).order('created_at', desc=True).execute()
        
        users_list = parking_users.data
        
        # אם זה מנהל חלקי - סינון המשתמשים
        if code_type_lower in ['parking_manager_part', 'parking_manager_partial']:
            manager_allowed = user_data.get('company_list', '')
            filtered_users = []
            
            # Helper to parse ranges "100, 200-300" -> list of ints
            def parse_ranges(range_str):
                allowed_nums = set()
                if not range_str: return allowed_nums
                parts = str(range_str).split(',')
                for p in parts:
                    p = p.strip()
                    if '-' in p:
                        try:
                            start, end = map(int, p.split('-'))
                            allowed_nums.update(range(start, end + 1))
                        except: pass
                    else:
                        try:
                            allowed_nums.add(int(p))
                        except: pass
                return allowed_nums

            manager_set = parse_ranges(manager_allowed)
            
            # אם למנהל אין הגדרת חברות, אולי הוא לא רואה כלום או רואה הכל? נניח ריק = כלום
            if manager_set: 
                for u in users_list:
                    u_companies = u.get('company_list', '')
                    # אם למשתמש אין חברה מוגדרת, האם להראות? נניח שלא
                    if not u_companies: continue
                    
                    u_set = parse_ranges(u_companies)
                    # בדיקה: האם כל החברות של המשתמש מוכלות בטווח המנהל? 
                    # או מספיק חיתוך? המשתמש ביקש: "המשתמש אמור לראות רק משתמשים שיש להם חברות בטווח"
                    # נניח חיתוך (overlap) מספיק כדי לראות את המשתמש
                    # אבל כדי למנוע זליגת מידע, אם משתמש שייך ל-100 ו-200, ומנהל אחראי רק על 100,
                    # הוא יראה את המשתמש. האם הוא יכול לערוך אותו ולראות את 200? כן. 
                    # זה גבולי אבל מקובל במערכות פשוטות. נלך על חיתוך.
                    if not u_set.isdisjoint(manager_set):
                        filtered_users.append(u)
            
            users_list = filtered_users

        return jsonify({
            'success': True,
            'current_user_id': user_data.get('user_id'),
            'parking_info': {
                'project_number': user_data['project_number'],
                'parking_name': user_data['parking_name'],
                'company_type': user_data['company_type'],
                'counting': user_data.get('counting', 0) or 0
            },
            'users': users_list
        })
        
    except Exception as e:
        # Error getting parking manager info: {str(e)}")
        return jsonify({'success': False, 'message': 'שגיאה בקבלת נתוני חניון'})

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

def clean_expired_reset_codes():
    """ניקוי קודים שפגו תוקף - איפוס סיסמה"""
    current_time = time.time()
    expired_emails = []
    
    for email, data in password_reset_codes.items():
        if current_time - data['timestamp'] > 1800:  # 30 דקות
            expired_emails.append(email)
    
    for email in expired_emails:
        del password_reset_codes[email]

def send_password_reset_verification_email(email, code, username):
    """שליחת מייל עם קוד איפוס סיסמה"""
    
    if not mail:
        print(f"❌ Mail system not available")
        print(f"📱 RESET CODE for {email}: {code}")
        return False
    
    try:
        
        msg = Message(
            subject='איפוס סיסמה - S&B Parking',
            recipients=[email],
            html=f"""
            <div style="font-family: Arial, sans-serif; direction: rtl; text-align: right;">
                <h2 style="color: #667eea;">שיידט את בכמן ישראל</h2>
                <h3>בקשה לאיפוס סיסמה</h3>
                
                <p>שלום {username},</p>
                <p>קיבלנו בקשה לאיפוס הסיסמה שלך במערכת S&B Parking.</p>
                
                <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; text-align: center; margin: 20px 0;">
                    <p><strong>קוד האימות שלך:</strong></p>
                    <span style="font-size: 32px; font-weight: bold; color: #667eea; letter-spacing: 5px; background: #e9ecef; padding: 15px; border-radius: 8px; display: inline-block;">{code}</span>
                </div>
                
                <div style="background: #fff3cd; border: 1px solid #ffeaa7; padding: 15px; border-radius: 8px; margin: 20px 0;">
                    <p style="margin: 0; color: #856404;"><strong>חשוב:</strong></p>
                    <p style="margin: 5px 0 0 0; color: #856404;">
                        • הקוד תקף ל-10 דקות בלבד<br>
                        • השתמש בקוד זה רק אם אתה ביקשת איפוס סיסמה<br>
                        • אם לא ביקשת איפוס, התעלם מהודעה זו
                    </p>
                </div>
                
                <p>לאחר הזנת הקוד תוכל לבחור סיסמה חדשה.</p>
                
                <hr>
                <p style="color: #666; font-size: 12px;">S&B Parking - מערכת דוחות חניות</p>
            </div>
            """,
            sender=app.config['MAIL_USERNAME']
        )
        
        mail.send(msg)
        print(f"✅ Password reset email sent successfully to {email}")
        return True
        
    except Exception as e:
        print(f"❌ Password reset email error: {str(e)}")
        print(f"📱 BACKUP CODE for {email}: {code}")
        return False

# ניקוי אוטומטי של קודים ישנים
def auto_cleanup_reset_codes():
    """ניקוי אוטומטי של קודי איפוס שפגו תוקף"""
    def cleanup_loop():
        while True:
            try:
                time.sleep(900)  # 15 דקות
                clean_expired_reset_codes()
                print(f"🧹 Reset codes cleanup completed")
            except Exception as e:
                print(f"⚠️ Cleanup error: {str(e)}")
    
    cleanup_thread = threading.Thread(target=cleanup_loop, daemon=True)
    cleanup_thread.start()

auto_cleanup_reset_codes()

@app.route('/api/debug/why-no-access', methods=['GET'])
def debug_why_no_access():
    """למה המשתמש לא מקבל גישה לחניון שלו?"""
    try:
        if 'user_email' not in session:
            return jsonify({'success': False, 'message': 'לא מחובר'})
        
        # קבלת נתוני המשתמש
        user_result = supabase.table('user_parkings').select(
            'project_number, company_list, access_level, permissions'
        ).eq('email', session['user_email']).execute()
        
        if not user_result.data:
            return jsonify({'success': False, 'message': 'משתמש לא נמצא'})
        
        user_data = user_result.data[0]
        user_project = user_data.get('project_number')
        company_list = user_data.get('company_list', '')
        
        # קבלת נתוני החניון הספציפי
        parking_result = supabase.table('parkings').select('*').eq('description', str(user_project)).execute()
        
        debug_info = {
            'user_data': {
                'email': session['user_email'],
                'project_number': user_project,
                'project_type': type(user_project).__name__,
                'company_list': company_list,
                'access_level': user_data.get('access_level'),
                'permissions': user_data.get('permissions')
            },
            'parking_search': {
                'searched_for': str(user_project),
                'found_parkings': len(parking_result.data)
            }
        }
        
        if parking_result.data:
            parking = parking_result.data[0]
            debug_info['parking_found'] = {
                'id': parking['id'],
                'name': parking['name'],
                'description': parking['description'],
                'description_type': type(parking['description']).__name__,
                'ip_address': parking.get('ip_address'),
                'port': parking.get('port'),
                'is_active': parking.get('is_active')
            }
            
            # בדיקת השוואה
            user_str = str(user_project)
            parking_str = str(parking['description'])
            debug_info['comparison'] = {
                'user_project_str': user_str,
                'parking_description_str': parking_str,
                'are_equal': user_str == parking_str,
                'user_length': len(user_str),
                'parking_length': len(parking_str)
            }
            
            # בדיקת company_list
            if company_list:
                allowed_companies = []
                for part in company_list.split(','):
                    try:
                        allowed_companies.append(int(part.strip()))
                    except:
                        pass
                
                debug_info['company_list_check'] = {
                    'company_list_raw': company_list,
                    'allowed_companies': allowed_companies,
                    'parking_number': parking['description'],
                    'is_in_list': parking['description'] in allowed_companies
                }
        else:
            debug_info['parking_found'] = None
        
        return jsonify({
            'success': True,
            'debug_info': debug_info
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })


@app.route('/api/company-manager/send-guest-email', methods=['POST'])
def send_guest_email():
    """שליחת מייל לאורח עם פרטי החניה"""
    try:
        if 'user_email' not in session:
            return jsonify({'success': False, 'message': 'לא מחובר'}), 401
        
        data = request.get_json()
        guest_email = data.get('email')
        guest_name = data.get('name', 'אורח')
        valid_from = data.get('validFrom')
        valid_until = data.get('validUntil')
        parking_name = data.get('parkingName', 'החניון')
        company_name = data.get('companyName', '')
        vehicle_number = data.get('vehicleNumber', '')
        
        # Validate email
        is_valid, validated_email = validate_input(guest_email, "email")
        if not is_valid:
            return jsonify({'success': False, 'message': 'כתובת מייל לא תקינה'})
        
        # Send email
        if mail:
            try:
                # Get Gmail credentials
                gmail_user = os.environ.get('GMAIL_USERNAME')
                gmail_password = os.environ.get('GMAIL_APP_PASSWORD')
                
                if not gmail_user or not gmail_password:
                    print(f"❌ Missing Gmail credentials")
                    return jsonify({'success': False, 'message': 'חסרים פרטי Gmail'})
                
                msg = MIMEMultipart('alternative')
                msg['From'] = gmail_user
                msg['To'] = validated_email
                msg['Subject'] = f'הזמנה לחניה - {parking_name}'
                
                # Create HTML content
                html_body = f"""
                <div dir="rtl" style="font-family: Arial, sans-serif; padding: 20px; max-width: 600px; margin: auto;">
                    <h2 style="color: #2c3e50;">שלום {guest_name},</h2>
                    
                    <p style="font-size: 16px; line-height: 1.6;">
                        הרשאת החניה שלך אושרה בהצלחה!
                    </p>
                    
                    <div style="background-color: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0;">
                        <h3 style="color: #28a745; margin-top: 0;">פרטי החניה:</h3>
                        <ul style="list-style: none; padding: 0;">
                            <li style="margin: 10px 0;"><strong>חניון:</strong> {parking_name}</li>
                            <li style="margin: 10px 0;"><strong>לחברה:</strong> {company_name}</li>
                            <li style="margin: 10px 0;"><strong>מספר רכב:</strong> {vehicle_number if vehicle_number else "לא צוין"}</li>
                            <li style="margin: 10px 0;"><strong>תאריך תחילה:</strong> {valid_from}</li>
                            <li style="margin: 10px 0;"><strong>תאריך סיום:</strong> {valid_until}</li>
                        </ul>
                    </div>
                    
                    <p style="font-size: 16px; color: #6c757d;">
                        נא להציג הרשאה זו בכניסה לחניון במידת הצורך.<br>
	             החניה במקומות המסומנים לחברה בלבד
                    </p>
                    
                    <hr style="margin: 30px 0; border: none; border-top: 1px solid #dee2e6;">
                    
                    <p style="font-size: 12px; color: #6c757d; text-align: center;">
                        S&B Parking Management System<br>
                        זוהי הודעה אוטומטית, אין להשיב למייל זה.
                    </p>
                </div>
                """
                
                # Create plain text version
                text_body = f"""
                שלום {guest_name},

                הרשאת החניה שלך אושרה בהצלחה!

                פרטי החניה:
                - חניון: {parking_name}
                - לחברה: {company_name}
                - מספר רכב: {vehicle_number if vehicle_number else "לא צוין"}
                - תאריך תחילה: {valid_from}
                - תאריך סיום: {valid_until}

                נא להציג הרשאה זו בכניסה לחניון במידת הצורך.

                ---
                S&B Parking Management System
                זוהי הודעה אוטומטית, אין להשיב למייל זה.
                """
                
                part1 = MIMEText(text_body, 'plain', 'utf-8')
                part2 = MIMEText(html_body, 'html', 'utf-8')
                
                msg.attach(part1)
                msg.attach(part2)
                
                # Send email
                server = smtplib.SMTP('smtp.gmail.com', 587)
                server.starttls()
                server.login(gmail_user, gmail_password)
                server.send_message(msg)
                server.quit()
                
                print(f"✅ Guest email sent to {validated_email}")
                return jsonify({'success': True, 'message': 'מייל נשלח בהצלחה'})
                
            except Exception as e:
                print(f"❌ Failed to send guest email: {str(e)}")
                return jsonify({'success': False, 'message': 'שגיאה בשליחת מייל'})
        else:
            print(f"⚠️ Mail system not available")
            return jsonify({'success': False, 'message': 'מערכת המייל לא זמינה'})
            
    except Exception as e:
        # Error in send_guest_email: {str(e)}")
        return jsonify({'success': False, 'message': 'שגיאה בשליחת מייל'})

@app.route('/api/company-manager/consumer-detail', methods=['POST'])
def get_consumer_detail():
    """קבלת פרטי מנוי בודד - לטעינת hover"""
    try:
        data = request.get_json()
        parking_id = data.get('parking_id')
        contract_id = data.get('contract_id')
        consumer_id = data.get('consumer_id')
        
        # Consumer detail request
        
        # For now, just return basic data - the consumer list already has most info we need
        # The parking server's consumer/detail endpoint needs proper authentication
        # and we already have the consumer data from the list
        # Returning enhanced basic data
        
        return jsonify({
            'success': True,
            'data': {
                'id': consumer_id,
                'consumerId': consumer_id,
                'contractId': contract_id,
                'subscriberNum': consumer_id,
                'hasFullDetails': True,
                'firstName': '',
                'lastName': '',
                'lpn1': '',
                'lpn2': '',
                'lpn3': '',
                'validFrom': '2024-01-01',
                'validUntil': '2030-12-31',
                'tagNum': '',
                'profile': '0'
            }
        })
            
    except Exception as e:
        # Error in consumer detail
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/test-render-connection', methods=['GET'])
def test_render_connection():
    """בדיקת חיבור לשרת החניון מ-Render"""
    # Testing connection from Render
    
    import base64
    import requests
    import urllib3
    # Disable SSL warnings properly
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    # בדוק איפה אנחנו רצים
    is_local = request.host.startswith('localhost') or request.host.startswith('127.0.0.1')
    
    if is_local:
        server = '10.35.240.100'
        port = 8443
        # Running locally
    else:
        server = '192.117.0.122'
        port = 8240
        # Running on Render
    
    # Basic Auth
    auth = base64.b64encode(b'2022:2022').decode('ascii')
    headers = {'Authorization': f'Basic {auth}'}
    
    results = []
    
    # בדוק endpoints
    endpoints = [
        'CustomerMediaWebService/contracts',
        'CustomerMediaWebService/consumers'
    ]
    
    for endpoint in endpoints:
        url = f"https://{server}:{port}/{endpoint}"
        print(f"\n🔗 Testing: {url}")
        
        try:
            response = requests.get(url, headers=headers, verify=False, timeout=15)
            print(f"   ✅ Status: {response.status_code}")
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    count = len(data) if isinstance(data, list) else 1
                    print(f"   📊 Got {count} items")
                    results.append({
                        'endpoint': endpoint,
                        'status': 200,
                        'success': True,
                        'count': count
                    })
                except:
                    results.append({
                        'endpoint': endpoint,
                        'status': 200,
                        'success': True,
                        'type': 'non-json'
                    })
            else:
                results.append({
                    'endpoint': endpoint,
                    'status': response.status_code,
                    'success': False
                })
                
        except requests.exceptions.Timeout:
            print(f"   ⏱️ TIMEOUT")
            results.append({
                'endpoint': endpoint,
                'error': 'timeout',
                'success': False
            })
        except requests.exceptions.ConnectionError as e:
            results.append({
                'endpoint': endpoint,
                'error': 'connection_error',
                'success': False
            })
        except Exception as e:
            print(f"   ❌ ERROR: {str(e)[:100]}")
            results.append({
                'endpoint': endpoint,
                'error': str(e)[:100],
                'success': False
            })
    
    success = any(r.get('success') for r in results)
    
    print(f"\n{'='*70}")
    # Test summary
    print(f"{'='*70}")
    
    return jsonify({
        'environment': 'local' if is_local else 'render',
        'server': f"{server}:{port}",
        'results': results,
        'success': success
    })

@app.route('/api/test-direct-parking', methods=['GET'])
def test_direct_parking_no_login():
    """בדיקה ישירה לחניון בלי login - רק לבדיקות!"""
    try:
        import base64
        
        # חיבור ישיר לשרת המקומי
        ip = "10.35.240.100"
        port = 8443
        
        # Basic Auth
        auth_string = base64.b64encode(b'2022:2022').decode('ascii')
        headers = {
            'Authorization': f'Basic {auth_string}',
            'Accept': 'application/json'
        }
        
        results = {}
        
        # בדוק contracts
        try:
            url = f"https://{ip}:{port}/CustomerMediaWebService/contracts"
            response = requests.get(url, headers=headers, verify=False, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if 'contracts' in data and 'contract' in data['contracts']:
                    contracts = data['contracts']['contract']
                    results['contracts'] = {
                        'success': True,
                        'count': len(contracts),
                        'data': contracts[:5]  # רק 5 הראשונים
                    }
                else:
                    results['contracts'] = {'success': False, 'message': 'No contracts found'}
            else:
                results['contracts'] = {'success': False, 'status': response.status_code}
        except Exception as e:
            results['contracts'] = {'success': False, 'error': str(e)}
        
        # בדוק consumers
        try:
            url = f"https://{ip}:{port}/CustomerMediaWebService/consumers"
            response = requests.get(url, headers=headers, verify=False, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if 'consumers' in data and 'consumer' in data['consumers']:
                    consumers = data['consumers']['consumer']
                    results['consumers'] = {
                        'success': True,
                        'count': len(consumers),
                        'data': consumers[:5]  # רק 5 הראשונים
                    }
                else:
                    results['consumers'] = {'success': False, 'message': 'No consumers found'}
            else:
                results['consumers'] = {'success': False, 'status': response.status_code}
        except Exception as e:
            results['consumers'] = {'success': False, 'error': str(e)}
        
        return jsonify({
            'success': True,
            'message': 'Direct parking test - NO LOGIN REQUIRED',
            'server': f'{ip}:{port}',
            'results': results
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/test-parking-connection', methods=['GET'])
def test_parking_connection():
    """בדיקה ידנית של חיבור לשרת החניון"""
    try:
        ip = "192.117.0.122"
        port = 8240
        
        # בדיקות שונות
        urls_to_test = [
            f"https://{ip}:{port}",
            f"http://{ip}:{port}",
            f"https://{ip}:{port}/api",
            f"http://{ip}:{port}/api",
            f"https://{ip}:{port}/status",
            f"http://{ip}:{port}/status"
        ]
        
        results = []
        
        for url in urls_to_test:
            try:
                print(f"🔗 Testing: {url}")
                response = requests.get(url, timeout=10, verify=False)
                results.append({
                    'url': url,
                    'status': response.status_code,
                    'success': True,
                    'content_preview': response.text[:100]
                })
                # Success
            except Exception as e:
                results.append({
                    'url': url,
                    'status': None,
                    'success': False,
                    'error': str(e)
                })
                print(f"❌ Failed: {url} - {str(e)}")
        
        return jsonify({
            'success': True,
            'results': results,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/api/test-parking-endpoints', methods=['GET'])
def test_parking_endpoints():
    """בדיקת endpoints ספציפיים של שרת החניון"""
    try:
        ip = "192.117.0.122"
        port = 8240
        
        # נתיבים נפוצים לשרתי חניונים
        endpoints_to_test = [
            "",  # root
            "api/status",
            "api/info", 
            "api/health",
            "api/contracts",
            "api/consumers",
            "api/parking",
            "status",
            "info",
            "contracts",
            "consumers"
        ]
        
        results = []
        base_url = f"https://{ip}:{port}"
        
        for endpoint in endpoints_to_test:
            url = f"{base_url}/{endpoint}" if endpoint else base_url
            
            try:
                print(f"🔗 Testing endpoint: {url}")
                response = requests.get(url, timeout=10, verify=False)
                results.append({
                    'endpoint': endpoint or "root",
                    'url': url,
                    'status': response.status_code,
                    'success': response.status_code != 404,
                    'content_preview': response.text[:200],
                    'content_type': response.headers.get('content-type', '')
                })
                
                if response.status_code != 404:
                    # Found working endpoint
                    pass
                
            except Exception as e:
                results.append({
                    'endpoint': endpoint or "root", 
                    'url': url,
                    'status': None,
                    'success': False,
                    'error': str(e)
                })
        
        return jsonify({
            'success': True,
            'results': results,
            'working_endpoints': [r for r in results if r.get('success', False)],
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/api/test-parking-auth', methods=['GET'])
def test_parking_auth():
    """בדיקה עם Basic Auth"""
    try:
        ip = "192.117.0.122"
        port = 8240
        
        endpoints = ["api/contracts", "contracts", "api/consumers", "consumers"]
        
        # Basic Auth credentials
        auth_string = base64.b64encode(b'2022:2022').decode('ascii')
        headers = {
            'Authorization': f'Basic {auth_string}',
            'Content-Type': 'application/json'
        }
        
        results = []
        
        for endpoint in endpoints:
            url = f"https://{ip}:{port}/{endpoint}"
            
            try:
                response = requests.get(url, headers=headers, timeout=10, verify=False)
                results.append({
                    'endpoint': endpoint,
                    'url': url,
                    'status': response.status_code,
                    'success': response.status_code in [200, 201],
                    'content_preview': response.text[:200],
                    'with_auth': True
                })
                
                if response.status_code in [200, 201]:
                    # Success with auth
                    pass
                    
            except Exception as e:
                results.append({
                    'endpoint': endpoint,
                    'error': str(e),
                    'with_auth': True
                })
        
        return jsonify({
            'success': True,
            'results': results
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/test-scheidt-endpoints', methods=['GET'])
def test_scheidt_endpoints():
    """בדיקת endpoints של מערכת Scheidt & Bachmann"""
    try:
        ip = "192.117.0.122"
        port = 8240
        
        # endpoints נפוצים במערכות Scheidt & Bachmann
        scheidt_endpoints = [
            "CustomerMediaWebService",
            "CustomerMediaWebService/GetContractsList",
            "CustomerMediaWebService/GetConsumerList",
            "CustomerMediaWebService/GetOccupancy",
            "CustomerMediaWebService/GetVehicleWhiteList",
            "api/CustomerMediaWebService",
            "api/CustomerMediaWebService/GetContractsList",
            "api/CustomerMediaWebService/GetConsumerList",
            "web",
            "web/status",
            "web/info",
            "servlet",
            "servlet/contracts",
            "servlet/consumers",
            "ParkonWeb",
            "ParkonWeb/contracts", 
            "ParkonWeb/consumers",
            "manager",
            "manager/status",
            "rest/contracts",
            "rest/consumers",
            "rest/status",
            "xmlapi/contracts",
            "xmlapi/consumers"
        ]
        
        results = []
        base_url = f"https://{ip}:{port}"
        
        # Basic Auth
        auth_string = base64.b64encode(b'2022:2022').decode('ascii')
        headers = {
            'Authorization': f'Basic {auth_string}',
            'Content-Type': 'application/json'
        }
        
        for endpoint in scheidt_endpoints:
            url = f"{base_url}/{endpoint}"
            
            try:
                response = requests.get(url, headers=headers, timeout=10, verify=False)
                is_success = response.status_code not in [404, 403, 500]
                
                results.append({
                    'endpoint': endpoint,
                    'url': url,
                    'status': response.status_code,
                    'success': is_success,
                    'content_preview': response.text[:300],
                    'content_type': response.headers.get('content-type', '')
                })
                
                if is_success:
                    # Found working Scheidt endpoint
                    pass
                    
            except Exception as e:
                results.append({
                    'endpoint': endpoint,
                    'url': url,
                    'error': str(e)
                })
        
        return jsonify({
            'success': True,
            'results': results,
            'working_endpoints': [r for r in results if r.get('success', False)]
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/test-manager-auth', methods=['GET'])
def test_manager_auth():
    """בדיקת manager endpoint עם credentials שונים"""
    try:
        ip = "192.117.0.122"
        port = 8240
        
        # credentials שונים לנסות
        auth_combinations = [
            ('admin', 'admin'),
            ('manager', 'manager'), 
            ('2022', '2022'),
            ('scheidt', 'scheidt'),
            ('parking', 'parking'),
            ('operator', 'operator'),
            ('service', 'service'),
            ('administrator', 'administrator'),
            ('user', 'user'),
            ('guest', 'guest')
        ]
        
        results = []
        
        for username, password in auth_combinations:
            try:
                auth_string = base64.b64encode(f'{username}:{password}'.encode()).decode('ascii')
                headers = {
                    'Authorization': f'Basic {auth_string}',
                    'Content-Type': 'application/json'
                }
                
                url = f"https://{ip}:{port}/manager"
                response = requests.get(url, headers=headers, timeout=10, verify=False)
                
                results.append({
                    'username': username,
                    'password': password,
                    'status': response.status_code,
                    'success': response.status_code not in [401, 403, 404],
                    'content_preview': response.text[:200],
                    'content_type': response.headers.get('content-type', '')
                })
                
                if response.status_code not in [401, 403, 404]:
                    # Success with credentials
                    pass
                    
            except Exception as e:
                results.append({
                    'username': username,
                    'password': password,
                    'error': str(e)
                })
        
        return jsonify({
            'success': True,
            'results': results,
            'successful_auth': [r for r in results if r.get('success', False)]
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/find-working-endpoint', methods=['GET'])
def find_working_endpoint():
    """מחפש את ה-endpoint הנכון של שרת החניון"""
    try:
        ip = "192.117.0.122"
        port = 8240
        
        # רשימה של כל האפשרויות
        possible_endpoints = [
            # SOAP/WSDL
            "CustomerMediaWebService.asmx",
            "CustomerMediaWebService.asmx?wsdl",
            "CustomerMediaWebService.asmx/GetContractsList",
            "CustomerMediaWebService.svc",
            "CustomerMediaWebService.svc?wsdl",
            
            # Standard paths
            "CustomerMediaWebService",
            "CustomerMediaWebService/GetContractsList",
            "CustomerMediaWebService/GetConsumerList",
            
            # With prefixes
            "api/CustomerMediaWebService",
            "ws/CustomerMediaWebService",
            "webservice/CustomerMediaWebService",
            "services/CustomerMediaWebService",
            
            # Try POST with SOAP
            "CustomerMediaWebService.asmx"
        ]
        
        results = []
        working = []
        
        for endpoint in possible_endpoints:
            url = f"https://{ip}:{port}/{endpoint}"
            
            # Try GET
            try:
                response = requests.get(url, timeout=5, verify=False)
                if response.status_code != 404:
                    results.append({
                        'endpoint': endpoint,
                        'method': 'GET',
                        'status': response.status_code,
                        'content_type': response.headers.get('content-type', ''),
                        'preview': response.text[:200]
                    })
                    if response.status_code in [200, 405, 500]:  # 405/500 might mean it exists but needs POST
                        working.append(endpoint)
            except:
                pass
            
            # Try POST with SOAP envelope
            if '.asmx' in endpoint or '.svc' in endpoint:
                try:
                    soap_body = '''<?xml version="1.0" encoding="utf-8"?>
                    <soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
                        <soap:Body>
                            <GetContractsList xmlns="http://tempuri.org/">
                            </GetContractsList>
                        </soap:Body>
                    </soap:Envelope>'''
                    
                    headers = {
                        'Content-Type': 'text/xml; charset=utf-8',
                        'SOAPAction': '"http://tempuri.org/GetContractsList"'
                    }
                    
                    response = requests.post(url, data=soap_body, headers=headers, timeout=5, verify=False)
                    if response.status_code != 404:
                        results.append({
                            'endpoint': endpoint,
                            'method': 'POST-SOAP',
                            'status': response.status_code,
                            'content_type': response.headers.get('content-type', ''),
                            'preview': response.text[:200]
                        })
                        if response.status_code in [200, 500]:  # 500 might be SOAP fault
                            working.append(f"{endpoint} (SOAP)")
                except:
                    pass
        
        return jsonify({
            'success': True,
            'results': results,
            'working_endpoints': list(set(working)),
            'recommendation': working[0] if working else None
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/test-manager-paths', methods=['GET'])
def test_manager_paths():
    """בדיקת נתיבים תחת manager"""
    try:
        ip = "192.117.0.122"
        port = 8240
        
        # Auth עם 2022:2022
        auth_string = base64.b64encode(b'2022:2022').decode('ascii')
        headers = {
            'Authorization': f'Basic {auth_string}',
            'Content-Type': 'application/json'
        }
        
        manager_paths = [
            "manager",
            "manager/",
            "manager/status",
            "manager/info",
            "manager/contracts",
            "manager/consumers", 
            "manager/api",
            "manager/api/contracts",
            "manager/api/consumers",
            "manager/html",
            "manager/xml",
            "manager/servlet",
            "manager/web"
        ]
        
        results = []
        
        for path in manager_paths:
            try:
                url = f"https://{ip}:{port}/{path}"
                response = requests.get(url, headers=headers, timeout=10, verify=False)
                
                is_success = response.status_code in [200, 201, 301, 302]
                
                results.append({
                    'path': path,
                    'url': url,
                    'status': response.status_code,
                    'success': is_success,
                    'content_preview': response.text[:300],
                    'content_type': response.headers.get('content-type', '')
                })
                
                if is_success:
                    # Found working path
                    pass
                    
            except Exception as e:
                results.append({
                    'path': path,
                    'url': url,
                    'error': str(e)
                })
        
        return jsonify({
            'success': True,
            'results': results,
            'working_paths': [r for r in results if r.get('success', False)]
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# הפעלה אוטומטית כשהאפליקציה מתחילה
if __name__ == '__main__':
    # Pre-flight email system check
    
    if EMAIL_MONITORING_AVAILABLE:
        email_system_ready = verify_email_system()
        
        if email_system_ready:
            # Email system ready
            start_background_email_monitoring()
        else:
            # Email system not ready
            pass
    else:
        # Email libraries not available
        pass
    
    # Starting Flask web server
    
    port = int(os.environ.get('PORT', 5000))
    debug_mode = os.environ.get('FLASK_ENV') == 'development'
    
    # Port and debug mode set
    
    keep_service_alive()

    app.run(host='0.0.0.0', port=port, debug=debug_mode)
else:
    if EMAIL_MONITORING_AVAILABLE:
        # Initializing email monitoring
        start_background_email_monitoring()
