@echo off
cd /d "%~dp0"
python bus_tracker_app.py || py bus_tracker_app.py
pause