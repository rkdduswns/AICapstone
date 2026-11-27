@echo off
setlocal
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 "%~dp0native_host.py"
    exit /b %errorlevel%
)
python "%~dp0native_host.py"
