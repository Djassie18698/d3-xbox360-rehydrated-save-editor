@echo off
rem Diablo III (Xbox 360, 2013) save editor for Rehydrated. Close the game first.
where pythonw >nul 2>nul
if errorlevel 1 (
    echo Python 3.10 or newer is needed: https://www.python.org/downloads/
    pause
    exit /b 1
)
start "" pythonw "%~dp0editor.py"
