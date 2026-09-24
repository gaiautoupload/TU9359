@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "PYTHON_EXE=C:\Users\pokem\anaconda3\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"

if not exist "%~dp0logs" mkdir "%~dp0logs"
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd"') do set "RUNDATE=%%i"
set "LOGFILE=%~dp0logs\update_%RUNDATE%.log"

echo [%date% %time%] Start TU9359 scheduled update>>"%LOGFILE%"
"%PYTHON_EXE%" -X utf8 "%~dp0scripts\scheduled_publish.py" >>"%LOGFILE%" 2>&1
set "RESULT=!ERRORLEVEL!"
if not "!RESULT!"=="0" (
  echo [%date% %time%] FAILED with exit code !RESULT!>>"%LOGFILE%"
  exit /b !RESULT!
)

echo [%date% %time%] Finished TU9359 scheduled update>>"%LOGFILE%"
exit /b 0
