@echo off
setlocal EnableExtensions
cd /d "%~dp0"

if not defined HOST set "HOST=127.0.0.1"
if not defined PORT set "PORT=8000"
set "VENV=.venv"
set "VPY=%VENV%\Scripts\python.exe"

set "CMD=%~1"
if "%CMD%"=="" set "CMD=help"

if /I "%CMD%"=="help" goto help
if /I "%CMD%"=="install" goto install
if /I "%CMD%"=="run" goto run
if /I "%CMD%"=="dev" goto dev
if /I "%CMD%"=="test" goto test
if /I "%CMD%"=="lint" goto lint
if /I "%CMD%"=="pre-commit" goto precommit
if /I "%CMD%"=="ollama-cpu" goto ollama
if /I "%CMD%"=="ollama-metal" goto ollama

echo Unknown target: %CMD%
echo.
goto help

:help
echo Audio Text Manager
echo.
echo   make.bat install       venv + dependencies (pytest, ruff, pre-commit)
echo   make.bat run           server  http://%HOST%:%PORT%/app/
echo   make.bat dev           same, with --reload
echo   make.bat test          pytest
echo   make.bat lint          ruff check backend tests
echo   make.bat pre-commit    install git hook (ruff on commit)
echo.
echo ffmpeg must be on PATH. Start Ollama (Start menu or: ollama serve).
echo Override host/port: set PORT=8001 ^&^& make.bat run
exit /b 0

:syspython
where py >nul 2>&1
if not errorlevel 1 (
  set "SYSPY=py -3"
  exit /b 0
)
where python >nul 2>&1
if not errorlevel 1 (
  set "SYSPY=python"
  exit /b 0
)
echo Python 3.10+ not found. Install from python.org and enable "Add python.exe to PATH".
exit /b 1

:ensure_venv
if exist "%VPY%" exit /b 0
call :syspython
if errorlevel 1 exit /b 1
%SYSPY% -m venv "%VENV%"
if errorlevel 1 exit /b 1
exit /b 0

:install
call :ensure_venv
if errorlevel 1 exit /b 1
"%VPY%" -m pip install -U pip
if errorlevel 1 exit /b 1
"%VPY%" -m pip install -e ".[dev]"
exit /b %ERRORLEVEL%

:ensure_uvicorn
call :ensure_venv
if errorlevel 1 exit /b 1
"%VPY%" -c "import uvicorn" >nul 2>&1
if errorlevel 1 call :install
exit /b %ERRORLEVEL%

:run
call :ensure_uvicorn
if errorlevel 1 exit /b 1
"%VPY%" -m uvicorn backend.app.main:app --host %HOST% --port %PORT%
exit /b %ERRORLEVEL%

:dev
call :ensure_uvicorn
if errorlevel 1 exit /b 1
"%VPY%" -m uvicorn backend.app.main:app --host %HOST% --port %PORT% --reload
exit /b %ERRORLEVEL%

:test
call :ensure_venv
if errorlevel 1 exit /b 1
"%VPY%" -c "import pytest" >nul 2>&1
if errorlevel 1 call :install
if errorlevel 1 exit /b 1
"%VPY%" -m pytest
exit /b %ERRORLEVEL%

:lint
call :ensure_venv
if errorlevel 1 exit /b 1
"%VPY%" -c "import ruff" >nul 2>&1
if errorlevel 1 call :install
if errorlevel 1 exit /b 1
"%VPY%" -m ruff check backend tests
exit /b %ERRORLEVEL%

:precommit
call :ensure_venv
if errorlevel 1 exit /b 1
"%VPY%" -c "import pre_commit" >nul 2>&1
if errorlevel 1 call :install
if errorlevel 1 exit /b 1
"%VPY%" -m pre_commit install
exit /b %ERRORLEVEL%

:ollama
echo macOS-only targets. On Windows start Ollama from the Start menu or run: ollama serve
exit /b 1
