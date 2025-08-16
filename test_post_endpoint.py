"""
בדיקה ספציפית של POST ל-proxy endpoint
"""
import requests
import json

BASE_URL = "https://s-b-parking-reports.onrender.com"

print("=" * 60)
print("🔍 בודק POST requests ל-proxy endpoint")
print("=" * 60)

# בדיקת GET (אמור לעבוד)
print("\n1️⃣ בודק GET:")
try:
    response = requests.get(f"{BASE_URL}/api/company-manager/proxy")
    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        print("   ✅ GET עובד!")
        print(f"   Response: {response.json()}")
    else:
        print(f"   ❌ GET נכשל: {response.text}")
except Exception as e:
    print(f"   ❌ Error: {e}")

# בדיקת OPTIONS (CORS)
print("\n2️⃣ בודק OPTIONS:")
try:
    response = requests.options(f"{BASE_URL}/api/company-manager/proxy")
    print(f"   Status: {response.status_code}")
    if response.status_code in [200, 204]:
        print("   ✅ OPTIONS עובד!")
    else:
        print(f"   ❌ OPTIONS נכשל: {response.text}")
except Exception as e:
    print(f"   ❌ Error: {e}")

# בדיקת POST עם נתונים
print("\n3️⃣ בודק POST עם נתונים:")
data = {
    "parking_id": "test",
    "endpoint": "test",
    "method": "GET"
}
try:
    response = requests.post(
        f"{BASE_URL}/api/company-manager/proxy",
        json=data,
        headers={"Content-Type": "application/json"}
    )
    print(f"   Status: {response.status_code}")
    if response.status_code == 401:
        print("   ⚠️ 401 - צריך להיות מחובר (זה בסדר)")
    elif response.status_code == 404:
        print("   ❌ 404 - הendpoint לא נמצא!")
    elif response.status_code == 200:
        print("   ✅ POST עובד!")
        print(f"   Response: {response.json()}")
    else:
        print(f"   ❓ Status אחר: {response.text[:200]}")
except Exception as e:
    print(f"   ❌ Error: {e}")

# בדיקת POST בלי נתונים
print("\n4️⃣ בודק POST בלי נתונים:")
try:
    response = requests.post(f"{BASE_URL}/api/company-manager/proxy")
    print(f"   Status: {response.status_code}")
    print(f"   Response: {response.text[:200]}...")
except Exception as e:
    print(f"   ❌ Error: {e}")

print("\n" + "=" * 60)
print("📊 סיכום:")
print("   אם GET עובד אבל POST לא - יש בעיה ברישום ה-route")
print("   אם שניהם עובדים - הבעיה היא cache בדפדפן")
print("=" * 60)
