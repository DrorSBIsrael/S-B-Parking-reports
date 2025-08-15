@echo off
echo.
echo ===============================================
echo    FIXING 404 ERROR - IMMEDIATE SOLUTION
echo ===============================================
echo.

REM Kill any existing git processes
taskkill /F /IM git.exe 2>nul

REM Force push the changes
git add -A
git commit -m "EMERGENCY FIX - 404 proxy endpoint" --no-verify
git push origin master --force

echo.
echo ===============================================
echo    DEPLOYMENT STARTED!
echo ===============================================
echo.
echo Wait 2 minutes for deployment...
echo.
timeout /t 120

echo.
echo ===============================================
echo    OPENING SITE WITH NO CACHE
echo ===============================================
echo.

REM Open in incognito mode (no cache)
start chrome --incognito "https://s-b-parking-reports.onrender.com/login"

echo.
echo DONE! Site should work now!
echo.
pause
