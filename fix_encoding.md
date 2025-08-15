# 🔧 תיקון בעיית הקידוד בעברית

## 📝 מה תיקנתי:

### 1. **הוספתי הגדרת קידוד UTF-8 ל-appV3.py**
```python
# -*- coding: utf-8 -*-
```

### 2. **הגדרתי את Flask לתמוך בעברית ב-JSON**
```python
app.config['JSON_AS_ASCII'] = False
app.config['JSONIFY_MIMETYPE'] = 'application/json; charset=utf-8'
```

### 3. **הוספתי headers מפורשים לתגובות JSON**
```python
response.headers['Content-Type'] = 'application/json; charset=utf-8'
```

## 🔍 בדיקות נוספות אם עדיין יש בעיה:

### אופציה 1: בדוק את הקידוד של הקובץ appV3.py
- ב-VS Code: בתחתית המסך, בדוק שכתוב "UTF-8"
- אם לא, לחץ עליו ובחר "Save with Encoding" > "UTF-8"

### אופציה 2: בדוק את הדפדפן
- פתח את Console (F12)
- בדוק את התגובה מה-API:
```javascript
fetch('/api/company-manager/proxy', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
        parking_id: 'YOUR_PARKING_ID',
        endpoint: 'contracts',
        method: 'GET'
    })
}).then(r => r.json()).then(console.log)
```

### אופציה 3: נסה לשמור מחדש את appV3.py
```bash
# ב-Windows PowerShell
$content = Get-Content appV3.py -Encoding UTF8
Set-Content appV3.py -Value $content -Encoding UTF8
```

## 📤 העלה לשרת:
```bash
git add appV3.py
git commit -m "Fix Hebrew encoding in JSON responses"
git push
```

## 💡 אם עדיין יש בעיה:
יכול להיות שה-mock data בקובץ parking-ui-integration-xml.js לא מקודד נכון.
נסה לשמור גם אותו עם UTF-8.

