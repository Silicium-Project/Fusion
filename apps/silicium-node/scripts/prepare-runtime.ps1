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
        throw "Python runtime source not found. Provide -PythonRuntime or install Python locally before building."
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

        # Compiled caches and nested standard-library test suites are not used
        # by the node and add several megabytes to every installer.
        Get-ChildItem -LiteralPath $targetLib -Directory -Recurse -Force | Where-Object {
            $_.Name -in @("__pycache__", "test", "tests")
        } | Sort-Object FullName -Descending | ForEach-Object {
            Remove-Item -LiteralPath $_.FullName -Recurse -Force
        }
    }

    if (-not (Test-Path -LiteralPath (Join-Path $Destination "python.exe"))) {
        throw "Python runtime source did not contain python.exe: $Source"
    }

    Write-Host "[ok] Bundled Python -> $Destination"
    return $true
}

function Repair-OpenSslRuntime {
    param(
        [string]$Destination,
        [string]$PythonRuntimeDestination = ""
    )

    if (-not $Destination -or -not (Test-Path -LiteralPath $Destination)) {
        return
    }
    $binDir = Join-Path $Destination "bin"
    $opensslExe = Join-Path $binDir "openssl.exe"
    if (-not (Test-Path -LiteralPath $opensslExe)) {
        $flatExe = Join-Path $Destination "openssl.exe"
        if (Test-Path -LiteralPath $flatExe) {
            New-Item -ItemType Directory -Force -Path $binDir | Out-Null
            Copy-Item -LiteralPath $flatExe -Destination $opensslExe -Force
        }
    }
    if (Test-Path -LiteralPath $binDir) {
        Get-ChildItem -LiteralPath $Destination -Recurse -File -Force -Filter "*.dll" | ForEach-Object {
            if (-not (Test-Path -LiteralPath (Join-Path $binDir $_.Name))) {
                Copy-Item -LiteralPath $_.FullName -Destination $binDir -Force
            }
        }
        Get-ChildItem -LiteralPath $Destination -File -Force | Where-Object {
            $_.Name -match '^(libcrypto|libssl|vcruntime|ucrtbase).*\.dll$'
        } | ForEach-Object {
            Copy-Item -LiteralPath $_.FullName -Destination $binDir -Force
        }
        if ($PythonRuntimeDestination -and (Test-Path -LiteralPath $PythonRuntimeDestination)) {
            Get-ChildItem -LiteralPath $PythonRuntimeDestination -File -Force | Where-Object {
                $_.Name -match '^(vcruntime|ucrtbase|msvcp).*\.dll$'
            } | ForEach-Object {
                if (-not (Test-Path -LiteralPath (Join-Path $binDir $_.Name))) {
                    Copy-Item -LiteralPath $_.FullName -Destination $binDir -Force
                }
            }
        }
        $systemDllCandidates = @(
            "vcruntime140.dll",
            "vcruntime140_1.dll",
            "msvcp140.dll",
            "msvcp140_1.dll",
            "msvcp140_2.dll",
            "concrt140.dll",
            "ucrtbase.dll"
        )
        foreach ($dllName in $systemDllCandidates) {
            $target = Join-Path $binDir $dllName
            if (Test-Path -LiteralPath $target) {
                continue
            }
            $source = Join-Path $env:WINDIR "System32\$dllName"
            if (Test-Path -LiteralPath $source) {
                Copy-Item -LiteralPath $source -Destination $target -Force
            }
        }
    }
}

function Copy-OpenSslRuntime {
    param(
        [string]$Source,
        [string]$Destination,
        [string]$PythonRuntimeDestination = ""
    )

    if (-not $Source -or -not (Test-Path -LiteralPath $Source)) {
        throw "OpenSSL runtime source not found. Provide -OpenSslRuntime or install OpenSSL locally before building."
    }

    $sourceBin = Join-Path $Source "bin"
    $opensslExe = Join-Path $sourceBin "openssl.exe"
    if (-not (Test-Path -LiteralPath $opensslExe)) {
        $opensslExe = Join-Path $Source "openssl.exe"
        $sourceBin = Split-Path -Parent $opensslExe
    }
    if (-not (Test-Path -LiteralPath $opensslExe)) {
        throw "OpenSSL executable not found in $Source"
    }

    $destBin = Join-Path $Destination "bin"
    New-Item -ItemType Directory -Force -Path $destBin | Out-Null
    Copy-Item -LiteralPath $opensslExe -Destination (Join-Path $destBin "openssl.exe") -Force

    Get-ChildItem -LiteralPath $sourceBin -File -Force | Where-Object {
        $_.Name -match '^(libcrypto|libssl|legacy|p_).*\.dll$'
    } | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination $destBin -Force
    }
    Get-ChildItem -LiteralPath $Source -File -Force | Where-Object {
        $_.Name -match '^(libcrypto|libssl).*\.dll$'
    } | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination $destBin -Force
    }

    $sourceModules = Get-OpenSslModulesDir -Destination $Source
    if ($sourceModules) {
        Copy-Directory -Source $sourceModules -Destination (Join-Path $Destination "lib\ossl-modules")
    }

    if ($PythonRuntimeDestination -and (Test-Path -LiteralPath $PythonRuntimeDestination)) {
        Get-ChildItem -LiteralPath $PythonRuntimeDestination -File -Force | Where-Object {
            $_.Name -match '^(vcruntime|msvcp|concrt).*\.dll$'
        } | ForEach-Object {
            if (-not (Test-Path -LiteralPath (Join-Path $destBin $_.Name))) {
                Copy-Item -LiteralPath $_.FullName -Destination $destBin -Force
            }
        }
    }

    foreach ($dllName in @("vcruntime140.dll", "vcruntime140_1.dll", "msvcp140.dll", "msvcp140_1.dll", "msvcp140_2.dll", "concrt140.dll")) {
        $target = Join-Path $destBin $dllName
        if (Test-Path -LiteralPath $target) {
            continue
        }
        $sourceDll = Join-Path $env:WINDIR "System32\$dllName"
        if (Test-Path -LiteralPath $sourceDll) {
            Copy-Item -LiteralPath $sourceDll -Destination $target -Force
        }
    }

    Write-Host "[ok] Bundled OpenSSL -> $Destination"
    return $true
}

function Get-OpenSslModulesDir {
    param([string]$Destination)

    $candidates = @(
        (Join-Path $Destination "lib\ossl-modules"),
        (Join-Path $Destination "bin\ossl-modules"),
        (Join-Path $Destination "ossl-modules")
    )
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) {
            return $candidate
        }
    }
    return ""
}

function Test-OpenSslRuntime {
    param([string]$Destination)

    $opensslExe = Join-Path $Destination "bin\openssl.exe"
    if (-not (Test-Path -LiteralPath $opensslExe)) {
        throw "OpenSSL runtime did not contain bin\openssl.exe: $Destination"
    }

    $binDir = Split-Path -Parent $opensslExe
    $modulesDir = Get-OpenSslModulesDir -Destination $Destination
    $previousPath = $env:PATH
    $previousModules = $env:OPENSSL_MODULES
    try {
        $env:PATH = "$binDir;$Destination;$previousPath"
        if ($modulesDir) {
            $env:OPENSSL_MODULES = $modulesDir
        }
        $output = & $opensslExe version 2>&1
        if ($LASTEXITCODE -ne 0) {
            throw "OpenSSL runtime check failed with exit code $LASTEXITCODE`: $output"
        }
        Write-Host "[ok] OpenSSL runtime check -> $output"
    } finally {
        $env:PATH = $previousPath
        $env:OPENSSL_MODULES = $previousModules
    }
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
$nativeRaytracerManifest = Join-Path $networkRoot "workloads\raytracer\native\Cargo.toml"
$nativeRaytracerTarget = Join-Path $appRoot "src-tauri\target\raytracer-native"

if (-not (Test-Path -LiteralPath (Join-Path $networkRoot "silicium"))) {
    throw "Network runtime not found: $networkRoot"
}
if (-not (Test-Path -LiteralPath $nativeRaytracerManifest)) {
    throw "Native raytracer manifest not found: $nativeRaytracerManifest"
}

$previousCargoTarget = $env:CARGO_TARGET_DIR
try {
    $env:CARGO_TARGET_DIR = $nativeRaytracerTarget
    & cargo build --release --manifest-path $nativeRaytracerManifest
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to build native raytracer."
    }
} finally {
    $env:CARGO_TARGET_DIR = $previousCargoTarget
}

if (Test-Path -LiteralPath $runtimeRoot) {
    Remove-Item -LiteralPath $runtimeRoot -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $runtimeNetwork | Out-Null

Copy-Item -LiteralPath (Join-Path $networkRoot "silicium") -Destination (Join-Path $runtimeNetwork "silicium") -Force
Copy-Directory -Source (Join-Path $networkRoot "tools") -Destination (Join-Path $runtimeNetwork "tools")
$null = Copy-OptionalDirectory -Source (Join-Path $networkRoot "workloads") -Destination (Join-Path $runtimeNetwork "workloads") -Label "optional workloads"
$null = Copy-OptionalDirectory -Source (Join-Path $networkRoot "bin") -Destination (Join-Path $runtimeNetwork "bin") -Label "optional workload binaries"
$copiedNativeTarget = Join-Path $runtimeNetwork "workloads\raytracer\native\target"
if (Test-Path -LiteralPath $copiedNativeTarget) {
    Remove-Item -LiteralPath $copiedNativeTarget -Recurse -Force
}
$raytracerDirectory = Join-Path $runtimeNetwork "bin\raytracer"
New-Item -ItemType Directory -Force -Path $raytracerDirectory | Out-Null
$raytracerPath = Join-Path $raytracerDirectory "silicium-raytracer.exe"
Copy-Item -LiteralPath (Join-Path $nativeRaytracerTarget "release\silicium-raytracer.exe") -Destination $raytracerPath -Force
if (-not (Test-Path -LiteralPath $raytracerPath)) {
    throw "Bundled native raytracer runtime missing: $raytracerPath"
}

$networkedSource = Join-Path $networkRoot "networked"
if (-not (Test-Path -LiteralPath $networkedSource -PathType Container)) {
    $networkedSource = Join-Path $networkRoot "demo\networked"
}
if (Test-Path -LiteralPath $networkedSource -PathType Container) {
    $networkedDestination = Join-Path $runtimeNetwork "networked"
    New-Item -ItemType Directory -Force -Path $networkedDestination | Out-Null
    foreach ($runtimeFile in @("__init__.py", "networked_runtime.py")) {
        $sourceFile = Join-Path $networkedSource $runtimeFile
        if (-not (Test-Path -LiteralPath $sourceFile -PathType Leaf)) {
            throw "Missing networked runtime file: $sourceFile"
        }
        Copy-Item -LiteralPath $sourceFile -Destination (Join-Path $networkedDestination $runtimeFile) -Force
    }
    Write-Host "[ok] Bundled minimal networked runtime -> $networkedDestination"
}

$envDir = Join-Path $runtimeRoot ".silicium\env"
New-Item -ItemType Directory -Force -Path $envDir | Out-Null
@(
    "SILICIUM_RAYTRACER_BIN=Network\bin\raytracer\silicium-raytracer.exe",
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
if (-not $pythonSource) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCommand) {
        $pythonSource = Split-Path -Parent $pythonCommand.Source
    }
}
$pythonDestination = Join-Path $runtimeRoot "tools\python"
$null = Copy-PythonRuntime -Source $pythonSource -Destination $pythonDestination

$p2pRequirements = Join-Path $networkRoot "requirements-p2p.txt"
$p2pSitePackages = Join-Path $pythonDestination "Lib\site-packages"
if (Test-Path -LiteralPath $p2pRequirements -PathType Leaf) {
    New-Item -ItemType Directory -Force -Path $p2pSitePackages | Out-Null
    $pythonInstaller = Join-Path $pythonSource "python.exe"
    if (-not (Test-Path -LiteralPath $pythonInstaller)) {
        throw "Python executable is required to bundle automatic ICE dependencies."
    }
    Write-Host "Installing automatic P2P dependencies into bundled runtime"
    & $pythonInstaller -m pip install --disable-pip-version-check --upgrade --target $p2pSitePackages -r $p2pRequirements
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to bundle automatic P2P dependencies."
    }
}

Write-Host "Runtime prepared: $runtimeRoot"
