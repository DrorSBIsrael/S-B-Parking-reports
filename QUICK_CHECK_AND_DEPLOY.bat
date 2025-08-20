@echo off
echo ========================================
echo    QUICK DEPLOYMENT CHECK
echo ========================================
echo.

echo [1] Checking GitHub remote...
git remote -v

echo.
echo [2] Fetching latest from GitHub...
git fetch origin master

echo.
echo [3] Checking if local is up to date...
git status

echo.
echo [4] Force pushing current state...
git push --force origin master

echo.
echo ========================================
echo    DONE - Wait 3-5 minutes for Render
echo ========================================
pause
