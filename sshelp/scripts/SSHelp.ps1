#Requires -Version 5.1
<#
.SYNOPSIS
Single Windows entry for SSHelp terminal and browser observers.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet("terminal", "web-open", "web-close", "dashboard-open", "dashboard-close")]
    [string]$Action,

    [Alias("Host")]
    [string]$SshHost,
    [string[]]$JobId,
    [int]$LocalPort = 7681,
    [int]$RemotePort = 7681,
    [int]$BaseTerminalPort = 7681,
    [int]$DashboardPort = 7679,
    [string]$SshConfig,
    [string]$KnownHosts,
    [string]$IdentityFile,
    [string]$WorkRoot,
    [switch]$Interactive,
    [switch]$NoBrowser,
    [switch]$KeepTerminalObservers
)

$ErrorActionPreference = "Stop"

if (-not $SshConfig) { $SshConfig = $env:SSHELP_SSH_CONFIG }
if (-not $SshConfig) { $SshConfig = $env:SSH_RESEARCH_CONFIG }
if (-not $KnownHosts) { $KnownHosts = $env:SSHELP_KNOWN_HOSTS }
if (-not $KnownHosts) { $KnownHosts = $env:SSH_RESEARCH_KNOWN_HOSTS }
if (-not $IdentityFile) { $IdentityFile = $env:SSHELP_IDENTITY_FILE }
if (-not $IdentityFile) { $IdentityFile = $env:SSH_RESEARCH_IDENTITY_FILE }
if (-not $WorkRoot) { $WorkRoot = $env:SSHELP_WORK_ROOT }
if (-not $WorkRoot) { $WorkRoot = Join-Path (Get-Location) ".sshelp" }
$env:SSHELP_WORK_ROOT = [IO.Path]::GetFullPath($WorkRoot)

function Require-Jobs([int]$Minimum = 1) {
    if (-not $JobId -or $JobId.Count -lt $Minimum) {
        throw "Action '$Action' requires at least $Minimum job id(s)."
    }
}

switch ($Action) {
    "terminal" {
        Require-Jobs
        $arguments = @{ SshHost = $SshHost; JobId = $JobId[0]; Interactive = $Interactive }
        if ($SshConfig) { $arguments.SshConfig = $SshConfig }
        if ($IdentityFile) { $arguments.IdentityFile = $IdentityFile }
        & (Join-Path $PSScriptRoot "_compat\Open-JobTerminal.ps1") @arguments
    }
    "web-open" {
        Require-Jobs
        $arguments = @{
            SshHost = $SshHost; JobId = $JobId[0]; LocalPort = $LocalPort;
            RemotePort = $RemotePort; NoBrowser = $NoBrowser
        }
        if ($SshConfig) { $arguments.SshConfig = $SshConfig }
        if ($KnownHosts) { $arguments.KnownHosts = $KnownHosts }
        if ($IdentityFile) { $arguments.IdentityFile = $IdentityFile }
        & (Join-Path $PSScriptRoot "_compat\Open-JobWeb.ps1") @arguments
    }
    "web-close" {
        Require-Jobs
        & (Join-Path $PSScriptRoot "_compat\Close-JobWeb.ps1") -JobId $JobId[0]
    }
    "dashboard-open" {
        Require-Jobs
        $arguments = @{
            SshHost = $SshHost; JobId = $JobId; BaseTerminalPort = $BaseTerminalPort;
            DashboardPort = $DashboardPort
        }
        if ($SshConfig) { $arguments.SshConfig = $SshConfig }
        if ($KnownHosts) { $arguments.KnownHosts = $KnownHosts }
        if ($IdentityFile) { $arguments.IdentityFile = $IdentityFile }
        & (Join-Path $PSScriptRoot "_compat\Open-MultiJobDashboard.ps1") @arguments
    }
    "dashboard-close" {
        & (Join-Path $PSScriptRoot "_compat\Close-MultiJobDashboard.ps1") `
            -DashboardPort $DashboardPort `
            -KeepTerminalObservers:$KeepTerminalObservers
    }
}
