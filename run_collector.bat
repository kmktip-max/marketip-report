@echo off
chcp 65001 > nul
title 마케팁 OS — 로컬 수집기
cd /d "%~dp0"
python -X utf8 collector.py
pause
