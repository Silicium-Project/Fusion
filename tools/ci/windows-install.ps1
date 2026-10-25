$ErrorActionPreference = 'Stop'
$files = @(Get-ChildItem '.artifacts/installers/*.exe')
if ($files.Count -ne 1) { throw 'Expected exactly one NSIS installer' }
$process = Start-Process -FilePath $files[0].FullName -ArgumentList '/S' -Wait -PassThru
if ($process.ExitCode -ne 0) { throw "Installer failed ($($process.ExitCode))" }
$channelSuffix = if ($env:RELEASE_CHANNEL -eq 'dev') { ' Dev' } else { '' }
$installed = Join-Path $env:LOCALAPPDATA "Silicium Node$channelSuffix/silicium-node.exe"
if (!(Test-Path $installed)) { throw 'Installed application executable not found' }
$version = (Get-Item $installed).VersionInfo.FileVersion
if (!$version) { throw 'Installed application has no file version' }
Write-Output "Installed executable version: $version"
# A second install exercises the updater's already-installed path without running network workloads.
$again = Start-Process -FilePath $files[0].FullName -ArgumentList '/S' -Wait -PassThru
if ($again.ExitCode -ne 0) { throw 'Reinstallation failed' }
