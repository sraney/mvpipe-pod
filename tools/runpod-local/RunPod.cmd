@echo off
cd /d "%~dp0"
python "%~dp0runpod_local.py" %*
if errorlevel 1 pause
