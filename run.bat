@echo off
chcp 65001 > nul
cd /d "%~dp0"

echo.
echo ============================================================
echo   SWING SCREENER  --  Daily Runner
echo ============================================================
echo.

echo [1/3] Building universe (Finviz)...
python build_universe.py
if errorlevel 1 (
    echo ERROR: build_universe.py failed.
    pause
    exit /b 1
)
echo.

echo [2/3] Running screener...
python screener.py --universe universe_today.txt --verbose
echo.

echo [3/3] Launch dashboard in browser?
choice /c YN /m "Open Streamlit dashboard? (Y=Yes / N=Skip)"
if errorlevel 2 goto end
if errorlevel 1 (
    echo Starting dashboard at http://localhost:8501 ...
    start "" http://localhost:8501
    python -m streamlit run dashboard.py --server.headless true --browser.gatherUsageStats false
)

:end
echo.
echo Finished. Press any key to close.
pause > nul