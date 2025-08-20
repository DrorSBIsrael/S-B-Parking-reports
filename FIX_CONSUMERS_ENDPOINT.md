# 🔧 תיקון endpoint למנויים

## 📝 הבעיה:
הקריאה ל-consumers מחזירה 0 תוצאות כי ה-endpoint לא נכון.

## 🔍 מה נסינו:

### נסיון 1: 
```javascript
contracts/${contractId}/consumers
```
נהיה: `CustomerMediaWebService/contracts/2/consumers`

### נסיון 2:
```javascript  
consumers?contractId=${contractId}
```
נהיה: `CustomerMediaWebService/consumers?contractId=2`

### נסיון 3 (נוכחי):
```javascript
consumers // עם contractId בpayload
```

## 🎯 מה צריך לבדוק:

בהתאם למסמך API, ה-endpoint הנכון הוא כנראה אחד מאלה:
1. `GET /CustomerMediaWebService/consumers?contractId=X`
2. `GET /CustomerMediaWebService/contracts/X/consumers`
3. `GET /CustomerMediaWebService/GetConsumerList?contractId=X`

## 📋 כדי לבדוק:

1. **הסתכל ב-Render logs** כדי לראות מה ה-URL המדויק שנשלח
2. **נסה ישירות מהדפדפן/Postman** את ה-endpoints השונים
3. **חפש בקוד הישן** איך זה עבד לפני

