@echo off
echo ========================================
echo    URGENT: DEPLOY PROXY ENDPOINT
echo ========================================
echo.
echo CRITICAL: The proxy endpoint is NOT on production!
echo This is why you get 404 errors.
echo.

echo [1/4] Adding ALL necessary files...
git add app.py
git add static/js/parking-api-live.js
git add templates/parking_subscribers.html

echo.
echo [2/4] Committing with critical fix...
git commit -m "CRITICAL: Deploy proxy endpoint + fix CustomerMediaWebService path"

echo.
echo [3/4] Force pushing to ensure deployment...
git push origin master --force

echo.
echo [4/4] Triggering manual deploy if needed...
echo Go to: https://dashboard.render.com/web/srv-ct5gfkd6l47c73ai5390
echo Click "Manual Deploy" > "Deploy latest commit"
echo.

echo ========================================
echo    WHAT WAS FIXED:
echo ========================================
echo.
echo 1. app.py - Added proxy endpoint (lines 3191-3410)
echo 2. JavaScript - Fixed endpoint path:
echo    Before: /contracts/2
echo    After:  CustomerMediaWebService/contracts/2
echo.
echo Wait 3-5 minutes for deployment to complete.
echo.
echo Then check console for:
echo - "Proxy request - endpoint: CustomerMediaWebService/contracts/2"
echo - No more 404 errors!
echo.
pause

