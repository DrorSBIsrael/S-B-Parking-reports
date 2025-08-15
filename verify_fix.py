"""
בדיקה מקיפה שהתיקון עובד
"""
import requests
import time

print("=" * 70)
print("🔍 בודק את התיקון של מערכת החניונים")
print("=" * 70)

BASE_URL = "https://s-b-parking-reports.onrender.com"

# רשימת בדיקות
tests = [
    {
        "name": "Server Status",
        "url": "/api/status",
        "method": "GET",
        "expected_status": 200,
        "check_version": "2.0.8"
    },
    {
        "name": "Proxy GET",
        "url": "/api/company-manager/proxy",
        "method": "GET",
        "expected_status": 200
    },
    {
        "name": "Proxy OPTIONS (CORS)",
        "url": "/api/company-manager/proxy",
        "method": "OPTIONS",
        "expected_status": [200, 204]
    },
    {
        "name": "Proxy POST (needs login)",
        "url": "/api/company-manager/proxy",
        "method": "POST",
        "data": {"parking_id": "test", "endpoint": "test"},
        "expected_status": [401, 200]  # 401 אם לא מחובר, 200 אם כן
    },
    {
        "name": "Company Manager Page",
        "url": "/company-manager",
        "method": "GET",
        "expected_status": [200, 302]  # 302 redirect אם לא מחובר
    }
]

results = []
all_pass = True

for test in tests:
    print(f"\n📌 בודק: {test['name']}")
    print(f"   URL: {BASE_URL}{test['url']}")
    print(f"   Method: {test['method']}")
    
    try:
        # שלח בקשה
        if test['method'] == 'GET':
            response = requests.get(BASE_URL + test['url'], allow_redirects=False)
        elif test['method'] == 'POST':
            response = requests.post(
                BASE_URL + test['url'],
                json=test.get('data', {}),
                headers={'Content-Type': 'application/json'}
            )
        elif test['method'] == 'OPTIONS':
            response = requests.options(BASE_URL + test['url'])
        
        # בדוק תוצאה
        expected = test['expected_status']
        if isinstance(expected, list):
            success = response.status_code in expected
        else:
            success = response.status_code == expected
        
        if success:
            print(f"   ✅ PASS - Status: {response.status_code}")
            
            # בדוק גרסה אם נדרש
            if 'check_version' in test:
                try:
                    data = response.json()
                    version = data.get('version', 'unknown')
                    if version == test['check_version']:
                        print(f"   ✅ Version correct: {version}")
                    else:
                        print(f"   ⚠️ Version mismatch: {version} (expected {test['check_version']})")
                except:
                    pass
        else:
            print(f"   ❌ FAIL - Status: {response.status_code} (expected {expected})")
            all_pass = False
            
        results.append({
            'name': test['name'],
            'status': response.status_code,
            'success': success
        })
        
    except Exception as e:
        print(f"   ❌ ERROR: {e}")
        all_pass = False
        results.append({
            'name': test['name'],
            'error': str(e),
            'success': False
        })
    
    time.sleep(0.5)  # המתנה קצרה בין בדיקות

# סיכום
print("\n" + "=" * 70)
print("📊 סיכום הבדיקה:")
print("=" * 70)

passed = sum(1 for r in results if r.get('success', False))
failed = len(results) - passed

print(f"\n✅ עברו: {passed}/{len(results)}")
print(f"❌ נכשלו: {failed}/{len(results)}")

if all_pass:
    print("\n🎉 מצוין! כל הבדיקות עברו בהצלחה!")
    print("   המערכת עובדת כמו שצריך!")
else:
    print("\n⚠️ יש בעיות שצריך לטפל בהן:")
    for r in results:
        if not r.get('success', False):
            print(f"   - {r['name']}: {r.get('status', r.get('error', 'unknown'))}")
    print("\n💡 פתרונות אפשריים:")
    print("   1. נקה cache בדפדפן (Ctrl+Shift+Delete)")
    print("   2. בדוק שהשינויים הועלו ל-Git")
    print("   3. וודא ש-Render עשה Deploy חדש")
    print("   4. נסה בחלון גלישה בסתר")

print("\n" + "=" * 70)
