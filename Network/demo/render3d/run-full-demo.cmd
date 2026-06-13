@echo off
setlocal
set "DEMO_DIR=%~dp0"
py "%DEMO_DIR%run_full_demo.py" %*
exit /b %ERRORLEVEL%
