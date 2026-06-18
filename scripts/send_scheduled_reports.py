#!/usr/bin/env python3
"""월간보고서 예약/정기 발송 — GitHub Actions / 서버 cron용 CLI.

scheduler.py 의 run_scheduled_reports() 를 1회 실행한다.
(로컬 스케줄러 없이도 클라우드에서 PC 꺼진 채 자동 발송되게 하기 위함)

상태(예약 status / 정기발송 last_sent_date)는 Supabase에 저장되므로
GitHub Actions(상태 비휘발)에서도 중복 발송이 방지된다.

필요 env (GitHub Secrets):
  SMTP_USER, SMTP_PASSWORD, SMTP_HOST, SMTP_PORT
  SUPABASE_URL, SUPABASE_KEY   (스케줄 상태 로드/저장 — 중복발송 방지에 필수)
"""
import os
import sys
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, ".env"))
except ImportError:
    pass


def main():
    print("[정기발송] 월간보고서 스케줄 1회 실행 시작", flush=True)
    if not os.getenv("SMTP_USER") or not os.getenv("SMTP_PASSWORD"):
        print("[정기발송] ⚠ SMTP_USER/SMTP_PASSWORD 환경변수가 없습니다. "
              "GitHub Secrets 설정 필요.", flush=True)
    try:
        from scheduler import run_scheduled_reports
        run_scheduled_reports()
        print("[정기발송] 완료", flush=True)
    except Exception as e:
        print(f"[정기발송] 오류: {type(e).__name__}: {e}", flush=True)
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
