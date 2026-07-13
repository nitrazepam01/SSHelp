#Requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [Alias("Host")]
    [string]$SshHost,

    [Parameter(Mandatory = $true)]
    [string[]]$JobId,

    [int]$BaseTerminalPort = 7681,
    [int]$DashboardPort = 7679,
    [string]$SshConfig = $env:SSHELP_SSH_CONFIG,
    [string]$KnownHosts = $env:SSHELP_KNOWN_HOSTS,
    [string]$IdentityFile = $env:SSHELP_IDENTITY_FILE
)

$ErrorActionPreference = "Stop"

if (-not $JobId -or $JobId.Count -eq 0) {
    throw "At least one job id is required."
}
if (($JobId | Select-Object -Unique).Count -ne $JobId.Count) {
    throw "Job ids must be unique."
}
foreach ($id in $JobId) {
    if ($id -notmatch '^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$') {
        throw "Invalid job id: $id"
    }
}

$lastTerminalPort = $BaseTerminalPort + $JobId.Count - 1
if ($BaseTerminalPort -lt 1024 -or $lastTerminalPort -gt 65535) {
    throw "The assigned terminal port range must stay between 1024 and 65535."
}
if ($DashboardPort -lt 1024 -or $DashboardPort -gt 65535) {
    throw "Dashboard port must be between 1024 and 65535."
}
if ($DashboardPort -ge $BaseTerminalPort -and $DashboardPort -le $lastTerminalPort) {
    throw "Dashboard port must not overlap terminal ports."
}
if (-not $SshConfig) {
    $SshConfig = $env:SSH_RESEARCH_CONFIG
}
if (-not $SshConfig) {
    $SshConfig = Join-Path $env:USERPROFILE ".ssh\config"
}
if (-not $KnownHosts) {
    $KnownHosts = $env:SSH_RESEARCH_KNOWN_HOSTS
}
if (-not $KnownHosts) {
    $KnownHosts = Join-Path $env:USERPROFILE ".ssh\known_hosts"
}
if (-not $IdentityFile) { $IdentityFile = $env:SSH_RESEARCH_IDENTITY_FILE }

$scriptsRoot = Split-Path $PSScriptRoot -Parent
$skillRoot = Split-Path $scriptsRoot -Parent
$workRoot = $env:SSHELP_WORK_ROOT
if (-not $workRoot) { $workRoot = Join-Path (Get-Location) ".sshelp" }
$runtimeDir = Join-Path ([IO.Path]::GetFullPath($workRoot)) "runtime"
New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null
$openJobWeb = Join-Path $PSScriptRoot "Open-JobWeb.ps1"
$closeJobWeb = Join-Path $PSScriptRoot "Close-JobWeb.ps1"
$terminals = @()

for ($index = 0; $index -lt $JobId.Count; $index++) {
    $id = $JobId[$index]
    $port = $BaseTerminalPort + $index
    $webStatePath = Join-Path $runtimeDir ("web-{0}.json" -f $id)
    $reuse = $false

    if (Test-Path -LiteralPath $webStatePath) {
        $webState = Get-Content -Raw -LiteralPath $webStatePath | ConvertFrom-Json
        $process = Get-Process -Id $webState.pid -ErrorAction SilentlyContinue
        $expectedUrl = "http://127.0.0.1:$port"
        $probe = Test-NetConnection -ComputerName 127.0.0.1 -Port $port -WarningAction SilentlyContinue
        if ($process -and $process.ProcessName -in @("ssh", "ssh.exe") -and $probe.TcpTestSucceeded -and $webState.browser_url -eq $expectedUrl) {
            $reuse = $true
        } else {
            & $closeJobWeb -JobId $id
        }
    }

    if (-not $reuse) {
        $existing = Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort $port -State Listen -ErrorAction SilentlyContinue
        if ($existing) {
            throw "Local terminal port $port is already used by an unrelated process."
        }
        $arguments = @{
            SshHost = $SshHost
            JobId = $id
            LocalPort = $port
            RemotePort = $port
            SshConfig = $SshConfig
            KnownHosts = $KnownHosts
            NoBrowser = $true
        }
        if ($IdentityFile) {
            $arguments.IdentityFile = $IdentityFile
        }
        & $openJobWeb @arguments | Out-Null
    }

    $terminals += [ordered]@{
        job_id = $id
        local_port = $port
        remote_port = $port
        url = "http://127.0.0.1:$port"
    }
}

$dashboardRuntimePath = Join-Path $runtimeDir ("dashboard-{0}.json" -f $DashboardPort)
if (Test-Path -LiteralPath $dashboardRuntimePath) {
    throw "Dashboard state already exists for port $DashboardPort. Close it before starting another dashboard."
}
$dashboardListener = Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort $DashboardPort -State Listen -ErrorAction SilentlyContinue
if ($dashboardListener) {
    throw "Dashboard port $DashboardPort is already in use."
}

$dashboardDir = Join-Path $runtimeDir ("dashboard-{0}" -f $DashboardPort)
New-Item -ItemType Directory -Force -Path $dashboardDir | Out-Null
$htmlPath = Join-Path $dashboardDir "index.html"
$templatePath = Join-Path $skillRoot "assets\dashboard.html"
$template = Get-Content -Raw -LiteralPath $templatePath
$config = [ordered]@{
    host = $SshHost
    created_at = [DateTimeOffset]::Now.ToString("o")
    terminals = $terminals
}
$configJson = ($config | ConvertTo-Json -Depth 5 -Compress).Replace('</', '<\/')
$html = $template.Replace('__DASHBOARD_CONFIG__', $configJson)
Set-Content -LiteralPath $htmlPath -Value $html -Encoding UTF8

$python = Get-Command python -ErrorAction Stop
$serverArguments = @(
    "-m", "http.server", $DashboardPort,
    "--bind", "127.0.0.1",
    "--directory", $dashboardDir
)
$server = Start-Process -FilePath $python.Source -ArgumentList $serverArguments -WindowStyle Hidden -PassThru
$dashboardUrl = "http://127.0.0.1:$DashboardPort/"

@{
    dashboard_port = $DashboardPort
    dashboard_url = $dashboardUrl
    pid = $server.Id
    process_name = $server.ProcessName
    directory = $dashboardDir
    html_path = $htmlPath
    jobs = $JobId
    terminal_ports = @($terminals | ForEach-Object { $_.local_port })
} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $dashboardRuntimePath -Encoding UTF8

$ready = $false
for ($attempt = 0; $attempt -lt 40; $attempt++) {
    if ($server.HasExited) {
        throw "The local dashboard server exited before becoming ready."
    }
    $probe = Test-NetConnection -ComputerName 127.0.0.1 -Port $DashboardPort -WarningAction SilentlyContinue
    if ($probe.TcpTestSucceeded) {
        $ready = $true
        break
    }
    Start-Sleep -Milliseconds 250
}
if (-not $ready) {
    Stop-Process -Id $server.Id -ErrorAction SilentlyContinue
    throw "Timed out waiting for the local dashboard server."
}

Write-Output $dashboardUrl
