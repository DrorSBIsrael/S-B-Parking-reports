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
from datetime import datetime, timedelta, timezone

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
    print("ג… Email monitoring libraries loaded successfully")
except ImportError as e:
    EMAIL_MONITORING_AVAILABLE = False
    print(f"ג ן¸ Email monitoring not available: {e}")

ERROR_EMAILS_DISABLED = True
# ׳”׳’׳“׳¨׳•׳× ׳׳™׳™׳׳™׳ ׳׳•׳˜׳•׳׳˜׳™׳™׳ - ׳׳”׳•׳¡׳™׳£ ׳׳—׳¨׳™ ׳”׳”׳’׳“׳¨׳•׳× ׳”׳§׳™׳™׳׳•׳×:
if EMAIL_MONITORING_AVAILABLE:
    EMAIL_CHECK_INTERVAL = 5  # ׳‘׳“׳™׳§׳” ׳›׳ 5 ׳“׳§׳•׳×
    PROCESSED_EMAILS_LIMIT = 100  # ׳׳§׳¡׳™׳׳•׳ ׳׳™׳™׳׳™׳ ׳׳–׳›׳•׳¨
    processed_email_ids = []  # ׳¨׳©׳™׳׳” ׳׳–׳›׳•׳¨ ׳׳™׳™׳׳™׳ ׳©׳›׳‘׳¨ ׳¢׳•׳‘׳“׳•
    last_cache_reset = None
password_reset_codes = {}
# ׳¨׳©׳™׳׳× ׳©׳•׳׳—׳™׳ ׳׳•׳¨׳©׳™׳ ׳׳©׳׳™׳—׳× ׳§׳‘׳¦׳™ ׳ ׳×׳•׳ ׳™׳
AUTHORIZED_SENDERS = [
    'Dror@sbparking.co.il',
    'dror@sbparking.co.il',  # case insensitive
    'Report@sbparking.co.il',
    'report@sbparking.co.il'  # case insensitive
]

print("נ€ S&B Parking Application Starting...")

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your-secret-key-here')

# Supabase configuration
SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_ANON_KEY')

print(f"נ” Supabase URL: {'ג… SET' if SUPABASE_URL else 'ג MISSING'}")
print(f"נ” Supabase KEY: {'ג… SET' if SUPABASE_KEY else 'ג MISSING'}")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("ג CRITICAL: Supabase credentials missing!")
    print("ג ן¸ Starting anyway to show error page...")
    supabase = None
else:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("ג… Supabase connection established")
    except Exception as e:
        print(f"ג Supabase connection failed: {e}")
        supabase = None

# ׳”׳’׳“׳¨׳•׳× ׳׳™׳™׳ ׳¢׳ Gmail + Environment Variables
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
app.config['MAIL_USE_SSL'] = os.environ.get('MAIL_USE_SSL', 'False').lower() == 'true'
app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'True').lower() == 'true'
app.config['MAIL_USERNAME'] = os.environ.get('GMAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('GMAIL_APP_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('GMAIL_USERNAME')
app.config['MAIL_SUPPRESS_SEND'] = False
app.config['MAIL_DEBUG'] = True

print(f"נ“§ Gmail Username: {'ג… SET' if app.config['MAIL_USERNAME'] else 'ג MISSING'}")
print(f"נ”‘ Gmail Password: {'ג… SET' if app.config['MAIL_PASSWORD'] else 'ג MISSING'}")

try:
    mail = Mail(app)
    print("ג… Mail system initialized")
except Exception as e:
    print(f"ג ן¸ Mail system initialization failed: {e}")
    mail = None

# ׳”׳’׳ ׳•׳× ׳׳‘׳˜׳—׳”
def validate_input(input_text, input_type="general"):
    """׳׳™׳׳•׳× ׳§׳׳˜ ׳׳₪׳ ׳™ SQL Injection ׳•׳×׳§׳™׳₪׳•׳× ׳׳—׳¨׳•׳×"""
    
    if not input_text:
        return False, "׳©׳“׳” ׳¨׳™׳§"
    
    # ׳”׳’׳ ׳” ׳‘׳¡׳™׳¡׳™׳× - ׳”׳¡׳¨׳× ׳×׳•׳•׳™׳ ׳׳¡׳•׳›׳ ׳™׳
    input_text = html.escape(input_text.strip())
    
    # ׳¨׳©׳™׳׳× ׳׳™׳׳™׳ ׳׳¡׳•׳›׳ ׳•׳× (SQL Injection)
    dangerous_words = [
        'select', 'insert', 'update', 'delete', 'drop', 'create', 'alter',
        'union', 'join', 'exec', 'execute', 'script', 'declare', 'cast',
        'convert', 'begin', 'end', 'if', 'else', 'while', 'waitfor',
        'shutdown', 'sp_', 'xp_', 'cmdshell', 'openrowset', 'opendatasource'
    ]
    
    # ׳‘׳“׳™׳§׳× ׳׳™׳׳™׳ ׳׳¡׳•׳›׳ ׳•׳×
    lower_input = input_text.lower()
    for word in dangerous_words:
        if word in lower_input:
            print(f"נ¨ Security threat detected: '{word}' in input")
            return False, f"׳§׳׳˜ ׳׳ ׳—׳•׳§׳™ - ׳׳›׳™׳ ׳׳™׳׳” ׳׳¡׳•׳¨׳”: {word}"
    
    # ׳‘׳“׳™׳§׳× ׳×׳•׳•׳™׳ ׳׳¡׳•׳›׳ ׳™׳
    dangerous_chars = ["'", '"', ';', '--', '/*', '*/', '<', '>', '&', '|', '`']
    for char in dangerous_chars:
        if char in input_text:
            print(f"נ¨ Security threat detected: '{char}' character in input")
            return False, f"׳§׳׳˜ ׳׳ ׳—׳•׳§׳™ - ׳׳›׳™׳ ׳×׳• ׳׳¡׳•׳¨: {char}"
    
    # ׳׳™׳׳•׳× ׳׳₪׳™ ׳¡׳•׳’ ׳”׳§׳׳˜
    if input_type == "username":
        if not re.match(r'^[a-zA-Z0-9._]+$', input_text):
            return False, "׳©׳ ׳׳©׳×׳׳© ׳™׳›׳•׳ ׳׳”׳›׳™׳ ׳¨׳§ ׳׳•׳×׳™׳•׳× ׳‘׳׳ ׳’׳׳™׳×, ׳׳¡׳₪׳¨׳™׳, ׳ ׳§׳•׳“׳” ׳•׳§׳• ׳×׳—׳×׳•׳"
        if len(input_text) < 3 or len(input_text) > 50:
            return False, "׳©׳ ׳׳©׳×׳׳© ׳—׳™׳™׳‘ ׳׳”׳™׳•׳× ׳‘׳™׳ 3-50 ׳×׳•׳•׳™׳"
    
    elif input_type == "password":
        if len(input_text) < 4 or len(input_text) > 100:
            return False, "׳¡׳™׳¡׳׳” ׳—׳™׳™׳‘׳× ׳׳”׳™׳•׳× ׳‘׳™׳ 4-100 ׳×׳•׳•׳™׳"
    
    elif input_type == "email":
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, input_text):
            return False, "׳›׳×׳•׳‘׳× ׳׳™׳׳™׳™׳ ׳׳ ׳×׳§׳™׳ ׳”"
    
    elif input_type == "verification_code":
        if not re.match(r'^[0-9]{6}$', input_text):
            return False, "׳§׳•׳“ ׳׳™׳׳•׳× ׳—׳™׳™׳‘ ׳׳”׳™׳•׳× 6 ׳¡׳₪׳¨׳•׳× ׳‘׳׳‘׳“"
    
    return True, input_text

def rate_limit_check(identifier, max_attempts=5, time_window=300):
    """׳‘׳“׳™׳§׳× ׳”׳’׳‘׳׳× ׳§׳¦׳‘ - ׳׳•׳ ׳¢ ׳”׳×׳§׳₪׳•׳× brute force"""
    print(f"נ” Rate limit check for: {identifier}")
    return True

def generate_verification_code():
    """׳™׳¦׳™׳¨׳× ׳§׳•׳“ ׳׳™׳׳•׳× ׳©׳ 6 ׳¡׳₪׳¨׳•׳×"""
    return ''.join(random.choices(string.digits, k=6))

def store_verification_code(email, code):
    """׳©׳׳™׳¨׳× ׳§׳•׳“ ׳׳™׳׳•׳× ׳‘׳˜׳‘׳׳× user_parkings ׳”׳§׳™׳™׳׳×"""
    if not supabase:
        print("ג Supabase not available")
        return False
        
    try:
        # ׳׳™׳׳•׳× ׳׳™׳׳™׳™׳ ׳׳₪׳ ׳™ ׳©׳׳™׳¨׳”
        is_valid, validated_email = validate_input(email, "email")
        if not is_valid:
            print(f"ג Invalid email format: {email}")
            return False
        
        # ׳—׳™׳©׳•׳‘ ׳–׳׳ ׳×׳₪׳•׳’׳” (10 ׳“׳§׳•׳× ׳׳¢׳›׳©׳™׳•)
        expires_at = datetime.now() + timedelta(minutes=10)
        expires_str = expires_at.strftime('%Y-%m-%d %H:%M:%S')
        
        print(f"נ”„ Updating user_parkings for {validated_email} with code {code}")
        
        # ׳©׳™׳׳•׳© ׳‘-Supabase ׳¢׳ ׳₪׳¨׳׳˜׳¨׳™׳ ׳‘׳˜׳•׳—׳™׳
        result = supabase.table('user_parkings').update({
            'verification_code': code,
            'code_expires_at': expires_str
        }).eq('email', validated_email).execute()
        
        print(f"ג… Update result: {result.data}")
        print(f"ג… Code saved: {code} expires at {expires_str}")
        return True
        
    except Exception as e:
        print(f"ג Failed to save code: {str(e)}")
        return False

def send_verification_email(email, code):
    """׳©׳׳™׳—׳× ׳׳™׳™׳ ׳¢׳ Gmail + App Password ׳-Environment Variables"""
    
    if not mail:
        print(f"ג Mail system not available")
        print(f"נ“± BACKUP CODE for {email}: {code}")
        return False
    
    # ׳׳™׳׳•׳× ׳׳™׳׳™׳™׳
    is_valid, validated_email = validate_input(email, "email")
    if not is_valid:
        print(f"ג Invalid email format: {email}")
        return False
    
    # ׳‘׳“׳™׳§׳” ׳©׳™׳© ׳ ׳×׳•׳ ׳™׳
    if not app.config['MAIL_USERNAME'] or not app.config['MAIL_PASSWORD']:
        print(f"ג Gmail credentials missing in environment variables")
        print(f"נ“± BACKUP CODE for {validated_email}: {code}")
        return False
    
    try:
        print(f"נ€ Starting Gmail send to {validated_email}...")
        
        msg = Message(
            subject='׳§׳•׳“ ׳׳™׳׳•׳× - S&B Parking',
            recipients=[validated_email],
            html=f"""
            <div style="font-family: Arial, sans-serif; direction: rtl; text-align: right;">
                <h2 style="color: #667eea;">׳©׳™׳™׳“׳˜ ׳׳× ׳‘׳›׳׳ ׳™׳©׳¨׳׳</h2>
                <h3>׳§׳•׳“ ׳”׳׳™׳׳•׳× ׳©׳׳:</h3>
                <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; text-align: center; margin: 20px 0;">
                    <span style="font-size: 32px; font-weight: bold; color: #667eea; letter-spacing: 5px;">{code}</span>
                </div>
                <p>׳”׳§׳•׳“ ׳×׳§׳£ ׳-10 ׳“׳§׳•׳× ׳‘׳׳‘׳“.</p>
                <p>׳׳ ׳׳ ׳‘׳™׳§׳©׳× ׳§׳•׳“ ׳–׳”, ׳”׳×׳¢׳׳ ׳׳”׳•׳“׳¢׳” ׳–׳•.</p>
                <hr>
                <p style="color: #666; font-size: 12px;">S&B Parking - ׳׳¢׳¨׳›׳× ׳“׳•׳—׳•׳× ׳—׳ ׳™׳•׳×</p>
            </div>
            """,
            sender=app.config['MAIL_USERNAME']
        )
        
        print(f"נ”„ Sending via Gmail...")
        mail.send(msg)
        
        print(f"ג… Gmail email sent successfully to {validated_email}")
        return True
        
    except Exception as e:
        print(f"ג Gmail error: {str(e)}")
        print(f"נ“± BACKUP CODE for {validated_email}: {code}")
        return False

def verify_code_from_database(email, code):
    """׳‘׳“׳™׳§׳× ׳§׳•׳“ ׳׳™׳׳•׳× ׳׳˜׳‘׳׳× user_parkings"""
    if not supabase:
        print("ג Supabase not available")
        return False
        
    try:
        # ׳׳™׳׳•׳× ׳§׳׳˜
        is_valid_email, validated_email = validate_input(email, "email")
        is_valid_code, validated_code = validate_input(code, "verification_code")
        
        if not is_valid_email:
            print(f"ג Invalid email format: {email}")
            return False
            
        if not is_valid_code:
            print(f"ג Invalid code format: {code}")
            return False
        
        # ׳—׳™׳₪׳•׳© ׳׳©׳×׳׳© ׳¢׳ ׳”׳§׳•׳“
        result = supabase.table('user_parkings').select('verification_code, code_expires_at').eq('email', validated_email).execute()
        
        if not result.data:
            print(f"ג No user found for {validated_email}")
            return False
            
        user_data = result.data[0]
        stored_code = user_data.get('verification_code')
        expires_at_str = user_data.get('code_expires_at')
        
        print(f"נ” Code verification attempt for {validated_email}")
        
        if not stored_code or stored_code != validated_code:
            print(f"ג Code mismatch")
            return False
            
        # ׳‘׳“׳™׳§׳× ׳×׳•׳§׳£
        if expires_at_str:
            expires_at = datetime.fromisoformat(expires_at_str.replace('Z', '').replace('+00:00', ''))
            if datetime.now() > expires_at:
                print(f"ג Code expired")
                return False
        
        # ׳׳—׳™׳§׳× ׳”׳§׳•׳“ ׳׳—׳¨׳™ ׳©׳™׳׳•׳© ׳׳•׳¦׳׳—
        supabase.table('user_parkings').update({
            'verification_code': None,
            'code_expires_at': None
        }).eq('email', validated_email).execute()
        
        print(f"ג… Code verified and cleared for {validated_email}")
        return True
        
    except Exception as e:
        print(f"ג Database verification failed: {str(e)}")
        return False
def connect_to_gmail_imap():
    """׳”׳×׳—׳‘׳¨׳•׳× ׳-Gmail IMAP"""
    if not EMAIL_MONITORING_AVAILABLE:
        return None
        
    try:
        mail = imaplib.IMAP4_SSL('imap.gmail.com')
        
        gmail_user = os.environ.get('GMAIL_USERNAME')
        gmail_password = os.environ.get('GMAIL_APP_PASSWORD')
        
        # ׳×׳™׳§׳•׳ type checking - ׳•׳™׳“׳•׳ ׳©׳”׳׳©׳×׳ ׳™׳ ׳׳ None
        if not gmail_user or not gmail_password:
            print("ג Missing Gmail credentials in environment variables")
            return None
            
        mail.login(gmail_user, gmail_password)
        print(f"ג… Connected to Gmail: {gmail_user}")
        
        return mail
        
    except Exception as e:
        print(f"ג Gmail IMAP connection failed: {str(e)}")
        return None

def download_csv_from_email(msg):
    """׳”׳•׳¨׳“׳× ׳§׳•׳‘׳¥ CSV ׳׳”׳׳™׳™׳ - ׳©׳׳™׳¨׳× bytes ׳׳§׳•׳¨׳™׳™׳ ׳׳–׳™׳”׳•׳™ ׳§׳™׳“׳•׳“"""
    csv_files = []
    
    try:
        for part in msg.walk():
            if part.get_content_disposition() == 'attachment':
                filename = part.get_filename()
                
                if filename and (filename.lower().endswith('.csv') or filename.lower().endswith('.txt')):
                    file_data = part.get_payload(decode=True)
                    
                    if file_data:
                        # ׳©׳׳™׳¨׳× ׳”׳‘׳™׳™׳˜׳™׳ ׳”׳׳§׳•׳¨׳™׳™׳ - ׳׳ ׳ ׳׳™׳¨ ׳string ׳›׳׳!
                        csv_files.append({
                            'filename': filename,
                            'data': file_data  # ׳ ׳©׳׳™׳¨ ׳׳× ׳–׳” ׳›-bytes
                        })
                        
                        print(f"נ“ Found CSV attachment: {filename} ({len(file_data)} bytes)")
        
        return csv_files
        
    except Exception as e:
        print(f"ג Error downloading CSV: {str(e)}")
        return []

def parse_csv_content(csv_content):
    """׳₪׳¨׳¡׳•׳¨ CSV ׳¢׳ ׳–׳™׳”׳•׳™ ׳§׳™׳“׳•׳“ ׳׳•׳˜׳•׳׳˜׳™ ׳׳¢׳‘׳¨׳™׳× ׳•׳׳™׳׳•׳× ׳×׳§׳™׳ ׳•׳×"""
    try:
        print(f"נ” Input type: {type(csv_content)}")
        
        # ׳׳ ׳–׳” bytes, ׳ ׳ ׳¡׳” ׳§׳™׳“׳•׳“׳™׳ ׳©׳•׳ ׳™׳
        if isinstance(csv_content, bytes):
            # ׳¨׳©׳™׳׳× ׳§׳™׳“׳•׳“׳™׳ ׳׳ ׳™׳¡׳™׳•׳ - ׳”׳¢׳‘׳¨׳™׳× ׳§׳•׳“׳
            encodings_to_try = [
                'windows-1255',  # ׳¢׳‘׳¨׳™׳× ANSI
                'cp1255',        # ׳¢׳‘׳¨׳™׳×
                'utf-8-sig',     # UTF-8 ׳¢׳ BOM
                'utf-8',         # UTF-8 ׳¨׳’׳™׳
                'iso-8859-8',    # ׳¢׳‘׳¨׳™׳× ISO
                'cp1252',        # Western European
                'latin1'         # fallback
            ]
            
            decoded_content = None
            used_encoding = None
            
            for encoding in encodings_to_try:
                try:
                    decoded_content = csv_content.decode(encoding)
                    used_encoding = encoding
                    print(f"ג… Successfully decoded with {encoding}")
                    break
                except UnicodeDecodeError:
                    print(f"ג Failed to decode with {encoding}")
                    continue
            
            if decoded_content is None:
                print("ג Could not decode with any encoding - using latin1 as fallback")
                decoded_content = csv_content.decode('latin1', errors='ignore')
                used_encoding = 'latin1'
            
            csv_content = decoded_content
        else:
            used_encoding = 'already_string'
        
        # ׳׳ ׳–׳” ׳׳ string, ׳ ׳׳™׳¨
        if not isinstance(csv_content, str):
            csv_content = str(csv_content)
        
        print(f"נ“‹ Content length: {len(csv_content)}")
        print(f"נ”₪ Used encoding: {used_encoding}")
        
        # ׳ ׳™׳§׳•׳™ ׳‘׳¡׳™׳¡׳™
        csv_content = csv_content.strip()
        if not csv_content:
            print("ג Empty content after decoding")
            return None
        
        # ׳”׳“׳₪׳¡׳× ׳”׳©׳•׳¨׳” ׳”׳¨׳׳©׳•׳ ׳” ׳›׳“׳™ ׳׳‘׳“׳•׳§ ׳¢׳‘׳¨׳™׳×
        first_line = csv_content.split('\n')[0]
        print(f"נ“„ First line: {repr(first_line)}")
        
        # ג ן¸ ׳‘׳“׳™׳§׳× ׳×׳§׳™׳ ׳•׳× CSV - ׳׳ ׳–׳” ׳§׳•׳‘׳¥ SQL ׳׳• ׳׳ ׳×׳§׳™׳
        if any(sql_keyword in first_line.lower() for sql_keyword in ['connect', 'insert', 'select', 'values', 'create']):
            print("נ« INVALID FILE: This appears to be a SQL file, not a CSV file!")
            print(f"נ« First line contains SQL keywords: {first_line}")
            return None
        
        # ׳‘׳“׳™׳§׳” ׳©׳™׳© ׳›׳•׳×׳¨׳•׳× CSV ׳×׳§׳™׳ ׳•׳×
        if 'ProjectNumber' not in first_line:
            print("נ« INVALID CSV: Missing expected header 'ProjectNumber'")
            print(f"נ« First line: {first_line}")
            return None
        
        # ׳׳ ׳™׳© ׳¢׳‘׳¨׳™׳× ׳‘׳©׳•׳¨׳” ׳”׳¨׳׳©׳•׳ ׳”, ׳ ׳“׳•׳•׳— ׳¢׳ ׳›׳
        if any('\u0590' <= char <= '\u05FF' for char in first_line):
            print("נ‡®נ‡± Hebrew characters detected in header")
        
        # ׳ ׳™׳¡׳™׳•׳ ׳₪׳¨׳¡׳•׳¨ ׳₪׳©׳•׳˜ ׳¢׳ ׳₪׳¡׳™׳§
        try:
            reader = csv.DictReader(io.StringIO(csv_content))
            rows = list(reader)
            print(f"נ“ Parsed {len(rows)} rows with comma delimiter")
            
            if rows:
                columns = list(rows[0].keys())
                print(f"נ“‹ Columns: {columns}")
                
                # ׳‘׳“׳™׳§׳” ׳ ׳•׳¡׳₪׳× - ׳׳ ׳”׳©׳•׳¨׳” ׳”׳¨׳׳©׳•׳ ׳” ׳¨׳™׳§׳” ׳׳• ׳׳ ׳×׳§׳™׳ ׳”
                if not rows or not any(rows[0].values()):
                    print("נ« INVALID CSV: First data row is empty or invalid")
                    return None
                
                # ׳‘׳“׳™׳§׳” ׳׳ ׳™׳© ׳¢׳‘׳¨׳™׳× ׳‘׳ ׳×׳•׳ ׳™׳
                for i, row in enumerate(rows[:3]):  # ׳‘׳“׳™׳§׳× 3 ׳©׳•׳¨׳•׳× ׳¨׳׳©׳•׳ ׳•׳×
                    for key, value in row.items():
                        if value and any('\u0590' <= char <= '\u05FF' for char in str(value)):
                            print(f"נ‡®נ‡± Hebrew text found in row {i+1}, column '{key}': {value}")
                            break
                
                return rows
        except Exception as e:
            print(f"ג Comma parsing failed: {e}")
        
        # ׳׳ ׳”׳’׳¢׳ ׳• ׳׳›׳׳, ׳”׳§׳•׳‘׳¥ ׳׳ ׳×׳§׳™׳
        print("נ« INVALID CSV: Could not parse as valid CSV file")
        return None
        
    except Exception as e:
        print(f"ג General error in CSV parsing: {e}")
        return None

def convert_to_csv_import_format(csv_rows):
    """׳”׳׳¨׳” ׳׳₪׳•׳¨׳׳˜ csv_import_shekels - ׳¢׳ ׳×׳׳™׳›׳” ׳‘׳©׳•׳¨׳•׳× ׳׳¨׳•׳‘׳•׳×"""
    converted_rows = []
    
    print(f"נ”„ Processing {len(csv_rows)} rows from CSV...")
    
    for index, row in enumerate(csv_rows):
        try:
            print(f"נ“ Processing row {index + 1}/{len(csv_rows)}...")
            
            # ׳”׳׳¨׳× ׳×׳׳¨׳™׳
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
                
            # ׳”׳׳¨׳× ׳ ׳×׳•׳ ׳™ ׳›׳¡׳£ - ׳”׳¢׳¨׳›׳™׳ ׳›׳‘׳¨ ׳‘׳©׳§׳׳™׳!
            def safe_int(value, default=0):
                try:
                    if value is None or value == '':
                        return default
                    return int(float(str(value)))
                except (ValueError, TypeError):
                    return default
            
            # ׳”׳¢׳¨׳›׳™׳ ׳›׳‘׳¨ ׳‘׳©׳§׳׳™׳ - ׳׳ ׳¦׳¨׳™׳ ׳—׳™׳©׳•׳‘׳™׳!
            cash_shekels = safe_int(row.get('SCASH'))
            credit_shekels = safe_int(row.get('SCREDIT'))
            pango_shekels = safe_int(row.get('SPANGO'))
            celo_shekels = safe_int(row.get('SCELO'))
            
            # ׳‘׳“׳™׳§׳× ׳˜׳§׳¡׳˜ ׳‘׳¢׳‘׳¨׳™׳×
            ctext_value = str(row.get('CTEXT', '')).strip()
            if ctext_value and any('\u0590' <= char <= '\u05FF' for char in ctext_value):
                print(f"נ‡®נ‡± Hebrew text in row {index + 1}: '{ctext_value}'")
            
            converted_row = {
                'project_number': str(row.get('ProjectNumber', '')),
                'l_global_ref': safe_int(row.get('LGLOBALREF')),
                's_computer': safe_int(row.get('SCOMPUTER')),
                's_shift_id': safe_int(row.get('SSHIFTID')),
                'report_start_time': str(row.get('TTCRET', '')),
                'report_end_time': str(row.get('TTENDT', '')),
                'report_date': formatted_date,
                'ctext': ctext_value,
                
                # ׳›׳¡׳£ ׳‘׳©׳§׳׳™׳ (׳ ׳©׳׳•׳¨ ׳›׳׳’׳•׳¨׳•׳× ׳‘׳©׳“׳•׳× ׳”׳׳׳•)
                's_cash_agorot': cash_shekels,
                's_credit_agorot': credit_shekels,
                's_pango_agorot': pango_shekels,
                's_celo_agorot': celo_shekels,
                'stot_cacr': safe_int(row.get('STOTCACR')),
                's_exp_agorot': safe_int(row.get('SEXP')),
                
                # ׳׳§׳•׳“׳“׳™׳
                's_encoder1': safe_int(row.get('SENCODER1')),
                's_encoder2': safe_int(row.get('SENCODER2')),
                's_encoder3': safe_int(row.get('SENCODER3')),
                'sencodertot': safe_int(row.get('SENCODERTOT')),
                
                # ׳×׳ ׳•׳¢׳”
                't_open_b': safe_int(row.get('TOPENB')),
                't_entry_s': safe_int(row.get('TENTRYS')),
                't_entry_p': safe_int(row.get('TENTRYP')),
                't_entry_tot': safe_int(row.get('TENTRYTOT')),
                't_exit_s': safe_int(row.get('TEEITS')),
                't_exit_p': safe_int(row.get('TEEITP')),
                't_exit_tot': safe_int(row.get('TEEITTOT')),
                't_entry_ap': safe_int(row.get('TENTRYAP')),
                't_exit_ap': safe_int(row.get('TEEITAP')),
                
                # ׳–׳׳ ׳™ ׳©׳”׳™׳™׳”
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
                
                # ׳׳˜׳-׳“׳˜׳”
                'created_at': datetime.now().isoformat(),
                'uploaded_by': 'email_automation'
            }
            
            converted_rows.append(converted_row)
            
            print(f"ג… Row {index+1}: project {converted_row['project_number']}, cash: {cash_shekels} shekels, text: '{ctext_value}'")
            
        except Exception as e:
            print(f"ג Error converting row {index+1}: {str(e)}")
            print(f"   Row data: {row}")
            continue  # ׳׳׳©׳™׳ ׳׳©׳•׳¨׳” ׳”׳‘׳׳” ׳‘׳׳§׳•׳ ׳׳”׳₪׳¡׳™׳§
    
    print(f"נ¯ Successfully converted {len(converted_rows)} out of {len(csv_rows)} rows")
    return converted_rows

def insert_to_csv_import_shekels(converted_data):
    """׳”׳›׳ ׳¡׳” ׳׳˜׳‘׳׳× csv_import_shekels (׳©׳׳‘ ׳‘׳™׳ ׳™׳™׳) - ׳’׳¨׳¡׳” ׳׳×׳•׳§׳ ׳×"""
    if not supabase:
        print("ג Supabase not available")
        return 0
        
    try:
        print(f"נ”„ Preparing to insert {len(converted_data)} rows to csv_import_shekels")
        
        # ׳׳—׳™׳§׳× ׳ ׳×׳•׳ ׳™׳ ׳™׳©׳ ׳™׳ ׳׳”׳˜׳‘׳׳”
        try:
            print("נ§¹ Clearing old data from csv_import_shekels...")
            delete_result = supabase.table('csv_import_shekels').delete().gt('id', 0).execute()
            print("ג… Old data cleared successfully")
        except Exception as e:
            print(f"ג ן¸ Could not clear old data: {str(e)}")
            # ׳׳׳©׳™׳›׳™׳ ׳’׳ ׳׳ ׳”׳׳—׳™׳§׳” ׳ ׳›׳©׳׳”
        
        # ׳ ׳™׳§׳•׳™ ׳”׳ ׳×׳•׳ ׳™׳ - ׳”׳¡׳¨׳× ׳©׳“׳•׳× ׳©׳׳ ׳¦׳¨׳™׳›׳™׳ ׳•׳•׳™׳“׳•׳ ׳×׳§׳™׳ ׳•׳×
        cleaned_data = []
        
        for i, row in enumerate(converted_data):
            try:
                # ׳™׳¦׳™׳¨׳× ׳©׳•׳¨׳” ׳ ׳§׳™׳™׳” ׳¢׳ ׳”׳›׳ ׳”׳¢׳¨׳›׳™׳ ׳”׳ ׳“׳¨׳©׳™׳
                cleaned_row = {
                    'project_number': str(row.get('project_number', '')).strip(),
                    'l_global_ref': int(row.get('l_global_ref', 0)),
                    's_computer': int(row.get('s_computer', 0)),
                    's_shift_id': int(row.get('s_shift_id', 0)),
                    'report_start_time': str(row.get('report_start_time', '')).strip(),
                    'report_end_time': str(row.get('report_end_time', '')).strip(),
                    'report_date': str(row.get('report_date', '')).strip(),
                    'ctext': str(row.get('ctext', '')).strip(),
                    
                    # ׳›׳¡׳£ ׳‘׳©׳§׳׳™׳
                    's_cash_shekels': float(row.get('s_cash_shekels', 0)),
                    's_credit_shekels': float(row.get('s_credit_shekels', 0)),
                    's_pango_shekels': float(row.get('s_pango_shekels', 0)),
                    's_celo_shekels': float(row.get('s_celo_shekels', 0)),
                    'total_revenue_shekels': float(row.get('total_revenue_shekels', 0)),
                    'net_revenue_shekels': float(row.get('net_revenue_shekels', 0)),
                    
                    # ׳›׳¡׳£ ׳‘׳׳’׳•׳¨׳•׳×
                    's_cash_agorot': int(row.get('s_cash_agorot', 0)),
                    's_credit_agorot': int(row.get('s_credit_agorot', 0)),
                    's_pango_agorot': int(row.get('s_pango_agorot', 0)),
                    's_celo_agorot': int(row.get('s_celo_agorot', 0)),
                    'stot_cacr': int(row.get('stot_cacr', 0)),
                    's_exp_agorot': int(row.get('s_exp_agorot', 0)),
                    
                    # ׳׳§׳•׳“׳“׳™׳
                    's_encoder1': int(row.get('s_encoder1', 0)),
                    's_encoder2': int(row.get('s_encoder2', 0)),
                    's_encoder3': int(row.get('s_encoder3', 0)),
                    'sencodertot': int(row.get('sencodertot', 0)),
                    
                    # ׳×׳ ׳•׳¢׳”
                    't_open_b': int(row.get('t_open_b', 0)),
                    't_entry_s': int(row.get('t_entry_s', 0)),
                    't_entry_p': int(row.get('t_entry_p', 0)),
                    't_entry_tot': int(row.get('t_entry_tot', 0)),
                    't_exit_s': int(row.get('t_exit_s', 0)),
                    't_exit_p': int(row.get('t_exit_p', 0)),
                    't_exit_tot': int(row.get('t_exit_tot', 0)),
                    't_entry_ap': int(row.get('t_entry_ap', 0)),
                    't_exit_ap': int(row.get('t_exit_ap', 0)),
                    
                    # ׳–׳׳ ׳™ ׳©׳”׳™׳™׳”
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
                    
                    # ׳׳˜׳-׳“׳˜׳” (created_at ׳•-uploaded_by ׳™׳•׳•׳¦׳¨׳• ׳׳•׳˜׳•׳׳˜׳™׳×)
                }
                
                cleaned_data.append(cleaned_row)
                
            except Exception as row_error:
                print(f"ג Error cleaning row {i}: {str(row_error)}")
                print(f"   Problematic row: {row}")
                continue
        
        if not cleaned_data:
            print("ג No valid data after cleaning")
            return 0
            
        print(f"ג… Cleaned {len(cleaned_data)} rows successfully")
        
        # ׳”׳›׳ ׳¡׳× ׳”׳ ׳×׳•׳ ׳™׳ ׳‘׳§׳‘׳•׳¦׳•׳×
        batch_size = 200
        total_inserted = 0
        
        for i in range(0, len(cleaned_data), batch_size):
            batch = cleaned_data[i:i + batch_size]
            batch_num = i // batch_size + 1
            
            try:
                print(f"נ”„ Inserting batch {batch_num}: {len(batch)} rows")
                
                result = supabase.table('csv_import_shekels').insert(batch).execute()
                
                if result.data:
                    batch_count = len(result.data)
                    total_inserted += batch_count
                    print(f"ג… Batch {batch_num} inserted successfully: {batch_count} rows")
                else:
                    print(f"ג ן¸ Batch {batch_num} returned no data")
                    
            except Exception as batch_error:
                print(f"ג Error in batch {batch_num}: {str(batch_error)}")
                
                # ׳׳ ׳”׳§׳‘׳•׳¦׳” ׳ ׳›׳©׳׳”, ׳ ׳ ׳¡׳” ׳©׳•׳¨׳” ׳׳—׳× ׳‘׳›׳ ׳₪׳¢׳
                print(f"נ”„ Trying individual rows for batch {batch_num}...")
                for j, single_row in enumerate(batch):
                    try:
                        single_result = supabase.table('csv_import_shekels').insert([single_row]).execute()
                        if single_result.data:
                            total_inserted += 1
                            if j % 10 == 0:  # ׳”׳“׳₪׳¡׳” ׳›׳ 10 ׳©׳•׳¨׳•׳×
                                print(f"   ג… Row {i+j+1} inserted")
                    except Exception as single_error:
                        print(f"   ג Row {i+j+1} failed: {str(single_error)}")
                        # ׳‘׳“׳™׳§׳” ׳׳ ׳–׳• ׳©׳’׳™׳׳× ׳׳‘׳ ׳” ׳—׳׳•׳¨׳”
                        if "column" in str(single_error).lower() and "does not exist" in str(single_error).lower():
                            print(f"   נ¨ CRITICAL: Column structure error - stopping batch")
                            break
        
        print(f"ג… Total inserted to csv_import_shekels: {total_inserted} rows out of {len(converted_data)}")
        return total_inserted
        
    except Exception as e:
        print(f"ג General error inserting to csv_import_shekels: {str(e)}")
        return 0

def transfer_to_parking_data():
    """׳”׳¢׳‘׳¨׳” ׳ csv_import_shekels ׳ parking_data - ׳¢׳ ׳×׳™׳§׳•׳ ׳™׳"""
    if not supabase:
        print("ג Supabase not available")
        return 0
        
    try:
        print("נ”„ Starting transfer from csv_import_shekels to parking_data...")
        
        # ׳§׳‘׳׳× ׳›׳ ׳”׳ ׳×׳•׳ ׳™׳ ׳׳˜׳‘׳׳× ׳”׳‘׳™׳ ׳™׳™׳
        csv_result = supabase.table('csv_import_shekels').select('*').execute()
        
        if not csv_result.data:
            print("ג ן¸ No data in csv_import_shekels to transfer")
            return 0
        
        print(f"נ“ Found {len(csv_result.data)} rows in csv_import_shekels")
        
        # ׳₪׳•׳ ׳§׳¦׳™׳” ׳׳§׳‘׳׳× parking_id
        def get_parking_id(project_number):
            try:
                if not supabase:
                    return None
                result = supabase.table('project_parking_mapping').select('parking_id').eq('project_number', str(project_number)).execute()
                if result.data and len(result.data) > 0:
                    return result.data[0]['parking_id']
                return None
            except Exception as e:
                print(f"ג Error getting parking_id: {str(e)}")
                return None
        
        # ׳¢׳™׳‘׳•׳“ ׳”׳ ׳×׳•׳ ׳™׳ ׳׳”׳¢׳‘׳¨׳” - ׳¢׳ ׳‘׳“׳™׳§׳•׳× ׳›׳₪׳™׳׳•׳× ׳׳©׳•׳₪׳¨׳•׳×
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
                    print(f"ג ן¸ Row {i+1}: Skipping - invalid project_number")
                    failed_transfers += 1
                    continue
                
                parking_id = get_parking_id(project_number)
                
                # ׳×׳™׳§׳•׳ c_text
                ctext_value = str(row.get('ctext', '')).strip()
                if ctext_value in ["' '", "'  '", "''", ""]:
                    ctext_value = ""
                
                # ׳™׳¦׳™׳¨׳× ׳©׳•׳¨׳” ׳—׳“׳©׳”
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
                
                # נ†• ׳‘׳“׳™׳§׳” ׳׳©׳•׳₪׳¨׳× ׳¢׳ 3 ׳©׳“׳•׳× ׳׳–׳”׳™׳ (׳‘׳׳§׳•׳ 5)
                try:
                    print(f"נ”„ Checking row {i+1}/{len(csv_result.data)}: project {project_number}, date {report_date}, text: '{ctext_value}'")
                    
                    # ׳‘׳“׳™׳§׳” ׳¢׳ ׳©׳™׳׳•׳‘ ׳©׳“׳•׳× - ׳›׳׳• constraint ׳‘׳׳¡׳“ ׳”׳ ׳×׳•׳ ׳™׳
                    existing_check = supabase.table('parking_data').select('id').eq(
                        'parking_id', parking_id
                    ).eq(
                        'report_date', report_date
                    ).eq(
                        's_shift_id', s_shift_id
                    ).execute()
                    
                    if existing_check.data:
                        print(f"נ”„ Row {i+1}: DUPLICATE DETECTED (constraint match) - skipping completely")
                        skipped_duplicates += 1
                        continue
                    
                    # ׳¨׳§ ׳׳ ׳׳ ׳§׳™׳™׳ - ׳”׳›׳ ׳¡ ׳—׳“׳©
                    result = supabase.table('parking_data').insert([transfer_row]).execute()
                    
                    if result.data:
                        successful_transfers += 1
                        print(f"ג… Row {i+1}: Successfully inserted as NEW record")
                    else:
                        failed_transfers += 1
                        print(f"ג Row {i+1}: Insert failed - no data returned")
                        
                except Exception as single_error:
                    # ׳˜׳™׳₪׳•׳ ׳‘׳©׳’׳™׳׳× constraint
                    if "duplicate key value violates unique constraint" in str(single_error):
                        print(f"נ”„ Row {i+1}: DUPLICATE DETECTED (database constraint) - skipping")
                        skipped_duplicates += 1
                        continue
                    else:
                        failed_transfers += 1
                        print(f"ג Row {i+1}: Error during processing: {str(single_error)}")
                        continue
                    
            except Exception as row_error:
                failed_transfers += 1
                print(f"ג Row {i+1}: Error processing row: {str(row_error)}")
                continue
        
        # ׳“׳•׳— ׳¡׳™׳›׳•׳ ׳׳₪׳•׳¨׳˜
        total_processed = successful_transfers + skipped_duplicates + failed_transfers
        print(f"\nנ“ Transfer Summary:")
        print(f"   ג… Successfully transferred: {successful_transfers} NEW records")
        print(f"   נ”„ Skipped duplicates: {skipped_duplicates} existing records")
        print(f"   ג Failed: {failed_transfers} records")
        print(f"   נ“ˆ Total processed: {total_processed} out of {len(csv_result.data)} rows")
        
        # ׳׳—׳™׳§׳× csv_import_shekels ׳׳—׳¨׳™ ׳”׳¢׳‘׳¨׳”
        if total_processed > 0:
            try:
                print("נ§¹ Cleaning csv_import_shekels...")
                delete_result = supabase.table('csv_import_shekels').delete().gt('id', 0).execute()
                print("ג… csv_import_shekels cleaned successfully")
            except Exception as cleanup_error:
                print(f"ג ן¸ Could not clean csv_import_shekels: {str(cleanup_error)}")
        
        return successful_transfers
            
    except Exception as e:
        print(f"ג Error transferring to parking_data: {str(e)}")
        return 0

def process_single_email(mail, email_id):
    """׳¢׳™׳‘׳•׳“ ׳׳™׳™׳ ׳™׳—׳™׳“ - ׳¢׳ ׳©׳׳™׳—׳× ׳׳™׳™׳׳™ ׳”׳•׳“׳¢׳•׳× ׳׳×׳•׳§׳"""
    sender = None  # ׳ ׳’׳“׳™׳¨ ׳׳× ׳”׳׳©׳×׳ ׳” ׳׳׳›׳×׳—׳™׳׳”
    
    try:
        _, msg_data = mail.fetch(email_id, '(RFC822)')
        
        # ׳‘׳“׳™׳§׳” ׳©׳™׳© ׳ ׳×׳•׳ ׳™׳
        if not msg_data or len(msg_data) == 0:
            print(f"ג No data for email ID: {email_id}")
            return False
            
        email_body = msg_data[0][1]
        
        # ׳‘׳“׳™׳§׳” ׳©׳™׳© body
        if not email_body:
            print(f"ג Empty email body for ID: {email_id}")
            return False
            
        email_message = email.message_from_bytes(email_body)
        
        # ׳§׳‘׳׳× ׳₪׳¨׳˜׳™ ׳”׳©׳•׳׳—
        sender = email_message.get('From', 'unknown@unknown.com')
        subject = email_message.get('Subject', 'No Subject') or 'No Subject'
        date = email_message.get('Date', 'No Date') or 'No Date'
        
        print(f"\nנ“§ Processing email from: {sender}")
        print(f"   Subject: {subject}")
        print(f"   Date: {date}")
        
        # ׳‘׳“׳™׳§׳” ׳©׳”׳©׳•׳׳— ׳×׳§׳™׳
        if sender == 'unknown@unknown.com' or '@' not in sender:
            print(f"ג Invalid sender address: {sender}")
            return False
        
        # ׳‘׳“׳™׳§׳× ׳©׳•׳׳— ׳׳•׳¨׳©׳”
        if not is_authorized_sender(sender):
            print(f"נ« UNAUTHORIZED SENDER: {sender}")
            print(f"ג… Authorized senders: {AUTHORIZED_SENDERS}")
            print(f"ג­ן¸ Skipping email from unauthorized sender")
            
            # נ†• ׳¡׳™׳׳•׳ ׳”׳׳™׳™׳ ׳›׳“׳™ ׳׳ ׳׳‘׳“׳•׳§ ׳׳•׳×׳• ׳©׳•׳‘
            try:
                print(f"נ·ן¸ Marking unauthorized email as processed (ID: {email_id})...")
                mail.store(email_id, '+FLAGS', '\\Seen \\Flagged')
                print(f"ג… Unauthorized email marked as processed")
            except Exception as mark_error:
                print(f"ג ן¸ Could not mark unauthorized email: {str(mark_error)}")
            
            print(f"נ“ UNAUTHORIZED ACCESS LOGGED: {sender} tried to send data files")
            return False
        
        print(f"ג… AUTHORIZED SENDER: {sender}")
        
        csv_files = download_csv_from_email(email_message)
        
        if not csv_files:
            print("ג ן¸ No CSV files found in email")
            # נ†• ׳©׳׳™׳—׳× ׳׳™׳™׳ ׳¢׳ ׳—׳•׳¡׳¨ ׳§׳‘׳¦׳™׳
            send_error_notification(sender, 
                "׳׳ ׳ ׳׳¦׳׳• ׳§׳‘׳¦׳™ CSV ׳‘׳׳™׳™׳. ׳׳ ׳ ׳•׳“׳ ׳©׳¦׳™׳¨׳₪׳× ׳§׳‘׳¦׳™ ׳ ׳×׳•׳ ׳™׳ ׳×׳§׳™׳ ׳™׳.")
            return False
        
        all_converted_data = []
        processed_files = []
        
        for csv_file in csv_files:
            print(f"\nנ”„ Processing file: {csv_file['filename']}")
            
            # ׳₪׳¨׳¡׳•׳¨ CSV
            csv_rows = parse_csv_content(csv_file['data'])
            if csv_rows is None:
                print(f"ג Failed to parse file: {csv_file['filename']}")
                continue
            
            # ׳”׳׳¨׳” ׳׳₪׳•׳¨׳׳˜ ׳©׳׳ ׳•
            converted_data = convert_to_csv_import_format(csv_rows)
            if not converted_data:
                print(f"ג Failed to convert file: {csv_file['filename']}")
                continue
            
            all_converted_data.extend(converted_data)
            processed_files.append({
                'name': csv_file['filename'],
                'rows': len(converted_data)
            })
            
            print(f"ג… File {csv_file['filename']}: {len(converted_data)} rows converted")
        
        # ׳‘׳“׳™׳§׳” ׳©׳™׳© ׳ ׳×׳•׳ ׳™׳ ׳×׳§׳™׳ ׳™׳
        if not all_converted_data:
            error_msg = "׳׳ ׳ ׳׳¦׳׳• ׳ ׳×׳•׳ ׳™׳ ׳×׳§׳™׳ ׳™׳ ׳‘׳§׳‘׳¦׳™׳. ׳׳ ׳ ׳‘׳“׳•׳§ ׳׳× ׳₪׳•׳¨׳׳˜ ׳”׳§׳‘׳¦׳™׳."
            print(f"ג {error_msg}")
            send_error_notification(sender, error_msg)
            return False
        
        print(f"נ“ Total converted data: {len(all_converted_data)} rows")
        
        # ׳”׳›׳ ׳¡׳” ׳׳˜׳‘׳׳× ׳”׳‘׳™׳ ׳™׳™׳
        inserted_count = insert_to_csv_import_shekels(all_converted_data)
        if inserted_count == 0:
            error_msg = "׳©׳’׳™׳׳” ׳‘׳”׳›׳ ׳¡׳× ׳”׳ ׳×׳•׳ ׳™׳ ׳׳׳¡׳“ ׳”׳ ׳×׳•׳ ׳™׳."
            print(f"ג {error_msg}")
            send_error_notification(sender, error_msg)
            return False
        
        print(f"ג… Inserted to csv_import_shekels: {inserted_count} rows")
        
        # ׳”׳¢׳‘׳¨׳” ׳׳˜׳‘׳׳” ׳”׳¡׳•׳₪׳™׳×
        transferred_count = transfer_to_parking_data()
        
        # נ†• ׳×׳׳™׳“ ׳©׳׳™׳—׳× ׳׳™׳™׳ ׳”׳¦׳׳—׳” - ׳’׳ ׳׳ ׳”׳›׳ ׳›׳₪׳™׳׳•׳™׳•׳×
        total_processed = len(all_converted_data)
        files_summary = ', '.join([f['name'] for f in processed_files])
        
        if transferred_count > 0:
            success_msg = f"׳¢׳•׳‘׳“׳• {transferred_count} ׳¨׳©׳•׳׳•׳× ׳—׳“׳©׳•׳× ׳׳×׳•׳ {total_processed} ׳¨׳©׳•׳׳•׳× ׳›׳•׳׳"
            print(f"נ‰ Email processed successfully: {success_msg}")
        else:
            success_msg = f"׳›׳ {total_processed} ׳”׳¨׳©׳•׳׳•׳× ׳›׳‘׳¨ ׳§׳™׳™׳׳•׳× ׳‘׳׳¢׳¨׳›׳× (׳›׳₪׳™׳׳•׳™׳•׳×)"
            print(f"נ‰ Email processed successfully: {success_msg}")
        
        # נ†• ׳©׳׳™׳—׳× ׳׳™׳™׳ ׳”׳¦׳׳—׳” ׳¢׳ ׳₪׳¨׳˜׳™׳ ׳׳׳׳™׳
        send_success_notification(sender, processed_files, transferred_count, total_processed)
        
# נ·ן¸ ׳¡׳™׳׳•׳ ׳”׳׳™׳™׳ ׳›׳׳¢׳•׳‘׳“ ׳‘׳׳§׳•׳ ׳׳—׳™׳§׳”
        try:
            print(f"נ·ן¸ Marking email as processed (ID: {email_id})...")
            mail.store(email_id, '+FLAGS', '\\Seen \\Flagged')
            print(f"ג… Email marked as processed successfully")
            
        except Exception as mark_error:
            print(f"ג ן¸ Could not mark email as processed: {str(mark_error)}")
            # ׳׳ ׳׳₪׳¡׳™׳§׳™׳ ׳׳× ׳”׳×׳”׳׳™׳ ׳‘׳’׳׳ ׳–׳”
        
        return True
        
    except Exception as e:
        error_msg = f"׳©׳’׳™׳׳” ׳˜׳›׳ ׳™׳× ׳‘׳¢׳™׳‘׳•׳“ ׳”׳׳™׳™׳: {str(e)}"
        print(f"ג Error processing email: {error_msg}")
        
        # נ†• ׳©׳׳™׳—׳× ׳׳™׳™׳ ׳©׳’׳™׳׳” ׳¢׳ ׳₪׳¨׳˜׳™׳
        if sender and sender != 'unknown@unknown.com':
            send_error_notification(sender, error_msg)
        else:
            print(f"ג Could not send error notification - unknown sender")
            
        return False

def send_success_notification(sender_email, processed_files, new_rows, total_rows):
    """׳©׳׳™׳—׳× ׳”׳×׳¨׳׳× ׳”׳¦׳׳—׳” - ׳’׳¨׳¡׳” ׳׳×׳•׳§׳ ׳× ׳¢׳ ׳₪׳¨׳˜׳™׳ ׳׳׳׳™׳"""
    
    # ׳‘׳“׳™׳§׳× ׳׳’׳‘׳׳” ׳™׳•׳׳™׳×
    if not hasattr(send_success_notification, 'daily_count'):
        send_success_notification.daily_count = 0
        send_success_notification.last_reset = datetime.now().date()
    
    # ׳׳™׳₪׳•׳¡ ׳™׳•׳׳™
    if send_success_notification.last_reset != datetime.now().date():
        send_success_notification.daily_count = 0
        send_success_notification.last_reset = datetime.now().date()
    
    # ׳”׳’׳‘׳׳” ׳-100 ׳׳™׳™׳׳™ ׳”׳¦׳׳—׳” ׳‘׳™׳•׳
    if send_success_notification.daily_count >= 100:
        files_summary = ', '.join([f['name'] for f in processed_files])
        print(f"ג ן¸ Daily success email limit reached (100/day) - logging only: {new_rows} new, {total_rows} total from {files_summary}")
        return
    
    # ׳‘׳“׳™׳§׳× ׳ ׳×׳•׳ ׳™׳
    gmail_user = os.environ.get('GMAIL_USERNAME')
    gmail_password = os.environ.get('GMAIL_APP_PASSWORD')
    
    if not gmail_user or not gmail_password:
        print(f"ג Missing Gmail credentials for success notification")
        files_summary = ', '.join([f['name'] for f in processed_files])
        print(f"נ“ Success logged: {new_rows} new, {total_rows} total from {files_summary}")
        return
        
    try:
        print(f"נ“§ Sending success notification to {sender_email}...")
        
        msg = MIMEMultipart()
        msg['From'] = gmail_user
        msg['To'] = sender_email
        msg['Subject'] = 'ג… ׳§׳‘׳¦׳™ ׳”׳ ׳×׳•׳ ׳™׳ ׳¢׳•׳‘׳“׳• ׳‘׳”׳¦׳׳—׳” - S&B Parking'
        
        files_list = '\n'.join([f"ג€¢ {file['name']} - {file['rows']:,} ׳©׳•׳¨׳•׳×" for file in processed_files])
        
        # נ†• ׳”׳•׳“׳¢׳” ׳׳₪׳•׳¨׳˜׳× ׳™׳•׳×׳¨
        if new_rows > 0:
            status_message = f"׳ ׳•׳¡׳₪׳• {new_rows:,} ׳¨׳©׳•׳׳•׳× ׳—׳“׳©׳•׳× ׳׳׳¡׳“ ׳”׳ ׳×׳•׳ ׳™׳"
            if new_rows < total_rows:
                status_message += f" (׳׳×׳•׳ {total_rows:,} ׳¨׳©׳•׳׳•׳× ׳›׳•׳׳ - ׳™׳×׳¨ ׳”׳¨׳©׳•׳׳•׳× ׳›׳‘׳¨ ׳§׳™׳™׳׳•׳×)"
        else:
            status_message = f"׳›׳ {total_rows:,} ׳”׳¨׳©׳•׳׳•׳× ׳›׳‘׳¨ ׳§׳™׳™׳׳•׳× ׳‘׳׳¢׳¨׳›׳× (׳׳ ׳ ׳•׳¡׳₪׳• ׳¨׳©׳•׳׳•׳× ׳—׳“׳©׳•׳×)"
        
        body = f"""
׳©׳׳•׳,

׳§׳‘׳¦׳™ ׳”׳ ׳×׳•׳ ׳™׳ ׳©׳׳ ׳¢׳•׳‘׳“׳• ׳‘׳”׳¦׳׳—׳” ׳‘׳׳¢׳¨׳›׳× S&B Parking:

נ“ ׳§׳‘׳¦׳™׳ ׳©׳¢׳•׳‘׳“׳•:
{files_list}

נ“ ׳×׳•׳¦׳׳•׳× ׳”׳¢׳™׳‘׳•׳“:
{status_message}

נ’¡ ׳”׳¢׳¨׳”: ׳׳ ׳”׳¨׳©׳•׳׳•׳× ׳›׳‘׳¨ ׳§׳™׳™׳׳•׳×, ׳–׳” ׳׳•׳׳¨ ׳©׳”׳ ׳×׳•׳ ׳™׳ ׳›׳‘׳¨ ׳”׳•׳¢׳׳• ׳§׳•׳“׳ ׳׳›׳.

נ” ׳”׳ ׳×׳•׳ ׳™׳ ׳–׳׳™׳ ׳™׳ ׳›׳¢׳× ׳‘׳“׳©׳‘׳•׳¨׳“ ׳׳¦׳₪׳™׳™׳” ׳•׳“׳•׳—׳•׳×.

׳‘׳‘׳¨׳›׳”,
׳׳¢׳¨׳›׳× S&B Parking (׳“׳•׳— ׳׳•׳˜׳•׳׳˜׳™)
׳ ׳©׳׳— ׳: {gmail_user}
        """
        
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(gmail_user, gmail_password)
        server.send_message(msg)
        server.quit()
        
        send_success_notification.daily_count += 1
        print(f"ג… Success notification sent to {sender_email} ({send_success_notification.daily_count}/100 today)")
        
    except Exception as e:
        error_str = str(e)
        if "sending limit exceeded" in error_str.lower():
            print(f"נ« Gmail daily limit exceeded - switching to log-only mode")
            send_success_notification.daily_count = 99
        else:
            print(f"ג Failed to send success notification: {str(e)}")
            files_summary = ', '.join([f['name'] for f in processed_files])
            print(f"נ“ Success logged: {new_rows} new, {total_rows} total from {files_summary}")

def send_error_notification(sender_email, error_message):
    """׳©׳׳™׳—׳× ׳”׳×׳¨׳׳× ׳©׳’׳™׳׳” - ׳׳•׳©׳‘׳×, ׳¨׳§ ׳׳•׳’"""
    
    # ׳‘׳“׳™׳§׳” ׳׳ ׳׳™׳™׳׳™ ׳©׳’׳™׳׳” ׳׳•׳©׳‘׳×׳™׳
    if ERROR_EMAILS_DISABLED:
        print(f"נ« Error email DISABLED - logging only")
        print(f"נ“ Error for {sender_email}: {error_message}")
        return
    
    # ׳׳ ׳׳ ׳׳•׳©׳‘׳×, ׳¨׳§ ׳׳•׳’ (׳׳׳ ׳©׳׳™׳—׳× ׳׳™׳™׳)
    print(f"נ“ ERROR LOGGED (no email sent): {sender_email} - {error_message}")
            
def verify_email_system():
    """׳‘׳“׳™׳§׳× ׳”׳×׳§׳™׳ ׳•׳× ׳©׳ ׳׳¢׳¨׳›׳× ׳”׳׳™׳™׳׳™׳"""
    if not EMAIL_MONITORING_AVAILABLE:
        print("ג ן¸ Email libraries not available - email monitoring disabled")
        return False
        
    print("נ”§ Verifying email system configuration...")
    
    # ׳‘׳“׳™׳§׳× ׳׳©׳×׳ ׳™ ׳¡׳‘׳™׳‘׳”
    gmail_user = os.environ.get('GMAIL_USERNAME')
    gmail_password = os.environ.get('GMAIL_APP_PASSWORD')
    
    print(f"נ“§ Gmail Username: {'ג… SET' if gmail_user else 'ג MISSING'}")
    print(f"נ”‘ Gmail Password: {'ג… SET' if gmail_password else 'ג MISSING'}")
    
    if not gmail_user or not gmail_password:
        print("ג ן¸ WARNING: Gmail credentials missing! Email monitoring will not work.")
        return False
    
    # ׳‘׳“׳™׳§׳× ׳—׳™׳‘׳•׳¨ IMAP (׳׳”׳™׳¨)
    try:
        mail = imaplib.IMAP4_SSL('imap.gmail.com', timeout=10)
        mail.login(gmail_user, gmail_password)
        mail.logout()
        print("נ Gmail IMAP connection: ג… SUCCESS")
        return True
    except Exception as e:
        print(f"ג Gmail IMAP connection failed: {str(e)}")
        return False

def start_email_monitoring_with_logs():
    """׳”׳₪׳¢׳׳× ׳׳¢׳§׳‘ ׳׳™׳™׳׳™׳ ׳¢׳ ׳׳•׳’׳™׳ ׳׳₪׳•׳¨׳˜׳™׳ - ׳׳׳ ׳›׳₪׳™׳׳•׳×"""
    if not EMAIL_MONITORING_AVAILABLE:
        print("ג ן¸ Email monitoring not available - libraries missing")
        return
        
    try:
        print("נ€ Starting email monitoring system...")
        
        # ׳‘׳“׳™׳§׳× ׳×׳§׳™׳ ׳•׳× ׳”׳׳¢׳¨׳›׳×
        if not verify_email_system():
            print("ג Email system verification failed. Monitoring will not start.")
            return
        
        def monitoring_loop():
            print("נ”„ Email monitoring loop started")
            check_count = 0
            
            while True:
                try:
                    # ׳‘׳“׳™׳§׳× ׳׳™׳™׳׳™׳ ׳›׳ 5 ׳“׳§׳•׳× (300 ׳©׳ ׳™׳•׳×)
                    with app.app_context():
                        print(f"ג° Email check triggered at {datetime.now()}")
                        check_for_new_emails()
                    
                    # ׳”׳׳×׳ ׳” ׳©׳ 5 ׳“׳§׳•׳×
                    time.sleep(150)  # 300 ׳©׳ ׳™׳•׳× = 5 ׳“׳§׳•׳×
                    
                    check_count += 1
                    if check_count % 6 == 0:  # ׳›׳ 30 ׳“׳§׳•׳× (6 * 5 ׳“׳§׳•׳×)
                        print(f"נ’“ Email monitoring alive - {check_count * 5} minutes running")
                        
                except KeyboardInterrupt:
                    print("\nנ›‘ Email monitoring stopped by user")
                    break
                except Exception as e:
                    print(f"ג Email monitoring error: {str(e)}")
                    print("ג³ Retrying in 5 minutes...")
                    time.sleep(300)  # 5 ׳“׳§׳•׳× ׳”׳׳×׳ ׳” ׳׳₪׳ ׳™ ׳ ׳™׳¡׳™׳•׳ ׳—׳•׳–׳¨
        
        # ׳”׳¨׳¦׳× ׳”׳׳•׳׳׳” ׳‘׳¨׳§׳¢
        monitor_thread = threading.Thread(target=monitoring_loop, daemon=True)
        monitor_thread.start()
        
        print("ג… Email monitoring started successfully in background")
        print(f"ג° Email checks scheduled every {EMAIL_CHECK_INTERVAL} minutes")
        
        # ׳‘׳“׳™׳§׳” ׳¨׳׳©׳•׳ ׳™׳× ׳׳¢׳•׳›׳‘׳× ׳׳׳ ׳™׳¢׳× ׳›׳₪׳™׳׳•׳×
        print("נ€ Running initial email check in 15 seconds...")
        def delayed_initial_check():
            time.sleep(15)  # ׳”׳׳×׳ ׳” ׳©׳ 15 ׳©׳ ׳™׳•׳×
            with app.app_context():
                check_for_new_emails()
        threading.Thread(target=delayed_initial_check, daemon=True).start()
        
    except Exception as e:
        print(f"ג Failed to start email monitoring: {str(e)}")

def start_background_email_monitoring():
    """׳ ׳§׳•׳“׳× ׳›׳ ׳™׳¡׳” ׳׳”׳₪׳¢׳׳× ׳׳¢׳§׳‘ ׳׳™׳™׳׳™׳ ׳‘׳¨׳§׳¢"""
    if not EMAIL_MONITORING_AVAILABLE:
        print("ג ן¸ Email monitoring not available - missing libraries")
        return
        
    try:
        print("נ“§ Initializing background email monitoring...")
        
        def delayed_start():
            time.sleep(5)
            print("נ“§ About to start email monitoring with logs...")  # נ†• ׳”׳•׳¡׳£ ׳“׳™׳‘׳•׳’
            start_email_monitoring_with_logs()
        
        startup_thread = threading.Thread(target=delayed_start, daemon=True)
        startup_thread.start()
        
        print("נ“§ Background email monitoring initialization started")
        
    except Exception as e:
        print(f"ג Background email monitoring initialization failed: {str(e)}")

def is_authorized_sender(sender_email):
    """׳‘׳“׳™׳§׳” ׳׳ ׳”׳©׳•׳׳— ׳׳•׳¨׳©׳” ׳׳©׳׳•׳— ׳§׳‘׳¦׳™ ׳ ׳×׳•׳ ׳™׳"""
    if not sender_email:
        return False
    
    # ׳ ׳™׳§׳•׳™ ׳›׳×׳•׳‘׳× ׳”׳׳™׳™׳ ׳׳×׳’׳™׳ ׳ ׳•׳¡׳₪׳™׳
    sender_clean = sender_email.strip().lower()
    
    # ׳—׳™׳׳•׳¥ ׳›׳×׳•׳‘׳× ׳”׳׳™׳™׳ ׳׳₪׳•׳¨׳׳˜ "Name <email@domain.com>"
    if '<' in sender_clean and '>' in sender_clean:
        start = sender_clean.find('<') + 1
        end = sender_clean.find('>')
        sender_clean = sender_clean[start:end].strip()
    
    # ׳‘׳“׳™׳§׳” ׳׳•׳ ׳¨׳©׳™׳׳× ׳”׳©׳•׳׳—׳™׳ ׳”׳׳•׳¨׳©׳™׳
    for authorized in AUTHORIZED_SENDERS:
        if sender_clean == authorized.lower():
            return True
    
    return False

def check_for_new_emails():
    """׳‘׳“׳™׳§׳× ׳׳™׳™׳׳™׳ ׳—׳“׳©׳™׳ - ׳×׳™׳§׳•׳ ׳×׳׳¨׳™׳›׳™׳"""
    global processed_email_ids, last_cache_reset
    
    # נ†• ׳׳™׳₪׳•׳¡ ׳–׳™׳›׳¨׳•׳ ׳׳—׳× ׳׳©׳¢׳”
    if last_cache_reset is None or (datetime.now() - last_cache_reset).seconds > 3600:
        processed_email_ids = []
        last_cache_reset = datetime.now()
        print(f"נ”„ Hourly cache reset completed")
    
    # ׳ ׳™׳§׳•׳™ ׳–׳™׳›׳¨׳•׳ ׳׳ ׳™׳© ׳™׳•׳×׳¨ ׳׳“׳™
    if len(processed_email_ids) > 50:
        processed_email_ids = processed_email_ids[-20:]
        print(f"נ§¹ Email cache cleaned - kept last 20 emails")
    
    if not EMAIL_MONITORING_AVAILABLE:
        print("ג ן¸ Email check skipped - libraries not available")
        return
    
    print(f"\nנ” ===== EMAIL CHECK STARTED at {datetime.now()} =====")
    
    # ׳‘׳“׳™׳§׳× ׳׳©׳×׳ ׳™ ׳¡׳‘׳™׳‘׳”
    gmail_user = os.environ.get('GMAIL_USERNAME')
    gmail_password = os.environ.get('GMAIL_APP_PASSWORD')
    
    if not gmail_user or not gmail_password:
        print("ג Missing Gmail credentials - skipping email check")
        return
    
    print(f"נ“§ Gmail user: {gmail_user}")
    print(f"נ”‘ Gmail password: {'***' if gmail_password else 'MISSING'}")
    
    mail = connect_to_gmail_imap()
    if not mail:
        print("ג Failed to connect to Gmail IMAP")
        return
    
    try:
        print("נ“‚ Selecting inbox...")
        mail.select('inbox')
        
        # ׳×׳™׳§׳•׳ ׳×׳׳¨׳™׳›׳™׳ - ׳׳—׳₪׳© ׳׳”׳™׳•׳׳™׳™׳ ׳”׳׳—׳¨׳•׳ ׳™׳
        today = datetime.now().strftime('%d-%b-%Y')
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%d-%b-%Y')
        
        # ׳—׳™׳₪׳•׳© ׳׳™׳™׳׳™׳ ׳׳”׳™׳•׳׳™׳™׳ ׳”׳׳—׳¨׳•׳ ׳™׳
        search_criteria = f'OR SINCE {yesterday} SINCE {today}'
        
        print(f"נ” Search criteria: {search_criteria}")
        print(f"נ“… Today: {today}, Yesterday: {yesterday}")
        
        _, message_ids = mail.search(None, f'({search_criteria}) UNFLAGGED')
        
        if not message_ids[0]:
            print("נ“­ No emails found from the last 2 days")
            print(f"נ“ Processed emails cache: {len(processed_email_ids)} emails")
            mail.logout()
            return
        
        email_ids = message_ids[0].split()
        print(f"נ“§ Found {len(email_ids)} emails from the last 2 days")
        
        new_emails = 0
        processed_successfully = 0
        
        for email_id in email_ids:
            email_id_str = email_id.decode() if isinstance(email_id, bytes) else str(email_id)
            
            if email_id_str in processed_email_ids:
                print(f"ג­ן¸ Skipping already processed email: {email_id_str}")
                continue
            
            print(f"\nנ†• Processing new email ID: {email_id_str}")
            
            # ׳¢׳™׳‘׳•׳“ ׳”׳׳™׳™׳
            success = process_single_email(mail, email_id)
            
            # נ”§ ׳×׳™׳§׳•׳: ׳”׳•׳¡׳£ ׳׳¨׳©׳™׳׳” ׳¨׳§ ׳׳ ׳”׳¦׳׳™׳—!
            if success:
                processed_email_ids.append(email_id_str)
                print(f"ג… Email {email_id_str} added to processed cache")
            else:
                # ׳׳ ׳׳•׳¡׳™׳₪׳™׳ ׳׳¨׳©׳™׳׳” - ׳ ׳ ׳¡׳” ׳©׳•׳‘ ׳‘׳₪׳¢׳ ׳”׳‘׳׳”
                print(f"ג Email {email_id_str} NOT added to cache - will retry next time")
            
            new_emails += 1
            
            # ׳¡׳₪׳™׳¨׳× ׳”׳¦׳׳—׳•׳× ׳‘׳׳‘׳“
            if success:
                processed_successfully += 1
                print(f"ג… Email {email_id_str} processed successfully")
            else:
                print(f"ג ן¸ Email {email_id_str} was rejected or failed")
            
            # ׳ ׳™׳§׳•׳™ cache ׳׳ ׳™׳© ׳™׳•׳×׳¨ ׳׳“׳™ ׳׳™׳™׳׳™׳
            if len(processed_email_ids) > PROCESSED_EMAILS_LIMIT:
                processed_email_ids = processed_email_ids[-PROCESSED_EMAILS_LIMIT:]
                print(f"נ§¹ Cleaned processed emails cache, now: {len(processed_email_ids)}")
            
            # ׳”׳׳×׳ ׳” ׳§׳¦׳¨׳” ׳‘׳™׳ ׳׳™׳™׳׳™׳
            time.sleep(2)
        
        # ׳¡׳™׳›׳•׳ ׳׳₪׳•׳¨׳˜
        print(f"ג… Email check completed:")
        print(f"   נ“§ New emails checked: {new_emails}")
        print(f"   נ‰ Successfully processed: {processed_successfully}")
        print(f"   נ« Rejected/Failed: {new_emails - processed_successfully}")
        print(f"   נ“ Total emails in cache: {len(processed_email_ids)}")
        
    except Exception as e:
        print(f"ג Error in email check: {str(e)}")
    
    finally:
        try:
            mail.logout()
            print("נ”“ Gmail connection closed")
        except:
            pass
        
        print(f"===== EMAIL CHECK ENDED at {datetime.now()} =====\n")

def keep_service_alive():
    """׳₪׳•׳ ׳§׳¦׳™׳” ׳׳©׳׳™׳¨׳” ׳¢׳ ׳”׳©׳™׳¨׳•׳× ׳¢׳¨׳ ׳™ - ׳’׳¨׳¡׳” ׳׳×׳•׳§׳ ׳×"""
    def ping_self():
        print("נ“ Keep-alive service started")
        
        # ׳§׳‘׳׳× URL ׳©׳ ׳”׳©׳¨׳× ׳׳”׳׳©׳×׳ ׳” ׳©׳”׳’׳“׳¨׳ ׳•
        app_url = os.environ.get('RENDER_EXTERNAL_URL', 'https://s-b-parking-reports.onrender.com')
        
        while True:
            try:
                # ׳©׳׳™׳—׳× ׳‘׳§׳©׳” ׳׳¢׳¦׳׳ ׳• ׳›׳ 10 ׳“׳§׳•׳×
                print(f"נ“ Sending keep-alive ping to {app_url}")
                response = requests.get(f'{app_url}/ping', timeout=30000)
                print(f"נ“ Keep-alive ping successful: {response.status_code}")
                
            except requests.exceptions.RequestException as e:
                print(f"ג ן¸ Keep-alive ping failed: {str(e)}")
                # ׳׳׳©׳™׳›׳™׳ ׳’׳ ׳‘׳׳§׳¨׳” ׳©׳ ׳©׳’׳™׳׳”
                
            except Exception as e:
                print(f"ג ן¸ Unexpected error in keep-alive: {str(e)}")
            
            # ׳”׳׳×׳ ׳” ׳©׳ 10 ׳“׳§׳•׳× (600 ׳©׳ ׳™׳•׳×)
            time.sleep(600)
    
    # ׳”׳¨׳¦׳× ׳”׳₪׳•׳ ׳§׳¦׳™׳” ׳‘׳¨׳§׳¢
    ping_thread = threading.Thread(target=ping_self, daemon=True)
    ping_thread.start()
    print("נ“ Keep-alive service initialized")

def validate_username(username):
    """
    ׳×׳™׳§׳•׳£ ׳©׳ ׳׳©׳×׳׳© - ׳¨׳§ ׳׳•׳×׳™׳•׳× ׳׳ ׳’׳׳™׳×, ׳׳¡׳₪׳¨׳™׳ ׳•׳§׳• ׳×׳—׳×׳•׳
    """
    import re
    
    if not username or len(username.strip()) == 0:
        return False, "׳™׳© ׳׳”׳–׳™׳ ׳©׳ ׳׳©׳×׳׳©"
    
    username = username.strip()
    
    # ׳‘׳“׳™׳§׳× ׳׳•׳¨׳
    if len(username) < 3:
        return False, "׳©׳ ׳׳©׳×׳׳© ׳—׳™׳™׳‘ ׳׳”׳™׳•׳× ׳׳₪׳—׳•׳× 3 ׳×׳•׳•׳™׳"
    
    if len(username) > 20:
        return False, "׳©׳ ׳׳©׳×׳׳© ׳™׳›׳•׳ ׳׳”׳™׳•׳× ׳׳§׳¡׳™׳׳•׳ 20 ׳×׳•׳•׳™׳"
    
    # ׳‘׳“׳™׳§׳” ׳©׳™׳© ׳¨׳§ ׳׳•׳×׳™׳•׳× ׳׳ ׳’׳׳™׳×, ׳׳¡׳₪׳¨׳™׳ ׳•׳§׳• ׳×׳—׳×׳•׳
    if not re.match(r'^[a-zA-Z0-9_]+$', username):
        return False, "׳©׳ ׳׳©׳×׳׳© ׳™׳›׳•׳ ׳׳›׳׳•׳ ׳¨׳§ ׳׳•׳×׳™׳•׳× ׳׳ ׳’׳׳™׳×, ׳׳¡׳₪׳¨׳™׳ ׳•׳§׳• ׳×׳—׳×׳•׳ (_)"
    
    # ׳‘׳“׳™׳§׳” ׳©׳׳×׳—׳™׳ ׳‘׳׳•׳×
    if not username[0].isalpha():
        return False, "׳©׳ ׳׳©׳×׳׳© ׳—׳™׳™׳‘ ׳׳”׳×׳—׳™׳ ׳‘׳׳•׳× ׳׳ ׳’׳׳™׳×"
    
    # ׳¨׳©׳™׳׳× ׳©׳׳•׳× ׳׳¡׳•׳¨׳™׳
    forbidden_names = [
        'admin', 'administrator', 'root', 'user', 'test', 'guest', 'null', 'undefined',
        'api', 'www', 'mail', 'email', 'support', 'help', 'info', 'contact',
        'scheidt', 'master', 'system', 'service'
    ]
    
    if username.lower() in forbidden_names:
        return False, "׳©׳ ׳׳©׳×׳׳© ׳–׳” ׳׳™׳ ׳• ׳–׳׳™׳"
    
    return True, username

@app.route('/api/test-email-system', methods=['GET'])
def test_email_system():
    """API ׳׳‘׳“׳™׳§׳× ׳׳¢׳¨׳›׳× ׳”׳׳™׳™׳׳™׳"""
    try:
        if not EMAIL_MONITORING_AVAILABLE:
            return jsonify({
                'success': False, 
                'message': 'Email system not available - missing libraries'
            })
            
        print("נ§× Manual email system test initiated")
        
        # ׳‘׳“׳™׳§׳× ׳×׳§׳™׳ ׳•׳×
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
        print(f"ג Email system test error: {str(e)}")
        return jsonify({
            'success': False, 
            'message': f'Test error: {str(e)}'
        })
# ======================== ׳ ׳§׳•׳“׳•׳× ׳§׳¦׳” (Routes) ========================

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
    """׳“׳£ ׳”׳“׳©׳‘׳•׳¨׳“ ׳”׳¨׳׳©׳™"""
    if 'user_email' not in session:
        return redirect(url_for('login_page'))
    return render_template('dashboard.html')

@app.route('/api/user-info', methods=['GET'])
def get_user_info():
    """׳§׳‘׳׳× ׳ ׳×׳•׳ ׳™ ׳”׳׳©׳×׳׳© ׳”׳׳—׳•׳‘׳¨"""
    try:
        if 'user_email' not in session:
            return jsonify({'success': False, 'message': '׳׳ ׳׳—׳•׳‘׳¨'}), 401
        
        if not supabase:
            return jsonify({'success': False, 'message': '׳׳¡׳“ ׳”׳ ׳×׳•׳ ׳™׳ ׳׳ ׳–׳׳™׳'})
        
        email = session['user_email']
        
        # ׳§׳‘׳׳× ׳ ׳×׳•׳ ׳™ ׳”׳׳©׳×׳׳©
        user_result = supabase.table('user_parkings').select(
            'username, email, role, project_number, parking_name, company_type, access_level'
        ).eq('email', email).execute()
        
        if not user_result.data:
            return jsonify({'success': False, 'message': '׳׳©׳×׳׳© ׳׳ ׳ ׳׳¦׳'})
        
        user_data = user_result.data[0]
        
        return jsonify({
            'success': True,
            'user': user_data
        })
        
    except Exception as e:
        print(f"ג Error getting user info: {str(e)}")
        return jsonify({'success': False, 'message': '׳©׳’׳™׳׳” ׳‘׳§׳‘׳׳× ׳ ׳×׳•׳ ׳™ ׳׳©׳×׳׳©'})

@app.route('/api/user-parkings', methods=['GET'])
def get_user_parkings():
    """׳§׳‘׳׳× ׳¨׳©׳™׳׳× ׳”׳—׳ ׳™׳•׳ ׳™׳ ׳¢׳‘׳•׳¨ ׳׳ ׳”׳ ׳§׳‘׳•׳¦׳”"""
    try:
        if 'user_email' not in session:
            return jsonify({'success': False, 'message': '׳׳ ׳׳—׳•׳‘׳¨'}), 401
        
        if not supabase:
            return jsonify({'success': False, 'message': '׳׳¡׳“ ׳”׳ ׳×׳•׳ ׳™׳ ׳׳ ׳–׳׳™׳'})
        
        email = session['user_email']
        
        # ׳‘׳“׳™׳§׳× ׳”׳¨׳©׳׳•׳× ׳׳©׳×׳׳©
        user_result = supabase.table('user_parkings').select(
            'access_level, company_type'
        ).eq('email', email).execute()
        
        if not user_result.data:
            return jsonify({'success': False, 'message': '׳׳©׳×׳׳© ׳׳ ׳ ׳׳¦׳'})
        
        user_data = user_result.data[0]
        
        if user_data['access_level'] != 'group_manager' and user_data['access_level'] != 'group_access':
            return jsonify({'success': False, 'message': '׳׳™׳ ׳”׳¨׳©׳׳” ׳׳¦׳₪׳™׳™׳” ׳‘׳—׳ ׳™׳•׳ ׳™׳ ׳׳¨׳•׳‘׳™׳'})
        
        # ׳§׳‘׳׳× ׳›׳ ׳”׳—׳ ׳™׳•׳ ׳™׳ ׳©׳ ׳”׳—׳‘׳¨׳”
        parkings_result = supabase.table('user_parkings').select(
            'project_number, parking_name'
        ).eq('company_type', user_data['company_type']).execute()
        
        # ׳”׳¡׳¨׳× ׳›׳₪׳™׳׳•׳™׳•׳×
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
        print(f"ג Error getting user parkings: {str(e)}")
        return jsonify({'success': False, 'message': '׳©׳’׳™׳׳” ׳‘׳§׳‘׳׳× ׳¨׳©׳™׳׳× ׳—׳ ׳™׳•׳ ׳™׳'})

@app.route('/api/parking-data', methods=['GET'])
def get_parking_data():
    """׳§׳‘׳׳× ׳ ׳×׳•׳ ׳™ ׳”׳—׳ ׳™׳•׳ ׳׳₪׳™ ׳×׳׳¨׳™׳›׳™׳ ׳•׳”׳¨׳©׳׳•׳×"""
    try:
        if 'user_email' not in session:
            return jsonify({'success': False, 'message': '׳׳ ׳׳—׳•׳‘׳¨'}), 401
        
        if not supabase:
            return jsonify({'success': False, 'message': '׳׳¡׳“ ׳”׳ ׳×׳•׳ ׳™׳ ׳׳ ׳–׳׳™׳'})
        
        # ׳§׳‘׳׳× ׳₪׳¨׳׳˜׳¨׳™׳
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        parking_id = request.args.get('parking_id')  # ׳׳•׳₪׳¦׳™׳•׳ ׳׳™ - ׳׳׳ ׳”׳׳™ ׳§׳‘׳•׳¦׳”
        
        if not start_date or not end_date:
            return jsonify({'success': False, 'message': '׳—׳¡׳¨׳™׳ ׳×׳׳¨׳™׳›׳™׳'})
        
        # ׳׳™׳׳•׳× ׳×׳׳¨׳™׳›׳™׳
        is_valid_start, validated_start = validate_input(start_date, "general")
        is_valid_end, validated_end = validate_input(end_date, "general")
        
        if not is_valid_start or not is_valid_end:
            return jsonify({'success': False, 'message': '׳×׳׳¨׳™׳›׳™׳ ׳׳ ׳×׳§׳™׳ ׳™׳'})
        
        email = session['user_email']
        
        # ׳§׳‘׳׳× ׳ ׳×׳•׳ ׳™ ׳”׳׳©׳×׳׳©
        user_result = supabase.table('user_parkings').select(
            'access_level, project_number, company_type'
        ).eq('email', email).execute()
        
        if not user_result.data:
            return jsonify({'success': False, 'message': '׳׳©׳×׳׳© ׳׳ ׳ ׳׳¦׳'})
        
        user_data = user_result.data[0]
        
        # ׳‘׳ ׳™׳™׳× ׳©׳׳™׳׳×׳” ׳‘׳”׳×׳׳ ׳׳”׳¨׳©׳׳•׳×
        query = supabase.table('parking_data').select('*')
        
        # ׳”׳’׳‘׳׳× ׳×׳׳¨׳™׳›׳™׳
        query = query.gte('report_date', validated_start).lte('report_date', validated_end)
        
        # ׳”׳’׳‘׳׳× ׳—׳ ׳™׳•׳ ׳™׳ ׳׳₪׳™ ׳”׳¨׳©׳׳•׳×
        if user_data['access_level'] == 'single_parking':
            # ׳׳©׳×׳׳© ׳—׳ ׳™׳•׳ ׳‘׳•׳“׳“ - ׳¨׳§ ׳”׳—׳ ׳™׳•׳ ׳©׳׳•
            query = query.eq('project_number', user_data['project_number'])
            
        elif user_data['access_level'] == 'group_manager' or user_data['access_level'] == 'group_access':
            # ׳׳ ׳”׳ ׳§׳‘׳•׳¦׳” ׳׳• ׳׳©׳×׳׳© ׳§׳‘׳•׳¦׳”
            if parking_id:
                # ׳׳™׳׳•׳× ׳©׳”׳—׳ ׳™׳•׳ ׳©׳™׳™׳ ׳׳—׳‘׳¨׳” ׳©׳׳•
                parking_check = supabase.table('user_parkings').select('project_number').eq(
                    'project_number', parking_id
                ).eq('company_type', user_data['company_type']).execute()
                
                if not parking_check.data:
                    return jsonify({'success': False, 'message': '׳׳™׳ ׳”׳¨׳©׳׳” ׳׳—׳ ׳™׳•׳ ׳–׳”'})
                
                query = query.eq('project_number', parking_id)
            else:
                # ׳›׳ ׳”׳—׳ ׳™׳•׳ ׳™׳ ׳©׳ ׳”׳—׳‘׳¨׳”
                company_parkings = supabase.table('user_parkings').select('project_number').eq(
                    'company_type', user_data['company_type']
                ).execute()
                
                parking_numbers = [p['project_number'] for p in company_parkings.data]
                
                if parking_numbers:
                    query = query.in_('project_number', parking_numbers)
                else:
                    return jsonify({'success': True, 'data': []})
        else:
            return jsonify({'success': False, 'message': '׳¨׳׳× ׳”׳¨׳©׳׳” ׳׳ ׳׳•׳›׳¨׳×'})
        
        # ׳”׳’׳‘׳׳× ׳›׳׳•׳× ׳”׳×׳•׳¦׳׳•׳× (׳׳‘׳˜׳—׳”)
        query = query.limit(10000)
        
        # ׳‘׳™׳¦׳•׳¢ ׳”׳©׳׳™׳׳×׳”
        result = query.execute()
        
        # ׳§׳‘׳׳× ׳׳™׳₪׳•׳™ ׳©׳׳•׳× ׳”׳—׳ ׳™׳•׳ ׳™׳ ׳-project_parking_mapping
        parking_names_map = {}
        try:
            mapping_result = supabase.table('project_parking_mapping').select('project_number, parking_name').execute()
            for mapping in mapping_result.data:
                parking_names_map[mapping['project_number']] = mapping['parking_name']
        except Exception as e:
            print(f"Warning: Could not load parking names mapping: {str(e)}")
        
        # ׳¢׳™׳‘׳•׳“ ׳”׳ ׳×׳•׳ ׳™׳
        processed_data = []
        for row in result.data:
            # ׳•׳™׳“׳•׳ ׳©׳›׳ ׳”׳©׳“׳•׳× ׳”׳ ׳“׳¨׳©׳™׳ ׳§׳™׳™׳׳™׳
            processed_row = {
                'id': row.get('id'),
                'parking_id': row.get('parking_id'),
                'report_date': row.get('report_date'),
                'project_number': row.get('project_number'),
                'parking_name': parking_names_map.get(row.get('project_number'), '') or row.get('parking_name', ''),  # ׳©׳ ׳—׳ ׳™׳•׳ ׳׳”׳׳™׳₪׳•׳™
                'total_revenue_shekels': float(row.get('total_revenue_shekels', 0)),
                'net_revenue_shekels': float(row.get('net_revenue_shekels', 0)),
                's_cash_shekels': float(row.get('s_cash_shekels', 0)),
                's_credit_shekels': float(row.get('s_credit_shekels', 0)),
                's_pango_shekels': float(row.get('s_pango_shekels', 0)),
                's_celo_shekels': float(row.get('s_celo_shekels', 0)),
                's_encoder1': int(row.get('s_encoder1', 0)),  # ׳”׳•׳¡׳£ ׳׳§׳•׳“׳“ 1
                's_encoder2': int(row.get('s_encoder2', 0)),  # ׳”׳•׳¡׳£ ׳׳§׳•׳“׳“ 2
                's_encoder3': int(row.get('s_encoder3', 0)),  # ׳”׳•׳¡׳£ ׳׳§׳•׳“׳“ 3
                'sencodertot': int(row.get('sencodertot', 0)),  # ׳”׳•׳¡׳£ ׳¡׳”"׳› ׳׳§׳•׳“׳“׳™׳
                't_entry_tot': int(row.get('t_entry_tot', 0)),
                't_exit_tot': int(row.get('t_exit_tot', 0)),
                't_exit_s': int(row.get('t_exit_s', 0)),
                't_exit_p': int(row.get('t_exit_p', 0)),
                't_entry_s': int(row.get('t_entry_s', 0)),  # ׳׳–׳“׳׳ ׳™׳
                't_entry_p': int(row.get('t_entry_p', 0)),  # ׳׳ ׳•׳™׳™׳
                't_entry_ap': int(row.get('t_entry_ap', 0)),  # ׳׳₪׳׳™׳§׳¦׳™׳”
                't_open_b': int(row.get('t_open_b', 0)),  # ׳₪׳×׳™׳—׳•׳× ׳׳—׳¡׳•׳
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
        
        print(f"ג… Retrieved {len(processed_data)} parking records for user {email}")
        
        return jsonify({
            'success': True,
            'data': processed_data,
            'total_records': len(processed_data)
        })
        
    except Exception as e:
        print(f"ג Error getting parking data: {str(e)}")
        return jsonify({'success': False, 'message': '׳©׳’׳™׳׳” ׳‘׳§׳‘׳׳× ׳ ׳×׳•׳ ׳™ ׳—׳ ׳™׳•׳'})

@app.route('/api/check-emails-now', methods=['POST'])
def manual_email_check():
    """API ׳׳‘׳“׳™׳§׳× ׳׳™׳™׳׳™׳ ׳™׳“׳ ׳™׳×"""
    try:
        if 'user_email' not in session:
            return jsonify({'success': False, 'message': '׳׳ ׳׳—׳•׳‘׳¨'}), 401
        
        if not supabase:
            return jsonify({'success': False, 'message': '׳׳¡׳“ ׳”׳ ׳×׳•׳ ׳™׳ ׳׳ ׳–׳׳™׳'})
        
        if not EMAIL_MONITORING_AVAILABLE:
            return jsonify({'success': False, 'message': '׳׳¢׳¨׳›׳× ׳׳™׳™׳׳™׳ ׳׳ ׳–׳׳™׳ ׳”'})
        
        email = session['user_email']
        user_result = supabase.table('user_parkings').select('role, access_level').eq('email', email).execute()
        
        if not user_result.data:
            return jsonify({'success': False, 'message': '׳׳©׳×׳׳© ׳׳ ׳ ׳׳¦׳'})
        
        user_data = user_result.data[0]
        if user_data.get('role') != 'admin' and user_data.get('access_level') != 'group_manager':
            return jsonify({'success': False, 'message': '׳׳™׳ ׳”׳¨׳©׳׳” ׳׳‘׳“׳™׳§׳× ׳׳™׳™׳׳™׳'})
        
        def test_check():
            with app.app_context():
                check_for_new_emails()
        
        threading.Thread(target=test_check, daemon=True).start()
        
        return jsonify({'success': True, 'message': '׳‘׳“׳™׳§׳× ׳׳™׳™׳׳™׳ ׳”׳—׳׳” ׳‘׳¨׳§׳¢'})
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/forgot-password')
def forgot_password_page():
    """׳“׳£ ׳׳™׳₪׳•׳¡ ׳¡׳™׳¡׳׳”"""
    return render_template('forgot-password.html')

@app.route('/api/forgot-password', methods=['POST'])
def forgot_password():
    """׳‘׳§׳©׳” ׳׳׳™׳₪׳•׳¡ ׳¡׳™׳¡׳׳” - ׳©׳׳™׳—׳× ׳§׳•׳“ ׳׳׳™׳™׳"""
    try:
        if not supabase:
            return jsonify({'success': False, 'message': '׳׳¡׳“ ׳”׳ ׳×׳•׳ ׳™׳ ׳׳ ׳–׳׳™׳'})
        
        data = request.get_json()
        email = data.get('email', '').strip()
        
        # ׳׳™׳׳•׳× ׳׳™׳™׳
        is_valid_email, validated_email = validate_input(email, "email")
        if not is_valid_email:
            return jsonify({'success': False, 'message': '׳›׳×׳•׳‘׳× ׳׳™׳™׳ ׳׳ ׳×׳§׳™׳ ׳”'})
        
        print(f"נ”„ Password reset request for: {validated_email}")
        
        # ׳‘׳“׳™׳§׳” ׳©׳”׳׳™׳™׳ ׳§׳™׳™׳ ׳‘׳׳¢׳¨׳›׳×
        user_result = supabase.table('user_parkings').select('username, email').eq('email', validated_email).execute()
        
        if not user_result.data:
            return jsonify({'success': False, 'message': '׳›׳×׳•׳‘׳× ׳׳™׳™׳ ׳׳ ׳ ׳׳¦׳׳” ׳‘׳׳¢׳¨׳›׳×'})
        
        user = user_result.data[0]
        
        # ׳™׳¦׳™׳¨׳× ׳§׳•׳“ ׳׳™׳׳•׳×
        reset_code = generate_verification_code()
        
        # ׳©׳׳™׳¨׳× ׳”׳§׳•׳“ ׳‘׳–׳™׳›׳¨׳•׳ ׳–׳׳ ׳™
        password_reset_codes[validated_email] = {
            'code': reset_code,
            'timestamp': time.time(),
            'attempts': 0,
            'username': user['username']
        }
        
        print(f"נ” Generated reset code for {validated_email}: {reset_code}")
        
        # ׳©׳׳™׳—׳× ׳׳™׳™׳
        email_sent = send_password_reset_verification_email(validated_email, reset_code, user['username'])
        
        if email_sent:
            return jsonify({
                'success': True,
                'message': '׳§׳•׳“ ׳׳™׳׳•׳× ׳ ׳©׳׳— ׳׳›׳×׳•׳‘׳× ׳”׳׳™׳™׳ ׳©׳׳'
            })
        else:
            return jsonify({
                'success': True,  # ׳ ׳—׳–׳™׳¨ ׳”׳¦׳׳—׳” ׳’׳ ׳׳ ׳”׳׳™׳™׳ ׳ ׳›׳©׳
                'message': '׳§׳•׳“ ׳׳™׳׳•׳× ׳ ׳•׳¦׳¨ (׳‘׳“׳•׳§ ׳׳•׳’׳™׳)'
            })
            
    except Exception as e:
        print(f"ג Forgot password error: {str(e)}")
        return jsonify({'success': False, 'message': '׳©׳’׳™׳׳” ׳‘׳׳¢׳¨׳›׳×'})

@app.route('/api/verify-reset-code', methods=['POST'])
def verify_reset_code():
    """׳׳™׳׳•׳× ׳§׳•׳“ ׳׳™׳₪׳•׳¡ ׳¡׳™׳¡׳׳”"""
    try:
        data = request.get_json()
        email = data.get('email', '').strip()
        code = data.get('code', '').strip()
        
        # ׳׳™׳׳•׳× ׳§׳׳˜
        is_valid_email, validated_email = validate_input(email, "email")
        is_valid_code, validated_code = validate_input(code, "verification_code")
        
        if not is_valid_email or not is_valid_code:
            return jsonify({'success': False, 'message': '׳ ׳×׳•׳ ׳™׳ ׳׳ ׳×׳§׳™׳ ׳™׳'})
        
        print(f"נ” Verifying reset code for: {validated_email}")
        
        # ׳ ׳™׳§׳•׳™ ׳§׳•׳“׳™׳ ׳™׳©׳ ׳™׳
        clean_expired_reset_codes()
        
        # ׳‘׳“׳™׳§׳” ׳©׳”׳§׳•׳“ ׳§׳™׳™׳
        if validated_email not in password_reset_codes:
            return jsonify({'success': False, 'message': '׳§׳•׳“ ׳׳ ׳ ׳׳¦׳ ׳׳• ׳₪׳’ ׳×׳•׳§׳£'})
        
        reset_data = password_reset_codes[validated_email]
        
        # ׳‘׳“׳™׳§׳× ׳×׳•׳§׳£ (10 ׳“׳§׳•׳×)
        if time.time() - reset_data['timestamp'] > 600:  # 10 ׳“׳§׳•׳×
            del password_reset_codes[validated_email]
            return jsonify({'success': False, 'message': '׳”׳§׳•׳“ ׳₪׳’ ׳×׳•׳§׳£'})
        
        # ׳‘׳“׳™׳§׳× ׳ ׳™׳¡׳™׳•׳ ׳•׳× (׳׳§׳¡׳™׳׳•׳ 3)
        if reset_data['attempts'] >= 3:
            del password_reset_codes[validated_email]
            return jsonify({'success': False, 'message': '׳—׳¨׳’׳× ׳׳׳¡׳₪׳¨ ׳”׳ ׳™׳¡׳™׳•׳ ׳•׳× ׳”׳׳•׳×׳¨'})
        
        # ׳‘׳“׳™׳§׳× ׳”׳§׳•׳“
        if reset_data['code'] != validated_code:
            reset_data['attempts'] += 1
            return jsonify({'success': False, 'message': '׳§׳•׳“ ׳©׳’׳•׳™'})
        
        # ׳™׳¦׳™׳¨׳× ׳˜׳•׳§׳ ׳׳׳™׳₪׳•׳¡
        import secrets
        reset_token = secrets.token_urlsafe(32)
        reset_data['token'] = reset_token
        reset_data['verified'] = True
        
        print(f"ג… Reset code verified for: {validated_email}")
        
        return jsonify({
            'success': True,
            'token': reset_token,
            'message': '׳§׳•׳“ ׳׳•׳׳× ׳‘׳”׳¦׳׳—׳”'
        })
        
    except Exception as e:
        print(f"ג Verify reset code error: {str(e)}")
        return jsonify({'success': False, 'message': '׳©׳’׳™׳׳” ׳‘׳׳¢׳¨׳›׳×'})

@app.route('/api/reset-password', methods=['POST'])
def reset_password():
    """׳¢׳“׳›׳•׳ ׳¡׳™׳¡׳׳” ׳—׳“׳©׳”"""
    try:
        if not supabase:
            return jsonify({'success': False, 'message': '׳׳¡׳“ ׳”׳ ׳×׳•׳ ׳™׳ ׳׳ ׳–׳׳™׳'})
        
        data = request.get_json()
        email = data.get('email', '').strip()
        token = data.get('token', '').strip()
        new_password = data.get('newPassword', '').strip()
        
        # ׳׳™׳׳•׳× ׳§׳׳˜
        is_valid_email, validated_email = validate_input(email, "email")
        if not is_valid_email or not token or not new_password:
            return jsonify({'success': False, 'message': '׳ ׳×׳•׳ ׳™׳ ׳׳ ׳×׳§׳™׳ ׳™׳'})
        
        if len(new_password) < 6:
            return jsonify({'success': False, 'message': '׳”׳¡׳™׳¡׳׳” ׳—׳™׳™׳‘׳× ׳׳”׳™׳•׳× ׳׳₪׳—׳•׳× 6 ׳×׳•׳•׳™׳'})
        
        print(f"נ”„ Resetting password for: {validated_email}")
        
        # ׳‘׳“׳™׳§׳× ׳”׳˜׳•׳§׳
        if validated_email not in password_reset_codes:
            return jsonify({'success': False, 'message': '׳˜׳•׳§׳ ׳׳ ׳×׳§׳™׳ ׳׳• ׳₪׳’ ׳×׳•׳§׳£'})
        
        reset_data = password_reset_codes[validated_email]
        
        if not reset_data.get('verified') or reset_data.get('token') != token:
            return jsonify({'success': False, 'message': '׳˜׳•׳§׳ ׳׳ ׳×׳§׳™׳'})
        
        # ׳‘׳“׳™׳§׳× ׳×׳•׳§׳£ (30 ׳“׳§׳•׳× ׳׳×׳—׳™׳׳× ׳”׳×׳”׳׳™׳)
        if time.time() - reset_data['timestamp'] > 1800:  # 30 ׳“׳§׳•׳×
            del password_reset_codes[validated_email]
            return jsonify({'success': False, 'message': '׳”׳˜׳•׳§׳ ׳₪׳’ ׳×׳•׳§׳£'})
        
        # ׳”׳¦׳₪׳ ׳× ׳”׳¡׳™׳¡׳׳” ׳”׳—׳“׳©׳”
        password_hash = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt(rounds=6, prefix=b'2a')).decode('utf-8')
        
        # ׳¢׳“׳›׳•׳ ׳”׳¡׳™׳¡׳׳” ׳‘׳‘׳¡׳™׳¡ ׳”׳ ׳×׳•׳ ׳™׳
        current_time = datetime.now(timezone.utc).isoformat()
        
        update_result = supabase.table('user_parkings').update({
            'password_hash': password_hash,
            'updated_at': current_time,
            'password_changed_at': current_time,
            'is_temp_password': False
        }).eq('email', validated_email).execute()
        
        if update_result.data:
            # ׳׳—׳™׳§׳× ׳”׳§׳•׳“ ׳׳”׳–׳™׳›׳¨׳•׳
            del password_reset_codes[validated_email]
            
            print(f"ג… Password reset successfully for: {validated_email}")
            
            return jsonify({
                'success': True,
                'message': '׳”׳¡׳™׳¡׳׳” ׳¢׳•׳“׳›׳ ׳” ׳‘׳”׳¦׳׳—׳”'
            })
        else:
            return jsonify({'success': False, 'message': '׳©׳’׳™׳׳” ׳‘׳¢׳“׳›׳•׳ ׳”׳¡׳™׳¡׳׳”'})
        
    except Exception as e:
        print(f"ג Reset password error: {str(e)}")
        return jsonify({'success': False, 'message': '׳©׳’׳™׳׳” ׳‘׳׳¢׳¨׳›׳×'})

# ׳”׳•׳¡׳£ ׳’׳ ׳₪׳•׳ ׳§׳¦׳™׳” ׳׳‘׳“׳™׳§׳× ׳×׳§׳₪׳•׳× ׳×׳׳¨׳™׳
def validate_date_format(date_string):
    """׳‘׳“׳™׳§׳× ׳×׳§׳₪׳•׳× ׳₪׳•׳¨׳׳˜ ׳×׳׳¨׳™׳ YYYY-MM-DD"""
    try:
        datetime.strptime(date_string, '%Y-%m-%d')
        return True
    except ValueError:
        return False

@app.route('/api/login', methods=['POST'])
def login():
    print("נ” === LOGIN FUNCTION STARTED ===")
    try:
        print("נ” Step 1: Checking supabase...")
        if not supabase:
            return jsonify({'success': False, 'message': '׳׳¡׳“ ׳”׳ ׳×׳•׳ ׳™׳ ׳׳ ׳–׳׳™׳'})
            
        print("נ” Step 2: Getting JSON data...")
        data = request.get_json()
        username = data.get('username', '').strip()
        password = data.get('password', '').strip()
        
        print("נ” Step 3: Validating input...")
        # ׳׳™׳׳•׳× ׳§׳׳˜
        is_valid_username, validated_username = validate_input(username, "username")
        is_valid_password, validated_password = validate_input(password, "password")
        
        if not is_valid_username:
            print(f"נ¨ Invalid username attempt: {username}")
            return jsonify({'success': False, 'message': '׳©׳ ׳׳©׳×׳׳© ׳׳ ׳×׳§׳™׳'})
        
        if not is_valid_password:
            print(f"נ¨ Invalid password attempt from user: {validated_username}")
            return jsonify({'success': False, 'message': '׳¡׳™׳¡׳׳” ׳׳ ׳×׳§׳™׳ ׳”'})
        
        print(f"נ”‘ Login attempt: {validated_username}")
        print("נ” About to call RPC function...")
        
# ׳§׳¨׳™׳׳” ׳׳₪׳•׳ ׳§׳¦׳™׳” ׳¢׳ ׳˜׳™׳₪׳•׳ ׳₪׳©׳•׳˜  
        try:
            result = supabase.rpc('user_login', {
                'p_username': validated_username,
                'p_password': validated_password
            }).execute()
            auth_result = result.data
            print(f"נ” Normal result: {auth_result}")
            
        except Exception as rpc_error:
            print(f"נ” RPC Exception: {rpc_error}")
            # ׳ ׳™׳§׳— ׳׳× ׳”׳×׳•׳¦׳׳” ׳׳”׳©׳’׳™׳׳”
            if hasattr(rpc_error, 'args') and rpc_error.args:
                auth_result = rpc_error.args[0]
                print(f"נ” From exception: {auth_result}")
                print(f"נ” Type: {type(auth_result)}")
                
                # ׳‘׳“׳™׳§׳× ׳¡׳•׳’ ׳”׳ ׳×׳•׳ ׳™׳
                if isinstance(auth_result, dict):
                    print(f"נ” It's already a dict!")
                elif isinstance(auth_result, str):
                    print(f"נ” Raw string: {repr(auth_result)}")
                    # ׳–׳” ׳›׳ ׳¨׳׳” string ׳©׳ ׳¨׳׳” ׳›׳׳• dict - ׳ ׳ ׳¡׳” eval
                    try:
                        import ast
                        auth_result = ast.literal_eval(auth_result)
                        print(f"נ” Converted with literal_eval: {auth_result}")
                    except:
                        try:
                            import json
                            auth_result = json.loads(auth_result)
                            print(f"נ” Converted with json: {auth_result}")
                        except:
                            print("נ” Could not parse - treating as error message")
                            return jsonify({'success': False, 'message': auth_result})
                else:
                    print(f"נ” Unknown type: {type(auth_result)}")
                    raise rpc_error
            else:
                raise rpc_error
        
        print(f"נ” Final result: {auth_result}")
        
        # ׳¢׳™׳‘׳•׳“ ׳”׳×׳•׳¦׳׳”
        if auth_result and auth_result.get('success'):
            # ׳‘׳“׳™׳§׳” ׳׳ ׳ ׳“׳¨׳© ׳׳©׳ ׳•׳× ׳¡׳™׳¡׳׳”
            if auth_result.get('require_password_change'):
                session['change_password_user'] = validated_username
                print("נ” Redirecting to password change")
                return jsonify({
                    'success': True,
                    'require_password_change': True,
                    'message': auth_result.get('message'),
                    'redirect': '/change-password'
                })
            
            # ׳”׳×׳—׳‘׳¨׳•׳× ׳¨׳’׳™׳׳” - ׳§׳‘׳׳× ׳”׳׳™׳׳™׳™׳
            user_result = supabase.table('user_parkings').select('email').eq('username', validated_username).execute()
            
            if user_result.data and len(user_result.data) > 0:
                email = user_result.data[0]['email']
                print(f"ג… Email found: {email}")
                
                # ׳™׳¦׳™׳¨׳× ׳§׳•׳“ ׳׳™׳׳•׳× ׳—׳“׳©
                verification_code = generate_verification_code()
                print(f"נ¯ Generated code: {verification_code}")
                
                # ׳©׳׳™׳¨׳” ׳‘׳׳¡׳“ ׳ ׳×׳•׳ ׳™׳
                if store_verification_code(email, verification_code):
                    # ׳©׳׳™׳—׳× ׳׳™׳™׳
                    print(f"נ€ Attempting to send email to {email}...")
                    email_sent = send_verification_email(email, verification_code)
                    print(f"נ“§ Email send result: {email_sent}")
                    
                    # ׳©׳׳™׳¨׳” ׳‘-session
                    session['pending_email'] = email
                    print(f"נ“§ Code ready for {email}: {verification_code}")
                    return jsonify({'success': True, 'redirect': '/verify'})
                else:
                    return jsonify({'success': False, 'message': '׳©׳’׳™׳׳” ׳‘׳©׳׳™׳¨׳× ׳”׳§׳•׳“'})
            else:
                return jsonify({'success': False, 'message': '׳׳©׳×׳׳© ׳׳ ׳ ׳׳¦׳'})
        else:
            error_msg = auth_result.get('message', '׳©׳ ׳׳©׳×׳׳© ׳׳• ׳¡׳™׳¡׳׳” ׳©׳’׳•׳™׳™׳') if auth_result else '׳©׳’׳™׳׳” ׳‘׳”׳×׳—׳‘׳¨׳•׳×'
            print(f"ג Authentication failed: {error_msg}")
            return jsonify({'success': False, 'message': error_msg})
            
    except Exception as e:
        print(f"ג OUTER EXCEPTION: {type(e)}")
        print(f"ג OUTER EXCEPTION MESSAGE: {str(e)}")
        return jsonify({'success': False, 'message': '׳©׳’׳™׳׳” ׳‘׳׳¢׳¨׳›׳×'})

@app.route('/api/verify-code', methods=['POST'])
def verify_code():
    try:
        if not supabase:
            return jsonify({'success': False, 'message': '׳׳¡׳“ ׳”׳ ׳×׳•׳ ׳™׳ ׳׳ ׳–׳׳™׳'})
            
        data = request.get_json()
        code = data.get('code', '').strip()
        email = session.get('pending_email')
        
        # ׳׳™׳׳•׳× ׳§׳•׳“
        is_valid_code, validated_code = validate_input(code, "verification_code")
        if not is_valid_code:
            print(f"נ¨ Invalid verification code format: {code}")
            return jsonify({'success': False, 'message': '׳§׳•׳“ ׳׳ ׳×׳§׳™׳'})
        
        if not email:
            print(f"נ¨ No pending email in session")
            return jsonify({'success': False, 'message': '׳׳™׳ ׳‘׳§׳©׳” ׳׳׳™׳׳•׳×'})
        
        print(f"נ” Verify attempt: code={validated_code}, email={email}")
        
        # ׳‘׳“׳™׳§׳× ׳”׳§׳•׳“ ׳׳”׳׳¡׳“ ׳ ׳×׳•׳ ׳™׳
        if verify_code_from_database(email, validated_code):
            session['user_email'] = email
            session.pop('pending_email', None)
            
            # נ†• ׳§׳‘׳׳× ׳ ׳×׳•׳ ׳™ ׳”׳׳©׳×׳׳© ׳׳§׳‘׳™׳¢׳× ׳”׳”׳₪׳ ׳™׳”
            try:
                user_result = supabase.table('user_parkings').select(
                    'code_type, access_level, role'
                ).eq('email', email).execute()
                
                if user_result.data and len(user_result.data) > 0:
                    user_data = user_result.data[0]
                    code_type = user_data.get('code_type', 'dashboard')
                    
                    print(f"ג… SUCCESS - User type: {code_type}")
                    
# ׳§׳‘׳™׳¢׳× ׳”׳₪׳ ׳™׳” ׳׳₪׳™ ׳¡׳•׳’ ׳”׳׳©׳×׳׳©
                    redirect_url = '/dashboard'  # ׳‘׳¨׳™׳¨׳× ׳׳—׳“׳
                    
                    if code_type == 'master':
                        redirect_url = '/master-users'
                        print(f"נ”§ Redirecting MASTER to: {redirect_url}")
                    elif code_type == 'parking_manager':
                        redirect_url = '/parking-manager-users'
                        print(f"נ…¿ן¸ Redirecting PARKING MANAGER to: {redirect_url}")
                    elif code_type == 'company_manager':
                        redirect_url = '/company-manager'
                        print(f"נ¢ Redirecting COMPANY MANAGER to: {redirect_url}")
                    else:
                        # ׳‘׳“׳™׳§׳× access_level ׳׳׳©׳×׳׳©׳™׳ ׳¨׳’׳™׳׳™׳
                        access_level = user_data.get('access_level', 'single_parking')
                        if access_level == 'company_manager':
                            redirect_url = '/company-manager'
                            print(f"נ¢ Redirecting COMPANY MANAGER to: {redirect_url}")
                        else:
                            redirect_url = '/dashboard'
                            print(f"נ“ Redirecting REGULAR USER to: {redirect_url}")

                    return jsonify({
                        'success': True, 
                        'redirect': redirect_url,
                        'user_type': code_type
                    })
                else:
                    print(f"ג ן¸ User data not found, redirecting to dashboard")
                    return jsonify({'success': True, 'redirect': '/dashboard'})
                    
            except Exception as e:
                print(f"ג Error getting user data: {str(e)}")
                # ׳‘׳׳§׳¨׳” ׳©׳ ׳©׳’׳™׳׳”, ׳ ׳₪׳ ׳” ׳׳“׳©׳‘׳•׳¨׳“ ׳¨׳’׳™׳
                return jsonify({'success': True, 'redirect': '/dashboard'})
        else:
            print(f"ג FAILED - Invalid or expired code")
            return jsonify({'success': False, 'message': '׳§׳•׳“ ׳©׳’׳•׳™ ׳׳• ׳₪׳’ ׳×׳•׳§׳£'})
            
    except Exception as e:
        print(f"ג Verify error: {str(e)}")
        return jsonify({'success': False, 'message': '׳©׳’׳™׳׳” ׳‘׳׳¢׳¨׳›׳×'})

# נ†• ׳”׳•׳¡׳£ ׳’׳ ׳₪׳•׳ ׳§׳¦׳™׳” ׳׳‘׳“׳™׳§׳× ׳”׳¨׳©׳׳•׳× ׳׳•׳§׳“׳׳× (׳׳•׳₪׳¦׳™׳•׳ ׳׳™׳×)
def get_user_redirect_url(email):
    """׳§׳‘׳׳× URL ׳׳”׳₪׳ ׳™׳” ׳׳₪׳™ ׳¡׳•׳’ ׳”׳׳©׳×׳׳©"""
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
        print(f"ג Error in get_user_redirect_url: {str(e)}")
        return '/dashboard'

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login_page'))

@app.route('/ping')
def ping():
    current_time = datetime.now()
    print(f"נ“ Ping received at {current_time}")
    print(f"נ”‹ Service status: Active and responsive")
    
    return jsonify({
        'status': 'pong',
        'timestamp': current_time.isoformat(),
        'message': 'Service is alive',
        'uptime': 'Active'
    }), 200

@app.route('/status')
def status():
    """׳‘׳“׳™׳§׳× ׳¡׳˜׳˜׳•׳¡ ׳׳₪׳•׳¨׳˜׳×"""
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
    """׳ ׳§׳•׳“׳× ׳§׳¦׳” ׳׳‘׳“׳™׳§׳× ׳×׳§׳™׳ ׳•׳× ׳”׳©׳™׳¨׳•׳×"""
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

# Route ׳׳“׳£ ׳©׳™׳ ׳•׳™ ׳¡׳™׳¡׳׳”
@app.route('/change-password')
def change_password_page():
    if 'change_password_user' not in session:
        return redirect(url_for('login_page'))
    return render_template('change-password.html')

# API ׳׳©׳™׳ ׳•׳™ ׳¡׳™׳¡׳׳”
@app.route('/api/change-password', methods=['POST'])
def change_password():
    try:
        if not supabase:
            return jsonify({'success': False, 'message': '׳׳¡׳“ ׳”׳ ׳×׳•׳ ׳™׳ ׳׳ ׳–׳׳™׳'})
        
        if 'change_password_user' not in session:
            return jsonify({'success': False, 'message': '׳׳™׳ ׳”׳¨׳©׳׳” ׳׳©׳™׳ ׳•׳™ ׳¡׳™׳¡׳׳”'})
        
        data = request.get_json()
        old_password = data.get('old_password', '').strip()
        new_password = data.get('new_password', '').strip()
        confirm_password = data.get('confirm_password', '').strip()
        
        # ׳׳™׳׳•׳× ׳§׳׳˜
        if not old_password or not new_password or not confirm_password:
            return jsonify({'success': False, 'message': '׳™׳© ׳׳׳׳ ׳׳× ׳›׳ ׳”׳©׳“׳•׳×'})
        
        if new_password != confirm_password:
            return jsonify({'success': False, 'message': '׳¡׳™׳¡׳׳׳•׳× ׳׳ ׳×׳•׳׳׳•׳×'})
        
        if len(new_password) < 6:
            return jsonify({'success': False, 'message': '׳¡׳™׳¡׳׳” ׳—׳™׳™׳‘׳× ׳׳”׳™׳•׳× ׳׳₪׳—׳•׳× 6 ׳×׳•׳•׳™׳'})
        
        username = session['change_password_user']
        
# ׳©׳™׳ ׳•׳™ ׳”׳¡׳™׳¡׳׳” ׳¢׳ ׳˜׳™׳₪׳•׳ ׳‘APIError
        try:
            result = supabase.rpc('change_user_password', {
                'p_username': username,
                'p_old_password': old_password,
                'p_new_password': new_password
            }).execute()
            change_result = result.data
        except Exception as rpc_error:
            # ׳˜׳™׳₪׳•׳ ׳‘׳׳•׳×׳” ׳‘׳¢׳™׳”
            if hasattr(rpc_error, 'args') and rpc_error.args:
                try:
                    import ast
                    change_result = ast.literal_eval(str(rpc_error.args[0]))
                except:
                    change_result = rpc_error.args[0]
            else:
                raise rpc_error
        
        if change_result and change_result.get('success'):
            # ׳׳—׳™׳§׳× ׳”׳׳©׳×׳׳© ׳׳”׳¡׳©׳ ׳•׳—׳–׳¨׳” ׳׳”׳×׳—׳‘׳¨׳•׳×
            session.pop('change_password_user', None)
            return jsonify({
                'success': True,
                'message': '׳¡׳™׳¡׳׳” ׳©׳•׳ ׳×׳” ׳‘׳”׳¦׳׳—׳”. ׳׳ ׳ ׳”׳×׳—׳‘׳¨ ׳׳—׳“׳©',
                'redirect': '/login'
            })
        else:
            error_msg = result.data.get('message', '׳©׳’׳™׳׳” ׳‘׳©׳™׳ ׳•׳™ ׳¡׳™׳¡׳׳”') if result.data else '׳©׳’׳™׳׳” ׳‘׳©׳™׳ ׳•׳™ ׳¡׳™׳¡׳׳”'
            return jsonify({'success': False, 'message': error_msg})
        
    except Exception as e:
        print(f"ג Change password error: {str(e)}")
        return jsonify({'success': False, 'message': '׳©׳’׳™׳׳” ׳‘׳׳¢׳¨׳›׳×'})

# API ׳׳™׳¦׳™׳¨׳× ׳׳©׳×׳׳© ׳—׳“׳© (׳׳׳׳¡׳˜׳¨)
@app.route('/api/create-user', methods=['POST'])
def create_user():
    try:
        if not supabase:
            return jsonify({'success': False, 'message': '׳׳¡׳“ ׳”׳ ׳×׳•׳ ׳™׳ ׳׳ ׳–׳׳™׳'})
        
        # ׳‘׳“׳™׳§׳× ׳”׳¨׳©׳׳•׳× - ׳›׳¨׳’׳¢ ׳ ׳—׳–׳•׳¨ ׳׳–׳” ׳׳—׳¨ ׳›׳
        if 'user_email' not in session:
            return jsonify({'success': False, 'message': '׳׳ ׳׳—׳•׳‘׳¨'})
        
        data = request.get_json()
        username = data.get('username', '').strip()
        email = data.get('email', '').strip()
        project_number = data.get('project_number')
        code_type = data.get('code_type', 'dashboard').strip()
        company_list = data.get('company_list', '').strip() or None
        
        # ׳׳™׳׳•׳× ׳§׳׳˜ ׳‘׳¡׳™׳¡׳™
        if not username or not email or not project_number:
            return jsonify({'success': False, 'message': '׳™׳© ׳׳׳׳ ׳׳× ׳›׳ ׳”׳©׳“׳•׳× ׳”׳ ׳“׳¨׳©׳™׳'})
        
        # ׳™׳¦׳™׳¨׳× ׳”׳׳©׳×׳׳©
        result = supabase.rpc('create_user_with_temp_password', {
            'p_username': username,
            'p_email': email,
            'p_project_number': int(project_number),
            'p_code_type': code_type,
            'p_created_by': session['user_email'],
            'p_company_list': company_list
        }).execute()
        
        if result.data and result.data.get('success'):
            # ׳©׳׳™׳—׳× ׳׳™׳™׳ ׳׳׳©׳×׳׳© ׳”׳—׳“׳©
            user_data = result.data
            send_new_user_email(
                user_data.get('email'),
                user_data.get('username'),
                user_data.get('temp_password'),
                user_data.get('login_url')
            )
            
            return jsonify({
                'success': True,
                'message': f'׳׳©׳×׳׳© ׳ ׳•׳¦׳¨ ׳‘׳”׳¦׳׳—׳”. ׳׳™׳™׳ ׳ ׳©׳׳— ׳-{email}',
                'user_data': {
                    'username': username,
                    'email': email,
                    'temp_password': user_data.get('temp_password')
                }
            })
        else:
            error_msg = result.data.get('message', '׳©׳’׳™׳׳” ׳‘׳™׳¦׳™׳¨׳× ׳׳©׳×׳׳©') if result.data else '׳©׳’׳™׳׳” ׳‘׳™׳¦׳™׳¨׳× ׳׳©׳×׳׳©'
            return jsonify({'success': False, 'message': error_msg})
        
    except Exception as e:
        print(f"ג Create user error: {str(e)}")
        return jsonify({'success': False, 'message': '׳©׳’׳™׳׳” ׳‘׳׳¢׳¨׳›׳×'})

def send_new_user_email(email, username, temp_password, login_url):
    """׳©׳׳™׳—׳× ׳׳™׳™׳ ׳׳׳©׳×׳׳© ׳—׳“׳© ׳¢׳ ׳₪׳¨׳˜׳™ ׳”׳×׳—׳‘׳¨׳•׳×"""
    
    if not mail:
        print(f"ג Mail system not available")
        print(f"נ“± NEW USER DETAILS for {email}:")
        print(f"   Username: {username}")
        print(f"   Password: {temp_password}")
        print(f"   URL: {login_url}")
        return False
    
    try:
        print(f"נ€ Sending new user email to {email}...")
        
        msg = Message(
            subject='׳—׳©׳‘׳•׳ ׳—׳“׳© - S&B Parking',
            recipients=[email],
            html=f"""
            <div style="font-family: Arial, sans-serif; direction: rtl; text-align: right;">
                <h2 style="color: #667eea;">׳©׳™׳™׳“׳˜ ׳׳× ׳‘׳›׳׳ ׳™׳©׳¨׳׳</h2>
                <h3>׳—׳©׳‘׳•׳ ׳—׳“׳© ׳ ׳•׳¦׳¨ ׳¢׳‘׳•׳¨׳ ׳‘׳׳¢׳¨׳›׳× ׳“׳•׳—׳•׳× ׳”׳—׳ ׳™׳•׳×</h3>
                
                <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0;">
                    <p><strong>׳©׳ ׳׳©׳×׳׳©:</strong> {username}</p>
                    <p><strong>׳¡׳™׳¡׳׳” ׳–׳׳ ׳™׳×:</strong> <span style="font-family: monospace; background: #e9ecef; padding: 2px 6px;">{temp_password}</span></p>
                    <p><strong>׳§׳™׳©׳•׳¨ ׳׳”׳×׳—׳‘׳¨׳•׳×:</strong></p>
                    <a href="{login_url}" style="color: #667eea; text-decoration: none; font-weight: bold;">{login_url}</a>
                </div>
                
                <div style="background: #fff3cd; border: 1px solid #ffeaa7; padding: 15px; border-radius: 8px; margin: 20px 0;">
                    <p style="margin: 0; color: #856404;"><strong>׳—׳©׳•׳‘:</strong></p>
                    <p style="margin: 5px 0 0 0; color: #856404;">
                        ג€¢ ׳”׳¡׳™׳¡׳׳” ׳”׳–׳׳ ׳™׳× ׳×׳₪׳•׳’ ׳‘-01/01/2025<br>
                        ג€¢ ׳‘׳›׳ ׳™׳¡׳” ׳”׳¨׳׳©׳•׳ ׳” ׳×׳×׳‘׳§׳© ׳׳©׳ ׳•׳× ׳׳× ׳”׳¡׳™׳¡׳׳”<br>
                        ג€¢ ׳׳׳—׳¨ ׳©׳™׳ ׳•׳™ ׳”׳¡׳™׳¡׳׳” ׳×׳•׳›׳ ׳׳”׳×׳—׳‘׳¨ ׳׳׳¢׳¨׳›׳×
                    </p>
                </div>
                
                <p>׳׳ ׳™׳© ׳׳ ׳©׳׳׳•׳×, ׳¦׳•׳¨ ׳§׳©׳¨ ׳¢׳ ׳׳ ׳”׳ ׳”׳׳¢׳¨׳›׳×.</p>
                
                <hr>
                <p style="color: #666; font-size: 12px;">S&B Parking - ׳׳¢׳¨׳›׳× ׳“׳•׳—׳•׳× ׳—׳ ׳™׳•׳×</p>
            </div>
            """,
            sender=app.config['MAIL_USERNAME']
        )
        
        mail.send(msg)
        print(f"ג… New user email sent successfully to {email}")
        return True
        
    except Exception as e:
        print(f"ג New user email error: {str(e)}")
        print(f"נ“± BACKUP - NEW USER DETAILS for {email}:")
        print(f"   Username: {username}")
        print(f"   Password: {temp_password}")
        print(f"   URL: {login_url}")
        return False

@app.route('/master-users')
def master_users_page():
    """׳“׳£ ׳ ׳™׳”׳•׳ ׳׳©׳×׳׳©׳™׳ ׳׳׳׳¡׳˜׳¨"""
    if 'user_email' not in session:
        return redirect(url_for('login_page'))
    
    # ׳‘׳“׳™׳§׳× ׳”׳¨׳©׳׳•׳× ׳׳׳¡׳˜׳¨
    try:
        user_result = supabase.table('user_parkings').select('code_type, access_level').eq('email', session['user_email']).execute()
        if not user_result.data or user_result.data[0].get('code_type') != 'master':
            print(f"ג ן¸ Unauthorized access attempt to master-users by {session['user_email']}")
            return redirect(url_for('dashboard'))
    except Exception as e:
        print(f"ג Error checking master permissions: {str(e)}")
        return redirect(url_for('dashboard'))
    
    return render_template('master_users.html')

@app.route('/parking-manager-users')
def parking_manager_users_page():
    """׳“׳£ ׳ ׳™׳”׳•׳ ׳׳©׳×׳׳©׳™׳ ׳׳׳ ׳”׳ ׳—׳ ׳™׳•׳"""
    if 'user_email' not in session:
        return redirect(url_for('login_page'))
    
    # ׳‘׳“׳™׳§׳× ׳”׳¨׳©׳׳•׳× ׳׳ ׳”׳ ׳—׳ ׳™׳•׳
    try:
        user_result = supabase.table('user_parkings').select('code_type, project_number, access_level').eq('email', session['user_email']).execute()
        if not user_result.data or user_result.data[0].get('code_type') != 'parking_manager':
            print(f"ג ן¸ Unauthorized access attempt to parking-manager-users by {session['user_email']}")
            return redirect(url_for('dashboard'))
    except Exception as e:
        print(f"ג Error checking parking manager permissions: {str(e)}")
        return redirect(url_for('dashboard'))
    
    return render_template('parking_manager_users.html')

# ========== API ׳׳׳׳¡׳˜׳¨ ==========

@app.route('/api/master/get-all-users', methods=['GET'])
def master_get_all_users():
    """׳§׳‘׳׳× ׳›׳ ׳”׳׳©׳×׳׳©׳™׳ - ׳׳׳׳¡׳˜׳¨ ׳‘׳׳‘׳“"""
    try:
        if 'user_email' not in session:
            return jsonify({'success': False, 'message': '׳׳ ׳׳—׳•׳‘׳¨'}), 401
        
        # ׳‘׳“׳™׳§׳× ׳”׳¨׳©׳׳•׳× ׳׳׳¡׳˜׳¨
        user_result = supabase.table('user_parkings').select('code_type').eq('email', session['user_email']).execute()
        if not user_result.data or user_result.data[0].get('code_type') != 'master':
            return jsonify({'success': False, 'message': '׳׳™׳ ׳”׳¨׳©׳׳”'}), 403
        
        # ׳§׳‘׳׳× ׳›׳ ׳”׳׳©׳×׳׳©׳™׳
        users_result = supabase.table('user_parkings').select(
            'user_id, username, email, role, project_number, parking_name, company_type, access_level, code_type, created_at, password_changed_at, is_temp_password'
        ).order('created_at', desc=True).execute()
        
        return jsonify({
            'success': True,
            'users': users_result.data
        })
        
    except Exception as e:
        print(f"ג Error getting all users: {str(e)}")
        return jsonify({'success': False, 'message': '׳©׳’׳™׳׳” ׳‘׳§׳‘׳׳× ׳¨׳©׳™׳׳× ׳׳©׳×׳׳©׳™׳'})

@app.route('/api/master/create-user', methods=['POST'])
def master_create_user():
    """׳™׳¦׳™׳¨׳× ׳׳©׳×׳׳© ׳—׳“׳© - ׳׳׳׳¡׳˜׳¨ ׳‘׳׳‘׳“ - ׳¢׳ user_id ׳™׳“׳ ׳™"""
    try:
        if 'user_email' not in session:
            return jsonify({'success': False, 'message': '׳׳ ׳׳—׳•׳‘׳¨'}), 401
        
        # ׳‘׳“׳™׳§׳× ׳”׳¨׳©׳׳•׳× ׳׳׳¡׳˜׳¨
        user_result = supabase.table('user_parkings').select('code_type').eq('email', session['user_email']).execute()
        if not user_result.data or user_result.data[0].get('code_type') != 'master':
            return jsonify({'success': False, 'message': '׳׳™׳ ׳”׳¨׳©׳׳”'}), 403
        
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
                return jsonify({'success': False, 'message': '׳¨׳©׳™׳׳× ׳׳¡׳₪׳¨׳™ ׳—׳‘׳¨׳•׳× ׳™׳›׳•׳׳” ׳׳›׳׳•׳ ׳¨׳§ ׳׳¡׳₪׳¨׳™׳ ׳•׳׳§׳₪׳™׳'})
    
        if '--' in company_list or company_list.startswith('-') or company_list.endswith('-'):
                return jsonify({'success': False, 'message': '׳₪׳•׳¨׳׳˜ ׳¨׳©׳™׳׳× ׳׳¡׳₪׳¨׳™ ׳—׳‘׳¨׳•׳× ׳׳ ׳×׳§׳™׳'})

        print(f"נ†• Creating new user: {username} ({email})")
        
        # ׳׳™׳׳•׳× ׳§׳׳˜ ׳‘׳¡׳™׳¡׳™
        if not username or not email:
            return jsonify({'success': False, 'message': '׳™׳© ׳׳׳׳ ׳©׳ ׳׳©׳×׳׳© ׳•׳׳™׳׳™׳™׳'})

        # ׳×׳™׳§׳•׳£ ׳©׳ ׳׳©׳×׳׳©
        is_valid_username, username_or_error = validate_username(username)
        if not is_valid_username:
            return jsonify({'success': False, 'message': username_or_error})
        
        # ׳׳™׳׳•׳× ׳׳™׳׳™׳™׳
        is_valid_email, validated_email = validate_input(email, "email")
        if not is_valid_email:
            return jsonify({'success': False, 'message': '׳›׳×׳•׳‘׳× ׳׳™׳׳™׳™׳ ׳׳ ׳×׳§׳™׳ ׳”'})
        
        # ׳‘׳“׳™׳§׳” ׳׳ ׳”׳׳©׳×׳׳© ׳›׳‘׳¨ ׳§׳™׳™׳
        existing_username = supabase.table('user_parkings').select('username').eq('username', username).execute()
        existing_email = supabase.table('user_parkings').select('email').eq('email', validated_email).execute()
        
        if existing_username.data:
            return jsonify({'success': False, 'message': f'׳©׳ ׳׳©׳×׳׳© "{username}" ׳›׳‘׳¨ ׳§׳™׳™׳ ׳‘׳׳¢׳¨׳›׳×'})
        
        if existing_email.data:
            return jsonify({'success': False, 'message': f'׳›׳×׳•׳‘׳× ׳׳™׳׳™׳™׳ "{validated_email}" ׳›׳‘׳¨ ׳§׳™׳™׳׳× ׳‘׳׳¢׳¨׳›׳×'})
        
        # ׳™׳¦׳™׳¨׳× hash ׳׳¡׳™׳¡׳׳”
        password_hash = bcrypt.hashpw('Dd123456'.encode('utf-8'), bcrypt.gensalt(rounds=6, prefix=b'2a')).decode('utf-8')
        
        # ׳§׳‘׳׳× user_id ׳”׳‘׳
        try:
            max_user_result = supabase.table('user_parkings').select('user_id').order('user_id', desc=True).limit(1).execute()
            
            if max_user_result.data:
                next_user_id = max_user_result.data[0]['user_id'] + 1
            else:
                next_user_id = 1
            
            print(f"נ†” Next user_id will be: {next_user_id}")
            
        except Exception as e:
            print(f"ג Error getting max user_id: {str(e)}")
            import random
            next_user_id = random.randint(1000, 9999)
            print(f"נ² Using random user_id: {next_user_id}")
        
        # ׳”׳›׳ ׳× ׳”׳ ׳×׳•׳ ׳™׳ ׳׳”׳•׳¡׳₪׳”
        current_time = datetime.now(timezone.utc).isoformat()
        
        new_user_data = {
            'user_id': next_user_id,
            'username': username,
            'email': validated_email,
            'password_hash': password_hash,
            'role': role,
            'project_number': int(project_number) if project_number else 0,
            'parking_name': parking_name if parking_name else '׳׳ ׳¦׳•׳™׳',
            'company_type': company_type if company_type else '׳׳ ׳¦׳•׳™׳',
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
        
        print(f"נ’¾ Inserting user data with user_id {next_user_id}")
        
        # ׳”׳•׳¡׳₪׳× ׳”׳׳©׳×׳׳© ׳׳׳¡׳“ ׳”׳ ׳×׳•׳ ׳™׳
        result = supabase.table('user_parkings').insert(new_user_data).execute()
        
        if result.data:
            print(f"ג… User created successfully: {username} (ID: {next_user_id})")
            
            # ׳©׳׳™׳—׳× ׳׳™׳™׳ ׳׳׳©׳×׳׳© ׳”׳—׳“׳©
            email_sent = send_new_user_welcome_email(
                validated_email,
                username,
                'Dd123456',
                'https://s-b-parking-reports.onrender.com'
            )
            
            if email_sent:
                message = f'׳׳©׳×׳׳© {username} ׳ ׳•׳¦׳¨ ׳‘׳”׳¦׳׳—׳”! ׳׳™׳™׳ ׳ ׳©׳׳— ׳-{validated_email}'
            else:
                message = f'׳׳©׳×׳׳© {username} ׳ ׳•׳¦׳¨ ׳‘׳”׳¦׳׳—׳”, ׳׳ ׳׳ ׳ ׳™׳×׳ ׳׳©׳׳•׳— ׳׳™׳™׳. ׳”׳¡׳™׳¡׳׳” ׳”׳¨׳׳©׳•׳ ׳™׳×: Dd123456'
            
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
            print(f"ג Failed to insert user to database")
            return jsonify({'success': False, 'message': '׳©׳’׳™׳׳” ׳‘׳™׳¦׳™׳¨׳× ׳”׳׳©׳×׳׳© ׳‘׳׳¡׳“ ׳”׳ ׳×׳•׳ ׳™׳'})
        
    except Exception as e:
        print(f"ג Master create user error: {str(e)}")
        return jsonify({'success': False, 'message': f'׳©׳’׳™׳׳” ׳‘׳׳¢׳¨׳›׳×: {str(e)}'})


@app.route('/api/parking-manager/create-user', methods=['POST'])
def parking_manager_create_user():
   """׳™׳¦׳™׳¨׳× ׳§׳•׳“ ׳׳ ׳”׳ ׳—׳‘׳¨׳” - ׳׳׳ ׳”׳ ׳—׳ ׳™׳•׳ ׳‘׳׳‘׳“ - ׳¨׳§ ׳׳—׳ ׳™׳•׳ ׳©׳׳•"""
   try:
       if 'user_email' not in session:
           return jsonify({'success': False, 'message': '׳׳ ׳׳—׳•׳‘׳¨'}), 401
       
       # ׳‘׳“׳™׳§׳× ׳”׳¨׳©׳׳•׳× ׳׳ ׳”׳ ׳—׳ ׳™׳•׳
       manager_result = supabase.table('user_parkings').select(
           'code_type, project_number, parking_name, company_type'
       ).eq('email', session['user_email']).execute()
       
       if not manager_result.data or manager_result.data[0].get('code_type') != 'parking_manager':
           return jsonify({'success': False, 'message': '׳׳™׳ ׳”׳¨׳©׳׳” - ׳ ׳“׳¨׳© ׳§׳•׳“ ׳׳ ׳”׳ ׳—׳ ׳™׳•׳'}), 403
       
       manager_data = manager_result.data[0]
       
       data = request.get_json()
       username = data.get('username', '').strip()
       email = data.get('email', '').strip()
       
       print(f"נ…¿ן¸ Parking manager creating COMPANY MANAGER for parking: {manager_data['project_number']} ({manager_data['parking_name']})")
       
       # ׳׳™׳׳•׳× ׳§׳׳˜ ׳‘׳¡׳™׳¡׳™
       if not username or not email:
           return jsonify({'success': False, 'message': '׳™׳© ׳׳׳׳ ׳©׳ ׳׳©׳×׳׳© ׳•׳׳™׳׳™׳™׳'})

       # ׳×׳™׳§׳•׳£ ׳©׳ ׳׳©׳×׳׳©
       is_valid_username, username_or_error = validate_username(username)
       if not is_valid_username:
           return jsonify({'success': False, 'message': username_or_error})
       
       # ׳׳™׳׳•׳× ׳׳™׳׳™׳™׳
       is_valid_email, validated_email = validate_input(email, "email")
       if not is_valid_email:
           return jsonify({'success': False, 'message': '׳›׳×׳•׳‘׳× ׳׳™׳׳™׳™׳ ׳׳ ׳×׳§׳™׳ ׳”'})
       
       # ׳‘׳“׳™׳§׳” ׳׳ ׳”׳׳©׳×׳׳© ׳›׳‘׳¨ ׳§׳™׳™׳
       existing_username = supabase.table('user_parkings').select('username').eq('username', username).execute()
       existing_email = supabase.table('user_parkings').select('email').eq('email', validated_email).execute()
       
       if existing_username.data:
           return jsonify({'success': False, 'message': f'׳©׳ ׳׳©׳×׳׳© "{username}" ׳›׳‘׳¨ ׳§׳™׳™׳ ׳‘׳׳¢׳¨׳›׳×'})
       
       if existing_email.data:
           return jsonify({'success': False, 'message': f'׳›׳×׳•׳‘׳× ׳׳™׳׳™׳™׳ "{validated_email}" ׳›׳‘׳¨ ׳§׳™׳™׳׳× ׳‘׳׳¢׳¨׳›׳×'})
       
       # ׳™׳¦׳™׳¨׳× hash ׳׳¡׳™׳¡׳׳”
       password_hash = bcrypt.hashpw('Dd123456'.encode('utf-8'), bcrypt.gensalt(rounds=6, prefix=b'2a')).decode('utf-8')
       
       # ׳§׳‘׳׳× user_id ׳”׳‘׳
       try:
           max_user_result = supabase.table('user_parkings').select('user_id').order('user_id', desc=True).limit(1).execute()
           
           if max_user_result.data:
               next_user_id = max_user_result.data[0]['user_id'] + 1
           else:
               next_user_id = 1
           
           print(f"נ†” Next user_id will be: {next_user_id}")
           
       except Exception as e:
           print(f"ג Error getting max user_id: {str(e)}")
           import random
           next_user_id = random.randint(1000, 9999)
           print(f"נ² Using random user_id: {next_user_id}")
       
       # ׳”׳›׳ ׳× ׳”׳ ׳×׳•׳ ׳™׳ ׳׳”׳•׳¡׳₪׳” - נ”’ ׳™׳•׳¦׳¨ ׳¨׳§ ׳§׳•׳“ ׳׳ ׳”׳ ׳—׳‘׳¨׳” ׳׳—׳ ׳™׳•׳ ׳”׳¡׳₪׳¦׳™׳₪׳™
       current_time = datetime.now(timezone.utc).isoformat()
       
       new_user_data = {
           'user_id': next_user_id,
           'username': username,
           'email': validated_email,
           'password_hash': password_hash,
           'role': 'user',
           'project_number': manager_data['project_number'],  # נ”’ ׳—׳•׳‘׳” - ׳¨׳§ ׳”׳—׳ ׳™׳•׳ ׳©׳ ׳”׳׳ ׳”׳
           'parking_name': manager_data['parking_name'],      # נ”’ ׳—׳•׳‘׳” - ׳¨׳§ ׳”׳—׳ ׳™׳•׳ ׳©׳ ׳”׳׳ ׳”׳
           'company_type': manager_data['company_type'],      # נ”’ ׳—׳•׳‘׳” - ׳¨׳§ ׳”׳—׳‘׳¨׳” ׳©׳ ׳”׳׳ ׳”׳
           'access_level': 'company_manager',                 # נ”’ ׳—׳•׳‘׳” - ׳×׳׳™׳“ ׳׳ ׳”׳ ׳—׳‘׳¨׳”
           'code_type': 'company_manager',                    # נ”’ ׳—׳•׳‘׳” - ׳×׳׳™׳“ ׳§׳•׳“ ׳׳ ׳”׳ ׳—׳‘׳¨׳”
           'created_at': current_time,
           'updated_at': current_time,
           'password_changed_at': current_time,
           'is_temp_password': True,
           'verification_code': None,
           'code_expires_at': None,
           'password_expires_at': None,
           'company_list': None
       }
       
       print(f"נ’¾ Creating COMPANY MANAGER user for parking: {manager_data['project_number']} ({manager_data['parking_name']})")
       
       # ׳”׳•׳¡׳₪׳× ׳”׳׳©׳×׳׳© ׳׳׳¡׳“ ׳”׳ ׳×׳•׳ ׳™׳
       result = supabase.table('user_parkings').insert(new_user_data).execute()
       
       if result.data:
           print(f"ג… Company manager created successfully: {username} (ID: {next_user_id}) - FOR PARKING: {manager_data['project_number']} ({manager_data['parking_name']})")
           
           # ׳©׳׳™׳—׳× ׳׳™׳™׳ ׳׳׳©׳×׳׳© ׳”׳—׳“׳©
           email_sent = send_new_user_welcome_email(
               validated_email,
               username,
               'Dd123456',
               'https://s-b-parking-reports.onrender.com'
           )
           
           if email_sent:
               message = f'׳׳ ׳”׳ ׳—׳‘׳¨׳” {username} ׳ ׳•׳¦׳¨ ׳‘׳”׳¦׳׳—׳” ׳¢׳‘׳•׳¨ ׳—׳ ׳™׳•׳ {manager_data["parking_name"]}! ׳׳™׳™׳ ׳ ׳©׳׳— ׳-{validated_email}'
           else:
               message = f'׳׳ ׳”׳ ׳—׳‘׳¨׳” {username} ׳ ׳•׳¦׳¨ ׳‘׳”׳¦׳׳—׳” ׳¢׳‘׳•׳¨ ׳—׳ ׳™׳•׳ {manager_data["parking_name"]}, ׳׳ ׳׳ ׳ ׳™׳×׳ ׳׳©׳׳•׳— ׳׳™׳™׳. ׳”׳¡׳™׳¡׳׳” ׳”׳¨׳׳©׳•׳ ׳™׳×: Dd123456'
           
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
           print(f"ג Failed to insert company manager to database")
           return jsonify({'success': False, 'message': '׳©׳’׳™׳׳” ׳‘׳™׳¦׳™׳¨׳× ׳”׳׳ ׳”׳ ׳‘׳׳¡׳“ ׳”׳ ׳×׳•׳ ׳™׳'})
       
   except Exception as e:
       print(f"ג Parking manager create company manager error: {str(e)}")
       return jsonify({'success': False, 'message': f'׳©׳’׳™׳׳” ׳‘׳׳¢׳¨׳›׳×: {str(e)}'})

@app.route('/api/master/reset-password', methods=['POST'])
def master_reset_password():
    """׳׳™׳₪׳•׳¡ ׳¡׳™׳¡׳׳” - ׳׳׳׳¡׳˜׳¨ ׳‘׳׳‘׳“"""
    try:
        if 'user_email' not in session:
            return jsonify({'success': False, 'message': '׳׳ ׳׳—׳•׳‘׳¨'}), 401
        
        # ׳‘׳“׳™׳§׳× ׳”׳¨׳©׳׳•׳× ׳׳׳¡׳˜׳¨
        user_result = supabase.table('user_parkings').select('code_type').eq('email', session['user_email']).execute()
        if not user_result.data or user_result.data[0].get('code_type') != 'master':
            return jsonify({'success': False, 'message': '׳׳™׳ ׳”׳¨׳©׳׳”'}), 403
        
        data = request.get_json()
        target_username = data.get('username', '').strip()
        
        if not target_username:
            return jsonify({'success': False, 'message': '׳™׳© ׳׳¦׳™׳™׳ ׳©׳ ׳׳©׳×׳׳©'})
        
        # ׳׳™׳₪׳•׳¡ ׳”׳¡׳™׳¡׳׳” ׳-Dd123456
        try:
            result = supabase.rpc('master_reset_password', {
                'p_username': target_username,
                'p_new_password': 'Dd123456',
                'p_reset_by': session['user_email']
            }).execute()
        except Exception as rpc_error:
            # ׳˜׳™׳₪׳•׳ ׳‘APIError
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
            # ׳§׳‘׳׳× ׳›׳×׳•׳‘׳× ׳”׳׳™׳™׳ ׳©׳ ׳”׳׳©׳×׳׳©
            user_info = supabase.table('user_parkings').select('email').eq('username', target_username).execute()
            if user_info.data:
                user_email = user_info.data[0]['email']
                send_password_reset_email(user_email, target_username, 'Dd123456')
            
            return jsonify({
                'success': True,
                'message': f'׳¡׳™׳¡׳׳” ׳׳•׳₪׳¡׳” ׳‘׳”׳¦׳׳—׳” ׳¢׳‘׳•׳¨ {target_username}'
            })
        else:
            error_msg = result_data.get('message', '׳©׳’׳™׳׳” ׳‘׳׳™׳₪׳•׳¡ ׳¡׳™׳¡׳׳”') if result_data else '׳©׳’׳™׳׳” ׳‘׳׳™׳₪׳•׳¡ ׳¡׳™׳¡׳׳”'
            return jsonify({'success': False, 'message': error_msg})
        
    except Exception as e:
        print(f"ג Master reset password error: {str(e)}")
        return jsonify({'success': False, 'message': '׳©׳’׳™׳׳” ׳‘׳׳¢׳¨׳›׳×'})

@app.route('/company-manager')
def company_manager_page():
    """׳“׳£ ׳ ׳™׳”׳•׳ ׳—׳‘׳¨׳” ׳׳׳ ׳”׳ ׳—׳‘׳¨׳”"""
    if 'user_email' not in session:
        return redirect(url_for('login_page'))
    
    # ׳‘׳“׳™׳§׳× ׳”׳¨׳©׳׳•׳× ׳׳ ׳”׳ ׳—׳‘׳¨׳”
    try:
        user_result = supabase.table('user_parkings').select(
            'code_type, access_level, permissions, company_list, project_number'
        ).eq('email', session['user_email']).execute()
        
        if not user_result.data:
            print(f"ג ן¸ User not found: {session['user_email']}")
            return redirect(url_for('dashboard'))
        
        user_data = user_result.data[0]
        code_type = user_data.get('code_type')
        access_level = user_data.get('access_level')
        permissions = user_data.get('permissions', '')
        company_list = user_data.get('company_list', '')
        project_number = user_data.get('project_number')
        
        # ׳‘׳“׳™׳§׳” ׳©׳–׳” ׳׳ ׳”׳ ׳—׳‘׳¨׳”
        if code_type != 'company_manager' and access_level != 'company_manager':
            print(f"ג ן¸ Unauthorized access attempt to company-manager by {session['user_email']}")
            return redirect(url_for('dashboard'))
        
        # ׳‘׳“׳™׳§׳× ׳”׳¨׳©׳׳•׳× - ׳¦׳¨׳™׳ ׳׳₪׳—׳•׳× ׳”׳¨׳©׳׳× R (report)
        if 'R' not in permissions and 'P' not in permissions:
            print(f"ג ן¸ No report permissions for {session['user_email']}")
            return redirect(url_for('dashboard'))
        
        # ׳©׳׳™׳¨׳× ׳ ׳×׳•׳ ׳™׳ ׳‘-session ׳׳©׳™׳׳•׳© ׳‘-API
        session['user_permissions'] = permissions
        session['user_company_list'] = company_list
        session['user_project_number'] = project_number
        session['user_access_level'] = access_level
            
    except Exception as e:
        print(f"ג Error checking company manager permissions: {str(e)}")
        return redirect(url_for('dashboard'))
    
    return render_template('parking_subscribers.html')
    
    
# ========== API ׳׳׳ ׳”׳ ׳—׳‘׳¨׳” - ׳—׳ ׳™׳•׳ ׳™׳ ׳•׳׳ ׳•׳™׳™׳ ==========

@app.route('/api/company-manager/get-parkings', methods=['GET'])
def company_manager_get_parkings():
    """׳§׳‘׳׳× ׳¨׳©׳™׳׳× ׳—׳ ׳™׳•׳ ׳™׳ ׳¢׳‘׳•׳¨ ׳׳ ׳”׳ ׳—׳‘׳¨׳”"""
    try:
        if 'user_email' not in session:
            return jsonify({'success': False, 'message': '׳׳ ׳׳—׳•׳‘׳¨'}), 401
        
        # ׳§׳‘׳׳× ׳ ׳×׳•׳ ׳™ ׳”׳׳©׳×׳׳©
        user_result = supabase.table('user_parkings').select(
            'project_number, company_list, access_level, permissions'
        ).eq('email', session['user_email']).execute()
        
        if not user_result.data:
            return jsonify({'success': False, 'message': '׳׳©׳×׳׳© ׳׳ ׳ ׳׳¦׳'}), 404
        
        user_data = user_result.data[0]
        company_list = user_data.get('company_list', '')
        permissions = user_data.get('permissions', '')
        
        # ׳‘׳“׳™׳§׳× ׳”׳¨׳©׳׳•׳×
        if 'R' not in permissions and 'P' not in permissions:
            return jsonify({'success': False, 'message': '׳׳™׳ ׳”׳¨׳©׳׳× ׳“׳•׳—׳•׳×'}), 403
        
        # ׳₪׳¢׳ ׳•׳— ׳¨׳©׳™׳׳× ׳”׳—׳‘׳¨׳•׳×
        allowed_companies = []
        if company_list:
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
        
        # ׳—׳™׳₪׳•׳© ׳—׳ ׳™׳•׳ ׳™׳ ׳‘׳˜׳‘׳׳× parking_lots
        parkings_result = supabase.table('parking_lots').select(
            'id, name, location, description, ip_address, port, is_active'
        ).execute()
        
        parkings = []
        for parking in parkings_result.data:
            # ׳‘׳“׳™׳§׳” ׳׳ ׳”׳—׳ ׳™׳•׳ ׳‘׳¨׳©׳™׳׳× ׳”׳—׳‘׳¨׳•׳× ׳”׳׳•׳¨׳©׳•׳×
            try:
                parking_number = int(parking.get('description', 0))
                if not allowed_companies or parking_number in allowed_companies:
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
            except:
                pass
        
        return jsonify({
            'success': True,
            'parkings': parkings,
            'user_permissions': permissions,
            'company_list': company_list
        })
        
    except Exception as e:
        print(f"ג Error getting parkings: {str(e)}")
        return jsonify({'success': False, 'message': '׳©׳’׳™׳׳” ׳‘׳˜׳¢׳™׳ ׳× ׳—׳ ׳™׳•׳ ׳™׳'}), 500


@app.route('/api/company-manager/get-subscribers', methods=['GET'])
def company_manager_get_subscribers():
    """׳§׳‘׳׳× ׳¨׳©׳™׳׳× ׳׳ ׳•׳™׳™׳ ׳׳—׳ ׳™׳•׳ ׳¡׳₪׳¦׳™׳₪׳™"""
    try:
        if 'user_email' not in session:
            return jsonify({'success': False, 'message': '׳׳ ׳׳—׳•׳‘׳¨'}), 401
        
        parking_id = request.args.get('parking_id')
        if not parking_id:
            return jsonify({'success': False, 'message': '׳—׳¡׳¨ ׳׳–׳”׳” ׳—׳ ׳™׳•׳'}), 400
        
        # ׳§׳‘׳׳× ׳ ׳×׳•׳ ׳™ ׳”׳׳©׳×׳׳©
        user_permissions = session.get('user_permissions', '')
        company_list = session.get('user_company_list', '')
        
        # ׳‘׳“׳™׳§׳× ׳”׳¨׳©׳׳•׳×
        if 'R' not in user_permissions and 'P' not in user_permissions:
            return jsonify({'success': False, 'message': '׳׳™׳ ׳”׳¨׳©׳׳× ׳“׳•׳—׳•׳×'}), 403
        
        # ׳§׳‘׳׳× ׳ ׳×׳•׳ ׳™ ׳”׳—׳ ׳™׳•׳ ׳›׳•׳׳ IP ׳•׳₪׳•׳¨׳˜
        parking_result = supabase.table('parking_lots').select(
            'name, ip_address, port, description'
        ).eq('id', parking_id).execute()
        
        if not parking_result.data:
            return jsonify({'success': False, 'message': '׳—׳ ׳™׳•׳ ׳׳ ׳ ׳׳¦׳'}), 404
        
        parking_data = parking_result.data[0]
        
        # ׳‘׳“׳™׳§׳” ׳׳ ׳”׳—׳ ׳™׳•׳ ׳‘׳¨׳©׳™׳׳× ׳”׳—׳‘׳¨׳•׳× ׳”׳׳•׳¨׳©׳•׳×
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
                    return jsonify({'success': False, 'message': '׳׳™׳ ׳”׳¨׳©׳׳” ׳׳—׳ ׳™׳•׳ ׳–׳”'}), 403
            except:
                pass
        
        # ׳™׳¦׳™׳¨׳× URL ׳׳§׳¨׳™׳׳” ׳׳©׳¨׳× ׳”׳—׳ ׳™׳•׳
        ip_address = parking_data.get('ip_address')
        port = parking_data.get('port', 443)
        
        if not ip_address:
            return jsonify({'success': False, 'message': '׳—׳¡׳¨׳™׳ ׳ ׳×׳•׳ ׳™ ׳—׳™׳‘׳•׳¨ ׳׳—׳ ׳™׳•׳'}), 500
        
        # ׳›׳׳ ׳¦׳¨׳™׳ ׳׳‘׳¦׳¢ ׳§׳¨׳™׳׳” ׳׳©׳¨׳× ׳”׳—׳ ׳™׳•׳
        # ׳׳¢׳× ׳¢׳×׳” ׳׳—׳–׳™׳¨׳™׳ ׳“׳•׳’׳׳”
        return jsonify({
            'success': True,
            'parking_name': parking_data['name'],
            'parking_api_url': f"https://{ip_address}:{port}",
            'subscribers': [],  # ׳™׳×׳׳׳ ׳׳”׳§׳¨׳™׳׳” ׳׳©׳¨׳× ׳”׳—׳ ׳™׳•׳
            'message': '׳ ׳“׳¨׳© ׳—׳™׳‘׳•׳¨ ׳׳©׳¨׳× ׳”׳—׳ ׳™׳•׳'
        })
        
    except Exception as e:
        print(f"ג Error getting subscribers: {str(e)}")
        return jsonify({'success': False, 'message': '׳©׳’׳™׳׳” ׳‘׳˜׳¢׳™׳ ׳× ׳׳ ׳•׳™׳™׳'}), 500


@app.route('/api/company-manager/proxy', methods=['POST'])
def company_manager_proxy():
    """Proxy ׳׳§׳¨׳™׳׳•׳× API ׳׳©׳¨׳×׳™ ׳”׳—׳ ׳™׳•׳ ׳™׳"""
    try:
        if 'user_email' not in session:
            return jsonify({'success': False, 'message': '׳׳ ׳׳—׳•׳‘׳¨'}), 401
        
        data = request.get_json()
        parking_id = data.get('parking_id')
        endpoint = data.get('endpoint')
        method = data.get('method', 'GET')
        payload = data.get('payload', {})
        
        if not parking_id or not endpoint:
            return jsonify({'success': False, 'message': '׳—׳¡׳¨׳™׳ ׳₪׳¨׳׳˜׳¨׳™׳'}), 400
        
        # ׳§׳‘׳׳× ׳ ׳×׳•׳ ׳™ ׳”׳—׳ ׳™׳•׳
        parking_result = supabase.table('parking_lots').select(
            'ip_address, port, description'
        ).eq('id', parking_id).execute()
        
        if not parking_result.data:
            return jsonify({'success': False, 'message': '׳—׳ ׳™׳•׳ ׳׳ ׳ ׳׳¦׳'}), 404
        
        parking_data = parking_result.data[0]
        ip_address = parking_data.get('ip_address')
        port = parking_data.get('port', 443)
        
        if not ip_address:
            return jsonify({'success': False, 'message': '׳—׳¡׳¨׳™׳ ׳ ׳×׳•׳ ׳™ ׳—׳™׳‘׳•׳¨'}), 500
        
        # ׳‘׳ ׳™׳™׳× URL
        protocol = "https" if port == 443 or port == 8443 else "http"
        url = f"{protocol}://{ip_address}:{port}/api/{endpoint}"
        
        # ׳‘׳™׳¦׳•׳¢ ׳”׳§׳¨׳™׳׳”
        headers = {'Content-Type': 'application/json'}
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, verify=False, timeout=10)
            elif method == 'POST':
                response = requests.post(url, json=payload, headers=headers, verify=False, timeout=10)
            elif method == 'PUT':
                response = requests.put(url, json=payload, headers=headers, verify=False, timeout=10)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers, verify=False, timeout=10)
            else:
                return jsonify({'success': False, 'message': '׳©׳™׳˜׳” ׳׳ ׳ ׳×׳׳›׳×'}), 400
            
            # ׳”׳—׳–׳¨׳× ׳”׳×׳•׳¦׳׳”
            if response.status_code == 200:
                return jsonify({
                    'success': True,
                    'data': response.json() if response.text else {}
                })
            else:
                return jsonify({
                    'success': False,
                    'message': f'׳©׳’׳™׳׳” ׳‘׳§׳¨׳™׳׳” ׳׳©׳¨׳× ׳”׳—׳ ׳™׳•׳: {response.status_code}'
                }), response.status_code
                
        except requests.exceptions.Timeout:
            return jsonify({'success': False, 'message': '׳–׳׳ ׳”׳”׳׳×׳ ׳” ׳׳©׳¨׳× ׳”׳—׳ ׳™׳•׳ ׳₪׳’'}), 504
        except requests.exceptions.ConnectionError:
            return jsonify({'success': False, 'message': '׳׳ ׳ ׳™׳×׳ ׳׳”׳×׳—׳‘׳¨ ׳׳©׳¨׳× ׳”׳—׳ ׳™׳•׳'}), 503
        except Exception as e:
            print(f"ג Proxy error: {str(e)}")
            return jsonify({'success': False, 'message': '׳©׳’׳™׳׳” ׳‘׳—׳™׳‘׳•׳¨ ׳׳©׳¨׳× ׳”׳—׳ ׳™׳•׳'}), 500
            
    except Exception as e:
        print(f"ג Company manager proxy error: {str(e)}")
        return jsonify({'success': False, 'message': '׳©׳’׳™׳׳” ׳›׳׳׳™׳×'}), 500

# ========== API ׳׳׳ ׳”׳ ׳—׳ ׳™׳•׳ ==========
@app.route('/api/parking-manager/get-parking-info', methods=['GET'])
def parking_manager_get_info():
    """׳§׳‘׳׳× ׳ ׳×׳•׳ ׳™ ׳”׳—׳ ׳™׳•׳ ׳©׳ ׳”׳׳ ׳”׳"""
    try:
        if 'user_email' not in session:
            return jsonify({'success': False, 'message': '׳׳ ׳׳—׳•׳‘׳¨'}), 401
        
        # ׳‘׳“׳™׳§׳× ׳”׳¨׳©׳׳•׳× ׳׳ ׳”׳ ׳—׳ ׳™׳•׳
        user_result = supabase.table('user_parkings').select(
            'code_type, project_number, parking_name, company_type'
        ).eq('email', session['user_email']).execute()
        
        if not user_result.data or user_result.data[0].get('code_type') != 'parking_manager':
            return jsonify({'success': False, 'message': '׳׳™׳ ׳”׳¨׳©׳׳” - ׳ ׳“׳¨׳© ׳§׳•׳“ ׳׳ ׳”׳ ׳—׳ ׳™׳•׳'}), 403
        
        user_data = user_result.data[0]
        
        # ׳§׳‘׳׳× ׳׳©׳×׳׳©׳™ ׳”׳—׳ ׳™׳•׳
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
        print(f"ג Error getting parking manager info: {str(e)}")
        return jsonify({'success': False, 'message': '׳©׳’׳™׳׳” ׳‘׳§׳‘׳׳× ׳ ׳×׳•׳ ׳™ ׳—׳ ׳™׳•׳'})

# ========== ׳₪׳•׳ ׳§׳¦׳™׳•׳× ׳׳™׳™׳׳™׳ ==========

def send_new_user_welcome_email(email, username, password, login_url):
    """׳©׳׳™׳—׳× ׳׳™׳™׳ ׳‘׳¨׳•׳›׳™׳ ׳”׳‘׳׳™׳ ׳׳׳©׳×׳׳© ׳—׳“׳©"""
    
    if not mail:
        print(f"ג Mail system not available")
        print(f"נ“± NEW USER DETAILS for {email}:")
        print(f"   Username: {username}")
        print(f"   Password: {password}")
        print(f"   URL: {login_url}")
        return False
    
    try:
        print(f"נ€ Sending welcome email to {email}...")
        
        msg = Message(
            subject='׳‘׳¨׳•׳›׳™׳ ׳”׳‘׳׳™׳ ׳׳׳¢׳¨׳›׳× S&B Parking',
            recipients=[email],
            html=f"""
            <div style="font-family: Arial, sans-serif; direction: rtl; text-align: right;">
                <h2 style="color: #667eea;">׳‘׳¨׳•׳›׳™׳ ׳”׳‘׳׳™׳ ׳׳׳¢׳¨׳›׳× S&B Parking</h2>
                <h3>׳—׳©׳‘׳•׳ ׳—׳“׳© ׳ ׳•׳¦׳¨ ׳¢׳‘׳•׳¨׳ ׳‘׳׳¢׳¨׳›׳× ׳“׳•׳—׳•׳× ׳”׳—׳ ׳™׳•׳×</h3>
                
                <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0;">
                    <p><strong>׳©׳ ׳׳©׳×׳׳©:</strong> {username}</p>
                    <p><strong>׳¡׳™׳¡׳׳” ׳¨׳׳©׳•׳ ׳™׳×:</strong> <span style="font-family: monospace; background: #e9ecef; padding: 2px 6px; color: #d63384; font-weight: bold;">Dd123456</span></p>
                    <p><strong>׳§׳™׳©׳•׳¨ ׳׳”׳×׳—׳‘׳¨׳•׳×:</strong></p>
                    <a href="{login_url}" style="color: #667eea; text-decoration: none; font-weight: bold;">{login_url}</a>
                </div>
                
                <div style="background: #fff3cd; border: 1px solid #ffeaa7; padding: 15px; border-radius: 8px; margin: 20px 0;">
                    <p style="margin: 0; color: #856404;"><strong>׳—׳©׳•׳‘ - ׳”׳•׳¨׳׳•׳× ׳‘׳˜׳™׳—׳•׳×:</strong></p>
                    <p style="margin: 5px 0 0 0; color: #856404;">
                        ג€¢ ׳‘׳›׳ ׳™׳¡׳” ׳”׳¨׳׳©׳•׳ ׳” ׳×׳×׳‘׳§׳© ׳׳©׳ ׳•׳× ׳׳× ׳”׳¡׳™׳¡׳׳”<br>
                        ג€¢ ׳׳ ׳ ׳©׳ ׳” ׳׳× ׳”׳¡׳™׳¡׳׳” ׳׳¡׳™׳¡׳׳” ׳׳™׳©׳™׳× ׳•׳—׳–׳§׳”<br>
                        ג€¢ ׳©׳׳•׳¨ ׳¢׳ ׳₪׳¨׳˜׳™ ׳”׳”׳×׳—׳‘׳¨׳•׳× ׳©׳׳ ׳‘׳׳§׳•׳ ׳‘׳˜׳•׳—<br>
                        ג€¢ ׳׳ ׳×׳©׳×׳£ ׳׳× ׳₪׳¨׳˜׳™ ׳”׳”׳×׳—׳‘׳¨׳•׳× ׳¢׳ ׳׳—׳¨׳™׳
                    </p>
                </div>
                
                <p>׳׳ ׳™׳© ׳׳ ׳©׳׳׳•׳× ׳׳• ׳‘׳¢׳™׳•׳× ׳‘׳”׳×׳—׳‘׳¨׳•׳×, ׳¦׳•׳¨ ׳§׳©׳¨ ׳¢׳ ׳׳ ׳”׳ ׳”׳׳¢׳¨׳›׳×.</p>
                
                <hr>
                <p style="color: #666; font-size: 12px;">
                    S&B Parking - ׳׳¢׳¨׳›׳× ׳ ׳™׳”׳•׳ ׳“׳•׳—׳•׳× ׳—׳ ׳™׳•׳×<br>
                    ׳׳™׳™׳ ׳׳•׳˜׳•׳׳˜׳™ - ׳׳ ׳ ׳׳ ׳×׳¢׳ ׳” ׳׳׳™׳™׳ ׳–׳”
                </p>
            </div>
            """,
            sender=app.config['MAIL_USERNAME']
        )
        
        mail.send(msg)
        print(f"ג… Welcome email sent successfully to {email}")
        return True
        
    except Exception as e:
        print(f"ג Welcome email error: {str(e)}")
        print(f"נ“± BACKUP - NEW USER DETAILS for {email}:")
        print(f"   Username: {username}")
        print(f"   Password: {password}")
        print(f"   URL: {login_url}")
        return False

def send_password_reset_email(email, username, new_password):
    """׳©׳׳™׳—׳× ׳׳™׳™׳ ׳¢׳ ׳׳™׳₪׳•׳¡ ׳¡׳™׳¡׳׳”"""
    
    if not mail:
        print(f"ג Mail system not available")
        print(f"נ“± PASSWORD RESET for {username}: {new_password}")
        return False
    
    try:
        print(f"נ€ Sending password reset email to {email}...")
        
        msg = Message(
            subject='׳׳™׳₪׳•׳¡ ׳¡׳™׳¡׳׳” - S&B Parking',
            recipients=[email],
            html=f"""
            <div style="font-family: Arial, sans-serif; direction: rtl; text-align: right;">
                <h2 style="color: #667eea;">׳׳™׳₪׳•׳¡ ׳¡׳™׳¡׳׳” - S&B Parking</h2>
                <h3>׳”׳¡׳™׳¡׳׳” ׳©׳׳ ׳׳•׳₪׳¡׳” ׳¢׳ ׳™׳“׳™ ׳׳ ׳”׳ ׳”׳׳¢׳¨׳›׳×</h3>
                
                <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0;">
                    <p><strong>׳©׳ ׳׳©׳×׳׳©:</strong> {username}</p>
                    <p><strong>׳¡׳™׳¡׳׳” ׳—׳“׳©׳”:</strong> <span style="font-family: monospace; background: #e9ecef; padding: 2px 6px; color: #d63384; font-weight: bold;">Dd123456</span></p>
                    <p><strong>׳§׳™׳©׳•׳¨ ׳׳”׳×׳—׳‘׳¨׳•׳×:</strong></p>
                    <a href="https://s-b-parking-reports.onrender.com" style="color: #667eea; text-decoration: none; font-weight: bold;">https://s-b-parking-reports.onrender.com</a>
                </div>
                
                <div style="background: #f8d7da; border: 1px solid #f5c6cb; padding: 15px; border-radius: 8px; margin: 20px 0;">
                    <p style="margin: 0; color: #721c24;"><strong>׳—׳©׳•׳‘:</strong></p>
                    <p style="margin: 5px 0 0 0; color: #721c24;">
                        ג€¢ ׳‘׳›׳ ׳™׳¡׳” ׳”׳‘׳׳” ׳×׳×׳‘׳§׳© ׳׳©׳ ׳•׳× ׳׳× ׳”׳¡׳™׳¡׳׳”<br>
                        ג€¢ ׳©׳ ׳” ׳׳× ׳”׳¡׳™׳¡׳׳” ׳׳™׳“ ׳׳¡׳™׳¡׳׳” ׳׳™׳©׳™׳× ׳•׳—׳–׳§׳”<br>
                        ג€¢ ׳׳ ׳×׳©׳×׳£ ׳׳× ׳”׳¡׳™׳¡׳׳” ׳¢׳ ׳׳—׳¨׳™׳
                    </p>
                </div>
                
                <p>׳׳ ׳׳ ׳‘׳™׳§׳©׳× ׳׳™׳₪׳•׳¡ ׳¡׳™׳¡׳׳”, ׳¦׳•׳¨ ׳§׳©׳¨ ׳¢׳ ׳׳ ׳”׳ ׳”׳׳¢׳¨׳›׳× ׳׳™׳“.</p>
                
                <hr>
                <p style="color: #666; font-size: 12px;">
                    S&B Parking - ׳׳¢׳¨׳›׳× ׳ ׳™׳”׳•׳ ׳“׳•׳—׳•׳× ׳—׳ ׳™׳•׳×<br>
                    ׳׳™׳™׳ ׳׳•׳˜׳•׳׳˜׳™ - ׳׳ ׳ ׳׳ ׳×׳¢׳ ׳” ׳׳׳™׳™׳ ׳–׳”
                </p>
            </div>
            """,
            sender=app.config['MAIL_USERNAME']
        )
        
        mail.send(msg)
        print(f"ג… Password reset email sent successfully to {email}")
        return True
        
    except Exception as e:
        print(f"ג Password reset email error: {str(e)}")
        print(f"נ“± BACKUP - PASSWORD RESET for {username}: {new_password}")
        return False 

def clean_expired_reset_codes():
    """׳ ׳™׳§׳•׳™ ׳§׳•׳“׳™׳ ׳©׳₪׳’׳• ׳×׳•׳§׳£ - ׳׳™׳₪׳•׳¡ ׳¡׳™׳¡׳׳”"""
    current_time = time.time()
    expired_emails = []
    
    for email, data in password_reset_codes.items():
        if current_time - data['timestamp'] > 1800:  # 30 ׳“׳§׳•׳×
            expired_emails.append(email)
    
    for email in expired_emails:
        del password_reset_codes[email]

def send_password_reset_verification_email(email, code, username):
    """׳©׳׳™׳—׳× ׳׳™׳™׳ ׳¢׳ ׳§׳•׳“ ׳׳™׳₪׳•׳¡ ׳¡׳™׳¡׳׳”"""
    
    if not mail:
        print(f"ג Mail system not available")
        print(f"נ“± RESET CODE for {email}: {code}")
        return False
    
    try:
        print(f"נ€ Sending password reset email to {email}...")
        
        msg = Message(
            subject='׳׳™׳₪׳•׳¡ ׳¡׳™׳¡׳׳” - S&B Parking',
            recipients=[email],
            html=f"""
            <div style="font-family: Arial, sans-serif; direction: rtl; text-align: right;">
                <h2 style="color: #667eea;">׳©׳™׳™׳“׳˜ ׳׳× ׳‘׳›׳׳ ׳™׳©׳¨׳׳</h2>
                <h3>׳‘׳§׳©׳” ׳׳׳™׳₪׳•׳¡ ׳¡׳™׳¡׳׳”</h3>
                
                <p>׳©׳׳•׳ {username},</p>
                <p>׳§׳™׳‘׳׳ ׳• ׳‘׳§׳©׳” ׳׳׳™׳₪׳•׳¡ ׳”׳¡׳™׳¡׳׳” ׳©׳׳ ׳‘׳׳¢׳¨׳›׳× S&B Parking.</p>
                
                <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; text-align: center; margin: 20px 0;">
                    <p><strong>׳§׳•׳“ ׳”׳׳™׳׳•׳× ׳©׳׳:</strong></p>
                    <span style="font-size: 32px; font-weight: bold; color: #667eea; letter-spacing: 5px; background: #e9ecef; padding: 15px; border-radius: 8px; display: inline-block;">{code}</span>
                </div>
                
                <div style="background: #fff3cd; border: 1px solid #ffeaa7; padding: 15px; border-radius: 8px; margin: 20px 0;">
                    <p style="margin: 0; color: #856404;"><strong>׳—׳©׳•׳‘:</strong></p>
                    <p style="margin: 5px 0 0 0; color: #856404;">
                        ג€¢ ׳”׳§׳•׳“ ׳×׳§׳£ ׳-10 ׳“׳§׳•׳× ׳‘׳׳‘׳“<br>
                        ג€¢ ׳”׳©׳×׳׳© ׳‘׳§׳•׳“ ׳–׳” ׳¨׳§ ׳׳ ׳׳×׳” ׳‘׳™׳§׳©׳× ׳׳™׳₪׳•׳¡ ׳¡׳™׳¡׳׳”<br>
                        ג€¢ ׳׳ ׳׳ ׳‘׳™׳§׳©׳× ׳׳™׳₪׳•׳¡, ׳”׳×׳¢׳׳ ׳׳”׳•׳“׳¢׳” ׳–׳•
                    </p>
                </div>
                
                <p>׳׳׳—׳¨ ׳”׳–׳ ׳× ׳”׳§׳•׳“ ׳×׳•׳›׳ ׳׳‘׳—׳•׳¨ ׳¡׳™׳¡׳׳” ׳—׳“׳©׳”.</p>
                
                <hr>
                <p style="color: #666; font-size: 12px;">S&B Parking - ׳׳¢׳¨׳›׳× ׳“׳•׳—׳•׳× ׳—׳ ׳™׳•׳×</p>
            </div>
            """,
            sender=app.config['MAIL_USERNAME']
        )
        
        mail.send(msg)
        print(f"ג… Password reset email sent successfully to {email}")
        return True
        
    except Exception as e:
        print(f"ג Password reset email error: {str(e)}")
        print(f"נ“± BACKUP CODE for {email}: {code}")
        return False

# ׳ ׳™׳§׳•׳™ ׳׳•׳˜׳•׳׳˜׳™ ׳©׳ ׳§׳•׳“׳™׳ ׳™׳©׳ ׳™׳
def auto_cleanup_reset_codes():
    """׳ ׳™׳§׳•׳™ ׳׳•׳˜׳•׳׳˜׳™ ׳©׳ ׳§׳•׳“׳™ ׳׳™׳₪׳•׳¡ ׳©׳₪׳’׳• ׳×׳•׳§׳£"""
    def cleanup_loop():
        while True:
            try:
                time.sleep(900)  # 15 ׳“׳§׳•׳×
                clean_expired_reset_codes()
                print(f"נ§¹ Reset codes cleanup completed")
            except Exception as e:
                print(f"ג ן¸ Cleanup error: {str(e)}")
    
    cleanup_thread = threading.Thread(target=cleanup_loop, daemon=True)
    cleanup_thread.start()

auto_cleanup_reset_codes()

# ׳”׳₪׳¢׳׳” ׳׳•׳˜׳•׳׳˜׳™׳× ׳›׳©׳”׳׳₪׳׳™׳§׳¦׳™׳” ׳׳×׳—׳™׳׳”
if __name__ == '__main__':
    print("\nנ”§ Pre-flight email system check...")
    
    if EMAIL_MONITORING_AVAILABLE:
        email_system_ready = verify_email_system()
        
        if email_system_ready:
            print("ג… Email system ready - starting background monitoring")
            start_background_email_monitoring()
        else:
            print("ג ן¸ Email system not ready - monitoring disabled")
            print("נ’¡ You can still use manual email checks via API")
    else:
        print("ג ן¸ Email libraries not available - monitoring disabled")
    
    print("\nנ Starting Flask web server...")
    
    port = int(os.environ.get('PORT', 5000))
    debug_mode = os.environ.get('FLASK_ENV') == 'development'
    
    print(f"נ” Port: {port}")
    print(f"נ” Debug mode: {debug_mode}")
    
    keep_service_alive()

    app.run(host='0.0.0.0', port=port, debug=debug_mode)
else:
    if EMAIL_MONITORING_AVAILABLE:
        print("נ“§ Initializing email monitoring for production...")
        start_background_email_monitoring()
