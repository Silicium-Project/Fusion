@echo off
setlocal
set "DEMO_DIR=%~dp0"
if "%~1"=="" (
  py "%DEMO_DIR%run_auto_split_demo.py" "%DEMO_DIR%scene.json"
) else (
  py "%DEMO_DIR%run_auto_split_demo.py" %*
)
