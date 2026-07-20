param(
    [switch]$Visible,
    [switch]$NoBrowser,
    [switch]$DryRun,
    [switch]$SkipNetworkNodes,
    [switch]$SkipDashboard,
    [switch]$SkipDatabase,
    [switch]$SkipBackend,
    [switch]$SkipFrontend,
    [string]$HostAddress = "127.0.0.1",
    [int]$OrchestratorPort = 46100,
    [int]$WorkerPort = 46101,
    [int]$VerifierPort = 46102,
    [int]$DatabasePort = 15432,
    [int]$DashboardPort = 5174,
    [int]$BackendPort = 8080,
    [int]$FrontendPort = 3000,
    [string]$MeshKey = "demo-mesh",
    [string]$WorkerReputation = "120",
    [string]$VerifierReputation = "90",
    [ValidateSet("sqlite", "postgres")]
    [string]$DatabaseDriver = $env:DATABASE_DRIVER,
    [string]$DatabaseUrl = $env:DATABASE_URL,
    [string]$SqlitePath = "",
    [string]$JwtSecret = $env:JWT_SECRET_KEY,
    [string]$RaytracerBin = $env:SILICIUM_RAYTRACER_BIN,
    [string]$MinComputeReputation = "50",
    [string]$MinVerifyReputation = "40"
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

    if (-not (Get-Command "git" -ErrorAction SilentlyContinue)) {
        throw "git is required to initialize Fusion submodules. Run git submodule update --init --recursive manually."
    }

    Push-Location $Root
    try {
        git submodule update --init --recursive
    } finally {
        Pop-Location
    }
}

Ensure-Submodules

$NetworkRoot = Join-Path $Root "Network"
$DashboardRoot = Join-Path $NetworkRoot "silicium-layer-dashboard"
$BackendRoot = Join-Path $Root "BackEnd"
$FrontendRoot = Join-Path $Root "FrontEnd"
$LogRoot = Join-Path $Root ".silicium\logs\local-start"
$DefaultSqlitePath = Join-Path $Root ".silicium\site\silicium.db"
$RaytracerEnvFile = Join-Path $Root ".silicium\env\raytracer.env"

if (-not $DatabaseDriver) {
    if ($DatabaseUrl) {
        $DatabaseDriver = "postgres"
    } else {
        $DatabaseDriver = "sqlite"
    }
}
if (-not $SqlitePath) {
    $SqlitePath = $DefaultSqlitePath
}
if ($DatabaseDriver -eq "postgres" -and -not $DatabaseUrl) {
    $DatabaseUrl = "host=localhost user=postgres password=postgres dbname=silicium port=$DatabasePort sslmode=disable"
}
if (-not $JwtSecret) {
    $JwtSecret = "silicium-local-dev-secret"
}
if (-not $RaytracerBin -and (Test-Path -LiteralPath $RaytracerEnvFile -PathType Leaf)) {
    foreach ($line in Get-Content -LiteralPath $RaytracerEnvFile) {
        if ($line -match '^SILICIUM_RAYTRACER_BIN=(.+)$') {
            $RaytracerBin = $Matches[1].Trim()
        }
    }
}

$RaytracerEnv = @()
if ($RaytracerBin) {
    if (-not (Test-Path -LiteralPath $RaytracerBin -PathType Leaf)) {
        Write-Warning "SILICIUM_RAYTRACER_BIN does not point to an executable file: $RaytracerBin"
    }
    $RaytracerEnv = @("set `"SILICIUM_RAYTRACER_BIN=$RaytracerBin`"")
} else {
    Write-Warning "SILICIUM_RAYTRACER_BIN is not set. Raytracer jobs will fail until each worker points to a local raytracer executable."
}

function Assert-Directory {
    param([string]$Path, [string]$Label)
    if (-not (Test-Path -LiteralPath $Path -PathType Container)) {
        # throw "\$Label directory not found: \$Path"
    }
}

function Get-Tool {
    param([string]$Name)
    return Get-Command $Name -ErrorAction SilentlyContinue
}

function Find-Go {
    $cmd = Get-Command "go.exe" -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }
    $candidates = @(
        "$env:ProgramFiles\Go\bin\go.exe",
        "${env:ProgramFiles(x86)}\Go\bin\go.exe"
    )
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            $dir = Split-Path -Parent $candidate
            if (($env:PATH -split ';') -notcontains $dir) {
                $env:PATH = "$dir;$env:PATH"
            }
            return $candidate
        }
    }
    return $null
}

function Test-ListeningPort {
    param([int]$Port)
    $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    return [bool]$conn
}

function Test-DockerDaemon {
    if (-not (Get-Tool "docker.exe")) {
        return $false
    }
    if ($DryRun) {
        return $true
    }
    $output = & docker.exe info 2>&1
    return ($LASTEXITCODE -eq 0)
}

function Wait-ListeningPort {
    param([int]$Port, [string]$Name, [int]$TimeoutSeconds = 30)
    if ($DryRun) {
        return
    }
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-ListeningPort $Port) {
            Write-Host "OK $Name listens on port $Port"
            return
        }
        Start-Sleep -Milliseconds 500
    }
    Write-Warning "$Name did not listen on port $Port after ${TimeoutSeconds}s. Check logs in $LogRoot."
}

function Write-CmdLauncher {
    param(
        [string]$Name,
        [string]$WorkingDirectory,
        [string[]]$Environment,
        [string]$Command
    )
    $file = Join-Path $LogRoot "$Name.cmd"
    $lines = New-Object System.Collections.Generic.List[string]
    $lines.Add("@echo off")
    $lines.Add("cd /d `"$WorkingDirectory`"")
    foreach ($entry in $Environment) {
        $lines.Add($entry)
    }
    $lines.Add("echo [$Name] %DATE% %TIME%")
    $lines.Add($Command)
    Set-Content -LiteralPath $file -Value $lines -Encoding ASCII
    return $file
}

function Start-LoggedProcess {
    param([string]$Name, [string]$CommandFile, [int]$Port = 0)

    if ($Port -gt 0 -and (Test-ListeningPort $Port)) {
        Write-Host "SKIP ${Name}: port $Port already listens."
        return
    }

    if ($DryRun) {
        Write-Host ""
        Write-Host "[dry-run] $Name"
        Write-Host "cmd.exe /c `"$CommandFile`""
        Get-Content -LiteralPath $CommandFile
        return
    }

    $stdout = Join-Path $LogRoot "$Name.out.log"
    $stderr = Join-Path $LogRoot "$Name.err.log"

    if ($Visible) {
        Start-Process -FilePath "cmd.exe" -ArgumentList "/k", "`"$CommandFile`"" -WorkingDirectory $Root
    } else {
        Start-Process -FilePath "cmd.exe" `
            -ArgumentList "/c", "`"$CommandFile`"" `
            -WorkingDirectory $Root `
            -WindowStyle Hidden `
            -RedirectStandardOutput $stdout `
            -RedirectStandardError $stderr
    }
    Write-Host "START $Name"
}

Assert-Directory $NetworkRoot "Network"
Assert-Directory $DashboardRoot "Devnet dashboard"
Assert-Directory $BackendRoot "BackEnd"
Assert-Directory $FrontendRoot "FrontEnd"

New-Item -ItemType Directory -Force -Path $LogRoot | Out-Null

Write-Host "Silicium local stack"
Write-Host "Root:      $Root"
Write-Host "Logs:      $LogRoot"
Write-Host "Frontend:  http://localhost:$FrontendPort/"
Write-Host "Backend:   http://localhost:$BackendPort"
Write-Host "Devnet UI: http://localhost:$DashboardPort/"
Write-Host "Database:  $DatabaseDriver"

$npm = Get-Tool "npm.cmd"
if (-not $npm -and (-not $SkipDashboard -or -not $SkipFrontend)) {
    throw "npm.cmd was not found. Run .\install-silicium-windows.cmd -InstallSystemDeps first."
}

if (-not $SkipNetworkNodes) {
    $nodeScript = Join-Path $NetworkRoot "networked\start-node.cmd"
    if (-not (Test-Path -LiteralPath $nodeScript -PathType Leaf)) {
        # throw "Network node launcher not found: $nodeScript"
    }
    $workerCmd = Write-CmdLauncher `
        -Name "network-worker" `
        -WorkingDirectory $NetworkRoot `
        -Environment $RaytracerEnv `
        -Command ".\networked\start-node.cmd worker-1 compute $WorkerPort http://${HostAddress}:$OrchestratorPort $HostAddress $MeshKey $WorkerReputation"
    $verifierCmd = Write-CmdLauncher `
        -Name "network-verifier" `
        -WorkingDirectory $NetworkRoot `
        -Environment $RaytracerEnv `
        -Command ".\networked\start-node.cmd verifier-1 verify $VerifierPort http://${HostAddress}:$OrchestratorPort $HostAddress $MeshKey $VerifierReputation"
    Start-LoggedProcess -Name "network-worker" -CommandFile $workerCmd -Port $WorkerPort
    Start-LoggedProcess -Name "network-verifier" -CommandFile $verifierCmd -Port $VerifierPort
    Wait-ListeningPort -Port $WorkerPort -Name "network-worker" -TimeoutSeconds 20
    Wait-ListeningPort -Port $VerifierPort -Name "network-verifier" -TimeoutSeconds 20
}

if (-not $SkipDashboard) {
    $dashboardCmd = Write-CmdLauncher `
        -Name "devnet-dashboard" `
        -WorkingDirectory $DashboardRoot `
        -Environment @() `
        -Command "npm.cmd run dev -- --host 127.0.0.1 --port $DashboardPort"
    Start-LoggedProcess -Name "devnet-dashboard" -CommandFile $dashboardCmd -Port $DashboardPort
    Wait-ListeningPort -Port $DashboardPort -Name "devnet-dashboard" -TimeoutSeconds 30
}

if (-not $SkipBackend -and -not $SkipDatabase -and $DatabaseDriver -eq "postgres") {
    if (Test-ListeningPort $DatabasePort) {
        Write-Host "SKIP database: port $DatabasePort already listens."
    } else {
        if (-not (Get-Tool "docker.exe") -and -not $DryRun) {
            throw "docker.exe was not found and PostgreSQL is not listening on port $DatabasePort. Run Docker Desktop, install Docker, or pass -SkipDatabase with a valid DATABASE_URL."
        } elseif (-not (Get-Tool "docker.exe") -and $DryRun) {
            Write-Warning "docker.exe was not found. Real launch will need Docker Desktop or an existing PostgreSQL on port $DatabasePort."
        } elseif (-not (Test-DockerDaemon)) {
            throw "Docker is installed but the daemon is not running. Start Docker Desktop, wait until it is ready, then rerun .\start-silicium-local.cmd -Visible."
        }
        $databaseCmd = Write-CmdLauncher `
            -Name "site-database" `
            -WorkingDirectory $BackendRoot `
            -Environment @(
                "set `"POSTGRES_DB=silicium`"",
                "set `"POSTGRES_USER=postgres`"",
                "set `"POSTGRES_PASSWORD=postgres`"",
                "set `"POSTGRES_PORT=$DatabasePort`"",
                "set `"HOST=db`"",
                "set `"JWT_SECRET_KEY=$JwtSecret`"",
                "set `"SILICIUM_NETWORK_ROOT=$NetworkRoot`"",
                "set `"SILICIUM_SEED_PEERS=http://${HostAddress}:$WorkerPort,http://${HostAddress}:$VerifierPort`"",
                "set `"SILICIUM_MESH_KEY=$MeshKey`"",
                "set `"SILICIUM_ORCHESTRATOR_HOST=$HostAddress`"",
                "set `"SILICIUM_DASHBOARD_URL=http://localhost:$DashboardPort/`"",
                "set `"SILICIUM_DEVNET_TRACE=1`"",
                "set `"SILICIUM_DEVNET_TX_DELAY_MS=2500`""
            ) `
            -Command "docker compose up -d db"
        Start-LoggedProcess -Name "site-database" -CommandFile $databaseCmd
        Wait-ListeningPort -Port $DatabasePort -Name "site-database" -TimeoutSeconds 60
    }
}

if (-not $SkipBackend) {
    $goPath = Find-Go
    if (-not $goPath -and -not $DryRun) {
        throw "go.exe was not found. Run .\install-silicium-windows.cmd -InstallSystemDeps first, then rerun this launcher."
    } elseif (-not $goPath -and $DryRun) {
        Write-Warning "go.exe was not found. Real launch will need Go installed and available in PATH."
    } elseif ($goPath) {
        Write-Host "OK Go -> $goPath"
    }
    $seedPeers = "http://${HostAddress}:$WorkerPort,http://${HostAddress}:$VerifierPort"
    $BackendEnv = @(
        "set `"DATABASE_DRIVER=$DatabaseDriver`"",
        "set `"DATABASE_URL=$DatabaseUrl`"",
        "set `"SQLITE_PATH=$SqlitePath`"",
        "set `"JWT_SECRET_KEY=$JwtSecret`"",
        "set `"SILICIUM_NETWORK_ROOT=$NetworkRoot`"",
        "set `"SILICIUM_SEED_PEERS=$seedPeers`"",
        "set `"SILICIUM_MESH_KEY=$MeshKey`"",
        "set `"SILICIUM_ORCHESTRATOR_HOST=$HostAddress`"",
        "set `"SILICIUM_DASHBOARD_URL=http://localhost:$DashboardPort/`"",
        "set `"SILICIUM_DEVNET_TRACE=1`"",
        "set `"SILICIUM_DEVNET_TX_DELAY_MS=2500`"",
        "set `"SILICIUM_MIN_COMPUTE_REPUTATION=$MinComputeReputation`"",
        "set `"SILICIUM_MIN_VERIFY_REPUTATION=$MinVerifyReputation`""
    ) + $RaytracerEnv
    $backendCmd = Write-CmdLauncher `
        -Name "site-backend" `
        -WorkingDirectory $BackendRoot `
        -Environment $BackendEnv `
        -Command "go run .\cmd\main.go"
    Start-LoggedProcess -Name "site-backend" -CommandFile $backendCmd -Port $BackendPort
    Wait-ListeningPort -Port $BackendPort -Name "site-backend" -TimeoutSeconds 45
}

if (-not $SkipFrontend) {
    $frontendCmd = Write-CmdLauncher `
        -Name "site-frontend" `
        -WorkingDirectory $FrontendRoot `
        -Environment @(
            "set `"NUXT_PUBLIC_API_BASE=http://localhost:$BackendPort`"",
            "set `"NUXT_PUBLIC_DEVNET_DASHBOARD_URL=http://localhost:$DashboardPort/`""
        ) `
        -Command "npm.cmd run dev -- --host 127.0.0.1 --port $FrontendPort"
    Start-LoggedProcess -Name "site-frontend" -CommandFile $frontendCmd -Port $FrontendPort
    Wait-ListeningPort -Port $FrontendPort -Name "site-frontend" -TimeoutSeconds 45
}

if (-not $NoBrowser -and -not $DryRun) {
    Start-Process "http://localhost:$FrontendPort/"
}

Write-Host ""
Write-Host "Local stack requested."
Write-Host "Open site:      http://localhost:$FrontendPort/"
Write-Host "Open dashboard: http://localhost:$DashboardPort/"
Write-Host "Logs:           $LogRoot"
Write-Host ""
Write-Host "Use -Visible to keep each service in an interactive terminal."
Write-Host "Use -DryRun to print launch commands without starting services."
