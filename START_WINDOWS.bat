@echo off
cd /d "%~dp0"
where py >nul 2>nul && (py -3 selfmade_reader.py) || (python selfmade_reader.py)
pause
