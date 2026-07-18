param(
    [switch]$InstallSystemDeps,
    [switch]$SkipNpmInstall,
    [switch]$SkipSolanaCheck,
    [switch]$SkipDockerCheck,
    [string]$RaytracerBin = $env:SILICIUM_RAYTRACER_BIN,
    [string]$RaytracerAssetsDir = $env:SILICIUM_RAYTRACER_ASSETS_DIR
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path

function Ensure-Submodules {
    $gitmodules = Join-Path $Root ".gitmodules"
    $requiredPaths = @(
        (Join-Path $Root "Network"),
        (Join-Path $Root "BackEnd"),
        (Join-Path $Root "FrontEnd")
    )

    if (-not (Test-Path -LiteralPath $gitmodules -PathType Leaf)) {
        return
    }

    $missing = @()
    foreach ($path in $requiredPaths) {
        if (-not (Test-Path -LiteralPath $path -PathType Container)) {
            $missing += $path
        }
    }

    if ($missing.Count -eq 0) {
        return
    }

    if (-not (Test-Command "git")) {
        throw "git is required to initialize Fusion submodules. Run git submodule update --init --recursive manually."
    }

    Write-Step "Initializing Git submodules"
    Push-Location $Root
    try {
        git submodule update --init --recursive
    } finally {
        Pop-Location
    }
}

function Write-Step($Message) {
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Test-Command($Name) {
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Find-OpenSsl {
    $cmd = Get-Command "openssl" -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }
    $candidates = @(
        "$env:ProgramFiles\OpenSSL-Win64\bin\openssl.exe",
        "$env:ProgramFiles\OpenSSL-Win32\bin\openssl.exe",
        "${env:ProgramFiles(x86)}\OpenSSL-Win32\bin\openssl.exe",
        "$env:ProgramFiles\Git\usr\bin\openssl.exe",
        "${env:ProgramFiles(x86)}\Git\usr\bin\openssl.exe"
    )
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path $candidate)) {
            $dir = Split-Path -Parent $candidate
            if (($env:PATH -split ';') -notcontains $dir) {
                $env:PATH = "$dir;$env:PATH"
            }
            return $candidate
        }
    }
    return $null
}

function Install-WingetPackage($Id, $Name) {
    if (-not (Test-Command "winget")) {
        Write-Warning "winget is not available. Install $Name manually."
        return
    }
    Write-Host "Installing $Name ($Id) with winget..."
    winget install --id $Id --exact --accept-source-agreements --accept-package-agreements
}

function Ensure-Tool($Command, $WingetId, $DisplayName, [switch]$Optional) {
    if (Test-Command $Command) {
        $path = (Get-Command $Command).Source
        Write-Host "[ok] $DisplayName -> $path"
        return $true
    }

    if ($InstallSystemDeps -and $WingetId) {
        Install-WingetPackage $WingetId $DisplayName
        if (Test-Command $Command) {
            Write-Host "[ok] $DisplayName installed"
            return $true
        }
        Write-Warning "$DisplayName may require a new terminal before it is visible in PATH."
        return $false
    }

    if ($Optional) {
        Write-Warning "[optional missing] $DisplayName"
    } else {
        Write-Warning "[missing] $DisplayName. Re-run with -InstallSystemDeps or install it manually."
    }
    return $false
}

function Invoke-NpmInstall($Path, $Name) {
    if ($SkipNpmInstall) {
        Write-Host "[skip] npm install for $Name"
        return
    }
    if (-not (Test-Path $Path)) {
        Write-Warning "$Name directory not found: $Path"
        return
    }
    if (-not (Test-Command "npm.cmd")) {
        Write-Warning "npm.cmd not found; cannot install $Name dependencies."
        return
    }
    Write-Step "Installing $Name npm dependencies"
    Push-Location $Path
    try {
        npm.cmd install
    } finally {
        Pop-Location
    }
}

function Install-P2PDependencies {
    $requirements = Join-Path $Root "Network\requirements-p2p.txt"
    if (-not (Test-Path -LiteralPath $requirements -PathType Leaf)) {
        Write-Warning "P2P requirements file not found: $requirements"
        return
    }
    if (-not (Test-Command "py")) {
        Write-Warning "Python launcher not found; automatic ICE support cannot be installed."
        return
    }
    Write-Step "Installing automatic P2P transport"
    py -m pip install --disable-pip-version-check --upgrade -r $requirements
}

function Find-RaytracerBinary {
    param([string]$ExplicitPath)

    $candidates = @()
    if ($ExplicitPath) {
        $candidates += $ExplicitPath
    }
    if ($env:SILICIUM_RAYTRACER_BIN) {
        $candidates += $env:SILICIUM_RAYTRACER_BIN
    }
    $candidates += @(
        (Join-Path $Root "Network\bin\raytracer\raytracer.exe"),
        (Join-Path $Root "Network\bin\raytracer\raytracer"),
        (Join-Path $Root "raytracer.exe"),
        (Join-Path $Root "raytracer")
    )

    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }

    $cmd = Get-Command "raytracer.exe" -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }
    $cmd = Get-Command "raytracer" -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }
    return ""
}

function Write-RaytracerEnv {
    param([string]$BinaryPath, [string]$AssetsPath)

    $envDir = Join-Path $Root ".silicium\env"
    New-Item -ItemType Directory -Force -Path $envDir | Out-Null
    $envFile = Join-Path $envDir "raytracer.env"
    $lines = @("SILICIUM_RAYTRACER_BIN=$BinaryPath")
    if ($AssetsPath -and (Test-Path -LiteralPath $AssetsPath -PathType Container)) {
        $lines += "SILICIUM_RAYTRACER_ASSETS_DIR=$((Resolve-Path -LiteralPath $AssetsPath).Path)"
    }
    Set-Content -LiteralPath $envFile -Value $lines -Encoding ASCII
    Write-Host "[ok] Raytracer runtime config -> $envFile"
}

function Install-RaytracerRuntime {
    param([string]$BinaryPath)

    $resolvedBinary = (Resolve-Path -LiteralPath $BinaryPath).Path
    $runtimeDir = Join-Path $Root ".silicium\bin\raytracer"
    New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null

    $installedBinary = Join-Path $runtimeDir (Split-Path -Leaf $resolvedBinary)
    if ($resolvedBinary -ne (Join-Path $runtimeDir (Split-Path -Leaf $resolvedBinary))) {
        Copy-Item -LiteralPath $resolvedBinary -Destination $installedBinary -Force
    }

    $sourceDir = Split-Path -Parent $resolvedBinary
    Get-ChildItem -LiteralPath $sourceDir -Filter "*.dll" -File -ErrorAction SilentlyContinue |
        ForEach-Object {
            $targetDll = Join-Path $runtimeDir $_.Name
            if ($_.FullName -ne $targetDll) {
                Copy-Item -LiteralPath $_.FullName -Destination $targetDll -Force
            }
        }

    $msysUcrtBin = "C:\msys64\ucrt64\bin"
    if (Test-Path -LiteralPath $msysUcrtBin -PathType Container) {
        $runtimeDlls = @(
            "libgcc_s_seh-1.dll",
            "libwinpthread-1.dll",
            "libstdc++-6.dll",
            "libsfml-system-3.dll",
            "libsfml-window-3.dll",
            "libsfml-graphics-3.dll",
            "libfreetype-6.dll",
            "libbz2-1.dll",
            "libbrotlidec.dll",
            "libbrotlicommon.dll",
            "zlib1.dll",
            "libpng16-16.dll",
            "libharfbuzz-0.dll",
            "libgraphite2.dll",
            "libglib-2.0-0.dll",
            "libintl-8.dll",
            "libiconv-2.dll",
            "libpcre2-8-0.dll"
        )
        foreach ($dll in $runtimeDlls) {
            $dllPath = Join-Path $msysUcrtBin $dll
            if (Test-Path -LiteralPath $dllPath -PathType Leaf) {
                Copy-Item -LiteralPath $dllPath -Destination (Join-Path $runtimeDir $dll) -Force
            }
        }
    }

    $assetsSource = ""
    if ($RaytracerAssetsDir -and (Test-Path -LiteralPath $RaytracerAssetsDir -PathType Container)) {
        $assetsSource = (Resolve-Path -LiteralPath $RaytracerAssetsDir).Path
    } elseif (Test-Path -LiteralPath (Join-Path $sourceDir "assets") -PathType Container) {
        $assetsSource = Join-Path $sourceDir "assets"
    }
    if ($assetsSource) {
        $assetsTarget = Join-Path $runtimeDir "assets"
        $resolvedAssetsSource = (Resolve-Path -LiteralPath $assetsSource).Path
        if ((Test-Path -LiteralPath $assetsTarget) -and ((Resolve-Path -LiteralPath $assetsTarget).Path -ne $resolvedAssetsSource)) {
            Remove-Item -LiteralPath $assetsTarget -Recurse -Force
        }
        if (-not (Test-Path -LiteralPath $assetsTarget)) {
            Copy-Item -LiteralPath $resolvedAssetsSource -Destination $assetsTarget -Recurse -Force
        }
    }

    return (Resolve-Path -LiteralPath $installedBinary).Path
}

function Show-Version($Command, [string[]]$VersionArgs = @("--version")) {
    if (Test-Command $Command) {
        try {
            & $Command @VersionArgs
        } catch {
            Write-Warning "Could not read version for ${Command}: $($_.Exception.Message)"
        }
    }
}

Write-Step "Checking system tools"
Ensure-Tool "git" "Git.Git" "Git" | Out-Null
Ensure-Tool "node" "OpenJS.NodeJS.LTS" "Node.js LTS" | Out-Null
Ensure-Tool "npm.cmd" "OpenJS.NodeJS.LTS" "npm" | Out-Null
Ensure-Tool "py" "Python.Python.3.10" "Python launcher" | Out-Null
$opensslPath = Find-OpenSsl
if ($opensslPath) {
    Write-Host "[ok] OpenSSL -> $opensslPath"
} else {
    Ensure-Tool "openssl" "ShiningLight.OpenSSL.Light" "OpenSSL" | Out-Null
}
Ensure-Tool "go" "GoLang.Go" "Go" | Out-Null
Ensure-Tool "rustup" "Rustlang.Rustup" "Rustup/Rust" -Optional | Out-Null
Ensure-Tool "cargo" "" "Cargo" -Optional | Out-Null

Ensure-Submodules

if (-not $SkipDockerCheck) {
    Ensure-Tool "docker" "Docker.DockerDesktop" "Docker Desktop" -Optional | Out-Null
}

if (-not $SkipSolanaCheck) {
    if (Test-Command "solana") {
        Write-Host "[ok] Solana CLI -> $((Get-Command solana).Source)"
    } else {
        Write-Warning "[missing] Solana CLI. Install it from the official Solana/Agave docs before deploying or tracing on Devnet from a fresh machine."
        Write-Warning "The existing demo can still use already-installed local tooling if this machine has it in another shell."
    }
}

Write-Step "Tool versions"
Show-Version "git"
Show-Version "node"
Show-Version "npm.cmd" @("--version")
Show-Version "py" @("--version")
Show-Version "openssl" @("version")
Show-Version "go" @("version")
Show-Version "solana" @("--version")

Write-Step "Installing JavaScript dependencies"
Install-P2PDependencies
Invoke-NpmInstall (Join-Path $Root "Network\silicium-layer-dashboard") "Network Devnet dashboard"
Invoke-NpmInstall (Join-Path $Root "Network\solana-layer") "Solana layer scripts"
Invoke-NpmInstall (Join-Path $Root "FrontEnd") "FrontEnd"
Invoke-NpmInstall (Join-Path $Root "apps\silicium-node") "Silicium Node desktop app"

Write-Step "Configuring raytracer workload runtime"
$detectedRaytracerBin = Find-RaytracerBinary $RaytracerBin
if ($detectedRaytracerBin) {
    Write-Host "[ok] Raytracer executable -> $detectedRaytracerBin"
    $installedRaytracerBin = Install-RaytracerRuntime $detectedRaytracerBin
    Write-Host "[ok] Raytracer installed runtime -> $installedRaytracerBin"
    Write-RaytracerEnv $installedRaytracerBin (Join-Path (Split-Path -Parent $installedRaytracerBin) "assets")
} else {
    Write-Warning "Raytracer executable not found. Raytracer jobs need a packaged binary."
    Write-Warning "Expected default path: Network\bin\raytracer\raytracer.exe"
    Write-Warning "Or run once: .\install-silicium-windows.cmd -RaytracerBin C:\path\to\raytracer.exe"
}

Write-Step "Checking Python files"
if (Test-Command "py") {
    Push-Location $Root
    try {
        py -m py_compile `
            Network\tools\network_node.py `
            Network\tools\mcp_server.py `
            Network\demo\networked\networked_runtime.py `
            Network\workloads\common.py `
            Network\workloads\raytracer\run_network_job.py `
            Network\workloads\raytracer\raytracer_workload.py
    } finally {
        Pop-Location
    }
}

Write-Step "Next steps"
Write-Host "1. If tools were installed during this run, close and reopen PowerShell so PATH is refreshed."
Write-Host ""
Write-Host "2. Start the full local stack from the repository root:"
Write-Host "   .\start-silicium-local.cmd -Visible"
Write-Host ""
Write-Host "3. Open the site:"
Write-Host "   http://localhost:3000/"
Write-Host ""
Write-Host "Useful checks:"
Write-Host "   .\start-silicium-local.cmd -DryRun"
Write-Host "   .\start-silicium-local.cmd -SkipBackend"
Write-Host ""
Write-Host "Install script completed."
