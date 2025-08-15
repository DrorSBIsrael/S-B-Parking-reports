"""
קובץ הגדרות לחיבור לבסיס נתונים והגדרת הרשאות
==========================================
עודכן לעבודה עם המבנה החדש של הטבלאות
"""

import os
from typing import Dict, List, Optional, Union
from dataclasses import dataclass
from dotenv import load_dotenv

# טעינת משתני סביבה מקובץ .env
load_dotenv()

# הגדרות חיבור לבסיס נתונים
DATABASE_CONFIG = {
    'SUPABASE_URL': os.environ.get('SUPABASE_URL'),
    'SUPABASE_KEY': os.environ.get('SUPABASE_ANON_KEY'),
}

# הגדרות הרשאות במערכת
PERMISSIONS = {
    'G': 'guest',      # אורח - הרשאות בסיסיות בלבד
    'N': 'new',        # חדש - משתמש חדש במערכת
    'R': 'report',     # דוחות - הרשאה לצפייה בדוחות
    'P': 'profile'     # פרופיל - הרשאה מלאה לניהול פרופיל
}

# רמות גישה במערכת
ACCESS_LEVELS = {
    'single_parking': 'חניון בודד',
    'company_manager': 'מנהל חברה',
    'parking_manager': 'מנהל חניונים',
    'master': 'מאסטר'
}

# שמות הטבלאות בבסיס הנתונים
TABLES = {
    'users': 'user_parkings',    # טבלת משתמשים
    'parkings': 'parkings'        # טבלת חניונים (לשעבר parking_lots)
}

@dataclass
class UserPermissions:
    """מחלקה לניהול הרשאות משתמש"""
    user_id: int
    username: str
    email: str
    role: str
    permissions: str  # G, N, R, P
    company_list: str  # רשימת מספרי חברות: "1,2,5-10,60"
    access_level: str
    project_number: Union[int, str]  # עכשיו מאפשר גם int (BIGINT בבסיס הנתונים)
    parking_name: str
    code_type: Optional[str] = None  # הוספת שדה code_type
    is_temp_password: bool = False   # הוספת שדה סיסמה זמנית
    
    def has_permission(self, permission: str) -> bool:
        """בדיקה אם למשתמש יש הרשאה מסוימת"""
        return permission in self.permissions if self.permissions else False
    
    def get_company_numbers(self) -> List[int]:
        """קבלת רשימת מספרי החברות המורשות"""
        if not self.company_list:
            return []
        
        companies = []
        parts = self.company_list.split(',')
        
        for part in parts:
            part = part.strip()
            if '-' in part:
                # טווח מספרים (למשל: 5-10)
                try:
                    start, end = part.split('-')
                    companies.extend(range(int(start), int(end) + 1))
                except ValueError:
                    print(f"⚠️ שגיאה בפענוח טווח: {part}")
            else:
                # מספר בודד
                try:
                    companies.append(int(part))
                except ValueError:
                    print(f"⚠️ שגיאה בפענוח מספר: {part}")
        
        return sorted(set(companies))  # מחזיר רשימה ממוינת ללא כפילויות
    
    def can_access_company(self, company_number: int) -> bool:
        """בדיקה אם המשתמש יכול לגשת לחברה מסוימת"""
        return company_number in self.get_company_numbers()
    
    def can_access_parking(self, parking_project_number: Union[int, str]) -> bool:
        """בדיקה אם המשתמש יכול לגשת לחניון מסוים"""
        # המרה למספר לצורך השוואה
        try:
            parking_num = int(parking_project_number)
            user_num = int(self.project_number)
            
            if self.access_level == 'single_parking':
                return parking_num == user_num
            elif self.access_level in ['company_manager', 'parking_manager', 'master']:
                return True  # יש להם גישה לכל החניונים של החברה
            return False
        except (ValueError, TypeError):
            return False
    
    def is_master(self) -> bool:
        """בדיקה אם המשתמש הוא מאסטר"""
        return self.access_level == 'master' or self.code_type == 'master'
    
    def is_company_manager(self) -> bool:
        """בדיקה אם המשתמש הוא מנהל חברה"""
        return self.access_level == 'company_manager'
    
    def is_parking_manager(self) -> bool:
        """בדיקה אם המשתמש הוא מנהל חניונים"""
        return self.access_level == 'parking_manager' or self.code_type == 'parking_manager'
    
    def get_permission_description(self) -> str:
        """קבלת תיאור ההרשאות"""
        perms = []
        if 'G' in self.permissions:
            perms.append('אורח')
        if 'N' in self.permissions:
            perms.append('חדש')
        if 'R' in self.permissions:
            perms.append('דוחות')
        if 'P' in self.permissions:
            perms.append('פרופיל')
        return ', '.join(perms) if perms else 'ללא הרשאות'


@dataclass
class Parking:
    """מחלקה לניהול נתוני חניון (עודכן לעבודה עם הטבלה החדשה)"""
    id: str
    name: str
    location: Optional[str] = None
    address: Optional[str] = None
    capacity: Optional[int] = None
    ip_address: str = ''
    port: int = 8443
    description: Union[int, str] = ''  # זה ה-project_number (BIGINT)
    is_active: bool = True
    client_logo_url: Optional[str] = None
    settings: Optional[Dict] = None
    
    @property
    def project_number(self) -> Union[int, str]:
        """מאפיין נוחות לקבלת project_number (שנשמר בשדה description)"""
        return self.description
    
    def get_connection_url(self, use_ssl: bool = None) -> str:
        """קבלת כתובת החיבור לחניון"""
        if use_ssl is None:
            # החלטה אוטומטית לפי הפורט
            use_ssl = self.port in [443, 8443]
        
        protocol = "https" if use_ssl else "http"
        return f"{protocol}://{self.ip_address}:{self.port}"
    
    def get_api_endpoint(self, endpoint: str) -> str:
        """קבלת כתובת API מלאה"""
        base_url = self.get_connection_url()
        endpoint = endpoint.lstrip('/')  # הסרת / מתחילת ה-endpoint אם קיים
        return f"{base_url}/api/{endpoint}"
    
    def is_online(self) -> bool:
        """בדיקה בסיסית אם החניון זמין (לצורך המחשה)"""
        import socket
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            result = sock.connect_ex((self.ip_address, self.port))
            sock.close()
            return result == 0
        except:
            return False


# תאימות לאחור - כדי שקוד ישן ימשיך לעבוד
ParkingLot = Parking


def parse_company_list(company_list_str: str) -> List[int]:
    """
    פענוח רשימת חברות מטקסט
    דוגמה: "1,2,5-10,60" => [1, 2, 5, 6, 7, 8, 9, 10, 60]
    """
    if not company_list_str:
        return []
    
    companies = []
    parts = company_list_str.split(',')
    
    for part in parts:
        part = part.strip()
        if '-' in part:
            try:
                start, end = part.split('-')
                companies.extend(range(int(start), int(end) + 1))
            except ValueError:
                print(f"⚠️ שגיאה בפענוח טווח: {part}")
        else:
            try:
                companies.append(int(part))
            except ValueError:
                print(f"⚠️ שגיאה בפענוח מספר: {part}")
    
    return sorted(set(companies))  # מחזיר רשימה ממוינת ללא כפילויות


def check_user_permissions(user_data: Dict, required_permission: str) -> bool:
    """
    בדיקת הרשאות משתמש
    
    Args:
        user_data: מידע על המשתמש מבסיס הנתונים
        required_permission: ההרשאה הנדרשת (G/N/R/P)
    
    Returns:
        True אם יש הרשאה, False אחרת
    """
    user_permissions = user_data.get('permissions', '')
    return required_permission in user_permissions


def get_parking_connection(parking_data: Dict) -> Dict:
    """
    קבלת פרטי חיבור לחניון (עודכן לעבודה עם הטבלה החדשה)
    
    Args:
        parking_data: נתוני החניון מבסיס הנתונים
    
    Returns:
        מילון עם פרטי החיבור
    """
    port = parking_data.get('port', 8443)
    use_ssl = port in [443, 8443]
    protocol = "https" if use_ssl else "http"
    
    return {
        'url': f"{protocol}://{parking_data['ip_address']}:{port}",
        'ip': parking_data['ip_address'],
        'port': port,
        'name': parking_data['name'],
        'project_number': parking_data['description'],  # description = project_number
        'is_active': parking_data.get('is_active', True)
    }


def create_user_from_db(user_data: Dict) -> UserPermissions:
    """
    יצירת אובייקט UserPermissions מנתוני בסיס הנתונים
    
    Args:
        user_data: שורה מטבלת user_parkings
    
    Returns:
        אובייקט UserPermissions
    """
    return UserPermissions(
        user_id=user_data.get('user_id'),
        username=user_data.get('username'),
        email=user_data.get('email'),
        role=user_data.get('role', 'user'),
        permissions=user_data.get('permissions', ''),
        company_list=user_data.get('company_list', ''),
        access_level=user_data.get('access_level', 'single_parking'),
        project_number=user_data.get('project_number'),
        parking_name=user_data.get('parking_name', ''),
        code_type=user_data.get('code_type'),
        is_temp_password=user_data.get('is_temp_password', False)
    )


def create_parking_from_db(parking_data: Dict) -> Parking:
    """
    יצירת אובייקט Parking מנתוני בסיס הנתונים
    
    Args:
        parking_data: שורה מטבלת parkings
    
    Returns:
        אובייקט Parking
    """
    return Parking(
        id=parking_data.get('id'),
        name=parking_data.get('name'),
        location=parking_data.get('location'),
        address=parking_data.get('address'),
        capacity=parking_data.get('capacity'),
        ip_address=parking_data.get('ip_address', ''),
        port=parking_data.get('port', 8443),
        description=parking_data.get('description'),  # זה ה-project_number
        is_active=parking_data.get('is_active', True),
        client_logo_url=parking_data.get('client_logo_url'),
        settings=parking_data.get('settings')
    )


# ========== בדיקות ודוגמאות שימוש ==========
if __name__ == "__main__":
    print("🔧 בדיקת קובץ הגדרות החיבור")
    print("=" * 50)
    
    # בדיקת הגדרות בסיס הנתונים
    print("\n📊 הגדרות בסיס הנתונים:")
    if DATABASE_CONFIG['SUPABASE_URL']:
        print(f"✅ SUPABASE_URL מוגדר")
    else:
        print(f"❌ SUPABASE_URL חסר - הגדר משתנה סביבה SUPABASE_URL")
    
    if DATABASE_CONFIG['SUPABASE_KEY']:
        print(f"✅ SUPABASE_KEY מוגדר")
    else:
        print(f"❌ SUPABASE_KEY חסר - הגדר משתנה סביבה SUPABASE_ANON_KEY")
    
    # דוגמה למשתמש
    print("\n👤 דוגמה למשתמש:")
    example_user = UserPermissions(
        user_id=305,
        username="DrorParking",
        email="SBparkingReport1@gmail.com",
        role="user",
        permissions="GR",  # אורח + דוחות
        company_list="1,2,5-10,60",
        access_level="company_manager",
        project_number=478131051,  # עכשיו יכול להיות מספר
        parking_name="שיידט בדיקות",
        code_type="company_manager"
    )
    
    print(f"  שם משתמש: {example_user.username}")
    print(f"  הרשאות: {example_user.get_permission_description()}")
    print(f"  רמת גישה: {ACCESS_LEVELS.get(example_user.access_level)}")
    print(f"  חברות מורשות: {example_user.get_company_numbers()}")
    print(f"  יכול לגשת לחברה 7? {example_user.can_access_company(7)}")
    print(f"  יכול לגשת לחברה 100? {example_user.can_access_company(100)}")
    print(f"  מנהל חברה? {example_user.is_company_manager()}")
    
    # דוגמה לחניון
    print("\n🚗 דוגמה לחניון:")
    example_parking = Parking(
        id="b4954e1c-646d-4905-9ab8-9e433bed75e4",
        name="שיידט בדיקות",
        location="לוד",
        ip_address="10.35.152.100",
        port=8443,
        description=478131051,  # זה ה-project_number (BIGINT)
        is_active=True
    )
    
    print(f"  שם: {example_parking.name}")
    print(f"  מיקום: {example_parking.location}")
    print(f"  מספר פרויקט: {example_parking.project_number}")
    print(f"  כתובת חיבור: {example_parking.get_connection_url()}")
    print(f"  API endpoint: {example_parking.get_api_endpoint('status')}")
    print(f"  פעיל? {example_parking.is_active}")
    
    # בדיקת פענוח רשימת חברות
    print("\n📋 בדיקת פענוח רשימת חברות:")
    test_list = "1,3,5-8,15,20-22"
    parsed = parse_company_list(test_list)
    print(f"  קלט: {test_list}")
    print(f"  פלט: {parsed}")
    
    print("\n✅ הבדיקה הושלמה!")
