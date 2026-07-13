#Requires -Version 5.1
[CmdletBinding()]
param(
    [int]$DashboardPort = 7679,
    [switch]$KeepTerminalObservers
)

$ErrorActionPreference = "Stop"

if ($DashboardPort -lt 1024 -or $DashboardPort -gt 65535) {
    throw "Dashboard port must be between 1024 and 65535."
}

$scriptsRoot = Split-Path $PSScriptRoot -Parent
$skillRoot = Split-Path $scriptsRoot -Parent
$workRoot = $env:SSHELP_WORK_ROOT
if (-not $workRoot) { $workRoot = Join-Path (Get-Location) ".sshelp" }
$runtimeDir = Join-Path ([IO.Path]::GetFullPath($workRoot)) "runtime"
$runtimePath = Join-Path $runtimeDir ("dashboard-{0}.json" -f $DashboardPort)
if (-not (Test-Path -LiteralPath $runtimePath)) {
    throw "No dashboard state exists for port $DashboardPort."
}

$state = Get-Content -Raw -LiteralPath $runtimePath | ConvertFrom-Json
$process = Get-Process -Id $state.pid -ErrorAction SilentlyContinue
if ($process) {
    if ($process.ProcessName -notin @("python", "python3", "python.exe", "python3.exe")) {
        throw "Recorded dashboard PID is not a Python process; refusing to stop it."
    }
    Stop-Process -Id $state.pid
}

if (-not $KeepTerminalObservers) {
    $closeJobWeb = Join-Path $PSScriptRoot "Close-JobWeb.ps1"
    foreach ($id in @($state.jobs)) {
        try {
            & $closeJobWeb -JobId $id
        } catch {
            Write-Warning "Could not close observer for job ${id}: $($_.Exception.Message)"
        }
    }
}

if ($state.html_path -and (Test-Path -LiteralPath $state.html_path)) {
    Remove-Item -LiteralPath $state.html_path
}
if ($state.directory -and (Test-Path -LiteralPath $state.directory)) {
    Remove-Item -LiteralPath $state.directory
}
Remove-Item -LiteralPath $runtimePath
