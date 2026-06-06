@echo off
chcp 65001 > nul
title 마케팁 OS — Streamlit 앱
echo.
echo ======================================
echo  MarketIP OS - Streamlit App
echo ======================================
cd /d C:\Users\COM\marketip-report

REM 기존 8501 포트 프로세스 종료
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8501 "') do (
    taskkill /F /PID %%a >nul 2>&1
)

echo  Starting Streamlit...
echo  URL: http://localhost:8501
echo  종료: Ctrl+C 또는 창 닫기
echo ======================================
echo.

python -m streamlit run app.py
pause
