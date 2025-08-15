"""
בדיקה פשוטה של טעינת app.py
"""
import sys

print("🔍 מנסה לטעון את app.py...")

try:
    # נסה לייבא את האפליקציה
    import app
    print("✅ app.py נטען בהצלחה!")
    
    # בדוק אם יש Flask app
    if hasattr(app, 'app'):
        print("✅ Flask app נמצא")
        
        # הדפס את כל ה-routes
        print("\n📌 Routes רשומים:")
        with app.app.app_context():
            for rule in app.app.url_map.iter_rules():
                methods = ', '.join(sorted(rule.methods - {'HEAD', 'OPTIONS'}))
                if methods:  # רק אם יש methods (לא רק HEAD/OPTIONS)
                    print(f"   {rule.rule} [{methods}] -> {rule.endpoint}")
        
        # בדוק ספציפית את ה-proxy endpoint
        proxy_found = False
        for rule in app.app.url_map.iter_rules():
            if '/api/company-manager/proxy' in str(rule):
                proxy_found = True
                print(f"\n✅ Proxy endpoint נמצא: {rule}")
                break
        
        if not proxy_found:
            print("\n❌ Proxy endpoint לא נמצא ב-url_map!")
            
    else:
        print("❌ Flask app לא נמצא במודול")
        
except ImportError as e:
    print(f"❌ שגיאה בייבוא: {e}")
    
except Exception as e:
    print(f"❌ שגיאה כללית: {e}")
    import traceback
    traceback.print_exc()

print("\n✅ הבדיקה הסתיימה")
