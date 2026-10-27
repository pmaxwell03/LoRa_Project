@echo off
rem Double-click to start the buoy map (Windows). Opens it in your browser.
cd /d "%~dp0"
set PY=python
where py >nul 2>nul && set PY=py
if not exist data.db %PY% simulate.py
%PY% server.py
pause
