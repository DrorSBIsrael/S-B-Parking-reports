"""
סקריפט בדיקה לחיבור לבסיס הנתונים ובדיקת הרשאות
=============================================
"""

import os
import sys
from supabase import create_client, Client
from dotenv import load_dotenv
import bcrypt
from connection_config import UserPermissions, ParkingLot, parse_company_list

# טעינת משתני סביבה
load_dotenv()

def test_supabase_connection():
    """בדיקת חיבור ל-Supabase"""
    print("🔍 בודק חיבור ל-Supabase...")
    
    try:
        url = os.environ.get('SUPABASE_URL')
        key = os.environ.get('SUPABASE_ANON_KEY')
        
        if not url or not key:
            print("❌ חסרים משתני סביבה SUPABASE_URL או SUPABASE_ANON_KEY")
            return None
        
        supabase = create_client(url, key)
        print("✅ חיבור ל-Supabase הצליח!")
        return supabase
    except Exception as e:
        print(f"❌ שגיאה בחיבור: {e}")
        return None


def test_user_login(supabase: Client, username: str, password: str):
    """בדיקת התחברות משתמש"""
    print(f"\n🔑 בודק התחברות עבור {username}...")
    
    try:
        # חיפוש המשתמש
        result = supabase.table('user_parkings').select('*').eq('username', username).execute()
        
        if not result.data:
            print(f"❌ משתמש {username} לא נמצא")
            return None
        
        user_data = result.data[0]
        print(f"✅ משתמש נמצא: {user_data['email']}")
        
        # בדיקת סיסמה (בייצור צריך להשתמש ב-bcrypt)
        # כאן רק נדפיס את פרטי המשתמש
        
        return user_data
    except Exception as e:
        print(f"❌ שגיאה בחיפוש משתמש: {e}")
        return None


def test_permissions(user_data: dict):
    """בדיקת הרשאות משתמש"""
    print("\n🔐 בודק הרשאות...")
    
    user = UserPermissions(
        user_id=user_data.get('user_id', 0),
        username=user_data.get('username', ''),
        email=user_data.get('email', ''),
        role=user_data.get('role', 'user'),
        permissions=user_data.get('permissions', ''),
        company_list=user_data.get('company_list', ''),
        access_level=user_data.get('access_level', 'single_parking'),
        project_number=user_data.get('project_number', ''),
        parking_name=user_data.get('parking_name', '')
    )
    
    print(f"📋 פרטי משתמש:")
    print(f"  - שם: {user.username}")
    print(f"  - תפקיד: {user.role}")
    print(f"  - רמת גישה: {user.access_level}")
    print(f"  - הרשאות: {user.permissions}")
    
    # בדיקת הרשאות
    permissions_map = {
        'G': 'Guest (אורח)',
        'N': 'New (חדש)',
        'R': 'Report (דוחות)',
        'P': 'Profile (פרופיל)'
    }
    
    print("\n🔍 הרשאות פעילות:")
    for perm, desc in permissions_map.items():
        if user.has_permission(perm):
            print(f"  ✅ {desc}")
    
    # בדיקת רשימת חברות
    if user.company_list:
        companies = user.get_company_numbers()
        print(f"\n🏢 חברות מורשות: {companies}")
        
        # בדיקת דוגמאות
        test_companies = [1, 7, 15, 60, 100]
        print("\n🧪 בדיקת גישה לחברות:")
        for company in test_companies:
            access = user.can_access_company(company)
            status = "✅" if access else "❌"
            print(f"  {status} חברה {company}: {'יש גישה' if access else 'אין גישה'}")
    
    return user


def test_parkings(supabase: Client, project_number: str = None):
    """בדיקת חניונים"""
    print("\n🚗 בודק חניונים...")
    
    try:
        query = supabase.table('parkings').select('*')
        
        if project_number:
            query = query.eq('description', project_number)
        
        result = query.execute()
        
        if not result.data:
            print("❌ לא נמצאו חניונים")
            return []
        
        parkings = []
        for parking_data in result.data:
            parking = ParkingLot(
                id=parking_data.get('id', ''),
                name=parking_data.get('name', ''),
                location=parking_data.get('location', ''),
                address=parking_data.get('address'),
                capacity=parking_data.get('capacity'),
                ip_address=parking_data.get('ip_address', ''),
                port=parking_data.get('port', 443),
                project_number=parking_data.get('description', ''),
                is_active=parking_data.get('is_active', False)
            )
            parkings.append(parking)
            
            print(f"\n📍 חניון: {parking.name}")
            print(f"  - מיקום: {parking.location}")
            print(f"  - מספר פרויקט: {parking.project_number}")
            print(f"  - סטטוס: {'🟢 פעיל' if parking.is_active else '🔴 לא פעיל'}")
            print(f"  - כתובת חיבור: {parking.get_connection_url()}")
            print(f"  - API endpoint דוגמה: {parking.get_api_endpoint('status')}")
        
        return parkings
    except Exception as e:
        print(f"❌ שגיאה בחיפוש חניונים: {e}")
        return []


def create_test_user(supabase: Client):
    """יצירת משתמש לבדיקה"""
    print("\n➕ יוצר משתמש לבדיקה...")
    
    try:
        # יצירת סיסמה מוצפנת
        password = "Test123456"
        password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
        test_user = {
            'username': 'TestUser1',
            'email': 'test@example.com',
            'password_hash': password_hash,
            'role': 'user',
            'project_number': '478131051',
            'parking_name': 'חניון בדיקה',
            'company_type': 'בדיקה',
            'access_level': 'company_manager',
            'company_list': '1,2,5-10,60',
            'permissions': 'GR',
            'is_temp_password': False
        }
        
        result = supabase.table('user_parkings').insert(test_user).execute()
        
        if result.data:
            print(f"✅ משתמש נוצר בהצלחה!")
            print(f"  - שם משתמש: {test_user['username']}")
            print(f"  - סיסמה: {password}")
            return result.data[0]
        else:
            print("❌ נכשל ביצירת משתמש")
            return None
    except Exception as e:
        print(f"❌ שגיאה ביצירת משתמש: {e}")
        return None


def main():
    """פונקציה ראשית לבדיקות"""
    print("=" * 50)
    print("🧪 מתחיל בדיקות מערכת")
    print("=" * 50)
    
    # 1. בדיקת חיבור
    supabase = test_supabase_connection()
    if not supabase:
        print("\n❌ לא ניתן להמשיך ללא חיבור ל-Supabase")
        return
    
    # 2. בדיקת משתמש קיים
    user_data = test_user_login(supabase, "DrorParking", "")
    
    if user_data:
        # 3. בדיקת הרשאות
        user = test_permissions(user_data)
        
        # 4. בדיקת חניונים
        test_parkings(supabase, user_data.get('project_number'))
    
    # 5. אפשרות ליצירת משתמש בדיקה
    print("\n" + "=" * 50)
    create_test = input("האם ליצור משתמש בדיקה? (y/n): ")
    if create_test.lower() == 'y':
        create_test_user(supabase)
    
    print("\n" + "=" * 50)
    print("✅ בדיקות הסתיימו")
    print("=" * 50)


if __name__ == "__main__":
    main()

