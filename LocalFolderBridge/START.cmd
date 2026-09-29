@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul
title Local Folder Bridge
pushd "%~dp0"
if errorlevel 1 goto fail
set "LFB_HOME=%CD%"
if exist "runtime\python.exe" goto launch
where py >nul 2>nul
if errorlevel 1 goto try_python
py -3 -c "import sys;sys.exit(0 if sys.version_info >= (3,11) else 1)" >nul 2>nul
if errorlevel 1 goto try_python
py -3 app.py %*
set "LFB_EXIT=%ERRORLEVEL%"
goto finished
:try_python
where python >nul 2>nul
if errorlevel 1 goto bootstrap
python -c "import sys;sys.exit(0 if sys.version_info >= (3,11) else 1)" >nul 2>nul
if errorlevel 1 goto bootstrap
python app.py %*
set "LFB_EXIT=%ERRORLEVEL%"
goto finished
:bootstrap
echo [1/2] First launch: downloading the official Python 3.13.15 runtime.
echo       This requires network access to www.python.org. No administrator rights needed.
echo       The published SHA-256 is checked before extraction.
powershell.exe -NoLogo -NoProfile -Command "$ErrorActionPreference='Stop'; try { $root=$env:LFB_HOME; $arch=$env:PROCESSOR_ARCHITEW6432; if(-not $arch){$arch=$env:PROCESSOR_ARCHITECTURE}; if($arch -eq 'ARM64'){$a='arm64';$sha='cd992cbfb33be433ff20f150691595efb2862e56f4f1bec684c6077d4775af8e'}elseif($arch -eq 'AMD64'){$a='amd64';$sha='d1f04d990aee1253d8569e8e5104e30fa9f5fa830899f14843448872d936a2cf'}else{throw 'This launcher supports Windows x64 or ARM64 only.'}; [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; $url='https://www.python.org/ftp/python/3.13.15/python-3.13.15-embed-'+$a+'.zip'; $zip=Join-Path $root 'python-runtime.download.zip'; $stage=Join-Path $root ('runtime-stage-'+[guid]::NewGuid().ToString('N')); Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $zip; if((Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLowerInvariant() -ne $sha){throw 'Runtime SHA-256 verification failed. Do not run this download.'}; Expand-Archive -LiteralPath $zip -DestinationPath $stage; if(-not (Test-Path -LiteralPath (Join-Path $stage 'python.exe'))){throw 'The archive has no python.exe.'}; if(Test-Path -LiteralPath (Join-Path $root 'runtime')){throw 'An incomplete runtime directory already exists. Rename it, then retry.'}; Move-Item -LiteralPath $stage -Destination (Join-Path $root 'runtime'); Remove-Item -LiteralPath $zip; Write-Host 'Official runtime downloaded and SHA-256 verified.'; exit 0 } catch { Write-Host ('Startup failed: '+$_.Exception.Message) -ForegroundColor Red; exit 1 }"
if errorlevel 1 goto fail
:launch
echo [2/2] Starting the local manager. Keep this window running.
"runtime\python.exe" app.py %*
set "LFB_EXIT=%ERRORLEVEL%"
:finished
if not "%LFB_EXIT%"=="0" goto fail
popd
exit /b 0
:fail
echo.
echo Startup did not complete. See the error above and the included manual.
echo Do not disable antivirus, certificate validation, or corporate security policy.
echo You may install a supported Python from python.org, then retry START.cmd.
echo.
pause
popd
exit /b 1
