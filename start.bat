@echo off
title Media Desk Studio
echo Starting Media Desk Studio Server on http://localhost:8000 ...
cd /d "%~dp0"
python server.py
pause

