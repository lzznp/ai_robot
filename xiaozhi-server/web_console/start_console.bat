@echo off
setlocal

REM ============================================================
REM  AI Theater console launcher (Streamlit)
REM
REM  Fixed interpreter: lzluck env (streamlit 1.55).
REM  This avoids the streamlit.exe of Python 3.13 that sits on PATH.
REM
REM  WARNING: do NOT run "python app.py" and do NOT click the green
REM  Run arrow on app.py. That only prints "missing ScriptRunContext"
REM  and exits -- no server is started.
REM
REM  Usage: double-click this file, or:  start_console.bat 8502
REM  NOTE: keep this file ASCII-only; cmd.exe reads .bat as GBK.
REM ============================================================

set "PY=C:\ProgramData\miniconda3\envs\lzluck\python.exe"
set "PORT=%~1"
if "%PORT%"=="" set "PORT=8501"

cd /d "%~dp0"

if not exist "%PY%" (
    echo [ERROR] interpreter not found: %PY%
    pause
    exit /b 1
)

echo.
echo   Console URL: http://localhost:%PORT%
echo   Press Ctrl+C to stop.
echo.

"%PY%" -m streamlit run app.py --server.port %PORT%
pause
