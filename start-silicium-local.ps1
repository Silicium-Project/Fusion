param(
    [switch]$Visible,
    [switch]$NoBrowser,
    [switch]$DryRun,
    [switch]$SkipNetworkNodes,
    [switch]$SkipDatabase,
    [switch]$SkipBackend,
    [switch]$SkipFrontend,
    [int]$OrchestratorPort = 46100,
    [int]$OrchestratorP2pPort = 46101,
    [int]$WorkerPort = 9092,
    [int]$ComputePort = 9090,
    [int]$DatabasePort = 15432,
    [int]$BackendPort = 8080,
    [int]$FrontendPort = 3000,
    [string]$ControlToken = "silicium-local-control-token",
    [ValidateSet("sqlite", "postgres")]
    [string]$DatabaseDriver = $env:DATABASE_DRIVER,
    [string]$DatabaseUrl = $env:DATABASE_URL,
    [string]$SqlitePath = "",
    [string]$JwtSecret = $env:JWT_SECRET_KEY,
    [string]$RaytracerBin = $env:SILICIUM_RAYTRACER_BIN
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path



$NetworkRoot = Join-Path $Root "network"
$BackendRoot = Join-Path $Root "apps/api"
$FrontendRoot = Join-Path $Root "apps/web"
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

Assert-Directory $NetworkRoot "network"
Assert-Directory $BackendRoot "apps/api"
Assert-Directory $FrontendRoot "apps/web"

New-Item -ItemType Directory -Force -Path $LogRoot | Out-Null

Write-Host "Silicium local stack"
Write-Host "Root:      $Root"
Write-Host "Logs:      $LogRoot"
Write-Host "Frontend:  http://localhost:$FrontendPort/"
Write-Host "Backend:   http://localhost:$BackendPort"
Write-Host "Database:  $DatabaseDriver"

$npm = Get-Tool "npm.cmd"
if (-not $npm -and -not $SkipFrontend) {
    throw "npm.cmd was not found. Run .\install-silicium-windows.cmd -InstallSystemDeps first."
}

# Local Rust network: an orchestrator (API on $OrchestratorPort, libp2p on
# $OrchestratorP2pPort, does not compute) and one desktop-like worker
# (compute_daemon + p2p_node) that trusts it through the pinned bootstrap
# address /p2p/<orchestrator peer id>, as the desktop app does.
$NodeBin = Join-Path $NetworkRoot "target\release"
$NodeDataRoot = Join-Path $Root ".silicium\local-network"
$OrchestratorDir = Join-Path $NodeDataRoot "orchestrator"
$WorkerDir = Join-Path $NodeDataRoot "worker"
$OrchestratorLog = Join-Path $LogRoot "network-orchestrator.node.log"

function Get-OrchestratorPeerId {
    param([int]$TimeoutSeconds = 30)
    if ($DryRun) {
        return "<orchestrator-peer-id>"
    }
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-Path -LiteralPath $OrchestratorLog -PathType Leaf) {
            $match = Select-String -LiteralPath $OrchestratorLog -Pattern "Local peer id: (\S+)" | Select-Object -First 1
            if ($match) {
                return $match.Matches[0].Groups[1].Value
            }
        }
        Start-Sleep -Milliseconds 500
    }
    throw "The orchestrator did not report its peer id after ${TimeoutSeconds}s. Check $OrchestratorLog."
}

if (-not $SkipNetworkNodes) {
    $nodeBinaries = @("p2p_node.exe", "compute_daemon.exe", "silicium-raytracer.exe")
    $missingBinaries = @($nodeBinaries | Where-Object { -not (Test-Path -LiteralPath (Join-Path $NodeBin $_) -PathType Leaf) })
    if ($missingBinaries.Count -gt 0 -and -not $DryRun) {
        if (-not (Get-Tool "cargo")) {
            throw "Missing $($missingBinaries -join ', ') in $NodeBin and cargo was not found. Install Rust, then rerun."
        }
        Write-Host "Building the Rust node (cargo build --release)..."
        & cargo build --release --locked --manifest-path (Join-Path $NetworkRoot "Cargo.toml") -p p2p_node -p compute_daemon -p silicium-raytracer
        if ($LASTEXITCODE -ne 0) {
            throw "cargo build failed for the Rust node."
        }
    }
    if (-not $RaytracerBin) {
        $RaytracerBin = Join-Path $NodeBin "silicium-raytracer.exe"
    }
    foreach ($dir in @("$OrchestratorDir\work", "$WorkerDir\work")) {
        New-Item -ItemType Directory -Force -Path $dir | Out-Null
    }
    $orchestratorCmd = Write-CmdLauncher `
        -Name "network-orchestrator" `
        -WorkingDirectory $OrchestratorDir `
        -Environment @(
            "set `"SILICIUM_NODE_ID=orchestrator-local`"",
            "set `"SILICIUM_NODE_ROLES=resource,storage`"",
            "set `"SILICIUM_RELEASE_CHANNEL=dev`"",
            "set `"SILICIUM_DATA_DIR=$OrchestratorDir`"",
            "set `"SILICIUM_COMPUTE_ROOT=$OrchestratorDir\work`"",
            "set `"SILICIUM_WORKLOAD_STORAGE_DIR=$OrchestratorDir\work\jobs`"",
            "set `"SILICIUM_EXPORT_DIR=$OrchestratorDir\export`"",
            "set `"SILICIUM_NODE_CONTROL_TOKEN=$ControlToken`"",
            "set `"SILICIUM_API_BIND=127.0.0.1`"",
            "set `"API_PORT=$OrchestratorPort`"",
            "set `"SILICIUM_P2P_BIND=127.0.0.1`"",
            "set `"SILICIUM_P2P_PORT=$OrchestratorP2pPort`"",
            "set `"SILICIUM_WORK_OWN_TASKS=0`""
        ) `
        -Command "`"$NodeBin\p2p_node.exe`" > `"$OrchestratorLog`" 2>&1"
    Start-LoggedProcess -Name "network-orchestrator" -CommandFile $orchestratorCmd -Port $OrchestratorPort
    $orchestratorPeerId = Get-OrchestratorPeerId

    $computeCmd = Write-CmdLauncher `
        -Name "network-compute" `
        -WorkingDirectory $WorkerDir `
        -Environment @(
            "set `"SILICIUM_COMPUTE_BIND=127.0.0.1:$ComputePort`"",
            "set `"SILICIUM_COMPUTE_ROOT=$WorkerDir\work`"",
            "set `"SILICIUM_RAYTRACER_BIN=$RaytracerBin`""
        ) `
        -Command "`"$NodeBin\compute_daemon.exe`""
    $workerCmd = Write-CmdLauncher `
        -Name "network-worker" `
        -WorkingDirectory $WorkerDir `
        -Environment @(
            "set `"SILICIUM_NODE_ID=worker-local`"",
            "set `"SILICIUM_NODE_ROLES=compute,verify`"",
            "set `"SILICIUM_RELEASE_CHANNEL=dev`"",
            "set `"SILICIUM_DATA_DIR=$WorkerDir`"",
            "set `"SILICIUM_COMPUTE_ROOT=$WorkerDir\work`"",
            "set `"SILICIUM_WORKLOAD_STORAGE_DIR=$WorkerDir\work\jobs`"",
            "set `"SILICIUM_EXPORT_DIR=$WorkerDir\export`"",
            "set `"SILICIUM_API_BIND=127.0.0.1`"",
            "set `"API_PORT=$WorkerPort`"",
            "set `"SILICIUM_P2P_BIND=127.0.0.1`"",
            "set `"SILICIUM_P2P_PORT=0`"",
            "set `"SILICIUM_BOOTSTRAP_PEERS=/ip4/127.0.0.1/tcp/$OrchestratorP2pPort/p2p/$orchestratorPeerId`"",
            "set `"SILICIUM_WORK_OWN_TASKS=1`"",
            "set `"COMPUTE_DAEMON_URL=http://127.0.0.1:$ComputePort`""
        ) `
        -Command "`"$NodeBin\p2p_node.exe`""
    Start-LoggedProcess -Name "network-compute" -CommandFile $computeCmd -Port $ComputePort
    Start-LoggedProcess -Name "network-worker" -CommandFile $workerCmd -Port $WorkerPort
    Wait-ListeningPort -Port $OrchestratorPort -Name "network-orchestrator" -TimeoutSeconds 20
    Wait-ListeningPort -Port $WorkerPort -Name "network-worker" -TimeoutSeconds 20
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
                "set `"SILICIUM_NETWORK_ROOT=$NetworkRoot`""
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
    $BackendEnv = @(
        "set `"DATABASE_DRIVER=$DatabaseDriver`"",
        "set `"DATABASE_URL=$DatabaseUrl`"",
        "set `"SQLITE_PATH=$SqlitePath`"",
        "set `"JWT_SECRET_KEY=$JwtSecret`"",
        "set `"SILICIUM_NETWORK_ROOT=$NetworkRoot`"",
        "set `"SILICIUM_NODE_API_URL=http://127.0.0.1:$OrchestratorPort`"",
        "set `"SILICIUM_NODE_CONTROL_TOKEN=$ControlToken`"",
        "set `"SILICIUM_ORCHESTRATOR_NODE_ID=orchestrator-local`"",
        "set `"SILICIUM_ORCHESTRATOR_EXPORT_DIR=$OrchestratorDir\export`"",
        "set `"SILICIUM_WORKLOAD_STORAGE_DIR=$OrchestratorDir\work\jobs`""
    )
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
            "set `"NUXT_PUBLIC_API_BASE=http://localhost:$BackendPort`""
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
Write-Host "Logs:           $LogRoot"
Write-Host ""
Write-Host "Use -Visible to keep each service in an interactive terminal."
Write-Host "Use -DryRun to print launch commands without starting services."
