@echo off
setlocal
set "SCRIPT_DIR=%~dp0"

if exist "%SCRIPT_DIR%.venv\Scripts\python.exe" (
    "%SCRIPT_DIR%.venv\Scripts\python.exe" "%SCRIPT_DIR%app.py"
    exit /b %errorlevel%
)

if exist "D:\Proiecte\ContabilaAi_local\python\python.exe" (
    "D:\Proiecte\ContabilaAi_local\python\python.exe" "%SCRIPT_DIR%app.py"
    exit /b %errorlevel%
)

where py >nul 2>nul
if %errorlevel%==0 (
    py "%SCRIPT_DIR%app.py"
    exit /b %errorlevel%
)

python "%SCRIPT_DIR%app.py"
