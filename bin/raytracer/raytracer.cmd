@echo off
setlocal

set "RAYTRACER_DIR=%~dp0"
if exist "%RAYTRACER_DIR%silicium-raytracer.exe" (
  "%RAYTRACER_DIR%silicium-raytracer.exe" %*
  exit /b %ERRORLEVEL%
)

if exist "%RAYTRACER_DIR%raytracer.py" (
  py "%RAYTRACER_DIR%raytracer.py" %*
  exit /b %ERRORLEVEL%
)

echo raytracer runtime unavailable: missing native executable and raytracer.py
exit /b 127
