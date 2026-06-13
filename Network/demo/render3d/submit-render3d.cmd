@echo off
setlocal
set "DEMO_DIR=%~dp0"
if "%~1"=="" (
  py "%DEMO_DIR%render3d_demo.py" submit "%DEMO_DIR%scene.json"
) else (
  py "%DEMO_DIR%render3d_demo.py" submit %*
)
exit /b %ERRORLEVEL%
