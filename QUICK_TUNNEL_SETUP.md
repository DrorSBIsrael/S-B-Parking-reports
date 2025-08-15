# הדרכה מהירה - חיבור החניון לאינטרנט עם ngrok

## שלב 1: הורדת ngrok
1. הורד מ: https://ngrok.com/download
2. הירשם חינם ב: https://dashboard.ngrok.com/signup
3. קבל Auth Token מ: https://dashboard.ngrok.com/get-started/your-authtoken

## שלב 2: הגדרת ngrok
במחשב שיש לו גישה לחניון (ברשת הפנימית):
```cmd
ngrok config add-authtoken YOUR_AUTH_TOKEN_HERE
```

## שלב 3: הפעלת ה-Tunnel
```cmd
ngrok http https://10.35.240.100:8240 --host-header=rewrite
```

## שלב 4: קבלת הכתובת הציבורית
תקבל משהו כמו:
```
Forwarding: https://abc123xyz.ngrok-free.app -> https://10.35.240.100:8240
```

## שלב 5: עדכון בבסיס הנתונים
עדכן את הכתובת בטבלת parkings ב-Supabase:
- במקום: `https://10.35.240.100:8240`
- שים: `https://abc123xyz.ngrok-free.app`

## חשוב!
- ngrok חינמי נותן כתובת זמנית שמשתנה כל הפעלה
- לכתובת קבועה - שדרג לתוכנית בתשלום ($8/חודש)
- או השתמש ב-Cloudflare Tunnel (חינמי עם דומיין משלך)

## פתרון קבוע - Cloudflare Tunnel
1. צריך דומיין משלך (כמו parking.yourcompany.com)
2. התקנה: https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/
3. חינמי לחלוטין ויציב יותר

## אלטרנטיבה - הרץ את השרת מקומית
במקום Render, הרץ את appV3.py על שרת ברשת הפנימית שלכם
