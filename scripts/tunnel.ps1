<#
.SYNOPSIS
Launch a user-owned tunnel profile. Runtime keys are prompted without echo and are not saved.
.EXAMPLE
.\scripts\tunnel.ps1 -Action run -ClientPath "D:\Tools\tunnel-client.exe"
#>
[CmdletBinding()]
param(
    [ValidateSet('init', 'doctor', 'run')][string]$Action = 'run',
    [Parameter(Mandatory = $true)][string]$ClientPath,
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$')][string]$Profile = 'share-local-files',
    [string]$ProfileDir,
    [string]$Root,
    [string]$TunnelId,
    [switch]$NonInteractive
)
$ErrorActionPreference = 'Stop'
$nodeCommand = (Get-Command node -ErrorAction Stop).Source
$launcher = Join-Path $PSScriptRoot 'tunnel.mjs'
$launchArguments = @($launcher, $Action, '--client', $ClientPath, '--profile', $Profile)
if ($ProfileDir) { $launchArguments += @('--profile-dir', $ProfileDir) }
if ($Root) { $launchArguments += @('--root', $Root) }
if ($TunnelId) { $launchArguments += @('--tunnel', $TunnelId) }
$previousKey = [Environment]::GetEnvironmentVariable('CONTROL_PLANE_API_KEY', 'Process')
$secret = $null
$keyPointer = [IntPtr]::Zero
try {
    if ($Action -ne 'init' -and [string]::IsNullOrWhiteSpace($previousKey)) {
        if ($NonInteractive) { throw 'No runtime key. NonInteractive mode requires a secret manager to set CONTROL_PLANE_API_KEY.' }
        $secret = Read-Host 'Runtime API key (hidden, not saved)' -AsSecureString
        $keyPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
        $env:CONTROL_PLANE_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($keyPointer)
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($keyPointer)
        $keyPointer = [IntPtr]::Zero
    }
    & $nodeCommand @launchArguments
    $launchExitCode = $LASTEXITCODE
} finally {
    if ($keyPointer -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($keyPointer) }
    if ($null -ne $secret) { $secret.Dispose() }
    [Environment]::SetEnvironmentVariable('CONTROL_PLANE_API_KEY', $previousKey, 'Process')
}
if ($launchExitCode -ne 0) { throw "tunnel-client exited with code $launchExitCode. Check the output above; do not paste keys into support messages." }
