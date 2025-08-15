@echo off
echo.
echo ========================================
echo   בדיקת תיקון ה-404 Error
echo ========================================
echo.
echo פותח דף בדיקה מקומי...
start test_proxy_fix.html
echo.
echo פותח גם את האתר החי ב-Render...
timeout /t 2 /nobreak >nul
start https://s-b-parking-reports.onrender.com/login
echo.
echo ========================================
echo   הוראות בדיקה:
echo ========================================
echo.
echo 1. בדף הבדיקה - לחץ על הכפתורים לבדיקת ה-endpoint
echo 2. אם מקבל "SUCCESS" - התיקון עובד!
echo 3. באתר החי - התחבר ובדוק את parking_subscribers
echo.
pause
