@echo off
setlocal
cd /d "%~dp0"

:: Auto-navigate to SwtorSim repo directory if launched from parent
if exist "SwtorSim\src\extractor\main.py" cd SwtorSim

:: Asset directories
set "LIVE_ASSETS=C:\Program Files (x86)\Steam\steamapps\common\Star Wars - The Old Republic\Assets"
set "PTS_ASSETS=C:\Program Files (x86)\Steam\steamapps\common\Star Wars - The Old Republic - PTS\Assets"

:: Determine Python runner (prefer pyclean if available, else py/python)
if exist "tools\pyclean.exe" (
    set "RUNNER=tools\pyclean.exe"
) else if exist ".venv\Scripts\python.exe" (
    set "RUNNER=.venv\Scripts\python.exe"
) else (
    set "RUNNER=py"
)

:menu
cls
echo ========================================================
echo             SwtorSim Game Data Extractor Launcher
echo ========================================================
echo.
echo   [1] Extract LIVE Data (Parsed Only - Fast and ~12MB)
echo   [2] Extract PTS Data  (Parsed Only - Fast and ~12MB)
echo   [3] Extract BOTH      (Live and PTS - Parsed Only)
echo.
echo   [4] Extract LIVE (Full Raw Dump - includes ~400MB extracted/)
echo   [5] Extract PTS  (Full Raw Dump - includes ~400MB extracted/)
echo.
echo   [6] Exit
echo.
set /p choice="Select an option (1-6): "

if "%choice%"=="1" goto extract_live_parsed
if "%choice%"=="2" goto extract_pts_parsed
if "%choice%"=="3" goto extract_both_parsed
if "%choice%"=="4" goto extract_live_full
if "%choice%"=="5" goto extract_pts_full
if "%choice%"=="6" goto end
goto menu

:extract_live_parsed
echo.
echo [INFO] Running LIVE extraction (--parsed-only)...
echo [INFO] Target dir: data\extractor\live\
echo.
%RUNNER% src\extractor\main.py --assets "%LIVE_ASSETS%" --parsed-only
if errorlevel 1 goto error
goto finish

:extract_pts_parsed
echo.
echo [INFO] Running PTS extraction (--pts --parsed-only)...
echo [INFO] Target dir: data\extractor\pts\
echo.
%RUNNER% src\extractor\main.py --assets "%PTS_ASSETS%" --pts --parsed-only
if errorlevel 1 goto error
goto finish

:extract_both_parsed
echo.
echo ========================================================
echo [1/2] Running LIVE extraction (--parsed-only)...
echo ========================================================
%RUNNER% src\extractor\main.py --assets "%LIVE_ASSETS%" --parsed-only
if errorlevel 1 goto error

echo.
echo ========================================================
echo [2/2] Running PTS extraction (--pts --parsed-only)...
echo ========================================================
%RUNNER% src\extractor\main.py --assets "%PTS_ASSETS%" --pts --parsed-only
if errorlevel 1 goto error
goto finish

:extract_live_full
echo.
echo [INFO] Running LIVE full extraction (with raw dumps)...
echo.
%RUNNER% src\extractor\main.py --assets "%LIVE_ASSETS%"
if errorlevel 1 goto error
goto finish

:extract_pts_full
echo.
echo [INFO] Running PTS full extraction (with raw dumps)...
echo.
%RUNNER% src\extractor\main.py --assets "%PTS_ASSETS%" --pts
if errorlevel 1 goto error
goto finish

:error
echo.
echo [FAIL] Extraction encountered an error. Check the output above.
pause
goto menu

:finish
echo.
echo ========================================================
echo [OK] Extraction completed successfully!
echo ========================================================
pause
goto menu

:end
endlocal
