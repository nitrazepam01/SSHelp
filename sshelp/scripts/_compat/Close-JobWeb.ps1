#Requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$JobId
)

$ErrorActionPreference = "Stop"

if ($JobId -notmatch '^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$') {
    throw "Invalid job id."
}

$scriptsRoot = Split-Path $PSScriptRoot -Parent
$skillRoot = Split-Path $scriptsRoot -Parent
$workRoot = $env:SSHELP_WORK_ROOT
if (-not $workRoot) { $workRoot = Join-Path (Get-Location) ".sshelp" }
$runtimePath = Join-Path (Join-Path ([IO.Path]::GetFullPath($workRoot)) "runtime") ("web-{0}.json" -f $JobId)
if (-not (Test-Path -LiteralPath $runtimePath)) {
    throw "No local Web observer state exists for job $JobId."
}

$state = Get-Content -Raw -LiteralPath $runtimePath | ConvertFrom-Json
$process = Get-Process -Id $state.pid -ErrorAction SilentlyContinue
if ($process) {
    if ($process.ProcessName -notin @("ssh", "ssh.exe")) {
        throw "Recorded tunnel PID is not an SSH process; refusing to stop it."
    }
    Stop-Process -Id $state.pid
}

$python = Get-Command python -ErrorAction Stop
$stopScript = Join-Path $scriptsRoot "sshelp.py"
$arguments = @(
    $stopScript,
    "web", "stop",
    "--host", $state.host,
    "--job-id", $JobId,
    "--ssh-config", $state.ssh_config,
    "--known-hosts", $state.known_hosts
)
if ($state.identity_file) {
    $arguments += @("--identity-file", $state.identity_file)
}

& $python.Source @arguments
if ($LASTEXITCODE -ne 0) {
    throw "The local tunnel stopped, but the remote ttyd observer could not be stopped."
}

Remove-Item -LiteralPath $runtimePath
