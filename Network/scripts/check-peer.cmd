@echo off
setlocal
if "%~1"=="" (
  echo Usage: scripts\check-peer.cmd http://IP:PORT
  exit /b 2
)
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$url='%~1'.TrimEnd('/');" ^
  "Write-Host ('Checking ' + $url);" ^
  "try { $r=Invoke-WebRequest -UseBasicParsing -TimeoutSec 5 ($url + '/healthz'); Write-Host ('healthz: ' + $r.StatusCode + ' ' + $r.Content) } catch { Write-Error ('healthz failed: ' + $_.Exception.Message); exit 1 }"
