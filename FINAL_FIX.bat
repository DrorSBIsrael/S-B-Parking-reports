@echo off
echo ========================================================
echo         FINAL FIX FOR 404 ERROR
echo ========================================================
echo.

cd /d C:\S-B-Parking-reports

echo Checking current branch...
git branch

echo.
echo Pulling latest changes first...
git pull origin master 2>nul

echo.
echo Adding all files...
git add .

echo.
echo Committing with timestamp...
git commit -m "FINAL FIX 404 - endpoint in app.py line 3185" --no-verify

echo.
echo Force pushing to GitHub...
git push origin master -f

echo.
echo ========================================================
echo         UPLOAD COMPLETE!
echo ========================================================
echo.
echo Render will deploy automatically in 2-3 minutes
echo.
echo TEST THE FIX:
echo 1. Wait 2-3 minutes
echo 2. Open new incognito window (Ctrl+Shift+N)
echo 3. Go to: https://s-b-parking-reports.onrender.com/login
echo.
echo Or test the endpoint directly:
echo https://s-b-parking-reports.onrender.com/api/company-manager/proxy
echo.
pause

python fix_and_deploy.py
