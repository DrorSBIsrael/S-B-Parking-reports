from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from supabase import create_client, Client
import os
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'  # החלף במפתח חזק יותר

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
    # וודא שיש משתמש בהמתנה לאימות
    if 'pending_email' not in session:
        return redirect(url_for('login_page'))
    return render_template('verify.html')

@app.route('/dashboard')
def dashboard():
    # וודא שהמשתמש מחובר
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
        
        # בדיקת פרטי התחברות עם הפונקציה החדשה
        auth_result = supabase.rpc('user_login', {
            'p_username': username,
            'p_password': password
        }).execute()
        
        if auth_result.data:
            # קבלת כתובת המייל של המשתמש מטבלת user_parkings
            user_result = supabase.table('user_parkings').select('email').eq('username', username).execute()
            
            if user_result.data and len(user_result.data) > 0:
                email = user_result.data[0]['email']
                
                # שליחת קוד אימות עם הפונקציה החדשה
                code_result = supabase.rpc('send_verification_code', {
                    'p_email': email
                }).execute()
                
                if code_result.data:
                    # שמירת המייל בסשן לשלב האימות
                    session['pending_email'] = email
                    return jsonify({'success': True, 'redirect': '/verify'})
                else:
                    return jsonify({'success': False, 'message': 'שגיאה בשליחת קוד אימות'})
            else:
                return jsonify({'success': False, 'message': 'שגיאה במציאת פרטי משתמש'})
        else:
            return jsonify({'success': False, 'message': 'שם משתמש או סיסמה שגויים'})
            
    except Exception as e:
        print(f"Login error: {str(e)}")
        return jsonify({'success': False, 'message': f'שגיאת שרת: {str(e)}'})

@app.route('/api/verify-code', methods=['POST'])
def verify_code_endpoint():
    try:
        data = request.get_json()
        code = data.get('code')
        email = session.get('pending_email')
        
        if not email:
            return jsonify({'success': False, 'message': 'לא נמצא משתמש בהמתנה לאימות'})
        
        if not code or len(code) != 6:
            return jsonify({'success': False, 'message': 'נא להזין קוד בן 6 ספרות'})
        
        # אימות הקוד עם הפונקציה החדשה
        result = supabase.rpc('verify_code', {
            'p_email': email,
            'p_code': code
        }).execute()
        
        # בדיקת התוצאה (הפונקציה מחזירה JSON)
        if result.data and result.data.get('success'):
            # אימות בוצע בהצלחה
            session['user_email'] = email
            session.pop('pending_email', None)  # ניקוי מהסשן
            return jsonify({'success': True, 'redirect': '/dashboard'})
        else:
            # קבלת הודעת השגיאה מהפונקציה
            error_message = result.data.get('message', 'קוד אימות שגוי או פג תוקף') if result.data else 'שגיאה באימות הקוד'
            return jsonify({'success': False, 'message': error_message})
            
    except Exception as e:
        print(f"Verify code error: {str(e)}")
        return jsonify({'success': False, 'message': f'שגיאת שרת: {str(e)}'})

@app.route('/api/resend-code', methods=['POST'])
def resend_code():
    try:
        email = session.get('pending_email')
        
        if not email:
            return jsonify({'success': False, 'message': 'לא נמצא משתמש בהמתנה לאימות'})
        
        # שליחת קוד חדש
        result = supabase.rpc('send_verification_code', {
            'p_email': email
        }).execute()
        
        if result.data:
            return jsonify({'success': True, 'message': 'קוד חדש נשלח בהצלחה'})
        else:
            return jsonify({'success': False, 'message': 'שגיאה בשליחת קוד חדש'})
            
    except Exception as e:
        print(f"Resend code error: {str(e)}")
        return jsonify({'success': False, 'message': f'שגיאת שרת: {str(e)}'})

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login_page'))

# בדיקת בריאות השרת
@app.route('/health')
def health_check():
    try:
        # בדיקת חיבור ל-Supabase עם הטבלה החדשה
        result = supabase.table('user_parkings').select('count').execute()
        return jsonify({'status': 'healthy', 'database': 'connected'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
