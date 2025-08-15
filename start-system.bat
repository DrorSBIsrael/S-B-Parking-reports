@echo off
echo ========================================
echo   Starting Kawa2 Parking System
echo ========================================
echo.

REM Start proxy server in background
echo Starting proxy server...
start /min cmd /c "node proxy-xml-server.js"

REM Wait a moment for server to start
timeout /t 2 /nobreak > nul

REM Open browser to main page
echo Opening browser...
start http://localhost:8080/index.html

echo.
echo ========================================
echo   System is running!
echo   Browser should open automatically.
echo   
echo   If not, navigate to:
echo   http://localhost:8080/index.html
echo ========================================
echo.
echo Press any key to view server logs...
pause > nul

REM Show server window
start cmd /c "node proxy-xml-server.js"

