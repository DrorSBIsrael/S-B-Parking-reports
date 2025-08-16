# מדריך העלאה ל-Render - מערכת ניהול מנויי חניה
=============================================

## 🎯 סיכום השינויים שבוצעו

### 1. עדכון appV3.py
- **שורה 2851-2894**: עודכן הנתיב `/company-manager` להשתמש ב-`parking_subscribers.html` במקום `company_manager.html`
- **הוספת בדיקות הרשאות**: 
  - בדיקת `permissions` (G/N/R/P)
  - בדיקת `company_list` (רשימת חברות מורשות)
- **שמירה ב-session**: נתוני הרשאות וחברות לשימוש ב-API

### 2. API Endpoints חדשים (להוסיף ל-appV3.py)
**חשוב:** צריך להוסיף את הקוד מ-`appV3_api_additions.py` אחרי שורה 2894 ב-`appV3.py`

הוספנו 3 endpoints חדשים:
- `/api/company-manager/get-parkings` - קבלת רשימת חניונים
- `/api/company-manager/get-subscribers` - קבלת מנויים מחניון
- `/api/company-manager/proxy` - Proxy לקריאות לשרתי חניונים

## 📋 רשימת משימות להעלאה

### שלב 1: הכנת הקבצים
```bash
# יצירת מבנה תיקיות
templates/
  └── parking_subscribers.html  # להעתיק את התוכן המלא מהקובץ המקורי
  └── login.html                # כבר קיים
  └── dashboard.html            # אם קיים

static/js/
  └── parking-api-xml.js
  └── config.js
  └── parking-ui-integration-xml.js
```

### שלב 2: עדכון appV3.py
1. פתח את `appV3.py`
2. חפש את שורה 2894 (אחרי פונקציית `company_manager_page`)
3. הוסף את כל הקוד מ-`appV3_api_additions.py`

### שלב 3: העתקת קבצים
**חשוב מאוד:** צריך להעתיק את התוכן המלא של `parking_subscribers.html` ל-`templates/parking_subscribers.html`

```powershell
# פקודות להעתקה (בטרמינל נקי)
Copy-Item parking_subscribers.html templates/parking_subscribers.html -Force
Copy-Item parking-api-xml.js static/js/parking-api-xml.js -Force
Copy-Item config.js static/js/config.js -Force
Copy-Item parking-ui-integration-xml.js static/js/parking-ui-integration-xml.js -Force
```

### שלב 4: בדיקת טבלאות בבסיס הנתונים

#### טבלת `user_parkings` - וודא שקיימים השדות:
- `permissions` (VARCHAR) - הרשאות G/N/R/P
- `company_list` (TEXT) - רשימת חברות "1,2,5-10,60"
- `project_number` (VARCHAR)  כרגע מוגדר INT8
- `access_level` (VARCHAR)  כרגע מוגדר TEXT

#### טבלת `parkings` - וודא שקיימים השדות:
- `ip_address` (VARCHAR) - כתובת IP של החניון
- `port` (INTEGER) - מוגדר INT4 פורט החניון
- `description` (VARCHAR) - מספר פרויקט מוגדר TEXT 
- `name` (VARCHAR) - שם החניון
- `is_active` (BOOLEAN)

### שלב 5: הגדרות ב-Render

#### Environment Variables:
```
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key
SECRET_KEY=your-secret-key
PORT=10000
FLASK_ENV=production

# אופציונלי (אם יש):
GMAIL_USERNAME=your-email@gmail.com
GMAIL_APP_PASSWORD=your-app-password
```

#### Build Command:
```bash
pip install -r requirements.txt
```

#### Start Command:
```bash
gunicorn appV3:app
```

## 🧪 בדיקות לאחר העלאה

### 1. בדיקת התחברות
- נסה להתחבר עם משתמש מסוג `company_manager`
- וודא שמופנה לדף הנכון

### 2. בדיקת הרשאות
- וודא שרק משתמשים עם הרשאת R או P יכולים לגשת
- בדוק שה-company_list עובד נכון

### 3. בדיקת API
בדוק בכלי Developer Tools:
```javascript
// בדיקת קבלת חניונים
fetch('/api/company-manager/get-parkings')
  .then(r => r.json())
  .then(console.log)

// בדיקת proxy
fetch('/api/company-manager/proxy', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({
    parking_id: 'xxx',
    endpoint: 'status',
    method: 'GET'
  })
})
```

## 🐛 פתרון בעיות נפוצות

### בעיה: דף לא נטען
- וודא ש-`parking_subscribers.html` נמצא ב-`templates/`
- בדוק לוגים ב-Render

### בעיה: 404 על קבצי JS
- וודא שהקבצים ב-`static/js/`
- בדוק שה-paths נכונים ב-HTML

### בעיה: אין נתוני חניונים
- וודא שטבלת `parkings` מכילה נתונים
- בדוק ש-`ip_address` ו-`port` מוגדרים

### בעיה: שגיאת הרשאות
- וודא ש-`permissions` מכיל R או P
- בדוק ש-`company_list` תקין

## 📝 צ'קליסט סופי

- [ ] appV3.py מעודכן עם הנתיב החדש
- [ ] הקוד מ-appV3_api_additions.py הוסף ל-appV3.py
- [ ] parking_subscribers.html הועתק ל-templates/
- [ ] קבצי JS הועתקו ל-static/js/
- [ ] connection_config.py קיים בתיקייה הראשית
- [ ] משתני סביבה הוגדרו ב-Render
- [ ] טבלאות בבסיס הנתונים מעודכנות
- [ ] בוצעה בדיקת התחברות
- [ ] בוצעה בדיקת API

## 💡 טיפים
1. שמור גיבוי של הקוד הישן לפני העדכון
2. בדוק בסביבת פיתוח לפני העלאה לייצור
3. עקוב אחרי הלוגים ב-Render בזמן אמת
4. השתמש ב-GitHub Actions לדיפלוי אוטומטי

---
**נוצר על ידי:** דרור פרינץ
**תאריך:** 11/08/2025


