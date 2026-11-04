@echo off
setlocal
cd /d "%~dp0"
"%~dp0engine\DK-Knowledge-API.exe"
exit /b %ERRORLEVEL%
