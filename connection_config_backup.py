"""
קובץ הגדרות לחיבור לבסיס נתונים והגדרת הרשאות
==========================================
"""

import os
from typing import Dict, List, Optional
from dataclasses import dataclass

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
    project_number: str
    parking_name: str
    
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
                start, end = part.split('-')
                companies.extend(range(int(start), int(end) + 1))
            else:
                # מספר בודד
                companies.append(int(part))
        
        return companies
    
    def can_access_company(self, company_number: int) -> bool:
        """בדיקה אם המשתמש יכול לגשת לחברה מסוימת"""
        return company_number in self.get_company_numbers()
    
    def is_master(self) -> bool:
        """בדיקה אם המשתמש הוא מאסטר"""
        return self.access_level == 'master'
    
    def is_company_manager(self) -> bool:
        """בדיקה אם המשתמש הוא מנהל חברה"""
        return self.access_level == 'company_manager'
    
    def is_parking_manager(self) -> bool:
        """בדיקה אם המשתמש הוא מנהל חניונים"""
        return self.access_level == 'parking_manager'


@dataclass
class ParkingLot:
    """מחלקה לניהול נתוני חניון"""
    id: str
    name: str
    location: str
    address: Optional[str]
    capacity: Optional[int]
    ip_address: str
    port: int
    project_number: str  # description field
    is_active: bool
    
    def get_connection_url(self) -> str:
        """קבלת כתובת החיבור לחניון"""
        protocol = "https" if self.port == 8443 else "http"
        return f"{protocol}://{self.ip_address}:{self.port}"
    
    def get_api_endpoint(self, endpoint: str) -> str:
        """קבלת כתובת API מלאה"""
        base_url = self.get_connection_url()
        return f"{base_url}/api/{endpoint}"


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
                print(f"שגיאה בפענוח טווח: {part}")
        else:
            try:
                companies.append(int(part))
            except ValueError:
                print(f"שגיאה בפענוח מספר: {part}")
    
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
    קבלת פרטי חיבור לחניון
    
    Args:
        parking_data: נתוני החניון מבסיס הנתונים
    
    Returns:
        מילון עם פרטי החיבור
    """
    return {
        'url': f"https://{parking_data['ip_address']}:{parking_data['port']}",
        'ip': parking_data['ip_address'],
        'port': parking_data['port'],
        'name': parking_data['name'],
        'project_number': parking_data['description'],
        'is_active': parking_data['is_active']
    }


# דוגמה לשימוש במחלקות
if __name__ == "__main__":
    # דוגמה למשתמש
    example_user = UserPermissions(
        user_id=305,
        username="DrorParking",
        email="SBparkingReport1@gmail.com",
        role="user",
        permissions="G",
        company_list="1,2,5-10,60",
        access_level="company_manager",
        project_number="478131051",
        parking_name="שיידט בדיקות"
    )
    
    print(f"משתמש: {example_user.username}")
    print(f"הרשאות: {example_user.permissions}")
    print(f"חברות מורשות: {example_user.get_company_numbers()}")
    print(f"יכול לגשת לחברה 7? {example_user.can_access_company(7)}")
    print(f"יכול לגשת לחברה 100? {example_user.can_access_company(100)}")
    
    # דוגמה לחניון
    example_parking = ParkingLot(
        id="b4954e1c-646d-4905-9ab8-9e433bed75e4",
        name="שיידט בדיקות",
        location="לוד",
        address=None,
        capacity=None,
        ip_address="10.35.152.100",
        port=8443,
        project_number="478131051",
        is_active=False
    )
    
    print(f"\nחניון: {example_parking.name}")
    print(f"כתובת חיבור: {example_parking.get_connection_url()}")
    print(f"API endpoint: {example_parking.get_api_endpoint('status')}")

