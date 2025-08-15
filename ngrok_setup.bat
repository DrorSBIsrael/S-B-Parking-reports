@echo off
echo =====================================
echo   הגדרת ngrok לחניון
echo =====================================
echo.
echo 1. הורד ngrok מ: https://ngrok.com/download
echo 2. פתח חשבון חינם ב: https://dashboard.ngrok.com/signup
echo 3. קבל Token מ: https://dashboard.ngrok.com/get-started/your-authtoken
echo.
echo 4. הרץ את הפקודות הבאות:
echo    ngrok config add-authtoken YOUR_TOKEN_HERE
echo    ngrok http 192.117.0.122:8240
echo.
echo 5. תקבל כתובת כמו: https://abc123.ngrok-free.app
echo.
echo 6. עדכן את הכתובת בטבלת parkings ב-Supabase
echo    במקום: https://192.117.0.122:8240
echo    שים: https://abc123.ngrok-free.app
echo.
pause
