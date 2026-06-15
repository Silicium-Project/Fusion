param(
    [switch]$InstallSystemDeps,
    [switch]$SkipNpmInstall,
    [switch]$SkipSolanaCheck,
    [switch]$SkipDockerCheck
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path

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
Invoke-NpmInstall (Join-Path $Root "Network\silicium-layer-dashboard") "Network Devnet dashboard"
Invoke-NpmInstall (Join-Path $Root "Network\solana-layer") "Solana layer scripts"
Invoke-NpmInstall (Join-Path $Root "Site\FrontEnd-main") "Site frontend"

Write-Step "Checking Python files"
if (Test-Command "py") {
    Push-Location $Root
    try {
        py -m py_compile `
            Network\tools\network_node.py `
            Network\tools\mcp_server.py `
            Network\demo\render3d\run_auto_split_demo.py `
            Network\demo\networked\networked_runtime.py
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
Write-Host "   http://localhost:3000/dashboard"
Write-Host ""
Write-Host "Useful checks:"
Write-Host "   .\start-silicium-local.cmd -DryRun"
Write-Host "   .\start-silicium-local.cmd -SkipBackend"
Write-Host ""
Write-Host "Install script completed."
