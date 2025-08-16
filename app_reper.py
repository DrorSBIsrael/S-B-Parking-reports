"""
תיקון כפילות בקובץ app.py
"""

# קרא את הקובץ
with open('app.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

print(f"📖 קראתי {len(lines)} שורות מ-app.py")

# מצא את הכפילות
first_parking_manager = None
second_parking_manager = None

for i, line in enumerate(lines):
    if 'def parking_manager_get_info():' in line:
        if first_parking_manager is None:
            first_parking_manager = i
            print(f"🔍 מצאתי את parking_manager_get_info הראשונה בשורה {i+1}")
        else:
            second_parking_manager = i
            print(f"🔍 מצאתי את parking_manager_get_info השנייה בשורה {i+1}")
            break

if first_parking_manager and second_parking_manager:
    # מחק את הכפילות
    new_lines = lines[:first_parking_manager] + lines[second_parking_manager-1:]
    
    # כתוב חזרה
    with open('app_fixed.py', 'w', encoding='utf-8') as f:
        f.writelines(new_lines)
    
    print(f"✅ יצרתי קובץ מתוקן: app_fixed.py")
    print(f"   מחקתי {second_parking_manager - first_parking_manager} שורות של קוד כפול")
    print(f"   הקובץ החדש מכיל {len(new_lines)} שורות")
    print("\n📌 עכשיו:")
    print("   1. בדוק את app_fixed.py")
    print("   2. אם הכל נראה טוב, שנה את השם:")
    print("      - מחק את app.py הישן")
    print("      - שנה את שם app_fixed.py ל-app.py")
else:
    print("❌ לא מצאתי כפילות!")
    if first_parking_manager:
        print(f"   יש רק מופע אחד של parking_manager_get_info בשורה {first_parking_manager+1}")
