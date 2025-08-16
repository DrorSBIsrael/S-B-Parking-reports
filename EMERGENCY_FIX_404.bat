@echo off
echo ====================================================
echo    EMERGENCY FIX FOR 404 ERROR
echo ====================================================
echo.

cd /d C:\S-B-Parking-reports

echo Killing any stuck git processes...
taskkill /F /IM git.exe 2>nul
taskkill /F /IM git-remote-https.exe 2>nul

echo.
echo Adding all files...
git add .

echo.
echo Committing changes...
git commit -m "EMERGENCY FIX - 404 proxy endpoint unified in app.py" --no-verify

echo.
echo Force pushing to server...
git push origin master --force

echo.
echo ====================================================
echo    DEPLOYMENT WILL START AUTOMATICALLY
echo ====================================================
echo.
echo Please wait 2-3 minutes for Render to deploy...
echo.
echo Then open the site in INCOGNITO MODE:
echo.
pause

start chrome --incognito "https://s-b-parking-reports.onrender.com/login?nocache=true"
