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

function Get-CargoExecutable {
  $cargoCommand = Get-Command 'cargo.exe' -ErrorAction SilentlyContinue
  if ($cargoCommand) {
    return $cargoCommand.Source
  }

  $userCargo = Join-Path $env:USERPROFILE '.cargo\bin\cargo.exe'
  if (Test-Path $userCargo) {
    return $userCargo
  }

  return $null
}

function Test-RustCoreBuildNeeded {
  param(
    [Parameter(Mandatory = $true)]
    [string]$RustCoreDir,
    [Parameter(Mandatory = $true)]
    [string]$RustCoreDll
  )

  if (-not (Test-Path $RustCoreDll)) {
    return $true
  }

  $dllInfo = Get-Item $RustCoreDll
  $sourceFiles = @(
    (Join-Path $RustCoreDir 'Cargo.toml'),
    (Join-Path $RustCoreDir 'Cargo.lock')
  )
  $sourceFiles += Get-ChildItem -Path (Join-Path $RustCoreDir 'src') -Filter '*.rs' -Recurse | Select-Object -ExpandProperty FullName

  foreach ($sourceFile in $sourceFiles) {
    if ((Test-Path $sourceFile) -and ((Get-Item $sourceFile).LastWriteTimeUtc -gt $dllInfo.LastWriteTimeUtc)) {
      return $true
    }
  }

  return $false
}

function Get-RustCoreExpectedVersion {
  param(
    [Parameter(Mandatory = $true)]
    [string]$RustCoreDir
  )

  $ffiPath = Join-Path $RustCoreDir 'src\ffi.rs'
  if (-not (Test-Path $ffiPath)) {
    return $null
  }

  $ffiSource = Get-Content -Path $ffiPath -Raw
  $versionMatch = [regex]::Match($ffiSource, 'mahjong_core_version\(\)\s*->\s*u32\s*\{\s*(?<version>\d+)\s*\}')
  if (-not $versionMatch.Success) {
    return $null
  }

  return [int]$versionMatch.Groups['version'].Value
}

function Assert-RustCoreBridge {
  param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectRoot,
    [Parameter(Mandatory = $true)]
    [string]$PythonExe,
    [Nullable[int]]$ExpectedVersion = $null
  )

  $expectedLiteral = if ($null -eq $ExpectedVersion) { 'None' } else { $ExpectedVersion.ToString() }
  $pythonScript = @"
import sys
from app import rust_core

version = rust_core.version()
if version is None:
    print("Rust core bridge unavailable")
    sys.exit(2)

expected = $expectedLiteral
if expected is not None and version != expected:
    print(f"Rust core version mismatch: expected {expected}, loaded {version}")
    sys.exit(3)

print(f"Rust core bridge loaded version {version}")
"@

  $tempScript = Join-Path ([System.IO.Path]::GetTempPath()) ("mahjong_rust_core_check_{0}.py" -f ([Guid]::NewGuid().ToString('N')))
  Set-Content -Path $tempScript -Value $pythonScript -Encoding Ascii

  Push-Location $ProjectRoot
  try {
    $previousErrorActionPreference = $ErrorActionPreference
    $previousPythonPath = $env:PYTHONPATH
    $pathSeparator = [System.IO.Path]::PathSeparator
    if ([string]::IsNullOrWhiteSpace($previousPythonPath)) {
      $env:PYTHONPATH = $ProjectRoot
    } else {
      $env:PYTHONPATH = "$ProjectRoot$pathSeparator$previousPythonPath"
    }
    $ErrorActionPreference = 'Continue'
    try {
      $bridgeOutput = & $PythonExe $tempScript 2>&1
      $bridgeExitCode = $LASTEXITCODE
    } finally {
      $env:PYTHONPATH = $previousPythonPath
      $ErrorActionPreference = $previousErrorActionPreference
    }
  } finally {
    Pop-Location
    Remove-Item -Path $tempScript -Force -ErrorAction SilentlyContinue
  }

  if ($bridgeOutput) {
    $bridgeOutput | ForEach-Object { Write-Host $_ }
  }

  if ($bridgeExitCode -ne 0) {
    throw 'Rust core bridge check failed.'
  }
}

function Ensure-RustCoreBuilt {
  param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectRoot,
    [Parameter(Mandatory = $true)]
    [string]$PythonExe
  )

  $rustCoreDir = Join-Path $ProjectRoot 'rust_core'
  $cargoToml = Join-Path $rustCoreDir 'Cargo.toml'
  $rustCoreDll = Join-Path $rustCoreDir 'target\release\mahjong_core.dll'
  $expectedVersion = Get-RustCoreExpectedVersion -RustCoreDir $rustCoreDir

  if (-not (Test-Path $cargoToml)) {
    Write-Host 'Rust core project was not found. Backend will use Python fallback.'
    return
  }

  $buildNeeded = Test-RustCoreBuildNeeded -RustCoreDir $rustCoreDir -RustCoreDll $rustCoreDll
  if (-not $buildNeeded) {
    Write-Host 'Rust core is up to date.'
  } else {
    $cargoExe = Get-CargoExecutable
    if (-not $cargoExe) {
      if (Test-Path $rustCoreDll) {
        Write-Host 'Cargo was not found. Existing Rust core DLL will be checked.'
      } else {
        Write-Host 'Cargo was not found. Backend will start with Python fallback, but AI performance will be lower.'
        return
      }
    } else {
      Write-Host 'Building Rust core acceleration layer...'
      Push-Location $rustCoreDir
      try {
        & $cargoExe build --release
        if ($LASTEXITCODE -ne 0) {
          throw "cargo build --release failed with exit code $LASTEXITCODE"
        }
      } finally {
        Pop-Location
      }

      if (-not (Test-Path $rustCoreDll)) {
        throw "Rust core build finished but DLL was not found: $rustCoreDll"
      }
    }
  }

  if (Test-Path $rustCoreDll) {
    Assert-RustCoreBridge -ProjectRoot $ProjectRoot -PythonExe $PythonExe -ExpectedVersion $expectedVersion
  }
}

function Test-FrontendBuildFresh {
  param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectRoot,
    [Parameter(Mandatory = $true)]
    [string]$FrontendIndex
  )

  if (-not (Test-Path $FrontendIndex)) {
    return $false
  }

  $uiRoot = Join-Path $ProjectRoot 'riichi-mahjong-ui'
  $srcRoot = Join-Path $uiRoot 'src'
  if (-not (Test-Path $srcRoot)) {
    return $true
  }

  $indexInfo = Get-Item $FrontendIndex
  $trackedInputs = @(
    (Join-Path $uiRoot 'package.json'),
    (Join-Path $uiRoot 'package-lock.json'),
    (Join-Path $uiRoot 'vite.config.ts'),
    (Join-Path $uiRoot 'index.html')
  )
  $trackedInputs += Get-ChildItem -Path $srcRoot -File -Recurse | Select-Object -ExpandProperty FullName

  foreach ($inputFile in $trackedInputs) {
    if ((Test-Path $inputFile) -and ((Get-Item $inputFile).LastWriteTimeUtc -gt $indexInfo.LastWriteTimeUtc)) {
      return $false
    }
  }

  return $true
}

function Get-NpmExecutable {
  $npmCommand = Get-Command 'npm.cmd' -ErrorAction SilentlyContinue
  if ($npmCommand) {
    return $npmCommand.Source
  }

  $npmFallback = Join-Path $env:ProgramFiles 'nodejs\npm.cmd'
  if (Test-Path $npmFallback) {
    return $npmFallback
  }

  return $null
}

function Ensure-FrontendBuilt {
  param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectRoot,
    [Parameter(Mandatory = $true)]
    [string]$FrontendIndex
  )

  if (Test-FrontendBuildFresh -ProjectRoot $ProjectRoot -FrontendIndex $FrontendIndex) {
    Write-Host 'Frontend build is up to date.'
    return
  }

  $uiRoot = Join-Path $ProjectRoot 'riichi-mahjong-ui'
  $packageJson = Join-Path $uiRoot 'package.json'
  if (-not (Test-Path $packageJson)) {
    throw "Frontend project not found: $packageJson"
  }

  $npmExe = Get-NpmExecutable
  if (-not $npmExe) {
    throw "Frontend build not found or stale: $FrontendIndex`nNode/npm was not found. Run: cd riichi-mahjong-ui && npm.cmd run build"
  }

  Write-Host 'Building frontend assets...'
  Push-Location $uiRoot
  try {
    & $npmExe run build
    if ($LASTEXITCODE -ne 0) {
      throw "npm run build failed with exit code $LASTEXITCODE"
    }
  } finally {
    Pop-Location
  }

  if (-not (Test-Path $FrontendIndex)) {
    throw "Frontend build finished but index was not found: $FrontendIndex"
  }
}

function Test-IsMahjongBackendProcess {
  param(
    [Parameter(Mandatory = $true)]
    [int]$ProcessId,
    [Parameter(Mandatory = $true)]
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

function Stop-StaleBackendPid {
  param(
    [Parameter(Mandatory = $true)]
    [int]$ProcessId,
    [Parameter(Mandatory = $true)]
    [string]$ProjectRoot
  )

  $process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
  if (-not $process) {
    return
  }

  if (-not (Test-IsMahjongBackendProcess -ProcessId $ProcessId -ProjectRoot $ProjectRoot)) {
    throw "Port 8000 is already in use by PID $ProcessId."
  }

  Write-Host "Stopping stale Mahjong backend PID $ProcessId..."
  Stop-Process -Id $ProcessId -Force
  Start-Sleep -Milliseconds 500
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

if (-not $pythonExe) {
  $candidateList = $pythonCandidates -join ', '
  throw "Python executable not found. Checked: $candidateList"
}

Write-Host 'Checking MySQL80...'
$mysqlService = Get-Service -Name $serviceName -ErrorAction Stop
if ($mysqlService.Status -ne 'Running') {
  if (-not (Test-IsAdministrator)) {
    Write-Host 'MySQL80 is stopped. Requesting administrator permission...'
    Start-Process -FilePath 'powershell.exe' -Verb RunAs -ArgumentList @(
      '-NoProfile',
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

Ensure-FrontendBuilt -ProjectRoot $projectRoot -FrontendIndex $frontendIndex

if (Test-UrlReady -Url $healthUrl -TimeoutSeconds 2) {
  Write-Host 'Mahjong system is already running. Opening browser...'
  Start-Process $siteUrl
  exit 0
}

$listener = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($listener) {
  if (Test-IsMahjongBackendProcess -ProcessId $listener.OwningProcess -ProjectRoot $projectRoot) {
    if (Test-UrlReady -Url $healthUrl -TimeoutSeconds 8) {
      Write-Host 'Mahjong system is already running. Opening browser...'
      Start-Process $siteUrl
      exit 0
    }
  }

  Stop-StaleBackendPid -ProcessId $listener.OwningProcess -ProjectRoot $projectRoot
  $listener = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($listener) {
    throw "Port 8000 is already in use by PID $($listener.OwningProcess)."
  }
}

Ensure-RustCoreBuilt -ProjectRoot $projectRoot -PythonExe $pythonExe

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
