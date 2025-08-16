# הנחיות התקנה וחיבור המערכת

## 📋 סקירה כללית
מערכת ניהול חניות עם אימות משתמשים, הרשאות ברמות שונות, וחיבור לחניונים מרוחקים.

## 🔧 שלב 1: הגדרת Supabase

### יצירת חשבון ופרויקט
1. היכנס ל-[Supabase](https://supabase.com)
2. צור פרויקט חדש
3. העתק את ה-URL וה-ANON KEY

### הרצת הסקריפט SQL
1. היכנס ל-SQL Editor בממשק Supabase
2. העתק את התוכן מ-`setup_database.sql`
3. הרץ את הסקריפט ליצירת הטבלאות והפונקציות

## 🔐 שלב 2: הגדרת משתני סביבה

צור קובץ `.env` בתיקיית הפרויקט:

```env
# Supabase Configuration
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key-here

# Gmail Configuration (לשליחת מיילים)
GMAIL_USERNAME=your-email@gmail.com
GMAIL_APP_PASSWORD=your-app-password

# Flask Settings
SECRET_KEY=your-secret-key-here
FLASK_ENV=development
PORT=5000
```

## 📊 שלב 3: הגדרת הטבלאות

### טבלת משתמשים (user_parkings)
מכילה את הנתונים הבאים:
- **user_id**: מזהה ייחודי
- **username**: שם משתמש להתחברות
- **email**: כתובת מייל
- **password_hash**: סיסמה מוצפנת
- **permissions**: הרשאות (G=guest, N=new, R=report, P=profile)
- **company_list**: רשימת חברות מורשות (למשל: "1,2,5-10,60")
- **access_level**: רמת גישה (single_parking, company_manager, parking_manager, master)
- **project_number**: מספר פרויקט/חניון
- **parking_name**: שם החניון
- **ip_address**: כתובת IP (בטבלת parking_lots)
- **port**: פורט (בטבלת parking_lots)

### טבלת חניונים (parking_lots)
מכילה את הנתונים הבאים:
- **id**: מזהה ייחודי (UUID)
- **name**: שם החניון
- **location**: מיקום
- **description**: מספר פרויקט (project_number)
- **ip_address**: כתובת IP של החניון
- **port**: פורט התקשורת
- **is_active**: האם פעיל

## 🚀 שלב 4: הפעלת המערכת

### התקנת תלויות Python
```bash
pip install -r requirements.txt
```

### הפעלת השרת
```bash
python appV3.py
```

## 🔑 שלב 5: הרשאות במערכת

### סוגי הרשאות (permissions)
- **G (Guest)**: אורח - גישה בסיסית
- **N (New)**: משתמש חדש
- **R (Report)**: הרשאת דוחות
- **P (Profile)**: ניהול פרופיל מלא

### רמות גישה (access_level)
1. **single_parking**: גישה לחניון בודד
2. **company_manager**: מנהל חברה - גישה לכל החניונים של החברה
3. **parking_manager**: מנהל חניונים - גישה למספר חניונים
4. **master**: מאסטר - גישה מלאה למערכת

## 📝 שלב 6: רשימת חברות (company_list)

### פורמט
- מספרים בודדים: `1,2,60`
- טווחים: `5-10`
- שילוב: `1,2,5-10,60`

### דוגמה
משתמש עם `company_list = "1,2,5-10,60"` יכול לגשת לחברות:
- 1, 2, 5, 6, 7, 8, 9, 10, 60

## 🌐 שלב 7: חיבור לחניונים

### שימוש בכתובת IP ופורט
```python
# מטבלת parking_lots
ip_address = "10.35.152.100"
port = 8443

# יצירת כתובת חיבור
url = f"https://{ip_address}:{port}"
```

## 🧪 שלב 8: בדיקת המערכת

### הוספת משתמש לדוגמה
```sql
INSERT INTO user_parkings (
    username, 
    email, 
    password_hash,
    role,
    project_number,
    parking_name,
    company_type,
    access_level,
    company_list,
    permissions
) VALUES (
    'DrorParking',
    'SBparkingReport1@gmail.com',
    crypt('Dd123456', gen_salt('bf')),
    'user',
    '478131051',
    'שיידט בדיקות',
    'שיידט',
    'company_manager',
    '1,2,5-10,60',
    'G'
);
```

### הוספת חניון לדוגמה
```sql
INSERT INTO parking_lots (
    name,
    location,
    description,
    ip_address,
    port,
    is_active
) VALUES (
    'שיידט בדיקות',
    'לוד',
    '478131051',
    '10.35.152.100',
    8443,
    FALSE
);
```

## 🔄 תהליך התחברות

1. **כניסה למערכת**: דף `login.html`
2. **אימות**: בדיקת שם משתמש וסיסמה מול `user_parkings`
3. **בדיקת הרשאות**: טעינת permissions ו-company_list
4. **גישה לחניונים**: שימוש ב-IP ופורט מ-`parking_lots`

## 📱 שימוש בקוד Python

```python
from connection_config import UserPermissions, ParkingLot, parse_company_list

# יצירת אובייקט משתמש
user = UserPermissions(
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

# בדיקת הרשאות
if user.has_permission('G'):
    print("יש הרשאת אורח")

# בדיקת גישה לחברה
if user.can_access_company(7):
    print("יש גישה לחברה 7")

# יצירת אובייקט חניון
parking = ParkingLot(
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

# קבלת כתובת חיבור
print(f"חיבור לחניון: {parking.get_connection_url()}")
```

## ⚠️ הערות חשובות

1. **אבטחה**: תמיד השתמש בסיסמאות מוצפנות (bcrypt)
2. **SSL**: השתמש ב-HTTPS לחיבורים מאובטחים (פורט 8443)
3. **תוקף סיסמה**: הגדר תוקף ל-90 יום
4. **סיסמאות זמניות**: דרוש שינוי בכניסה ראשונה

## 📞 תמיכה

לשאלות ובעיות, פנה ל:
- Email: dror@sbparking.co.il
- נוצר על ידי: דרור פרינץ

