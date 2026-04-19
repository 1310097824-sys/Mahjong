@echo off
setlocal
chcp 65001 >nul
powershell.exe -ExecutionPolicy Bypass -File "%~dp0start_mahjong_system.ps1"
if errorlevel 1 (
  echo.
  echo Startup failed. Please check the message above.
  pause
)
endlocal
