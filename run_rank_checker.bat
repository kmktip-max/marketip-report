@echo off
chcp 65001 > nul
title 마케팁 OS — 네이버 순위 조회기
echo.
echo  마케팁 OS - 네이버 파워링크 순위 조회기
echo  ==========================================
echo  실행 전 확인사항:
echo    1. [그룹 관리] 탭에서 그룹에 '검색 도메인' 설정
echo    2. 인터넷 연결 확인
echo.
python -X utf8 rank_checker.py
if errorlevel 1 (
    echo.
    echo [오류] 실행 중 오류가 발생했습니다.
    pause
)
