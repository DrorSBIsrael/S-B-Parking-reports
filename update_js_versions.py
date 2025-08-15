"""
עדכון מספרי גרסה של קבצי JavaScript בכל הפרויקט
"""
import os
import re
import time

# מספר גרסה חדש (timestamp)
new_version = str(int(time.time()))

print(f"🔧 מעדכן גרסאות JavaScript ל-v={new_version}")
print("=" * 60)

# רשימת קבצים לבדוק
files_to_check = []

# חפש קבצי HTML ו-JavaScript
for root, dirs, files in os.walk('.'):
    # דלג על תיקיות לא רלוונטיות
    if 'node_modules' in root or '.git' in root or '__pycache__' in root:
        continue
    
    for file in files:
        if file.endswith(('.html', '.js', '.py')):
            files_to_check.append(os.path.join(root, file))

# Patterns לחיפוש
patterns = [
    (r'parking-api-live\.js\?v=\d+', f'parking-api-live.js?v={new_version}'),
    (r'parking-ui-live\.js\?v=\d+', f'parking-ui-live.js?v={new_version}'),
    (r'parking-api-v2\.js\?v=\d+', f'parking-api-v2.js?v={new_version}'),
    (r'parking-ui-v2\.js\?v=\d+', f'parking-ui-v2.js?v={new_version}'),
    (r'parking-api-xml\.js\?v=\d+', f'parking-api-xml.js?v={new_version}'),
    (r'parking-ui-integration-xml\.js\?v=\d+', f'parking-ui-integration-xml.js?v={new_version}'),
]

updated_files = []

for filepath in files_to_check:
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        for pattern, replacement in patterns:
            if re.search(pattern, content):
                content = re.sub(pattern, replacement, content)
        
        if content != original_content:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            updated_files.append(filepath)
            print(f"✅ עודכן: {filepath}")
    except Exception as e:
        # דלג על קבצים שלא ניתן לקרוא
        pass

print("\n" + "=" * 60)
if updated_files:
    print(f"📊 סיכום: עודכנו {len(updated_files)} קבצים")
    print("\n📁 קבצים שעודכנו:")
    for f in updated_files:
        print(f"   - {f}")
    
    print("\n📝 הוראות:")
    print("1. בדוק את השינויים")
    print("2. העלה ל-Git:")
    print("   git add -A")
    print(f'   git commit -m "Update JS versions to {new_version}"')
    print("   git push")
else:
    print("❌ לא נמצאו קבצים לעדכון")
    print("   כנראה הגרסאות נטענות דינמית מהשרת")
