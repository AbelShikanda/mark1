$root = $PSScriptRoot
$venvPython = Join-Path $root 'backend\venv\Scripts\python.exe'

$pids = New-Object System.Collections.Generic.HashSet[int]

# Anything currently listening on the app port.
Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue | ForEach-Object {
    if ($_.OwningProcess -gt 0) { [void]$pids.Add([int]$_.OwningProcess) }
}

# The venv launcher (and, through taskkill /T, its interpreter child).
Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue | Where-Object {
    $_.ExecutablePath -and $_.ExecutablePath -ieq $venvPython
} | ForEach-Object {
    [void]$pids.Add([int]$_.ProcessId)
}

if ($pids.Count -eq 0) {
    Write-Host 'Marketing Bot is not running.'
    exit 0
}

foreach ($serverPid in $pids) {
    $proc = Get-Process -Id $serverPid -ErrorAction SilentlyContinue
    if (-not $proc) { continue }
    if ($proc.ProcessName -notlike 'python*') {
        Write-Host "Port 8000 is held by $($proc.ProcessName) (PID $serverPid); refusing to stop it."
        exit 1
    }
    Write-Host "Stopping $($proc.ProcessName) PID $serverPid (and its children)..."
    taskkill /PID $serverPid /T /F 2>$null | Out-Null
}

Start-Sleep -Milliseconds 1200

if (Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue) {
    Write-Host 'Port 8000 is still in use.'
    exit 1
}

Write-Host 'Stopped. You can start Marketing Bot again.'
exit 0
