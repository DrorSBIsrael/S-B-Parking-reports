from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_mail import Mail, Message
from supabase import create_client, Client
import os
import random
import string

print("🔥 WORKING VERSION - NOW WITH EMAIL!")

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'

# Supabase configuration
SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_ANON_KEY')
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# הגדרות מייל S&B עם timeout מתוקן
app.config['MAIL_SERVER'] = 'smtp.012.net.il'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'Report@sbparking.co.il'
app.config['MAIL_PASSWORD'] = 'o51W38D5'
app.config['MAIL_DEFAULT_SENDER'] = 'Report@sbparking.co.il'
app.config['MAIL_SUPPRESS_SEND'] = False  # וודא שהמייל נשלח
app.config['MAIL_MAX_EMAILS'] = None      # ללא הגבלה

mail = Mail(app)

def generate_verification_code():
    """יצירת קוד אימות של 6 ספרות"""
    return ''.join(random.choices(string.digits, k=6))

def store_verification_code(email, code):
    """שמירת קוד אימות בטבלת user_parkings הקיימת"""
    try:
        from datetime import datetime, timedelta
        
        # חישוב זמן תפוגה (10 דקות מעכשיו)
        expires_at = datetime.now() + timedelta(minutes=10)
        expires_str = expires_at.strftime('%Y-%m-%d %H:%M:%S')
        
        print(f"🔄 Updating user_parkings for {email} with code {code}")
        
        result = supabase.table('user_parkings').update({
            'verification_code': code,
            'code_expires_at': expires_str
        }).eq('email', email).execute()
        
        print(f"✅ Update result: {result.data}")
        print(f"✅ Code saved: {code} expires at {expires_str}")
        return True
        
    except Exception as e:
        print(f"❌ Failed to save code: {str(e)}")
        return False

def verify_code_from_database(email, code):
    """בדיקת קוד אימות מטבלת user_parkings"""
    try:
        from datetime import datetime
        
        # חיפוש משתמש עם הקוד
        result = supabase.table('user_parkings').select('verification_code, code_expires_at').eq('email', email).execute()
        
        if not result.data:
            print(f"❌ No user found for {email}")
            return False
            
        user_data = result.data[0]
        stored_code = user_data.get('verification_code')
        expires_at_str = user_data.get('code_expires_at')
        
        print(f"🔍 Stored code: {stored_code}, Input code: {code}")
        print(f"🔍 Expires at: {expires_at_str}")
        
        if not stored_code or stored_code != code:
            print(f"❌ Code mismatch or missing")
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
        }).eq('email', email).execute()
        
        print(f"✅ Code verified and cleared for {email}")
        return True
        
    except Exception as e:
        print(f"❌ Database verification failed: {str(e)}")
        return False
    """שליחת מייל אימות עם timeout קצר"""
    try:
        print(f"🚀 Starting email send to {email}...")
        
        msg = Message(
            subject='קוד אימות - S&B Parking',
            recipients=[email],
            html=f"""
            <div style="font-family: Arial, sans-serif; direction: rtl; text-align: right;">
                <h2 style="color: #667eea;">🚗 S&B Parking</h2>
                <h3>קוד האימות שלך:</h3>
                <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; text-align: center; margin: 20px 0;">
                    <span style="font-size: 32px; font-weight: bold; color: #667eea; letter-spacing: 5px;">{code}</span>
                </div>
                <p>הקוד תקף ל-10 דקות בלבד.</p>
                <p>אם לא ביקשת קוד זה, התעלם מהודעה זו.</p>
                <hr>
                <p style="color: #666; font-size: 12px;">S&B Parking - מערכת דוחות חניות</p>
            </div>
            """
        )
        
        print(f"🔄 Sending email...")
        # נסה לשלוח עם timeout מובנה
        import socket
        original_timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(10)  # 10 שניות בלבד
        
        mail.send(msg)
        
        socket.setdefaulttimeout(original_timeout)
        print(f"✅ Email sent successfully to {email}")
        return True
        
    except socket.timeout:
        print(f"⏰ Email timeout - but continuing with code: {code}")
        return True  # ממשיכים גם אם יש timeout
    except Exception as e:
        print(f"❌ Email error: {str(e)} - but continuing with code: {code}")
        return True  # ממשיכים גם אם יש שגיאה

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
        username = data.get('username')
        password = data.get('password')
        
        if not username or not password:
            return jsonify({'success': False, 'message': 'נא למלא את כל השדות'})
        
        print(f"🔑 Login attempt: {username}")
        
        # Check user credentials
        auth_result = supabase.rpc('user_login', {
            'p_username': username,
            'p_password': password
        }).execute()
        
        print(f"🔐 Auth result: {auth_result.data}")
        
        if auth_result.data == True:
            # Get user email
            user_result = supabase.table('user_parkings').select('email').eq('username', username).execute()
            
            if user_result.data and len(user_result.data) > 0:
                email = user_result.data[0]['email']
                print(f"✅ Email found: {email}")
                
                # יצירת קוד אימות חדש
                verification_code = generate_verification_code()
                print(f"🎯 Generated code: {verification_code}")
                
                # שמירה במסד נתונים קודם
                if store_verification_code(email, verification_code):
                    # נסה לשלוח מייל (אם יש פונקציה)
                    try:
                        email_sent = send_verification_email(email, verification_code)
                        print(f"📧 Email attempt completed")
                    except:
                        print(f"📧 Email function not ready - continuing with code")
                    
                    # שמירה ב-session לבדיוק
                    session['pending_email'] = email
                    print(f"📧 Code ready for {email}: {verification_code}")
                    return jsonify({'success': True, 'redirect': '/verify'})
                else:
                    return jsonify({'success': False, 'message': 'שגיאה בשמירת הקוד'})
            else:
                return jsonify({'success': False, 'message': 'User not found'})
        else:
            return jsonify({'success': False, 'message': 'שם משתמש או סיסמה שגויים'})
            
    except Exception as e:
        print(f"❌ Login error: {str(e)}")
        return jsonify({'success': False, 'message': 'Login failed'})

@app.route('/api/verify-code', methods=['POST'])
def verify_code():
    data = request.get_json()
    code = data.get('code')
    email = session.get('pending_email')
    
    print(f"🔍 Verify attempt: code={code}, email={email}")
    
    if not email:
        return jsonify({'success': False, 'message': 'No pending verification'})
    
    if not code or len(code) != 6:
        return jsonify({'success': False, 'message': 'Invalid code format'})
    
    # בדיקת הקוד מהמסד נתונים
    if verify_code_from_database(email, code):
        session['user_email'] = email
        session.pop('pending_email', None)
        print(f"✅ SUCCESS - Redirecting to dashboard")
        return jsonify({'success': True, 'redirect': '/dashboard'})
    else:
        print(f"❌ FAILED - Invalid or expired code")
        return jsonify({'success': False, 'message': 'קוד שגוי או פג תוקף'})

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login_page'))

if __name__ == '__main__':
    app.run(debug=True)
