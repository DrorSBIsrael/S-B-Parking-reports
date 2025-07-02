# VERSION: 2025-07-02 20:10 - FINAL CLEAN VERSION
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from supabase import create_client, Client
import os
from datetime import datetime, timedelta

print("🚀 FINAL CLEAN VERSION - 2025-07-02 20:10")

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
        
        if auth_result.data == True:
            # קבלת כתובת המייל
            user_result = supabase.table('user_parkings').select('email').eq('username', username).execute()
            
            if user_result.data and len(user_result.data) > 0:
                email = user_result.data[0]['email']
                print(f"✅ Found email: {email}")
                
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
    print("🔧 CLEAN VERIFY FUNCTION VERSION 20:10")
    try:
        data = request.get_json()
        code = data.get('code')
        email = session.get('pending_email')
        
        print(f"🔍 Verifying code: {code} for email: {email}")
        
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
        
        # בדיקה אם התוצאה מכילה success
        result_str = str(result.data)
        print(f"🎯 Result string: {result_str}")
        
        if "'success': True" in result_str or '"success": true' in result_str:
            session['user_email'] = email
            session.pop('pending_email', None)
            print(f"✅ SUCCESS - User {email} verified, redirecting to dashboard")
            return jsonify({'success': True, 'redirect': '/dashboard'})
        else:
            print(f"❌ FAILED - verification unsuccessful for {email}")
            return jsonify({'success': False, 'message': 'קוד אימות שגוי או פג תוקף'})
            
    except Exception as e:
        print(f"❌ Verify exception: {str(e)}")
        return jsonify({'success': False, 'message': f'שגיאת שרת: {str(e)}'})

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login_page'))

@app.route('/health')
def health_check():
    try:
        result = supabase.table('user_parkings').select('count').execute()
        return jsonify({'status': 'healthy', 'database': 'connected'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
