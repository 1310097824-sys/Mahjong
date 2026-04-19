$ErrorActionPreference = 'Stop'

function Test-IsAdministrator {
  $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
  $principal = New-Object Security.Principal.WindowsPrincipal($identity)
  return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Test-UrlReady {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Url,
    [int]$TimeoutSeconds = 20
  )

  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  while ((Get-Date) -lt $deadline) {
    try {
      $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 3
      if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
        return $true
      }
    } catch {
      Start-Sleep -Milliseconds 700
    }
  }

  return $false
}

$scriptPath = $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptPath
$projectParent = Split-Path -Parent $projectRoot
$pythonCandidates = @(
  (Join-Path $projectRoot '.venv\Scripts\python.exe'),
  (Join-Path $projectParent '.venv\Scripts\python.exe')
)
$pythonExe = $pythonCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
$frontendIndex = Join-Path $projectRoot 'riichi-mahjong-ui\dist\index.html'
$healthUrl = 'http://127.0.0.1:8000/api/health'
$siteUrl = 'http://127.0.0.1:8000'
$pidFile = Join-Path $projectRoot 'uvicorn.pid'
$stdoutLog = Join-Path $projectRoot 'uvicorn.out.log'
$stderrLog = Join-Path $projectRoot 'uvicorn.err.log'
$serviceName = 'MySQL80'

Write-Host 'Checking MySQL80...'
$mysqlService = Get-Service -Name $serviceName -ErrorAction Stop
if ($mysqlService.Status -ne 'Running') {
  if (-not (Test-IsAdministrator)) {
    Write-Host 'MySQL80 is stopped. Requesting administrator permission...'
    Start-Process -FilePath 'powershell.exe' -Verb RunAs -ArgumentList @(
      '-ExecutionPolicy',
      'Bypass',
      '-File',
      $scriptPath
    )
    exit 0
  }

  Write-Host 'Starting MySQL80...'
  Start-Service -Name $serviceName
  $mysqlService.WaitForStatus('Running', [TimeSpan]::FromSeconds(20))
}

if (-not $pythonExe) {
  $candidateList = $pythonCandidates -join ', '
  throw "Python executable not found. Checked: $candidateList"
}

if (-not (Test-Path $frontendIndex)) {
  throw "Frontend build not found: $frontendIndex`nRun: cd riichi-mahjong-ui && npm.cmd run build"
}

if (Test-UrlReady -Url $healthUrl -TimeoutSeconds 2) {
  Write-Host 'Mahjong system is already running. Opening browser...'
  Start-Process $siteUrl
  exit 0
}

$listener = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($listener) {
  throw "Port 8000 is already in use by PID $($listener.OwningProcess)."
}

Remove-Item -Path $pidFile, $stdoutLog, $stderrLog -Force -ErrorAction SilentlyContinue

Write-Host 'Starting FastAPI backend...'
$process = Start-Process `
  -FilePath $pythonExe `
  -ArgumentList @('-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000', '--app-dir', $projectRoot) `
  -WorkingDirectory $projectRoot `
  -RedirectStandardOutput $stdoutLog `
  -RedirectStandardError $stderrLog `
  -PassThru `
  -WindowStyle Hidden

Set-Content -Path $pidFile -Value $process.Id -Encoding Ascii

if (-not (Test-UrlReady -Url $healthUrl -TimeoutSeconds 25)) {
  if (Get-Process -Id $process.Id -ErrorAction SilentlyContinue) {
    Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
  }

  $errorOutput = if (Test-Path $stderrLog) {
    (Get-Content $stderrLog -Tail 40) -join [Environment]::NewLine
  } else {
    'No stderr log available.'
  }

  throw "Backend failed to start.`n$errorOutput"
}

Write-Host 'Mahjong system started successfully. Opening browser...'
Start-Process $siteUrl
