# הגדרת משתני סביבה למערכת S&B Parking

## 🔧 מה צריך להגדיר

### 1. יצירת קובץ `.env`
צור קובץ חדש בשם `.env` בתיקייה הראשית של הפרויקט והוסף את השורות הבאות:

```env
# Supabase - הגדרות בסיס הנתונים
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key-here

# Gmail - הגדרות שליחת מיילים
GMAIL_USERNAME=your-email@gmail.com
GMAIL_APP_PASSWORD=your-app-password-here

# הגדרות נוספות אופציונליות
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_SSL=False
MAIL_USE_TLS=True

# Flask Secret Key (שנה לערך אקראי וחזק)
SECRET_KEY=your-secret-key-here-change-this
```

### 2. קבלת פרטי Supabase

1. היכנס לחשבון Supabase שלך: https://app.supabase.com
2. בחר את הפרויקט שלך
3. לך ל-Settings > API
4. העתק את:
   - **Project URL** → `SUPABASE_URL`
   - **anon public key** → `SUPABASE_ANON_KEY`

### 3. הגדרת Gmail לשליחת מיילים

1. היכנס לחשבון Gmail שלך
2. הפעל אימות דו-שלבי (אם לא פעיל)
3. צור App Password:
   - לך ל: https://myaccount.google.com/apppasswords
   - בחר "Mail" ו-"Other (Custom name)"
   - תן שם כמו "S&B Parking System"
   - העתק את הסיסמה שנוצרה → `GMAIL_APP_PASSWORD`

### 4. יצירת Secret Key לאבטחה

ב-Python, הרץ:
```python
import secrets
print(secrets.token_hex(32))
```
והעתק את הערך ל-`SECRET_KEY`

## 🚀 בדיקת ההגדרות

הרץ את הסקריפט הבא כדי לבדוק שהכל מוגדר נכון:

```bash
python connection_config_updated.py
```

אמור לראות:
- ✅ SUPABASE_URL מוגדר
- ✅ SUPABASE_KEY מוגדר

## ⚠️ אבטחה

**חשוב מאוד:**
- **לעולם** אל תעלה את קובץ `.env` ל-Git
- וודא ש-`.env` מופיע ב-`.gitignore`
- שמור גיבוי של הערכים במקום בטוח
- השתמש בסיסמאות חזקות וייחודיות

## 📝 משתנים נוספים אופציונליים

```env
# הגדרות דיבאג
DEBUG=False
TESTING=False

# הגדרות שרת
HOST=0.0.0.0
PORT=5000

# הגדרות בסיס נתונים נוספות
DATABASE_POOL_SIZE=10
DATABASE_MAX_OVERFLOW=20

# הגדרות אימייל נוספות
MAIL_MAX_EMAILS=100
MAIL_SUPPRESS_SEND=False
MAIL_DEBUG=False
```

## 🔍 פתרון בעיות

### בעיה: "SUPABASE_URL חסר"
**פתרון:** וודא שיצרת את קובץ `.env` והוספת את השורה:
```
SUPABASE_URL=https://your-project.supabase.co
```

### בעיה: "שגיאה בשליחת מייל"
**פתרון:** בדוק ש:
1. הפעלת אימות דו-שלבי ב-Gmail
2. יצרת App Password ולא משתמש בסיסמה הרגילה
3. ה-GMAIL_USERNAME הוא כתובת המייל המלאה

### בעיה: "Session security error"
**פתרון:** צור SECRET_KEY חדש וחזק:
```python
import secrets
print(secrets.token_hex(32))
```

