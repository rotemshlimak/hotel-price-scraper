@echo off
cd /d "%~dp0"
if not exist logs mkdir logs
call "%~dp0venv\Scripts\activate.bat"
python "%~dp0run.py" >> "%~dp0logs\run.log" 2>&1
