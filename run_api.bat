@echo off
cd /d "%~dp0"
if not exist logs mkdir logs
call "%~dp0venv\Scripts\activate.bat"
python "%~dp0run_api.py" >> "%~dp0logs\run_api.log" 2>&1
