@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

:: Auto-navigate to SwtorSim repo directory if launched from parent
if exist "SwtorSim\src\extractor\main.py" cd SwtorSim

:: Preset Asset Directories
set "STEAM_LIVE_ASSETS=C:\Program Files (x86)\Steam\steamapps\common\Star Wars - The Old Republic\Assets"
set "STEAM_PTS_ASSETS=C:\Program Files (x86)\Steam\steamapps\common\Star Wars - The Old Republic - PTS\Assets"

set "LAUNCHER_LIVE_ASSETS=C:\Program Files (x86)\Electronic Arts\BioWare\Star Wars - The Old Republic\Assets"
set "LAUNCHER_PTS_ASSETS=C:\Program Files (x86)\Electronic Arts\BioWare\Star Wars - The Old Republic - PTS\Assets"

:: Default to Steam initially
set "SOURCE_NAME=Steam"
set "LIVE_ASSETS=%STEAM_LIVE_ASSETS%"
set "PTS_ASSETS=%STEAM_PTS_ASSETS%"

:: Determine Python runner (prefer pyclean if available, else py/python)
if exist "tools\pyclean.exe" (
    set "RUNNER=tools\pyclean.exe"
) else if exist ".venv\Scripts\python.exe" (
    set "RUNNER=.venv\Scripts\python.exe"
) else (
    set "RUNNER=py"
)

:select_source
cls
echo ================================================================
echo            Select SWTOR Installation Asset Source
echo ================================================================
echo.
echo   [1] Steam
echo       Live: %STEAM_LIVE_ASSETS%
echo       PTS:  %STEAM_PTS_ASSETS%
echo.
echo   [2] Launcher (Electronic Arts / BioWare)
echo       Live: %LAUNCHER_LIVE_ASSETS%
echo       PTS:  %LAUNCHER_PTS_ASSETS%
echo.
echo   [3] Custom Path (Enter your own Live / PTS Assets folder)
echo   [4] Exit
echo.
set "src_choice="
set /p src_choice="Select source (1-4) [default: 1]: "

if "%src_choice%"=="" goto set_steam
if "%src_choice%"=="1" goto set_steam
if "%src_choice%"=="2" goto set_launcher
if "%src_choice%"=="3" goto set_custom
if "%src_choice%"=="4" goto end
goto select_source

:set_steam
set "SOURCE_NAME=Steam"
set "LIVE_ASSETS=%STEAM_LIVE_ASSETS%"
set "PTS_ASSETS=%STEAM_PTS_ASSETS%"
goto menu

:set_launcher
set "SOURCE_NAME=Launcher"
set "LIVE_ASSETS=%LAUNCHER_LIVE_ASSETS%"
set "PTS_ASSETS=%LAUNCHER_PTS_ASSETS%"
goto menu

:set_custom
echo.
echo --- Custom Asset Paths (press Enter to keep current default) ---
set "custom_live="
set /p custom_live="Enter custom LIVE Assets path [%LIVE_ASSETS%]: "
if not "%custom_live%"=="" (
    set "custom_live=%custom_live:"=%"
    if exist "!custom_live!\Assets\" set "custom_live=!custom_live!\Assets"
    set "LIVE_ASSETS=!custom_live!"
)
set "custom_pts="
set /p custom_pts="Enter custom PTS Assets path  [%PTS_ASSETS%]: "
if not "%custom_pts%"=="" (
    set "custom_pts=%custom_pts:"=%"
    if exist "!custom_pts!\Assets\" set "custom_pts=!custom_pts!\Assets"
    set "PTS_ASSETS=!custom_pts!"
)
set "SOURCE_NAME=Custom"
goto menu

:menu
cls
echo ================================================================
echo              SwtorSim Game Data Extractor Launcher
echo ================================================================
echo   Active Source: [%SOURCE_NAME%]
echo   LIVE Assets:   %LIVE_ASSETS%
echo   PTS Assets:    %PTS_ASSETS%
echo ----------------------------------------------------------------
echo   [1] Extract LIVE Data (Parsed Only - Fast and ~12MB)
echo   [2] Extract PTS Data  (Parsed Only - Fast and ~12MB)
echo   [3] Extract BOTH      (Live and PTS - Parsed Only)
echo.
echo   [4] Extract LIVE (Full Raw Dump - includes ~400MB extracted/)
echo   [5] Extract PTS  (Full Raw Dump - includes ~400MB extracted/)
echo.
echo   [6] Change Asset Source (Steam / Launcher / Custom)
echo   [7] Exit
echo ================================================================
echo.
set "choice="
set /p choice="Select an option (1-7): "

if "%choice%"=="1" goto extract_live_parsed
if "%choice%"=="2" goto extract_pts_parsed
if "%choice%"=="3" goto extract_both_parsed
if "%choice%"=="4" goto extract_live_full
if "%choice%"=="5" goto extract_pts_full
if "%choice%"=="6" goto select_source
if "%choice%"=="7" goto end
goto menu

:extract_live_parsed
echo.
echo [INFO] Running LIVE extraction (--parsed-only)...
echo [INFO] Source:     %SOURCE_NAME%
echo [INFO] Assets:     %LIVE_ASSETS%
echo [INFO] Target dir: data\extractor\live\
echo.
%RUNNER% src\extractor\main.py --assets "%LIVE_ASSETS%" --parsed-only
if errorlevel 1 goto error
goto finish

:extract_pts_parsed
echo.
echo [INFO] Running PTS extraction (--pts --parsed-only)...
echo [INFO] Source:     %SOURCE_NAME%
echo [INFO] Assets:     %PTS_ASSETS%
echo [INFO] Target dir: data\extractor\pts\
echo.
%RUNNER% src\extractor\main.py --assets "%PTS_ASSETS%" --pts --parsed-only
if errorlevel 1 goto error
goto finish

:extract_both_parsed
echo.
echo ================================================================
echo [1/2] Running LIVE extraction (--parsed-only)...
echo ================================================================
%RUNNER% src\extractor\main.py --assets "%LIVE_ASSETS%" --parsed-only
if errorlevel 1 goto error

echo.
echo ================================================================
echo [2/2] Running PTS extraction (--pts --parsed-only)...
echo ================================================================
%RUNNER% src\extractor\main.py --assets "%PTS_ASSETS%" --pts --parsed-only
if errorlevel 1 goto error
goto finish

:extract_live_full
echo.
echo [INFO] Running LIVE full extraction (with raw dumps)...
echo [INFO] Source:     %SOURCE_NAME%
echo [INFO] Assets:     %LIVE_ASSETS%
echo [INFO] Target dir: data\extractor\live\
echo.
%RUNNER% src\extractor\main.py --assets "%LIVE_ASSETS%"
if errorlevel 1 goto error
goto finish

:extract_pts_full
echo.
echo [INFO] Running PTS full extraction (with raw dumps)...
echo [INFO] Source:     %SOURCE_NAME%
echo [INFO] Assets:     %PTS_ASSETS%
echo [INFO] Target dir: data\extractor\pts\
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
echo ================================================================
echo [OK] Extraction completed successfully!
echo ================================================================
pause
goto menu

:end
endlocal
