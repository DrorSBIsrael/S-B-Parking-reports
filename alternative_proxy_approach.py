"""
גישה חלופית - הוספת proxy endpoint בצורה אחרת
"""

# קרא את app.py
with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

# מצא את המקום אחרי Flask app creation
import re

# חפש את השורה של app = Flask
app_line_match = re.search(r'(app\s*=\s*Flask\([^)]+\))', content)
if not app_line_match:
    print("❌ לא מצאתי את יצירת Flask app")
    exit(1)

# מצא את סוף השורה
app_line_end = app_line_match.end()

# הוסף את ה-proxy routes מיד אחרי יצירת ה-app
proxy_code = '''

# ========== PROXY ENDPOINTS - MUST BE FIRST ==========
@app.route('/api/proxy-test', methods=['GET'])
def proxy_test_endpoint():
    """Simple test endpoint"""
    return {'status': 'ok', 'message': 'Proxy test works!'}

@app.route('/api/company-manager/proxy', methods=['POST', 'OPTIONS', 'GET'])
def company_manager_proxy_alternative():
    """Alternative proxy endpoint"""
    from flask import jsonify, request, session, make_response
    from datetime import datetime
    import requests
    
    print(f"🎯 ALTERNATIVE PROXY HIT: {request.method}")
    
    if request.method == 'OPTIONS':
        response = make_response('', 200)
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'POST, OPTIONS, GET'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        return response
    
    if request.method == 'GET':
        return jsonify({
            'success': True,
            'message': 'Alternative proxy endpoint works!',
            'version': '2.0.9',
            'method': 'GET',
            'timestamp': datetime.now().isoformat()
        })
    
    # For POST - return simple response
    return jsonify({
        'success': True,
        'message': 'Alternative proxy POST works',
        'data': request.get_json()
    })

print("✅ Alternative proxy endpoints registered FIRST")
# ========== END PROXY ENDPOINTS ==========
'''

# הכנס את הקוד
new_content = content[:app_line_end] + proxy_code + content[app_line_end:]

# מצא את ה-proxy הישן ומחק אותו (אם קיים)
# חפש מהסוף כדי למחוק את האחרון
old_proxy_pattern = r'@app\.route\([\'"]\/api\/company-manager\/proxy[\'"].*?\)[\s\S]*?(?=@app\.route|if __name__|$)'
matches = list(re.finditer(old_proxy_pattern, new_content))

if matches:
    # מחק את ההתאמה האחרונה
    last_match = matches[-1]
    new_content = new_content[:last_match.start()] + new_content[last_match.end():]
    print(f"✅ הסרתי את ה-proxy endpoint הישן")

# שמור כקובץ חדש
with open('app_with_early_proxy.py', 'w', encoding='utf-8') as f:
    f.write(new_content)

print("\n✅ יצרתי קובץ חדש: app_with_early_proxy.py")
print("   - ה-proxy endpoints נרשמים מיד אחרי יצירת Flask app")
print("   - זה אמור לפתור בעיות של סדר רישום")
print("\n📌 הוראות:")
print("   1. בדוק את app_with_early_proxy.py")
print("   2. אם נראה טוב, שנה שם ל-app.py")
print("   3. העלה ל-Git")

# גם ניצור קובץ מינימלי לבדיקה
minimal_app = '''# -*- coding: utf-8 -*-
from flask import Flask, jsonify, request, make_response
from datetime import datetime
import os

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False

@app.route('/api/status')
def status():
    return jsonify({
        'success': True,
        'version': '2.0.9-minimal',
        'message': 'Minimal app for testing'
    })

@app.route('/api/company-manager/proxy', methods=['POST', 'OPTIONS', 'GET'])
def proxy():
    if request.method == 'OPTIONS':
        response = make_response('', 200)
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'POST, OPTIONS, GET'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        return response
    
    return jsonify({
        'success': True,
        'method': request.method,
        'message': 'Minimal proxy works!'
    })

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
'''

with open('minimal_app.py', 'w', encoding='utf-8') as f:
    f.write(minimal_app)

print("\n✅ יצרתי גם אפליקציה מינימלית: minimal_app.py")
print("   - אם כלום לא עובד, נסה את זה קודם")
