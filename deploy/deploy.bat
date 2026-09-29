@echo off
REM ============================================================
REM  Terroir Atlas - Windows deploy entry (double-clickable)
REM
REM  Usage:  deploy.bat [options]
REM    (no arg)        full: build + smoke + sync + restart
REM    --skip-build    skip local build
REM    --dry-run       check only, do not touch the server
REM    --full          force full photos upload (no delta)
REM
REM  Real logic lives in deploy.local.sh (Git Bash script).
REM  This file only locates Git Bash and calls it.
REM
REM  NOTE: keep this file pure ASCII. Non-ASCII text in a .bat
REM  gets mangled on Chinese Windows (GBK vs UTF-8).
REM ============================================================

setlocal enabledelayedexpansion
set "HERE=%~dp0"
set "BASH_EXE="

if exist "%ProgramFiles%\Git\bin\bash.exe" set "BASH_EXE=%ProgramFiles%\Git\bin\bash.exe"
if not defined BASH_EXE if exist "%ProgramFiles(x86)%\Git\bin\bash.exe" set "BASH_EXE=%ProgramFiles(x86)%\Git\bin\bash.exe"
if not defined BASH_EXE if exist "%LOCALAPPDATA%\Programs\Git\bin\bash.exe" set "BASH_EXE=%LOCALAPPDATA%\Programs\Git\bin\bash.exe"
if not defined BASH_EXE if exist "%USERPROFILE%\.workbuddy\binaries\PortableGit\versions\1.2.0\bin\bash.exe" set "BASH_EXE=%USERPROFILE%\.workbuddy\binaries\PortableGit\versions\1.2.0\bin\bash.exe"

if not defined BASH_EXE (
  echo.
  echo [x] Git Bash not found.
  echo     Install Git for Windows: https://git-scm.com/download/win
  echo.
  pause
  exit /b 1
)

echo Using Git Bash: %BASH_EXE%
echo Deploy script : %HERE%deploy.local.sh
echo.

"%BASH_EXE%" "%HERE%deploy.local.sh" %*
set "RC=%ERRORLEVEL%"

echo.
if "%RC%"=="0" (
  echo [OK] Deploy finished.
) else (
  echo [x] Deploy FAILED, exit code %RC%. See errors above.
)
echo.
pause
exit /b %RC%
