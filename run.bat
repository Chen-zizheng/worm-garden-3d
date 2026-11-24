@echo off
rem Worms Garden Adventure 3D - launcher (Windows)
rem Requires Python 3.10+ with numpy + Pillow + pygame-ce available to "python".
rem A self-contained copy of the dependencies can also be dropped into vendor\.
setlocal
cd /d "%~dp0"
set PYTHONPATH=%~dp0vendor

set PY=python
if exist "%~dp0vendor\python.exe" set PY=%~dp0vendor\python.exe

echo starting Worms Garden Adventure 3D ...
"%PY%" main.py %*
if errorlevel 1 pause
