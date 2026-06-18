# marketip-report

네이버 광고 대행 운영을 위한 **마케팅 리포트 자동화 도구** (Streamlit 웹앱).

## 스택
- **Streamlit** (웹 UI) + **Supabase** (DB / 스토리지 / 인증)
- **Playwright + stealth** — 네이버 광고 데이터 스크래핑
- **OpenAI** — 리포트 분석/생성
- **APScheduler** — 보고서 자동 정기발송
- PDF/엑셀 생성(fpdf2, openpyxl), 차트(plotly, matplotlib)

## 구조
- `app.py` — 메인 진입점
- `pages/` — 16개 화면 (광고주관리, 자동입찰, 부정클릭관리, 월간보고서, 정산관리, 페이백신청 등)
- `collector.py` — 데이터 수집 / `rank_checker.py` — 순위 체크
- `bizmoney_alert.py` — 비즈머니 알림 / `notifications.py` — 알림(카카오 알림톡 등)
- `scheduler.py` — 보고서 자동발송 / `report_engine/` — 리포트 생성
- `auth.py` — 인증 / `db.py` — DB 접근
- `utils/`, `components/`, `fraud/`, `static/`, `data/`

## 실행
```bash
pip install -r requirements.txt
playwright install
streamlit run app.py    # 또는 run_streamlit.bat
```
환경변수는 `.env`에 설정 (`.env.example` 참고). **`.env`는 git에 올리지 않음** — 컴퓨터마다 따로 둬야 함.

## 작업 흐름 (데스크탑 ↔ 노트북 동기화)
이 프로젝트는 데스크탑과 노트북 두 곳에서 작업하며 GitHub로 동기화한다.
- **작업 시작 전:** `git pull` (또는 `동기화_받기.bat`)
- **작업 끝난 후:** `git add -A && git commit && git push` (또는 `동기화_올리기.bat`)
- 한쪽에서 push를 안 한 채 다른 쪽에서 같은 파일을 고치면 충돌이 나므로, **끝나면 바로 push**.

## 메모
- README 대신 이 파일이 프로젝트 안내 역할.
- 커밋 메시지는 한글 + `feat:/fix:/style:/perf:` 접두어 관례 사용.
