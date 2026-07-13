#Requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [Alias("Host")]
    [string]$SshHost,

    [Parameter(Mandatory = $true)]
    [string]$JobId,

    [int]$LocalPort = 7681,
    [int]$RemotePort = 7681,
    [string]$SshConfig = $env:SSHELP_SSH_CONFIG,
    [string]$KnownHosts = $env:SSHELP_KNOWN_HOSTS,
    [string]$IdentityFile = $env:SSHELP_IDENTITY_FILE,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"

if ($JobId -notmatch '^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$') {
    throw "Invalid job id."
}
if ($LocalPort -lt 1024 -or $LocalPort -gt 65535 -or $RemotePort -lt 1024 -or $RemotePort -gt 65535) {
    throw "Ports must be between 1024 and 65535."
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

$existing = Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort $LocalPort -State Listen -ErrorAction SilentlyContinue
if ($existing) {
    throw "Local port $LocalPort is already in use."
}

$python = Get-Command python -ErrorAction Stop
$scriptsRoot = Split-Path $PSScriptRoot -Parent
$skillRoot = Split-Path $scriptsRoot -Parent
$startScript = Join-Path $scriptsRoot "sshelp.py"
$arguments = @(
    $startScript,
    "web", "start",
    "--host", $SshHost,
    "--job-id", $JobId,
    "--local-port", $LocalPort,
    "--remote-port", $RemotePort,
    "--ssh-config", $SshConfig,
    "--known-hosts", $KnownHosts
)
if ($IdentityFile) {
    $arguments += @("--identity-file", $IdentityFile)
}

$jsonText = & $python.Source @arguments
if ($LASTEXITCODE -ne 0) {
    throw ($jsonText -join [Environment]::NewLine)
}
$result = ($jsonText -join [Environment]::NewLine) | ConvertFrom-Json
if (-not $result.ok) {
    throw $result.error.message
}

$tunnelArgv = @($result.tunnel_argv)
$sshExecutable = $tunnelArgv[0]
$sshArguments = @($tunnelArgv[1..($tunnelArgv.Count - 1)])
$tunnel = Start-Process -FilePath $sshExecutable -ArgumentList $sshArguments -WindowStyle Hidden -PassThru

$workRoot = $env:SSHELP_WORK_ROOT
if (-not $workRoot) { $workRoot = Join-Path (Get-Location) ".sshelp" }
$runtimeDir = Join-Path ([IO.Path]::GetFullPath($workRoot)) "runtime"
New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null
$runtimePath = Join-Path $runtimeDir ("web-{0}.json" -f $JobId)
@{
    job_id = $JobId
    host = $SshHost
    pid = $tunnel.Id
    browser_url = $result.browser_url
    local_port = $LocalPort
    remote_port = $RemotePort
    backend = $result.backend
    ssh_config = $SshConfig
    known_hosts = $KnownHosts
    identity_file = $IdentityFile
} | ConvertTo-Json | Set-Content -LiteralPath $runtimePath -Encoding UTF8

$ready = $false
for ($attempt = 0; $attempt -lt 40; $attempt++) {
    if ($tunnel.HasExited) {
        throw "The SSH tunnel exited before the Web observer became ready."
    }
    $probe = Test-NetConnection -ComputerName 127.0.0.1 -Port $LocalPort -WarningAction SilentlyContinue
    if ($probe.TcpTestSucceeded) {
        $ready = $true
        break
    }
    Start-Sleep -Milliseconds 250
}
if (-not $ready) {
    Stop-Process -Id $tunnel.Id -ErrorAction SilentlyContinue
    throw "Timed out waiting for the local Web observer port."
}

Write-Output $result.browser_url
if (-not $NoBrowser) {
    Start-Process $result.browser_url
}
