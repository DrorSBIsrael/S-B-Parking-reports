# תיקון דחוף - הקובץ appV3.py לא נטען נכון ב-Render

## הבעיה
למרות שהגרסה מעודכנת ל-2.0.5, ה-endpoint `/api/company-manager/proxy` לא נמצא (404).

## פתרון מיידי

### אופציה 1: בדוק שהקובץ הנכון הועלה
1. היכנס ל-Render Dashboard
2. לך ל-"Shell" 
3. הרץ:
```bash
grep -n "company-manager/proxy" appV3.py
```

אם לא מוצא - הקובץ הישן עדיין שם!

### אופציה 2: העלה מחדש עם שינוי קטן
1. שנה את הגרסה ב-appV3.py מ-'2.0.5' ל-'2.0.6'
2. העלה מחדש:
```bash
git add appV3.py
git commit -m "Force update to v2.0.6"
git push
```

### אופציה 3: העתק ישירות
אם יש לך גישה ל-Shell ב-Render:
```bash
# גבה את הקובץ הישן
cp appV3.py appV3_backup.py

# העתק את התוכן החדש (תצטרך להעתיק ולהדביק)
nano appV3.py
```

### קבצים שחייבים להיות מעודכנים:
1. **appV3.py** - חייב להכיל את השורה:
   ```python
   @app.route('/api/company-manager/proxy', methods=['POST', 'OPTIONS'])
   ```

2. **static/js/parking-ui-live.js** - התיקון של contractData

## בדיקה מהירה
אחרי העדכון, בדוק:
```
https://s-b-parking-reports.onrender.com/api/status
```
צריך להראות גרסה 2.0.6

ואז בקונסול:
```javascript
fetch('/api/company-manager/proxy', {method: 'OPTIONS'})
  .then(r => console.log('Status:', r.status))
```
צריך להחזיר 200, לא 404!
