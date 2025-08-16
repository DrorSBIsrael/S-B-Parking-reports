"""
בדיקת הקבצים המקומיים מול השרת
"""
import requests
import json

print("=" * 60)
print("🔍 בדיקת גרסאות ו-endpoints")
print("=" * 60)

# בדיקת השרת המרוחק
print("\n📡 בדיקת השרת ב-Render:")
print("-" * 40)

try:
    # בדיקת גרסה
    response = requests.get('https://s-b-parking-reports.onrender.com/api/status')
    if response.ok:
        data = response.json()
        version = data.get('version', 'unknown')
        print(f"✅ גרסה בשרת: {version}")
        if version == '2.0.6':
            print("   ✅ גרסה נכונה!")
        else:
            print(f"   ❌ צריך לעדכן לגרסה 2.0.6 (כרגע: {version})")
    else:
        print(f"❌ לא ניתן לקבל גרסה: {response.status_code}")
except Exception as e:
    print(f"❌ שגיאה: {e}")

try:
    # בדיקת proxy endpoint
    response = requests.get('https://s-b-parking-reports.onrender.com/api/company-manager/proxy')
    print(f"\nProxy GET status: {response.status_code}")
    if response.status_code == 200:
        print("✅ Proxy endpoint עובד!")
        print(f"   Response: {response.json()}")
    elif response.status_code == 404:
        print("❌ Proxy endpoint לא נמצא - הקובץ החדש לא נטען!")
    else:
        print(f"⚠️ Status: {response.status_code}")
except Exception as e:
    print(f"❌ שגיאה: {e}")

print("\n" + "=" * 60)
print("📝 מה לעשות:")
print("-" * 40)

print("""
אם הגרסה לא 2.0.6 או ה-proxy מחזיר 404:

1. וודא שהקבצים המקומיים מעודכנים:
   - appV3.py צריך להכיל גרסה 2.0.6
   - appV3.py צריך להכיל @app.route('/api/company-manager/proxy', methods=['POST', 'OPTIONS', 'GET'])

2. העלה ל-Render:
   git add appV3.py static/js/parking-ui-live.js
   git commit -m "Fix v2.0.6 - proxy endpoint"
   git push

3. ב-Render Dashboard:
   - בדוק ב-Events שיש Deploy חדש
   - אם לא, לחץ Manual Deploy > Clear build cache & deploy

4. חכה 5 דקות והרץ את הסקריפט שוב
""")

print("=" * 60)
