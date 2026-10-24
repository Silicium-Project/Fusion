# Prepares the Windows runtime bundled in the installer
# (src-tauri/resources/runtime): the Rust node (p2p_node.exe), the compute
# daemon (compute_daemon.exe) and the native raytracer, plus the raytracer
# environment file read by the app. Nothing else ships: the network runtime
# needs neither Python nor OpenSSL.

$ErrorActionPreference = "Stop"

function Invoke-CargoBuild {
    param(
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [string]$TargetDir = "",
        [Parameter(Mandatory = $true)][string]$What
    )

    $previousTarget = $env:CARGO_TARGET_DIR
    try {
        if ($TargetDir) {
            $env:CARGO_TARGET_DIR = $TargetDir
        } else {
            Remove-Item Env:CARGO_TARGET_DIR -ErrorAction SilentlyContinue
        }
        & cargo build @Arguments
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to build $What."
        }
    } finally {
        if ($null -eq $previousTarget) {
            Remove-Item Env:CARGO_TARGET_DIR -ErrorAction SilentlyContinue
        } else {
            $env:CARGO_TARGET_DIR = $previousTarget
        }
    }
}

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$appRoot = Resolve-Path (Join-Path $scriptRoot "..")
$repoRoot = Resolve-Path (Join-Path $appRoot "..\..")
$networkRoot = Join-Path $repoRoot "Network"
$runtimeRoot = Join-Path $appRoot "src-tauri\resources\runtime"
$runtimeNetwork = Join-Path $runtimeRoot "Network"
$nativeRaytracerManifest = Join-Path $networkRoot "crates\raytracer\Cargo.toml"
$nativeRaytracerTarget = Join-Path $appRoot "src-tauri\target\raytracer-native"

if (-not (Test-Path -LiteralPath $nativeRaytracerManifest)) {
    throw "Native raytracer manifest not found: $nativeRaytracerManifest"
}

$nativeNodeTarget = Join-Path $networkRoot "target\release"
$p2pNodeBinary = Join-Path $nativeNodeTarget "p2p_node.exe"
$computeDaemonBinary = Join-Path $nativeNodeTarget "compute_daemon.exe"
if (-not (Test-Path -LiteralPath $p2pNodeBinary) -or -not (Test-Path -LiteralPath $computeDaemonBinary)) {
    Invoke-CargoBuild -What "the Rust node runtime" -Arguments @(
        "--release", "--locked", "--manifest-path", (Join-Path $networkRoot "Cargo.toml"), "-p", "p2p_node", "-p", "compute_daemon"
    )
}
Invoke-CargoBuild -What "the native raytracer" -TargetDir $nativeRaytracerTarget -Arguments @(
    "--release", "--manifest-path", $nativeRaytracerManifest
)

if (Test-Path -LiteralPath $runtimeRoot) {
    Remove-Item -LiteralPath $runtimeRoot -Recurse -Force
}
$runtimeBin = Join-Path $runtimeNetwork "bin"
$raytracerDirectory = Join-Path $runtimeBin "raytracer"
New-Item -ItemType Directory -Force -Path $raytracerDirectory | Out-Null
Copy-Item -LiteralPath $p2pNodeBinary -Destination (Join-Path $runtimeBin "p2p_node.exe") -Force
Copy-Item -LiteralPath $computeDaemonBinary -Destination (Join-Path $runtimeBin "compute_daemon.exe") -Force
$raytracerPath = Join-Path $raytracerDirectory "silicium-raytracer.exe"
Copy-Item -LiteralPath (Join-Path $nativeRaytracerTarget "release\silicium-raytracer.exe") -Destination $raytracerPath -Force
if (-not (Test-Path -LiteralPath $raytracerPath)) {
    throw "Bundled native raytracer runtime missing: $raytracerPath"
}

$envDir = Join-Path $runtimeRoot ".silicium\env"
New-Item -ItemType Directory -Force -Path $envDir | Out-Null
@(
    "SILICIUM_RAYTRACER_BIN=Network\bin\raytracer\silicium-raytracer.exe",
    "SILICIUM_RAYTRACER_ASSETS_DIR=Network\bin\raytracer"
) | Set-Content -Path (Join-Path $envDir "raytracer.env") -Encoding ASCII

Write-Host "Runtime prepared: $runtimeRoot"
