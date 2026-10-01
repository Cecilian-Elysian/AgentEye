@echo off
rem AgentEye launcher. Tries .venv first, then pythonw, then py -3w, and
rem finally prints actionable advice instead of failing silently with no
rem window.

chcp 65001 >nul

set "MAIN=%~dp0main.py"
set "VENVW=%~dp0.venv\Scripts\pythonw.exe"

rem Project venv wins: it is the environment the developer actually tested.
if exist "%VENVW%" (
    start "" "%VENVW%" "%MAIN%"
    exit /b 0
)

where pythonw >nul 2>nul
if %ERRORLEVEL%==0 (
    start "" pythonw "%MAIN%"
    exit /b 0
)

where py >nul 2>nul
if %ERRORLEVEL%==0 (
    start "" py -3w "%MAIN%"
    exit /b 0
)

echo Python was not found, AgentEye cannot start.
echo.
echo Pick one:
echo   1. Reinstall Python and tick "Add python.exe to PATH"
echo   2. Or append the Python install dir to your PATH
echo   3. Or run  python "%MAIN%"  in a terminal to see the error
echo.
echo Note: if the requests package is missing, run:
echo   pip install -r "%~dp0requirements.txt"
echo.
pause
exit /b 1
