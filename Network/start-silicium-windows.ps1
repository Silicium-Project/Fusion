param(
    [switch]$SkipInstall,
    [switch]$InstallSystemDeps,
    [switch]$SkipDashboard,
    [switch]$SkipWorldNode,
    [switch]$SkipDoctor,
    [switch]$RunDoctor,
    [switch]$NoBrowser,
    [string]$NodeId = "windows-1",
    [string]$WorldName = "team-europe",
    [string]$WorldSeeds = "",
    [string]$WorldRoles = "compute,verify,storage,audit,resource",
    [string]$DashboardPort = "5174"
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Write-Warn {
    param([string]$Message)
    Write-Host "[WARN] $Message" -ForegroundColor Yellow
}

function Write-Ok {
    param([string]$Message)
    Write-Host "[OK] $Message" -ForegroundColor Green
}

function Find-Command {
    param([string[]]$Names)
    foreach ($name in $Names) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd) {
            return $cmd.Source
        }
    }
    return $null
}

function Require-Command {
    param(
        [string[]]$Names,
        [string]$InstallHint
    )
    $found = Find-Command $Names
    if (-not $found) {
        throw "Missing command: $($Names -join ', '). $InstallHint"
    }
    return $found
}

function Install-WithWinget {
    param(
        [string]$PackageId,
        [string]$Name
    )
    $winget = Find-Command @("winget")
    if (-not $winget) {
        throw "Cannot install $Name automatically because winget is not available."
    }
    Write-Step "Install $Name with winget"
    Invoke-Checked -FilePath $winget -Arguments @(
        "install",
        "--id", $PackageId,
        "--exact",
        "--accept-package-agreements",
        "--accept-source-agreements"
    ) -WorkingDirectory $script:RepoRoot
}

function Ensure-Command {
    param(
        [string[]]$Names,
        [string]$InstallHint,
        [string]$WingetId,
        [string]$DisplayName
    )
    $found = Find-Command $Names
    if ($found) {
        return $found
    }
    if ($InstallSystemDeps -and $WingetId) {
        Install-WithWinget -PackageId $WingetId -Name $DisplayName
        $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
        $found = Find-Command $Names
        if ($found) {
            return $found
        }
        throw "$DisplayName was installed or requested, but the command is still not available in this shell. Reopen PowerShell and rerun the launcher."
    }
    throw "Missing command: $($Names -join ', '). $InstallHint"
}

function Add-PathDirectory {
    param([string]$Directory)
    if (-not $Directory -or -not (Test-Path $Directory)) {
        return
    }
    $parts = @($env:Path -split ";" | Where-Object { $_ })
    if ($parts -notcontains $Directory) {
        $env:Path = $Directory + ";" + $env:Path
    }
}

function Find-OpenSSL {
    $found = Find-Command @("openssl")
    if ($found) {
        return $found
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
            Add-PathDirectory -Directory (Split-Path -Parent $candidate)
            return $candidate
        }
    }
    return $null
}

function Test-TcpPort {
    param(
        [string]$HostName,
        [int]$Port
    )
    try {
        $client = [System.Net.Sockets.TcpClient]::new()
        $async = $client.BeginConnect($HostName, $Port, $null, $null)
        $ok = $async.AsyncWaitHandle.WaitOne(500)
        if ($ok) {
            $client.EndConnect($async)
        }
        $client.Close()
        return $ok
    } catch {
        return $false
    }
}

function Wait-Port {
    param(
        [string]$HostName,
        [int]$Port,
        [int]$TimeoutSeconds = 30
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-TcpPort -HostName $HostName -Port $Port) {
            return $true
        }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

function Start-DetachedCommand {
    param(
        [string]$WorkingDirectory,
        [string]$Command,
        [string]$LogName
    )

    $logDir = Join-Path $script:NetworkRoot ".silicium\windows-launch"
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null

    $outLog = Join-Path $logDir "$LogName.out.log"
    $errLog = Join-Path $logDir "$LogName.err.log"
    $cmdLine = "/d /s /c `"$Command > `"$outLog`" 2> `"$errLog`"`""

    $psi = [System.Diagnostics.ProcessStartInfo]::new()
    $psi.FileName = "cmd.exe"
    $psi.Arguments = $cmdLine
    $psi.WorkingDirectory = $WorkingDirectory
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true

    # Some Windows shells expose both Path and PATH; ProcessStartInfo rejects that.
    $psi.EnvironmentVariables.Clear()
    foreach ($name in @("SystemRoot", "WINDIR", "COMSPEC", "TEMP", "TMP", "USERPROFILE", "APPDATA", "LOCALAPPDATA")) {
        $value = [Environment]::GetEnvironmentVariable($name)
        if ($value) {
            $psi.EnvironmentVariables[$name] = $value
        }
    }
    $psi.EnvironmentVariables["PATH"] = $env:Path

    $process = [System.Diagnostics.Process]::Start($psi)
    return [pscustomobject]@{
        Process = $process
        OutLog = $outLog
        ErrLog = $errLog
    }
}

function Invoke-Checked {
    param(
        [string]$FilePath,
        [string[]]$Arguments,
        [string]$WorkingDirectory
    )
    Write-Host "> $FilePath $($Arguments -join ' ')" -ForegroundColor DarkGray
    $psi = [System.Diagnostics.ProcessStartInfo]::new()
    $psi.FileName = $FilePath
    $psi.Arguments = ($Arguments | ForEach-Object {
        $arg = [string]$_
        if ($arg -match '[\s"]') {
            '"' + ($arg -replace '"', '\"') + '"'
        } else {
            $arg
        }
    }) -join " "
    $psi.WorkingDirectory = $WorkingDirectory
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $false
    $psi.EnvironmentVariables.Clear()
    foreach ($name in @("SystemRoot", "WINDIR", "COMSPEC", "TEMP", "TMP", "USERPROFILE", "APPDATA", "LOCALAPPDATA")) {
        $value = [Environment]::GetEnvironmentVariable($name)
        if ($value) {
            $psi.EnvironmentVariables[$name] = $value
        }
    }
    $psi.EnvironmentVariables["PATH"] = $env:Path
    $process = [System.Diagnostics.Process]::Start($psi)
    $process.WaitForExit()
    if ($process.ExitCode -ne 0) {
        throw "Command failed with exit code $($process.ExitCode): $FilePath $($Arguments -join ' ')"
    }
}

$script:RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
if (Test-Path (Join-Path $RepoRoot "silicium")) {
    $script:NetworkRoot = $RepoRoot
    $ProjectRoot = Split-Path -Parent $script:NetworkRoot
} else {
    $script:NetworkRoot = Join-Path $RepoRoot "Network"
    $ProjectRoot = $RepoRoot
}
$DashboardRoot = Join-Path $script:NetworkRoot "silicium-layer-dashboard"

if (-not (Test-Path $script:NetworkRoot)) {
    throw "Network directory not found: $script:NetworkRoot"
}

Write-Step "Silicium Windows launcher"
Write-Host "Project: $ProjectRoot"
Write-Host "Network: $script:NetworkRoot"

$python = Ensure-Command -Names @("py", "python") -InstallHint "Install Python 3.11+ from https://www.python.org/downloads/windows/ or rerun with -InstallSystemDeps." -WingetId "Python.Python.3.12" -DisplayName "Python"
$node = Ensure-Command -Names @("node") -InstallHint "Install Node.js LTS from https://nodejs.org/ or rerun with -InstallSystemDeps." -WingetId "OpenJS.NodeJS.LTS" -DisplayName "Node.js LTS"
$npm = Ensure-Command -Names @("npm.cmd", "npm") -InstallHint "Install Node.js LTS, which includes npm, or rerun with -InstallSystemDeps." -WingetId "OpenJS.NodeJS.LTS" -DisplayName "npm"
$openssl = Find-OpenSSL
if (-not $openssl -and $InstallSystemDeps) {
    Install-WithWinget -PackageId "ShiningLight.OpenSSL.Light" -Name "OpenSSL Light"
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
    $openssl = Find-OpenSSL
}
$docker = Find-Command @("docker")
if (-not $docker -and $InstallSystemDeps) {
    Install-WithWinget -PackageId "Docker.DockerDesktop" -Name "Docker Desktop"
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
    $docker = Find-Command @("docker")
}

Write-Ok "Python launcher: $python"
Write-Ok "Node: $node"
Write-Ok "npm: $npm"
if ($openssl) {
    Write-Ok "OpenSSL: $openssl"
} else {
    Write-Warn "OpenSSL not found. Signed P2P node identity will fail; rerun with -InstallSystemDeps or install OpenSSL and reopen PowerShell."
}
if ($docker) {
    Write-Ok "Docker: $docker"
} else {
    Write-Warn "Docker not found. The dashboard can run, but Docker-backed node/compute services will be skipped."
}

if (-not $SkipInstall) {
    Write-Step "Install Python dependencies"
    Invoke-Checked -FilePath $python -Arguments @("-m", "pip", "install", "--upgrade", "pip") -WorkingDirectory $script:NetworkRoot
    Invoke-Checked -FilePath $python -Arguments @("-m", "pip", "install", "-r", "requirements-dev.txt", "-r", "requirements-tui.txt") -WorkingDirectory $script:NetworkRoot

    Write-Step "Install dashboard dependencies"
    if (Find-Command @("yarn.cmd", "yarn")) {
        $yarn = Find-Command @("yarn.cmd", "yarn")
        Invoke-Checked -FilePath $yarn -Arguments @("install", "--frozen-lockfile") -WorkingDirectory $DashboardRoot
    } else {
        Invoke-Checked -FilePath $npm -Arguments @("install", "--no-package-lock") -WorkingDirectory $DashboardRoot
    }
} else {
    Write-Warn "Dependency install skipped by -SkipInstall."
}

if ($RunDoctor -and -not $SkipDoctor) {
    Write-Step "Run Silicium doctor"
    try {
        Invoke-Checked -FilePath $python -Arguments @("silicium", "doctor") -WorkingDirectory $script:NetworkRoot
    } catch {
        Write-Warn $_.Exception.Message
    }
}

if (-not $SkipDashboard) {
    Write-Step "Start dashboard"
    if (Test-TcpPort -HostName "127.0.0.1" -Port ([int]$DashboardPort)) {
        Write-Ok "Dashboard already listening on http://127.0.0.1:$DashboardPort"
    } else {
        $dashboard = Start-DetachedCommand -WorkingDirectory $DashboardRoot -Command "npm.cmd run dev -- --host 0.0.0.0 --port $DashboardPort" -LogName "dashboard"
        if (Wait-Port -HostName "127.0.0.1" -Port ([int]$DashboardPort) -TimeoutSeconds 45) {
            Write-Ok "Dashboard started on http://127.0.0.1:$DashboardPort (pid $($dashboard.Process.Id))"
        } else {
            Write-Warn "Dashboard did not answer on port $DashboardPort. Logs:"
            Write-Host "  $($dashboard.OutLog)"
            Write-Host "  $($dashboard.ErrLog)"
        }
    }
    if (-not $NoBrowser) {
        Start-Process "http://127.0.0.1:$DashboardPort"
    }
}

if (-not $SkipWorldNode) {
    if (-not $docker) {
        Write-Warn "World node skipped because Docker is not installed or not in PATH."
    } else {
        Write-Step "Start Docker world node"
        $worldArgs = @(
            "tools\world_node.py",
            "up",
            "--node-id", $NodeId,
            "--world", $WorldName,
            "--roles", $WorldRoles
        )
        if ($WorldSeeds) {
            $worldArgs += @("--seed", $WorldSeeds)
        }
        try {
            Invoke-Checked -FilePath $python -Arguments $worldArgs -WorkingDirectory $script:NetworkRoot
            Write-Ok "World node requested. Check status with: py tools\world_node.py ps --node-id $NodeId"
        } catch {
            Write-Warn "World node failed to start: $($_.Exception.Message)"
        }
    }
}

Write-Step "Done"
Write-Host "Dashboard: http://127.0.0.1:$DashboardPort"
Write-Host "Logs:      $script:NetworkRoot\.silicium\windows-launch"
Write-Host ""
Write-Host "Useful commands:"
Write-Host "  cd `"$script:NetworkRoot`""
Write-Host "  py silicium doctor"
Write-Host "  .\demo\render3d\run-full-demo.cmd .\demo\render3d\scene.json --task-id render-demo-002 --node-mode cli"
Write-Host "  py tools\world_node.py ps --node-id $NodeId"
Write-Host "  py tools\world_node.py peers --node-id $NodeId"
