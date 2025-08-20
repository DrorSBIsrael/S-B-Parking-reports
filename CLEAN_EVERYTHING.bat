@echo off
echo ========================================
echo    MASSIVE CLEANUP - REMOVE ALL JUNK
echo ========================================
echo.
echo WARNING: This will delete ALL test files and junk!
echo Press Ctrl+C to cancel, or
pause

echo.
echo [1/10] Removing ALL test files...
del test*.* /q 2>nul
del TEST*.* /q 2>nul
del check_*.* /q 2>nul
del CHECK_*.* /q 2>nul
del verify*.* /q 2>nul
del find_*.* /q 2>nul
del debug_*.* /q 2>nul
del quick_test*.* /q 2>nul

echo.
echo [2/10] Removing ALL batch files (except this one)...
for %%f in (*.bat) do if not "%%f"=="CLEAN_EVERYTHING.bat" del "%%f" /q 2>nul

echo.
echo [3/10] Removing ALL markdown docs we created...
del DEPLOY_*.md /q 2>nul
del EMERGENCY_*.md /q 2>nul
del FINAL_*.md /q 2>nul
del UPLOAD_*.md /q 2>nul
del MONITOR_*.md /q 2>nul
del SOLUTION_*.md /q 2>nul
del IMPLEMENT_*.md /q 2>nul
del COMPARISON_*.md /q 2>nul
del ADVANCED_*.md /q 2>nul
del IMMEDIATE_*.md /q 2>nul
del CRITICAL_*.md /q 2>nul
del URGENT_*.md /q 2>nul
del CHECK_*.md /q 2>nul
del fix_*.md /q 2>nul
del immediate_*.md /q 2>nul
del temporary_*.md /q 2>nul

echo.
echo [4/10] Removing log files...
del Log*.txt /q 2>nul
del *.log /q 2>nul

echo.
echo [5/10] Removing Python test scripts...
del fix_*.py /q 2>nul
del alternative_*.py /q 2>nul
del backup_*.py /q 2>nul

echo.
echo [6/10] Removing temp directories...
rd /s /q .tmp.driveupload 2>nul
rd /s /q __pycache__ 2>nul
rd /s /q Temp 2>nul
rd /s /q גיבוי 2>nul
del *.pyc /s /q 2>nul

echo.
echo [7/10] Removing duplicate/test HTML files...
del test*.html /q 2>nul
del mock-*.html /q 2>nul
del direct_test.html /q 2>nul
del force_update_cache.html /q 2>nul
del clear_cache_instructions.html /q 2>nul
del CLEAR_CACHE_NOW.html /q 2>nul

echo.
echo [8/10] Removing unnecessary JS files from root...
del parking-api*.js /q 2>nul
del parking-ui*.js /q 2>nul
del proxy*.js /q 2>nul
del config.js /q 2>nul
del parse_*.js /q 2>nul

echo.
echo [9/10] Removing misc junk...
del tatus /q 2>nul
del 300 /q 2>nul
del "node proxy-xml-server.js.להפעיל ב CMD" /q 2>nul
del TextPTCPT.txt /q 2>nul
del startCommandOld.txt /q 2>nul
del deploy_commands.txt /q 2>nul
del deploy_files_list.txt /q 2>nul
del env_update_guide.txt /q 2>nul
del info_for_provider.txt /q 2>nul
del "חיבור לאתר ובסיס נתונים.txt" /q 2>nul
del "שאילתא.txt" /q 2>nul

echo.
echo [10/10] Removing old app versions...
del appOld.py /q 2>nul
del appV3*.py /q 2>nul
del app_reper.py /q 2>nul
del app_structure_report.txt /q 2>nul
del connection_config_*.py /q 2>nul

echo.
echo ========================================
echo    CLEANUP COMPLETE!
echo ========================================
echo.
echo Files that should remain:
echo - app.py (main application)
echo - requirements.txt
echo - render.yaml
echo - gunicorn.conf.py
echo - README.md
echo - static/ (CSS/JS files)
echo - templates/ (HTML templates)
echo - backend/ (if needed)
echo.
echo Now run: git status
echo to see what's left
echo.
pause
