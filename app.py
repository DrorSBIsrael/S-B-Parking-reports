from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_mail import Mail, Message
from supabase import create_client, Client
import os
import bcrypt
import jwt
import random
import string
from datetime import datetime, timedelta
from dotenv import load_dotenv
import json
import logging

# טעינת הגדרות סביבה
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'your-secret-key-here')

# הגדרת לוגים
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# הגדרת מייל
app.config['MAIL_SERVER'] = os.getenv('EMAIL_HOST', 'smtp.012.net.il')
app.config['MAIL_PORT'] = int(os.getenv('EMAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.getenv('EMAIL_USE_TLS', 'True').lower() == 'true'
app.config['MAIL_USERNAME'] = os.getenv('EMAIL_USER', 'Report@sbparking.co.il')
app.config['MAIL_PASSWORD'] = os.getenv('EMAIL_PASS', 'o51W38D5')

mail = Mail(app)

# חיבור לSupabase
try:
    supabase: Client = create_client(
        os.getenv('SUPABASE_URL', 'your-supabase-url'),
        os.getenv('SUPABASE_KEY', 'your-supabase-key')
    )
    logger.info("✅ התחברות לSupabase הצליחה")
except Exception as e:
    logger.error(f"❌ שגיאה בהתחברות לSupabase: {e}")
    supabase = None

# ===============================
# פונקציות עזר - אימות ומייל
# ===============================

def generate_verification_code():
    """יצירת קוד אימות רנדומלי בן 6 ספרות"""
    return ''.join(random.choices(string.digits, k=6))

def send_verification_email(email, code, username):
    """שליחת מייל עם קוד אימות"""
    try:
        msg = Message(
            subject='🔐 קוד אימות - מערכת דוחות חניונים S&B',
            sender=app.config['MAIL_USERNAME'],
            recipients=[email]
        )
        
        msg.html = f"""
        <div style="direction: rtl; font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background: linear-gradient(135deg, #1E40AF, #EA580C); padding: 30px; border-radius: 15px; color: white; text-align: center;">
                <h1 style="margin: 0; font-size: 2rem;">🚗 S&B Parking Reports</h1>
                <p style="margin: 10px 0 0 0; opacity: 0.9;">קוד אימות להתחברות למערכת</p>
            </div>
            
            <div style="background: white; padding: 30px; border-radius: 15px; margin-top: 20px; box-shadow: 0 10px 30px rgba(0,0,0,0.1);">
                <h2 style="color: #333; margin-top: 0;">שלום {username},</h2>
                <p style="color: #666; font-size: 16px; line-height: 1.6;">
                    התקבלה בקשה להתחברות למערכת דוחות החניונים שלך.<br>
                    השתמש בקוד הבא כדי להשלים את תהליך ההתחברות:
                </p>
                
                <div style="background: linear-gradient(135deg, #F9FAFB, #F3F4F6); padding: 25px; border-radius: 15px; text-align: center; margin: 25px 0; border: 2px solid #E5E7EB;">
                    <p style="color: #374151; font-size: 14px; margin-bottom: 15px; font-weight: 600;">הקוד שלך הוא:</p>
                    <div style="font-size: 36px; font-weight: 800; color: #1E40AF; letter-spacing: 8px; font-family: monospace; margin: 10px 0;">
                        {code}
                    </div>
                    <p style="color: #6B7280; font-size: 12px; margin-top: 15px;">
                        ⏰ הקוד תקף למשך 10 דקות בלבד
                    </p>
                </div>
                
                <div style="background: #FEF3C7; border: 1px solid #F59E0B; padding: 15px; border-radius: 10px; margin: 20px 0;">
                    <h4 style="color: #92400E; margin: 0 0 8px 0; font-size: 14px;">🛡️ טיפי אבטחה:</h4>
                    <ul style="color: #92400E; font-size: 13px; margin: 0; padding-right: 20px; line-height: 1.6;">
                        <li>אל תשתף את הקוד עם אף אחד</li>
                        <li>אם לא ביקשת התחברות, התעלם ממייל זה</li>
                        <li>צור קשר איתנו אם אתה חושד בפעילות חשודה</li>
                    </ul>
                </div>
                
                <div style="border-top: 2px solid #E5E7EB; margin-top: 30px; padding-top: 20px; text-align: center;">
                    <p style="color: #9CA3AF; font-size: 12px; margin: 0;">
                        מערכת דוחות חניונים S&B<br>
                        📧 {app.config['MAIL_USERNAME']} | 📞 +972-50-123-4567
                    </p>
                </div>
            </div>
        </div>
        """
        
        mail.send(msg)
        logger.info(f"✅ קוד אימות נשלח למייל: {email}")
        return True
        
    except Exception as e:
        logger.error(f"❌ שגיאה בשליחת מייל אימות: {e}")
        return False

def verify_user_credentials(username, password):
    """בדיקת פרטי התחברות מול בסיס הנתונים"""
    if not supabase:
        logger.error("❌ אין חיבור לSupabase")
        return None
        
    try:
        # חיפוש המשתמש בטבלה
        response = supabase.table('user_parkings').select('*').eq('username', username).execute()
        
        if response.data and len(response.data) > 0:
            user = response.data[0]
            
            # בדיקת סיסמה מוצפנת
            if user.get('password_hash'):
                if bcrypt.checkpw(password.encode('utf-8'), user['password_hash'].encode('utf-8')):
                    logger.info(f"✅ התחברות מוצלחת למשתמש: {username}")
                    return user
            
            # בדיקת סיסמה פשוטה (לאחור-תאימות)
            elif user.get('password') == password:
                logger.info(f"✅ התחברות מוצלחת (סיסמה פשוטה) למשתמש: {username}")
                return user
                
        logger.warning(f"⚠️ התחברות נכשלה למשתמש: {username}")
        return None
        
    except Exception as e:
        logger.error(f"❌ שגיאה בבדיקת פרטי התחברות: {e}")
        return None

def get_user_allowed_parkings(user_id):
    """קבלת רשימת חניונים מותרים למשתמש"""
    if not supabase:
        return []
        
    try:
        response = supabase.rpc('get_user_allowed_parkings', {'input_user_id': user_id}).execute()
        return response.data or []
    except Exception as e:
        logger.error(f"❌ שגיאה בקבלת חניונים מותרים: {e}")
        return []

def get_parking_data_for_user(user_id, project_number=None, start_date=None, end_date=None):
    """קבלת נתוני חניון עם הרשאות"""
    if not supabase:
        return []
        
    try:
        params = {'input_user_id': user_id}
        if project_number:
            params['input_project_number'] = project_number
        if start_date:
            params['start_date'] = start_date
        if end_date:
            params['end_date'] = end_date
            
        response = supabase.rpc('get_parking_data_for_user', params).execute()
        return response.data or []
    except Exception as e:
        logger.error(f"❌ שגיאה בקבלת נתוני חניון: {e}")
        return []

def get_user_revenue_summary(user_id):
    """קבלת סיכום הכנסות למשתמש"""
    if not supabase:
        return {}
        
    try:
        response = supabase.rpc('get_user_revenue_summary_simple', {'input_user_id': user_id}).execute()
        return response.data[0] if response.data else {}
    except Exception as e:
        logger.error(f"❌ שגיאה בקבלת סיכום הכנסות: {e}")
        return {}

# ===============================
# נתיבי המערכת
# ===============================

@app.route('/')
def index():
    """עמוד הבית - הפניה לדשבורד או התחברות"""
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    """עמוד התחברות - שלב ראשון"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        # בדיקות בסיסיות
        if not username or not password:
            flash('נא למלא את כל השדות', 'error')
            return render_template('login.html')
        
        # בדיקת פרטי התחברות
        user = verify_user_credentials(username, password)
        if not user:
            flash('שם משתמש או סיסמה שגויים', 'error')
            return render_template('login.html')
        
        # יצירת קוד אימות ושליחה במייל
        verification_code = generate_verification_code()
        
        # שליחת מייל אימות
        if send_verification_email(user.get('email', ''), verification_code, user.get('display_name', username)):
            # שמירת פרטים זמניים בסשן
            session['temp_user_id'] = user['user_id']
            session['temp_username'] = username
            session['verification_code'] = verification_code
            session['verification_time'] = datetime.now().isoformat()
            
            flash('קוד אימות נשלח לכתובת המייל שלך', 'success')
            return redirect(url_for('verify'))
        else:
            flash('שגיאה בשליחת קוד האימות. נסה שוב מאוחר יותר.', 'error')
    
    return render_template('login.html')

@app.route('/verify', methods=['GET', 'POST'])
def verify():
    """עמוד אימות - שלב שני"""
    # בדיקה שעבר שלב ראשון
    if 'temp_user_id' not in session or 'verification_code' not in session:
        flash('נא להתחבר תחילה', 'error')
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        entered_code = request.form.get('verification_code', '').strip()
        
        if not entered_code:
            flash('נא להזין קוד אימות', 'error')
            return render_template('verify.html')
        
        # בדיקת תוקף הקוד (10 דקות)
        try:
            verification_time = datetime.fromisoformat(session.get('verification_time'))
            if datetime.now() > verification_time + timedelta(minutes=10):
                session.clear()
                flash('קוד האימות פג תוקף. נא להתחבר מחדש', 'error')
                return redirect(url_for('login'))
        except:
            session.clear()
            flash('שגיאה בבדיקת תוקף הקוד. נא להתחבר מחדש', 'error')
            return redirect(url_for('login'))
        
        # בדיקת הקוד
        if entered_code == session.get('verification_code'):
            # התחברות מוצלחת
            session['user_id'] = session['temp_user_id']
            session['username'] = session['temp_username']
            session['login_time'] = datetime.now().isoformat()
            
            # ניקוי נתוני אימות זמניים
            session.pop('temp_user_id', None)
            session.pop('temp_username', None)
            session.pop('verification_code', None)
            session.pop('verification_time', None)
            
            logger.info(f"✅ משתמש התחבר בהצלחה: {session['username']}")
            flash('התחברת בהצלחה למערכת!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('קוד אימות שגוי. נסה שוב', 'error')
    
    return render_template('verify.html')

@app.route('/dashboard')
def dashboard():
    """עמוד דשבורד ראשי"""
    # בדיקת התחברות
    if 'user_id' not in session:
        flash('נא להתחבר תחילה', 'error')
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    
    try:
        # קבלת חניונים מותרים
        allowed_parkings = get_user_allowed_parkings(user_id)
        
        # קבלת סיכום הכנסות
        revenue_summary = get_user_revenue_summary(user_id)
        
        # קבלת נתונים אחרונים
        recent_data = get_parking_data_for_user(user_id)
        
        return render_template('dashboard.html', 
                             parkings=allowed_parkings, 
                             summary=revenue_summary,
                             recent_data=recent_data)
                             
    except Exception as e:
        logger.error(f"❌ שגיאה בטעינת דשבורד: {e}")
        flash('שגיאה בטעינת הנתונים', 'error')
        return render_template('dashboard.html', parkings=[], summary={}, recent_data=[])

@app.route('/logout')
def logout():
    """יציאה מהמערכת"""
    username = session.get('username', 'משתמש לא ידוע')
    session.clear()
    logger.info(f"✅ משתמש יצא מהמערכת: {username}")
    flash('התנתקת בהצלחה מהמערכת', 'success')
    return redirect(url_for('login'))

# ===============================
# API Endpoints
# ===============================

@app.route('/api/parking-data/<project_number>')
def api_parking_data(project_number):
    """API לקבלת נתוני חניון ספציפי"""
    if 'user_id' not in session:
        return jsonify({'error': 'לא מחובר למערכת'}), 401
    
    user_id = session['user_id']
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    try:
        # טיפול בבקשה לכל החניונים
        project_num = None if project_number == 'all' else project_number
        
        data = get_parking_data_for_user(user_id, project_num, start_date, end_date)
        return jsonify(data)
        
    except Exception as e:
        logger.error(f"❌ שגיאה ב-API נתוני חניון: {e}")
        return jsonify({'error': 'שגיאה בקבלת הנתונים'}), 500

@app.route('/api/revenue-summary')
def api_revenue_summary():
    """API לקבלת סיכום הכנסות"""
    if 'user_id' not in session:
        return jsonify({'error': 'לא מחובר למערכת'}), 401
    
    user_id = session['user_id']
    
    try:
        summary = get_user_revenue_summary(user_id)
        return jsonify(summary)
        
    except Exception as e:
        logger.error(f"❌ שגיאה ב-API סיכום הכנסות: {e}")
        return jsonify({'error': 'שגיאה בקבלת הסיכום'}), 500

@app.route('/api/user-parkings')
def api_user_parkings():
    """API לקבלת חניונים מותרים למשתמש"""
    if 'user_id' not in session:
        return jsonify({'error': 'לא מחובר למערכת'}), 401
    
    user_id = session['user_id']
    
    try:
        parkings = get_user_allowed_parkings(user_id)
        return jsonify(parkings)
        
    except Exception as e:
        logger.error(f"❌ שגיאה ב-API חניונים מותרים: {e}")
        return jsonify({'error': 'שגיאה בקבלת החניונים'}), 500

# ===============================
# עמודי שגיאה
# ===============================

@app.errorhandler(404)
def page_not_found(e):
    """עמוד שגיאה 404"""
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(e):
    """עמוד שגיאה 500"""
    logger.error(f"❌ שגיאת שרת 500: {e}")
    return render_template('500.html'), 500

# ===============================
# Context Processors
# ===============================

@app.context_processor
def inject_user():
    """הזרקת פרטי משתמש לכל התבניות"""
    if 'user_id' not in session:
        return {'current_user': None}
    
    try:
        # קבלת פרטי המשתמש מבסיס הנתונים
        if supabase:
            response = supabase.table('user_parkings').select('display_name, email, user_type').eq('user_id', session['user_id']).execute()
            if response.data:
                return {'current_user': response.data[0]}
    except Exception as e:
        logger.error(f"❌ שגיאה בקבלת פרטי משתמש: {e}")
    
    # ברירת מחדל
    return {'current_user': {
        'display_name': session.get('username', 'משתמש'),
        'email': 'unknown@example.com',
        'user_type': 'user'
    }}

# ===============================
# הפעלת השרת
# ===============================

if __name__ == '__main__':
    # בדיקת הגדרות חיוניות
    required_env_vars = ['SUPABASE_URL', 'SUPABASE_KEY', 'SECRET_KEY']
    missing_vars = [var for var in required_env_vars if not os.getenv(var)]
    
    if missing_vars:
        logger.warning(f"⚠️ חסרים משתני סביבה: {', '.join(missing_vars)}")
        logger.info("💡 ודא שיש לך קובץ .env עם כל ההגדרות הנדרשות")
    
    # הפעלת השרת
    debug_mode = os.getenv('DEBUG', 'False').lower() == 'true'
    port = int(os.getenv('PORT', 5000))
    
    logger.info("🚀 מפעיל את מערכת דוחות החניונים S&B...")
    logger.info(f"🌐 השרת ירוץ על פורט: {port}")
    logger.info(f"🔧 מצב debug: {debug_mode}")
    
    app.run(host='0.0.0.0', port=port, debug=debug_mode)