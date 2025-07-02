from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from supabase import create_client, Client
import os

print("🔥 WORKING VERSION - NO MORE BUGS!")

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
                
                session['pending_email'] = email
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
    
    print(f"🔍 Verify attempt: code={code}, email={email}")
    
    if not email:
        return jsonify({'success': False, 'message': 'No pending verification'})
    
    if not code or len(code) != 6:
        return jsonify({'success': False, 'message': 'Invalid code format'})
    
    # Call verify function
    result = supabase.rpc('verify_code', {
        'p_email': email,
        'p_code': code
    }).execute()
    
    print(f"🎯 Raw result: {result.data}")
    
    # Simple string check - if it contains success and True
    result_str = str(result.data)
    if 'success' in result_str and 'True' in result_str:
        session['user_email'] = email
        session.pop('pending_email', None)
        print(f"✅ SUCCESS - Redirecting to dashboard")
        return jsonify({'success': True, 'redirect': '/dashboard'})
    
    print(f"❌ FAILED - No success found in result")
    return jsonify({'success': False, 'message': 'קוד שגוי או פג תוקף'})

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login_page'))

if __name__ == '__main__':
    app.run(debug=True)
