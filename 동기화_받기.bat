@echo off
chcp 65001 >nul
REM ── 작업 시작 전: 깃허브에서 최신 내용 받아오기 (pull) ──
cd /d "%~dp0"
echo [동기화] 깃허브에서 최신 내용을 받아옵니다...
git pull
if %errorlevel%==0 (
  echo.
  echo [완료] 최신 상태입니다. 이제 작업을 시작하세요.
) else (
  echo.
  echo [주의] 받아오기에 문제가 있습니다. 충돌이 있을 수 있으니 확인하세요.
)
echo.
pause
