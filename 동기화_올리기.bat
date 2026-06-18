@echo off
chcp 65001 >nul
REM ── 작업 끝난 후: 내 작업을 깃허브에 올리기 (add → commit → push) ──
cd /d "%~dp0"

echo [동기화] 먼저 최신 내용을 받아옵니다...
git pull
echo.

echo [변경된 파일]
git status -s
echo.

set /p msg="커밋 메시지를 입력하세요 (그냥 엔터=자동 메시지): "
if "%msg%"=="" set msg=update: 작업 내용 저장

git add -A
git commit -m "%msg%"
git push

if %errorlevel%==0 (
  echo.
  echo [완료] 깃허브에 올렸습니다. 다른 컴퓨터에서 [동기화_받기]로 받을 수 있어요.
) else (
  echo.
  echo [주의] 올리기에 문제가 있습니다. 메시지를 확인하세요.
)
echo.
pause
