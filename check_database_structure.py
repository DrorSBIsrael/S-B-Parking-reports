"""
סקריפט לבדיקת המבנה הקיים של בסיס הנתונים
================================================
מטרה: לבדוק בדיוק מה יש בבסיס הנתונים לפני שינויים
"""

from dotenv import load_dotenv
import os
from supabase import create_client, Client

# טעינת משתני סביבה
load_dotenv()

def check_database():
    """בדיקת מבנה בסיס הנתונים הקיים"""
    
    # חיבור ל-Supabase
    url = os.environ.get('SUPABASE_URL')
    key = os.environ.get('SUPABASE_ANON_KEY')
    
    if not url or not key:
        print("❌ חסרים פרטי התחברות ל-Supabase")
        print("   SUPABASE_URL:", "✅" if url else "❌")
        print("   SUPABASE_ANON_KEY:", "✅" if key else "❌")
        return
    
    try:
        supabase = create_client(url, key)
        print("✅ מחובר ל-Supabase")
        print("=" * 60)
        
        # 1. בדיקת טבלאות קיימות
        print("\n📊 בדיקת טבלאות קיימות:")
        print("-" * 40)
        
        tables_to_check = [
            'user_parkings',
            'parkings', 
            'parking_lots',
            'parking_data',
            'project_parking_mapping'
        ]
        
        existing_tables = []
        
        for table_name in tables_to_check:
            try:
                # ננסה לבצע שאילתה פשוטה
                result = supabase.table(table_name).select('*').limit(1).execute()
                print(f"✅ {table_name} - קיימת")
                existing_tables.append(table_name)
                
                # נבדוק כמה רשומות יש
                count_result = supabase.table(table_name).select('*', count='exact').execute()
                if hasattr(count_result, 'count'):
                    print(f"   └─ מספר רשומות: {count_result.count}")
                    
            except Exception as e:
                if "relation" in str(e).lower() and "does not exist" in str(e).lower():
                    print(f"❌ {table_name} - לא קיימת")
                else:
                    print(f"⚠️ {table_name} - שגיאה: {str(e)[:50]}")
        
        # 2. בדיקת מבנה הטבלאות הקיימות
        print("\n📋 מבנה הטבלאות הקיימות:")
        print("-" * 40)
        
        for table_name in existing_tables:
            print(f"\n🔍 טבלה: {table_name}")
            try:
                # נקבל רשומה אחת כדי לראות את השדות
                result = supabase.table(table_name).select('*').limit(1).execute()
                if result.data and len(result.data) > 0:
                    columns = list(result.data[0].keys())
                    print(f"   עמודות: {', '.join(columns)}")
                else:
                    print("   (טבלה ריקה - לא ניתן לקבל מבנה)")
            except Exception as e:
                print(f"   שגיאה בקריאת מבנה: {str(e)[:50]}")
        
        # 3. בדיקה ספציפית של user_parkings
        if 'user_parkings' in existing_tables:
            print("\n👤 בדיקת טבלת user_parkings:")
            print("-" * 40)
            try:
                # בדיקת משתמש לדוגמה
                result = supabase.table('user_parkings').select('*').limit(1).execute()
                if result.data:
                    user = result.data[0]
                    print("דוגמה לרשומה:")
                    for key, value in user.items():
                        if key == 'password_hash':
                            print(f"   {key}: {'***מוצפן***' if value else 'ריק'}")
                        elif key == 'project_number':
                            print(f"   {key}: {value} (סוג: {type(value).__name__})")
                        else:
                            print(f"   {key}: {value}")
            except Exception as e:
                print(f"   שגיאה: {str(e)}")
        
        # 4. בדיקה ספציפית של parkings
        if 'parkings' in existing_tables:
            print("\n🚗 בדיקת טבלת parkings:")
            print("-" * 40)
            try:
                result = supabase.table('parkings').select('*').limit(1).execute()
                if result.data:
                    parking = result.data[0]
                    print("דוגמה לרשומה:")
                    for key, value in parking.items():
                        if key == 'description':
                            print(f"   {key}: {value} (סוג: {type(value).__name__})")
                        else:
                            print(f"   {key}: {value}")
            except Exception as e:
                print(f"   שגיאה: {str(e)}")
        
        # 5. בדיקת חיבור בין הטבלאות
        print("\n🔗 בדיקת קישור בין הטבלאות:")
        print("-" * 40)
        
        if 'user_parkings' in existing_tables and 'parkings' in existing_tables:
            try:
                # נבדוק אם יש project_numbers תואמים
                users = supabase.table('user_parkings').select('project_number').limit(5).execute()
                parkings = supabase.table('parkings').select('description').limit(5).execute()
                
                if users.data and parkings.data:
                    user_projects = [u.get('project_number') for u in users.data if u.get('project_number')]
                    parking_projects = [p.get('description') for p in parkings.data if p.get('description')]
                    
                    print(f"   project_numbers ב-user_parkings: {user_projects[:3]}")
                    print(f"   descriptions ב-parkings: {parking_projects[:3]}")
                    
                    # בדיקת התאמה
                    matching = set(str(up) for up in user_projects) & set(str(pp) for pp in parking_projects)
                    if matching:
                        print(f"   ✅ נמצאו התאמות: {list(matching)[:3]}")
                    else:
                        print(f"   ⚠️ לא נמצאו התאמות בין הטבלאות")
                        
            except Exception as e:
                print(f"   שגיאה בבדיקת קישור: {str(e)}")
        
        # 6. המלצות
        print("\n💡 המלצות:")
        print("-" * 40)
        
        if 'parking_lots' in existing_tables:
            print("⚠️ נמצאה טבלת parking_lots - כנראה צריך להעביר נתונים ל-parkings")
        
        if 'parkings' in existing_tables:
            print("✅ טבלת parkings קיימת - צריך לוודא שהמבנה תואם")
        
        print("\n📝 סיכום:")
        print(f"   טבלאות קיימות: {', '.join(existing_tables)}")
        
    except Exception as e:
        print(f"❌ שגיאה כללית: {str(e)}")

if __name__ == "__main__":
    print("🔍 בדיקת מבנה בסיס הנתונים הקיים")
    print("=" * 60)
    check_database()

