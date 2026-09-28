@echo off
:: Run once as Administrator so colleagues can reach CashUp on port 5000.
title CashUp - Windows Firewall
cd /d "%~dp0"

net session >nul 2>&1
if errorlevel 1 (
    echo Please right-click this file and choose "Run as administrator".
    pause
    exit /b 1
)

netsh advfirewall firewall delete rule name="CashUp Server" >nul 2>&1
:: Private + Public: office Wi-Fi is often marked "Public" on Windows
netsh advfirewall firewall add rule name="CashUp Server" dir=in action=allow protocol=TCP localport=5000 profile=private,public

echo.
echo Allowed inbound TCP port 5000 (Private and Public networks).
echo.
echo Tell colleagues to use THIS PC's current address:
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /i "IPv4"') do echo   http://%%a:5000
echo.
echo (If that address changes after reconnecting Wi-Fi, share the new one from start_cashup.bat)
echo.
pause
