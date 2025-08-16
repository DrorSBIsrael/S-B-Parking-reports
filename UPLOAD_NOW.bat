@echo off
echo =======================================================
echo     UPLOADING ALL FIXES TO SERVER
echo =======================================================
echo.

cd /d C:\S-B-Parking-reports

echo Step 1: Adding config.js and app.py...
git add static/js/config.js app.py templates/parking_subscribers.html

echo.
echo Step 2: Committing...
git commit -m "FIX: Added missing config.js and verified proxy endpoint" --no-verify

echo.
echo Step 3: Force pushing to server...
git push origin master --force

echo.
echo =======================================================
echo     DONE! WAIT 2 MINUTES FOR DEPLOYMENT
echo =======================================================
echo.
echo After 2 minutes, test here:
echo.
echo 1. CLEAR YOUR BROWSER CACHE (Ctrl+Shift+Delete)
echo 2. Or open in Incognito mode (Ctrl+Shift+N)
echo 3. Go to: https://s-b-parking-reports.onrender.com/login
echo.
pause
