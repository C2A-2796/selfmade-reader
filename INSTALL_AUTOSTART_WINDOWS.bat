@echo off
cd /d "%~dp0"
where py >nul 2>nul && (py -3 selfmade_reader.py --install-autostart) || (python selfmade_reader.py --install-autostart)
pause
