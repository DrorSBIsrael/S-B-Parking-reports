@echo off
echo ========================================
echo    FORCE DEPLOYMENT TO RENDER
echo ========================================
echo.

echo [1] Stage all changes...
git add -A

echo.
echo [2] Create new commit...
git commit -m "CRITICAL FIX: Add contracts/X/detail endpoint for pooling data" --allow-empty

echo.
echo [3] Force push to GitHub...
git push --force origin master

echo.
echo ========================================
echo    DEPLOYMENT TRIGGERED!
echo ========================================
echo.
echo Render will automatically deploy in 3-5 minutes.
echo.
echo Check deployment status at:
echo https://dashboard.render.com/
echo.
echo After deployment, test at:
echo https://s-b-parking-reports.onrender.com/parking_subscribers
echo.
pause
