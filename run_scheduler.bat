@echo off
chcp 65001 > nul
title 마케팁 OS — 자동입찰 스케줄러
echo.
echo ======================================
echo  Marketip Auto Bid Scheduler
echo ======================================
echo  BAT PATH: %~f0
echo  CURRENT DIR BEFORE CD: %CD%
cd /d C:\Users\COM\marketip-report
echo  CURRENT DIR AFTER CD:  %CD%
echo  PYTHON:
where python
echo ======================================
echo  - Supabase에서 자동입찰 ON 그룹 조회
echo  - 키워드별 순위 확인 및 입찰가 자동 조정
echo  - 종료: Ctrl+C
echo.
echo  [주의] 이 창을 닫으면 자동입찰이 중지됩니다.
echo.
python -X utf8 scheduler.py
echo.
echo ======================================
echo  Scheduler process ended.
echo ======================================
if errorlevel 1 (
    echo [오류] 실행 중 오류가 발생했습니다.
)
pause
