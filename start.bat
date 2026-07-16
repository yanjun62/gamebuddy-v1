@echo off
rem Game Buddy 一键启动（Windows 双击即可）
cd /d "%~dp0"
python start_buddy.py %*
pause
