"""
סקריפט לבדיקת מבנה app.py
"""
import os
import re

print("🔍 בודק את מבנה app.py...")
print("=" * 50)

# בדיקה 1: האם הקובץ קיים
if not os.path.exists('app.py'):
    print("❌ הקובץ app.py לא נמצא!")
    exit(1)

# בדיקה 2: גודל הקובץ
file_size = os.path.getsize('app.py')
print(f"📏 גודל הקובץ: {file_size:,} bytes ({file_size/1024/1024:.2f} MB)")

if file_size > 1024 * 1024:  # 1MB
    print("⚠️  הקובץ גדול מאוד! זה עלול לגרום לבעיות ב-Render")

# בדיקה 3: קריאת הקובץ
with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()
    lines = content.splitlines()

print(f"📄 מספר שורות: {len(lines):,}")

# בדיקה 4: חיפוש Flask app
flask_app_pattern = r'app\s*=\s*Flask'
flask_matches = re.findall(flask_app_pattern, content)
print(f"\n✅ Flask app instances: {len(flask_matches)}")
if len(flask_matches) != 1:
    print("⚠️  צריך להיות רק Flask app אחד!")

# בדיקה 5: חיפוש routes
routes = re.findall(r'@app\.route\([\'"]([^\'"]+)[\'"].*?\)', content)
print(f"\n📌 Routes found ({len(routes)}):")
for i, route in enumerate(routes[:20]):  # הצג רק 20 ראשונים
    print(f"   {i+1}. {route}")
if len(routes) > 20:
    print(f"   ... ועוד {len(routes)-20} routes")

# בדיקה 6: חיפוש ה-proxy endpoint
proxy_endpoint = '/api/company-manager/proxy'
if proxy_endpoint in routes:
    print(f"\n✅ Proxy endpoint נמצא: {proxy_endpoint}")
    
    # מצא את המיקום המדויק
    for i, line in enumerate(lines):
        if proxy_endpoint in line and '@app.route' in line:
            print(f"   שורה {i+1}: {line.strip()}")
            # הצג גם את השורות הבאות
            for j in range(1, 10):
                if i+j < len(lines):
                    print(f"   שורה {i+j+1}: {lines[i+j].strip()}")
                    if 'def ' in lines[i+j]:
                        break
else:
    print(f"\n❌ Proxy endpoint לא נמצא!")

# בדיקה 7: חיפוש כפילויות
print("\n🔍 בודק כפילויות...")
function_names = re.findall(r'def\s+(\w+)\s*\(', content)
duplicates = {}
for name in function_names:
    if name in duplicates:
        duplicates[name] += 1
    else:
        duplicates[name] = 1

has_duplicates = False
for name, count in duplicates.items():
    if count > 1:
        has_duplicates = True
        print(f"⚠️  כפילות: {name} מופיע {count} פעמים")

if not has_duplicates:
    print("✅ אין כפילויות של פונקציות")

# בדיקה 8: בדיקת הגרסה
version_matches = re.findall(r'[\'"]version[\'"]:\s*[\'"]([^\'"\s]+)[\'"]', content)
if version_matches:
    print(f"\n📦 גרסאות שנמצאו:")
    for v in set(version_matches):
        print(f"   - {v}")

# בדיקה 9: בדיקת if __name__ == "__main__"
if 'if __name__ == "__main__":' in content:
    print("\n✅ יש בלוק main להרצה")
else:
    print("\n⚠️  אין בלוק main - הקובץ לא יריץ ישירות")

# בדיקה 10: בדיקת imports
critical_imports = ['Flask', 'jsonify', 'request', 'create_client']
print("\n📚 Imports קריטיים:")
for imp in critical_imports:
    if imp in content:
        print(f"   ✅ {imp}")
    else:
        print(f"   ❌ {imp} חסר!")

print("\n" + "=" * 50)
print("✅ הבדיקה הסתיימה")

# יצירת דוח
with open('app_structure_report.txt', 'w', encoding='utf-8') as f:
    f.write(f"דוח בדיקת app.py - {content[:100]}...\n")
    f.write(f"גודל: {file_size} bytes\n")
    f.write(f"שורות: {len(lines)}\n")
    f.write(f"Routes: {len(routes)}\n")
    f.write(f"Proxy endpoint: {'נמצא' if proxy_endpoint in routes else 'לא נמצא'}\n")
    
print("\n📄 דוח נשמר ב-app_structure_report.txt")
