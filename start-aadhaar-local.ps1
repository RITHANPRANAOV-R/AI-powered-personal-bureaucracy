[CmdletBinding(SupportsShouldProcess = $true)]
param([switch]$EnablePortalDiagnostics, [ValidateRange(5,120)][int]$ReadinessTimeoutSeconds = 45)
$ErrorActionPreference = 'Stop'
$pythonPath = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) { throw 'Project interpreter missing.' }
Write-Output 'Command: .\.venv\Scripts\python.exe -u -B -m uvicorn api.app:app --host 127.0.0.1 --port 8000 --workers 1'
Write-Output "Diagnostics enabled: $([bool]$EnablePortalDiagnostics); permitted origin: http://localhost:5173"
if (-not $PSCmdlet.ShouldProcess('127.0.0.1:8000', 'Start tracked backend and verify /api/health')) { return }
# Listener inspection is optional when Windows denies access. Uvicorn's bind is authoritative.
try {
    $listeners = @([System.Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners() | Where-Object Port -eq 8000)
    if ($listeners.Count) { throw 'PORT_OCCUPIED: an existing listener uses port 8000.' }
} catch {
    if ($_.Exception.Message -like '*PORT_OCCUPIED*') { throw }
    Write-Warning 'OS listener inspection unavailable; startup logs will identify any bind failure.'
}
$logDirectory = Join-Path ([System.IO.Path]::GetTempPath()) ('aadhaar-startup-' + [guid]::NewGuid().ToString('N'))
[void](New-Item -ItemType Directory -Path $logDirectory)
$stdoutPath = Join-Path $logDirectory 'stdout.log'
$stderrPath = Join-Path $logDirectory 'stderr.log'
$settings = @{ AADHAAR_ENABLE_PORTAL_DIAGNOSTICS = $(if ($EnablePortalDiagnostics) {'1'} else {'0'}); AADHAAR_FRONTEND_ORIGINS = 'http://localhost:5173'; AADHAAR_ALLOW_ALL_ORIGINS = '0' }
$savedEnvironment = @{}
foreach ($name in $settings.Keys) { $savedEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, 'Process') }
try {
    foreach ($name in $settings.Keys) { [Environment]::SetEnvironmentVariable($name, $settings[$name], 'Process') }
    $backendProcess = Start-Process -FilePath $pythonPath -ArgumentList '-u','-B','-m','uvicorn','api.app:app','--host','127.0.0.1','--port','8000','--workers','1' -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath -PassThru
} finally {
    foreach ($name in $settings.Keys) { [Environment]::SetEnvironmentVariable($name, $savedEnvironment[$name], 'Process') }
}
Write-Output "Tracked PID: $($backendProcess.Id); stdout: $stdoutPath; stderr: $stderrPath"
$deadline = [DateTime]::UtcNow.AddSeconds($ReadinessTimeoutSeconds)
$lastHealthError = 'No health response.'
while ([DateTime]::UtcNow -lt $deadline) {
    $backendProcess.Refresh()
    if ($backendProcess.HasExited) {
        $backendProcess.WaitForExit()
        $startupError = Get-Content -LiteralPath $stderrPath -Raw
        Write-Output "Exit code: $($backendProcess.ExitCode)"
        Write-Output $startupError
        if ($startupError -match '10048|address already in use|only one usage') { throw 'PORT_OCCUPIED: Uvicorn bind failed.' }
        throw 'BACKEND_START_FAILED: see captured Python/Uvicorn error above.'
    }
    try {
        $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/health' -TimeoutSec 2
        $backendProcess.Refresh()
        $startupLog = Get-Content -LiteralPath $stderrPath -Raw
        if (-not $backendProcess.HasExited -and $health.status -eq 'ok' -and $health.service -eq 'aadhaar-assistant-api' -and $startupLog -match 'Uvicorn running on http://127\.0\.0\.1:8000') {
            Write-Output "READY: /api/health responded; tracked PID $($backendProcess.Id); loopback bind recorded by Uvicorn."
            Write-Output ($health | ConvertTo-Json -Compress)
            return
        }
        $lastHealthError = 'Health or tracked-process startup identity did not match.'
    } catch { $lastHealthError = $_.Exception.Message }
    Start-Sleep -Milliseconds 500
}
$backendProcess.Refresh()
Write-Output (Get-Content -LiteralPath $stderrPath -Raw)
if ($backendProcess.HasExited) { $backendProcess.WaitForExit(); throw "BACKEND_START_FAILED: exit code $($backendProcess.ExitCode)." }
throw "READINESS_TIMEOUT: PID $($backendProcess.Id) remains alive; readiness unverified. No process was terminated. $lastHealthError"
