@echo off
echo ========================================
echo    DEPLOYING DIRECT CONNECTION FIX
echo ========================================
echo.
echo This fix makes:
echo - LOCAL: Direct connection to 10.35.240.100:8443
echo - PRODUCTION: Proxy to 192.117.0.122:8240
echo.

echo [1/3] Adding fixed files...
git add static/js/parking-api-live.js
git add templates/parking_subscribers.html

echo.
echo [2/3] Committing...
git commit -m "Fix: Direct connection for local, proxy for production"

echo.
echo [3/3] Pushing to Render...
git push origin master

echo.
echo ========================================
echo    DEPLOYMENT COMPLETE!
echo ========================================
echo.
echo After 2-3 minutes:
echo.
echo LOCAL (your computer):
echo - Will connect directly to 10.35.240.100:8443
echo - No proxy needed
echo.
echo PRODUCTION (Render):
echo - Will use proxy to reach 192.117.0.122:8240
echo - Proxy handles external connection
echo.
echo Check console for:
echo - "LOCAL MODE: Direct connection"
echo - "PRODUCTION MODE: Using proxy"
echo.
pause

