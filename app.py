# שורה זו מאלצת עדכון - 2025-07-02 09:40
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from supabase import create_client, Client
import os
from datetime import datetime, timedelta

print("🚀 NEW APP VERSION - 2025-07-02 09:40")  # שורה זו תוודא שהקוד החדש רץ

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'

# Supabase configuration
SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_ANON_KEY')
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

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

# API Routes
@app.route('/api/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')
        
        if not username or not password:
            return jsonify({'success': False, 'message': 'נא למלא את כל השדות'})
        
        print(f"🔑 Attempting login for user: {username}")
        
        # בדיקת פרטי התחברות
        auth_result = supabase.rpc('user_login', {
            'p_username': username,
            'p_password': password
        }).execute()
        
        print(f"🔐 Auth result: {auth_result.data}")
        
        if auth_result.data:
            # קבלת כתובת המייל
            user_result = supabase.table('user_parkings').select('email').eq('username', username).execute()
            
            print(f"📧 User result: {user_result.data}")
            
            if user_result.data and len(user_result.data) > 0:
                email = user_result.data[0]['email']
                print(f"✅ Found email: {email}")
                
                # שליחת קוד אימות - גם אם נכשל, ממשיכים
                try:
                    code_result = supabase.rpc('send_verification_code', {
                        'p_email': email
                    }).execute()
                    print(f"📨 Code result: {code_result.data}")
                except Exception as code_error:
                    print(f"❌ Code sending failed: {code_error}")
                
                # בכל מקרה ממשיכים לverify
                session['pending_email'] = email
                return jsonify({'success': True, 'redirect': '/verify'})
            else:
                return jsonify({'success': False, 'message': 'שגיאה במציאת פרטי משתמש'})
        else:
            return jsonify({'success': False, 'message': 'שם משתמש או סיסמה שגויים'})
            
    except Exception as e:
        print(f"❌ Login error: {str(e)}")
        return jsonify({'success': False, 'message': f'שגיאת שרת: {str(e)}'})

@app.route('/api/verify-code', methods=['POST'])
def verify_code_endpoint():
    try:
        data = request.get_json()
        code = data.get('code')
        email = session.get('pending_email')
        
        print(f"🔍 Verifying code {code} for email {email}")
        
        if not email:
            return jsonify({'success': False, 'message': 'לא נמצא משתמש בהמתנה לאימות'})
        
        if not code or len(code) != 6:
            return jsonify({'success': False, 'message': 'נא להזין קוד בן 6 ספרות'})
        
        # אימות הקוד
        result = supabase.rpc('verify_code', {
            'p_email': email,
            'p_code': code
        }).execute()
        
        print(f"🎯 Verify result: {result.data}")
        
        # בדיקת התוצאה (הפונקציה מחזירה JSON)
        if result.data and result.data.get('success'):
            session['user_email'] = email
            session.pop('pending_email', None)
            print(f"✅ User verified successfully: {email}")
            return jsonify({'success': True, 'redirect': '/dashboard'})
        else:
            error_message = result.data.get('message', 'קוד אימות שגוי או פג תוקף') if result.data else 'שגיאה באימות הקוד'
            return jsonify({'success': False, 'message': error_message})
            
    except Exception as e:
        print(f"❌ Verify code error: {str(e)}")
        return jsonify({'success': False, 'message': f'שגיאת שרת: {str(e)}'})

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login_page'))

if __name__ == '__main__':
    app.run(debug=True)
