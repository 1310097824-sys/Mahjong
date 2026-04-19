@echo off
setlocal
chcp 65001 >nul
powershell.exe -ExecutionPolicy Bypass -File "%~dp0stop_mahjong_system.ps1"
if errorlevel 1 (
  echo.
  echo Shutdown failed. Please check the message above.
  pause
)
endlocal
