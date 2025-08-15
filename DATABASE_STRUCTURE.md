# מבנה בסיס הנתונים - S&B Parking System

## סקירה כללית
המערכת משתמשת ב-2 טבלאות עיקריות:
1. **`user_parkings`** - טבלת משתמשים והרשאות
2. **`parkings`** - טבלת חניונים (לשעבר parking_lots)

## טבלת user_parkings
טבלה זו מכילה את כל המשתמשים במערכת והרשאותיהם.

### עמודות עיקריות:
- **`project_number`** (BIGINT/INT8) - מספר הפרויקט/חניון שהמשתמש משויך אליו
- **`company_list`** (TEXT) - רשימת מספרי חברות שהמשתמש מורשה לגשת אליהן (פורמט: "1,2,5-10,60")
- **`permissions`** (VARCHAR) - הרשאות המשתמש (G=guest, N=new, R=report, P=profile)
- **`access_level`** (VARCHAR) - רמת הגישה:
  - `single_parking` - חניון בודד
  - `company_manager` - מנהל חברה
  - `parking_manager` - מנהל חניונים
  - `master` - מאסטר

### עמודות נוספות:
- `user_id` - מזהה ייחודי
- `username` - שם משתמש
- `email` - כתובת מייל
- `password_hash` - סיסמה מוצפנת
- `role` - תפקיד המשתמש
- `parking_name` - שם החניון
- `company_type` - סוג/שם החברה
- `verification_code` - קוד אימות
- `code_expires_at` - תוקף הקוד
- `code_type` - סוג הקוד
- `is_temp_password` - האם סיסמה זמנית
- `password_changed_at` - תאריך שינוי סיסמה אחרון
- `password_expires_at` - תוקף הסיסמה

## טבלת parkings
טבלה זו מכילה את כל החניונים במערכת.

### עמודות עיקריות:
- **`description`** (BIGINT/INT8) - מספר הפרויקט (מקושר ל-project_number בטבלת user_parkings)
- **`ip_address`** (VARCHAR) - כתובת IP של שרת החניון
- **`port`** (INT4) - פורט התקשורת

### עמודות נוספות:
- `id` - מזהה ייחודי (UUID)
- `name` - שם החניון
- `location` - מיקום
- `address` - כתובת
- `capacity` - קיבולת
- `client_logo_url` - כתובת לוגו
- `settings` - הגדרות נוספות (JSONB)
- `is_active` - האם החניון פעיל
- `created_at` - תאריך יצירה
- `updated_at` - תאריך עדכון אחרון
- `future_code` - קוד עתידי

## הקישור בין הטבלאות

הקישור העיקרי בין הטבלאות הוא דרך:
- **`user_parkings.project_number`** ⟷ **`parkings.description`**

שני השדות הם מסוג BIGINT (INT8) ומייצגים את מספר הפרויקט/חניון.

### דוגמה לשאילתא:
```sql
-- קבלת פרטי חניון עבור משתמש
SELECT 
    u.username,
    u.email,
    p.name as parking_name,
    p.ip_address,
    p.port
FROM user_parkings u
JOIN parkings p ON u.project_number = p.description
WHERE u.username = 'DrorParking';
```

## הגדרת הרשאות

### permissions (תווים):
- **G** - Guest (אורח)
- **N** - New (חדש)
- **R** - Report (דוחות)
- **P** - Profile (פרופיל)

### access_level (רמות גישה):
1. **single_parking** - גישה לחניון בודד בלבד
2. **company_manager** - גישה לכל החניונים של החברה
3. **parking_manager** - ניהול חניונים
4. **master** - גישת מאסטר לכל המערכת

## מיגרציה
אם יש לך בסיס נתונים קיים, הרץ את `migration_script.sql` כדי:
1. לעדכן את סוגי העמודות
2. לשנות את שם הטבלה מ-parking_lots ל-parkings
3. לעדכן את האינדקסים

## בדיקת המערכת
השתמש ב-`test_connection.py` כדי לבדוק:
- חיבור לבסיס הנתונים
- טבלאות קיימות
- נתוני משתמשים וחניונים
- הרשאות

