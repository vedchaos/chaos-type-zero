@echo off
chcp 65001 >nul 2>&1
title CTZ - Chaos Type Zero Launcher
color 0D

cd /d "%~dp0"

echo.
echo  ================================================
echo    CHAOS TYPE ZERO - LAUNCHER (Ved ki girlfriend)
echo  ================================================
echo.
echo   [1] Dashboard + Automation  (http://localhost:8080)
echo   [2] Chat CLI                (python chat_ctz.py)
echo   [3] Dono chalao             (Dashboard + Chat)
echo   [4] Exit
echo.
set /p choice="  Choose (1-4): "

if "%choice%"=="1" goto dashboard
if "%choice%"=="2" goto chat
if "%choice%"=="3" goto both
if "%choice%"=="4" exit /b
echo  Invalid choice! Try again.
pause
exit /b

:dashboard
echo.
echo  [*] Starting CTZ Dashboard + Max Automation...
echo  [*] Open browser: http://localhost:8080
echo  [*] Band karne ke liye: Ctrl+C
echo.
python ctz_unified.py
if errorlevel 1 (
  echo.
  echo  [!] Error! Python installed hai? Check karo: python --version
  pause
)
exit /b

:chat
echo.
echo  [*] Starting CTZ Chat Console...
echo  [*] Band karne ke liye: exit ya Ctrl+C
echo.
python chat_ctz.py
if errorlevel 1 (
  echo.
  echo  [!] Error! Python installed hai? Check karo: python --version
  pause
)
exit /b

:both
echo.
echo  [*] Starting Dashboard (background) + Chat...
start "CTZ Dashboard" cmd /k "pushd %~dp0 && python ctz_unified.py"
timeout /t 3 /nobreak >nul
python chat_ctz.py
exit /b