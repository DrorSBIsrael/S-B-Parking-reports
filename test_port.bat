@echo off
echo =====================================
echo   בודק חיבור לחניון
echo =====================================
echo.
echo בודק את פורט 8240 בכתובת 192.117.0.122...
echo.

powershell -Command "Test-NetConnection -ComputerName 192.117.0.122 -Port 8240 | Select-Object ComputerName, RemotePort, TcpTestSucceeded"

echo.
echo =====================================
echo אם TcpTestSucceeded = False
echo הפורט חסום או השירות לא רץ
echo =====================================
echo.
pause
