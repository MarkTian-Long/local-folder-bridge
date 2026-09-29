@echo off
setlocal
cd /d "%~dp0"
call START.cmd --self-test
set "RESULT=%ERRORLEVEL%"
echo.
echo Local regression tests finished. See reports/current/local-tests.json and reports/current/local-tests.txt.
pause
exit /b %RESULT%
