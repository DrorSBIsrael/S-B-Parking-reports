from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_mail import Mail, Message
from supabase import create_client, Client
import os
import random
import string
import re
import html

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
        from datetime import datetime, timedelta
        
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
        from datetime import datetime
        
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
    if 'user_email' not in session:
        return redirect(url_for('login_page'))
    return render_template('dashboard.html')

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

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login_page'))

if __name__ == '__main__':
    app.run(debug=True)
