@echo off
setlocal
cd /d "%~dp0"
set "LOG=%~dp0run.log"

rem If the app is already serving, just open another tab. This is what makes
rem repeated shortcut clicks open repeated tabs without starting a second
rem server or rebuilding the UI.
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/health' -TimeoutSec 2; if ($r.status -eq 'ok') { exit 0 } } catch {}; exit 1"
if not errorlevel 1 (
    echo [%date% %time%] Already running; opening a new tab.>>"%LOG%"
    start "" "http://127.0.0.1:8000"
    exit /b 0
)

rem The server is not up: show a splash window that closes itself once
rem /health answers, so the boot is visible instead of a silent delay.
start "" powershell -NoProfile -STA -WindowStyle Hidden -File "%~dp0splash.ps1"

rem A second click while the first launch is still building must not start a
rem second build/server. Wait for the server that is already starting.
if exist "%~dp0.launcher.lock" (
    echo [%date% %time%] Another launch is in progress; waiting for the server...>>"%LOG%"
    powershell -NoProfile -ExecutionPolicy Bypass -Command "for ($i = 0; $i -lt 90; $i++) { try { $r = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/health' -TimeoutSec 2; if ($r.status -eq 'ok') { exit 0 } } catch {}; Start-Sleep -Seconds 1 }; exit 1"
    if not errorlevel 1 (
        echo [%date% %time%] Server ready; opening a new tab.>>"%LOG%"
        start "" "http://127.0.0.1:8000"
        exit /b 0
    )
    echo [%date% %time%] Previous launch did not start; taking over.>>"%LOG%"
    rmdir "%~dp0.launcher.lock" >nul 2>&1
)
mkdir "%~dp0.launcher.lock" >nul 2>&1
if errorlevel 1 (
    echo [%date% %time%] Launch lock busy; opening a new tab.>>"%LOG%"
    start "" "http://127.0.0.1:8000"
    exit /b 0
)

echo.>>"%LOG%"
echo [%date% %time%] Building frontend...>>"%LOG%"
pushd "%~dp0frontend"
call npm run build>>"%LOG%" 2>&1
if errorlevel 1 (
    echo Build failed. See "%LOG%".
    powershell -NoProfile -Command "Add-Type -AssemblyName PresentationFramework; [System.Windows.MessageBox]::Show('The UI build failed. See run.log in the project folder.','Marketing Bot')">>"%LOG%" 2>&1
    popd
    rmdir "%~dp0.launcher.lock" >nul 2>&1
    exit /b 1
)
popd
rmdir "%~dp0.launcher.lock" >nul 2>&1

echo [%date% %time%] Starting server...>>"%LOG%"
if exist "%~dp0backend.log" for %%A in ("%~dp0backend.log") do if %%~zA GTR 10485760 del /Q "%~dp0backend.log" >nul 2>&1
pushd "%~dp0backend"
"venv\Scripts\python.exe" main.py>>"%~dp0backend.log" 2>&1
popd
