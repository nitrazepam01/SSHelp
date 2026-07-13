#Requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [Alias("Host")]
    [string]$SshHost,

    [Parameter(Mandatory = $true)]
    [string]$JobId,

    [string]$SshConfig = $env:SSHELP_SSH_CONFIG,
    [string]$IdentityFile = $env:SSHELP_IDENTITY_FILE,
    [switch]$Interactive
)

$ErrorActionPreference = "Stop"

if ($JobId -notmatch '^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$') {
    throw "Invalid job id."
}

if (-not $SshConfig) {
    $SshConfig = $env:SSH_RESEARCH_CONFIG
}
if (-not $SshConfig) {
    $SshConfig = Join-Path $env:USERPROFILE ".ssh\config"
}
if (-not $IdentityFile) { $IdentityFile = $env:SSH_RESEARCH_IDENTITY_FILE }

$python = Get-Command python -ErrorAction Stop
$attachScript = Join-Path (Split-Path $PSScriptRoot -Parent) "sshelp.py"
$attachArgs = @(
    $attachScript,
    "job", "attach",
    "--host", $SshHost,
    "--job-id", $JobId,
    "--ssh-config", $SshConfig
)

if ($Interactive) {
    $attachArgs += "--interactive"
}

if ($IdentityFile) {
    $attachArgs += @("--identity-file", $IdentityFile)
}

$terminal = Get-Command wt.exe -ErrorAction SilentlyContinue
if ($terminal) {
    $title = "SSH job $JobId"
    & $terminal.Source new-tab --title $title $python.Source @attachArgs
    exit $LASTEXITCODE
}

Write-Warning "Windows Terminal was not found; attaching in the current terminal."
& $python.Source @attachArgs
exit $LASTEXITCODE
