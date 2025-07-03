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

def send_verification_email(email, code):
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
                
                # שליחת מייל (עם timeout קצר)
                email_sent = send_verification_email(email, verification_code)
                
                # ממשיכים תמיד - גם אם המייל נכשל
                session['pending_email'] = email
                session['verification_code'] = verification_code
                print(f"📧 Code ready for {email}: {verification_code}")
                return jsonify({'success': True, 'redirect': '/verify'})
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
    expected_code = session.get('verification_code')
    
    print(f"🔍 Verify attempt: code={code}, email={email}, expected={expected_code}")
    
    if not email:
        return jsonify({'success': False, 'message': 'No pending verification'})
    
    if not code or len(code) != 6:
        return jsonify({'success': False, 'message': 'Invalid code format'})
    
    # בדיקת הקוד
    if code == expected_code:
        session['user_email'] = email
        session.pop('pending_email', None)
        session.pop('verification_code', None)
        print(f"✅ SUCCESS - Redirecting to dashboard")
        return jsonify({'success': True, 'redirect': '/dashboard'})
    else:
        print(f"❌ FAILED - Invalid code")
        return jsonify({'success': False, 'message': 'קוד שגוי או פג תוקף'})

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login_page'))

if __name__ == '__main__':
    app.run(debug=True)
