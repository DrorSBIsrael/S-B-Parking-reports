@echo off
echo ========================================
echo    DEPLOYING COMPLETE FIX - v16.12.2024
echo ========================================
echo.
echo All fixes included:
echo ✅ 1. UTF-8 encoding for Hebrew text
echo ✅ 2. Consumer filtering (both methods)
echo ✅ 3. Contract detail endpoint with pooling data
echo ✅ 4. Parking facilities breakdown
echo ✅ 5. Alternative consumers endpoint format
echo.

echo [1/3] Adding all fixed files...
git add app.py
git add static/js/parking-api-live.js
git add static/js/parking-ui-live.js
git add templates/parking_subscribers.html

echo.
echo [2/3] Committing changes...
git commit -m "Complete fix: Hebrew encoding, consumer filtering, pooling data with facilities breakdown"

echo.
echo [3/3] Pushing to Render...
git push origin master

echo.
echo ========================================
echo    ✅ DEPLOYMENT COMPLETE!
echo ========================================
echo.
echo Wait 3-5 minutes, then check:
echo.
echo 1. Hebrew text displays correctly
echo 2. Each company shows its occupancy (X/Y)
echo 3. Only relevant consumers per company
echo 4. In console: "Parking lots breakdown"
echo.
echo Render Dashboard:
echo https://dashboard.render.com/
echo.
pause
