$ErrorActionPreference = 'Stop'
$files = @(Get-ChildItem '.artifacts/installers/*.exe')
if ($files.Count -ne 1) { throw 'Expected exactly one NSIS installer' }
$process = Start-Process -FilePath $files[0].FullName -ArgumentList '/S' -Wait -PassThru
if ($process.ExitCode -ne 0) { throw "Installer failed ($($process.ExitCode))" }
$productName = (Get-Content 'apps/node/src-tauri/tauri.conf.json' -Raw | ConvertFrom-Json).productName
$installed = Join-Path $env:LOCALAPPDATA "$productName/silicium-node.exe"
if (!(Test-Path $installed)) { throw 'Installed application executable not found' }
$version = (Get-Item $installed).VersionInfo.FileVersion
if (!$version) { throw 'Installed application has no file version' }
Write-Output "Installed executable version: $version"
# A second install exercises the updater's already-installed path without running network workloads.
$again = Start-Process -FilePath $files[0].FullName -ArgumentList '/S' -Wait -PassThru
if ($again.ExitCode -ne 0) { throw 'Reinstallation failed' }
