param(
    [string]$PythonRuntime = "",
    [string]$OpenSslRuntime = ""
)

$ErrorActionPreference = "Stop"

function Copy-Directory {
    param(
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$Destination
    )

    if (-not (Test-Path -LiteralPath $Source)) {
        throw "Missing runtime source: $Source"
    }
    New-Item -ItemType Directory -Force -Path $Destination | Out-Null
    Get-ChildItem -LiteralPath $Source -Force | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination $Destination -Recurse -Force
    }
}

function Copy-OptionalDirectory {
    param(
        [string]$Source,
        [string]$Destination,
        [string]$Label
    )

    if ($Source -and (Test-Path -LiteralPath $Source)) {
        Copy-Directory -Source $Source -Destination $Destination
        Write-Host "[ok] Bundled $Label -> $Destination"
        return $true
    }
    Write-Warning "Optional runtime not bundled: $Label"
    return $false
}

function Copy-PythonRuntime {
    param(
        [string]$Source,
        [string]$Destination
    )

    if (-not $Source -or -not (Test-Path -LiteralPath $Source)) {
        Write-Warning "Optional runtime not bundled: Python"
        return $false
    }

    New-Item -ItemType Directory -Force -Path $Destination | Out-Null
    Get-ChildItem -LiteralPath $Source -File -Force | Where-Object {
        $_.Name -match '^(python|pythonw|vcruntime|ucrtbase).*\.((exe)|(dll))$' -or $_.Name -match '^python\d+\.dll$'
    } | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination $Destination -Force
    }

    $dlls = Join-Path $Source "DLLs"
    if (Test-Path -LiteralPath $dlls) {
        Copy-Directory -Source $dlls -Destination (Join-Path $Destination "DLLs")
    }

    $lib = Join-Path $Source "Lib"
    if (Test-Path -LiteralPath $lib) {
        $targetLib = Join-Path $Destination "Lib"
        New-Item -ItemType Directory -Force -Path $targetLib | Out-Null
        Get-ChildItem -LiteralPath $lib -Force | Where-Object {
            $_.Name -notin @("site-packages", "__pycache__", "test", "idlelib", "ensurepip", "tkinter", "turtledemo")
        } | ForEach-Object {
            Copy-Item -LiteralPath $_.FullName -Destination $targetLib -Recurse -Force
        }
    }

    if (-not (Test-Path -LiteralPath (Join-Path $Destination "python.exe"))) {
        throw "Python runtime source did not contain python.exe: $Source"
    }

    Write-Host "[ok] Bundled Python -> $Destination"
    return $true
}

function Find-FirstExisting {
    param([string[]]$Candidates)
    foreach ($candidate in $Candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate)) {
            return $candidate
        }
    }
    return ""
}

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$appRoot = Resolve-Path (Join-Path $scriptRoot "..")
$repoRoot = Resolve-Path (Join-Path $appRoot "..\..")
$networkRoot = Join-Path $repoRoot "Network"
$runtimeRoot = Join-Path $appRoot "src-tauri\resources\runtime"
$runtimeNetwork = Join-Path $runtimeRoot "Network"

if (-not (Test-Path -LiteralPath (Join-Path $networkRoot "silicium"))) {
    throw "Network runtime not found: $networkRoot"
}

if (Test-Path -LiteralPath $runtimeRoot) {
    Remove-Item -LiteralPath $runtimeRoot -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $runtimeNetwork | Out-Null

Copy-Item -LiteralPath (Join-Path $networkRoot "silicium") -Destination (Join-Path $runtimeNetwork "silicium") -Force
Copy-Directory -Source (Join-Path $networkRoot "tools") -Destination (Join-Path $runtimeNetwork "tools")
Copy-Directory -Source (Join-Path $networkRoot "workloads") -Destination (Join-Path $runtimeNetwork "workloads")
Copy-Directory -Source (Join-Path $networkRoot "bin") -Destination (Join-Path $runtimeNetwork "bin")

$networkedDemo = Join-Path $runtimeNetwork "demo\networked"
New-Item -ItemType Directory -Force -Path $networkedDemo | Out-Null
Copy-Item -LiteralPath (Join-Path $networkRoot "demo\networked\networked_runtime.py") -Destination $networkedDemo -Force

$envDir = Join-Path $runtimeRoot ".silicium\env"
New-Item -ItemType Directory -Force -Path $envDir | Out-Null
@(
    "SILICIUM_RAYTRACER_BIN=Network\bin\raytracer\raytracer.exe",
    "SILICIUM_RAYTRACER_ASSETS_DIR=Network\bin\raytracer"
) | Set-Content -Path (Join-Path $envDir "raytracer.env") -Encoding ASCII

$pythonSource = $PythonRuntime
if (-not $pythonSource) {
    $pythonSource = Find-FirstExisting @(
        (Join-Path $appRoot "vendor\python"),
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python314"),
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python313"),
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python312"),
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python311"),
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python310")
    )
}
$null = Copy-PythonRuntime -Source $pythonSource -Destination (Join-Path $runtimeRoot "tools\python")

$opensslSource = $OpenSslRuntime
if (-not $opensslSource) {
    $opensslSource = Find-FirstExisting @(
        (Join-Path $appRoot "vendor\openssl"),
        "C:\Program Files\OpenSSL-Win64",
        "C:\Program Files\OpenSSL-Win32",
        "C:\Program Files\Git\usr"
    )
}
$null = Copy-OptionalDirectory -Source $opensslSource -Destination (Join-Path $runtimeRoot "tools\openssl") -Label "OpenSSL"

Write-Host "Runtime prepared: $runtimeRoot"
