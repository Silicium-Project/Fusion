$ErrorActionPreference = "Stop"

if ($args.Count -lt 1 -or [string]::IsNullOrWhiteSpace($args[0])) {
  throw "Tauri did not provide a Windows binary to sign"
}

$targetPath = [IO.Path]::GetFullPath($args[0])
if (-not (Test-Path -LiteralPath $targetPath -PathType Leaf)) {
  throw "The Windows binary to sign does not exist: $targetPath"
}

$certificatePath = $env:SILICIUM_WINDOWS_CERTIFICATE_PATH
if ([string]::IsNullOrWhiteSpace($certificatePath) -or -not (Test-Path -LiteralPath $certificatePath -PathType Leaf)) {
  throw "SILICIUM_WINDOWS_CERTIFICATE_PATH does not point to a certificate file"
}
if ([string]::IsNullOrEmpty($env:SILICIUM_WINDOWS_CERTIFICATE_PASSWORD)) {
  throw "SILICIUM_WINDOWS_CERTIFICATE_PASSWORD is missing"
}

$signToolPath = $env:TAURI_WINDOWS_SIGNTOOL_PATH
if ([string]::IsNullOrWhiteSpace($signToolPath) -or -not (Test-Path -LiteralPath $signToolPath -PathType Leaf)) {
  $signTool = Get-ChildItem `
    -Path "${env:ProgramFiles(x86)}\Windows Kits\10\bin" `
    -Filter signtool.exe -File -Recurse `
    -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -match "\\x64\\signtool\.exe$" } |
    Sort-Object FullName -Descending |
    Select-Object -First 1
  if (-not $signTool) {
    throw "Windows SDK signtool.exe was not found on the runner"
  }
  $signToolPath = $signTool.FullName
}

$timestampUrl = if ([string]::IsNullOrWhiteSpace($env:SILICIUM_WINDOWS_TIMESTAMP_URL)) {
  "http://timestamp.digicert.com"
} else {
  $env:SILICIUM_WINDOWS_TIMESTAMP_URL
}

& $signToolPath sign `
  /fd SHA256 `
  /f $certificatePath `
  /p $env:SILICIUM_WINDOWS_CERTIFICATE_PASSWORD `
  /tr $timestampUrl `
  /td SHA256 `
  $targetPath
if ($LASTEXITCODE -ne 0) {
  throw "signtool.exe failed with exit code $LASTEXITCODE for $targetPath"
}

# A self-signed test certificate is intentionally not added to the Windows
# certificate stores. The caller verifies the signer certificate and explicitly
# allows the trust-only failure mode when test packaging is enabled.
