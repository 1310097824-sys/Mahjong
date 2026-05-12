$ErrorActionPreference = 'Stop'

function Stop-PidIfRunning {
  param(
    [int]$ProcessId,
    [System.Collections.Generic.HashSet[int]]$StoppedPids,
    [string]$ProjectRoot
  )

  if ($StoppedPids.Contains($ProcessId)) {
    return
  }

  $process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
  if ($process) {
    if (-not (Test-IsMahjongBackendProcess -ProcessId $ProcessId -ProjectRoot $ProjectRoot)) {
      Write-Host "Skipped PID $ProcessId because it does not look like this Mahjong backend."
      return
    }

    Stop-Process -Id $ProcessId -Force
    [void]$StoppedPids.Add($ProcessId)
  }
}

function Test-IsMahjongBackendProcess {
  param(
    [int]$ProcessId,
    [string]$ProjectRoot
  )

  $processInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction SilentlyContinue
  if (-not $processInfo -or [string]::IsNullOrWhiteSpace($processInfo.CommandLine)) {
    return $false
  }

  $normalizedCommand = $processInfo.CommandLine.Replace('/', '\').ToLowerInvariant()
  $normalizedRoot = $ProjectRoot.Replace('/', '\').ToLowerInvariant()
  return $normalizedCommand.Contains('uvicorn') -and
    $normalizedCommand.Contains('app.main:app') -and
    $normalizedCommand.Contains($normalizedRoot)
}

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$pidFile = Join-Path $projectRoot 'uvicorn.pid'
$stoppedPids = [System.Collections.Generic.HashSet[int]]::new()

Write-Host 'Stopping Mahjong backend...'

if (Test-Path $pidFile) {
  $savedPidText = (Get-Content $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1).Trim()
  if ($savedPidText -match '^\d+$') {
    Stop-PidIfRunning -ProcessId ([int]$savedPidText) -StoppedPids $stoppedPids -ProjectRoot $projectRoot
  }
  Remove-Item -Path $pidFile -Force -ErrorAction SilentlyContinue
}

$listenerIds = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue |
  Select-Object -ExpandProperty OwningProcess -Unique

foreach ($listenerId in $listenerIds) {
  Stop-PidIfRunning -ProcessId $listenerId -StoppedPids $stoppedPids -ProjectRoot $projectRoot
}

if ($stoppedPids.Count -gt 0) {
  $pidSummary = ($stoppedPids | Sort-Object | ForEach-Object { $_.ToString() }) -join ', '
  Write-Host "Stopped backend PID(s): $pidSummary"
} else {
  Write-Host 'No running backend process was found on port 8000.'
}

Write-Host 'MySQL80 was left running intentionally.'
