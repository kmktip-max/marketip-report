#!/usr/bin/env python3
"""
비즈머니 잔액 감시 CLI 스크립트
GitHub Actions 또는 서버 cron에서 실행됩니다.

광고주 정보는 clients.json(월간보고서 광고주 등록 데이터)에서 읽습니다.
알림 설정만 data/bizmoney_settings.json 에서 읽고 씁니다.

사용법:
  python scripts/check_bizmoney_alerts.py --dry-run     # 조회만, 발송 안 함
  python scripts/check_bizmoney_alerts.py --send        # 실제 알림톡 발송
  python scripts/check_bizmoney_alerts.py --customer 1234567  # 특정 광고주만
  python scripts/check_bizmoney_alerts.py list          # 광고주 목록
  python scripts/check_bizmoney_alerts.py history -n 30 # 발송 이력
"""

import argparse
import os
import sys
from datetime import datetime, timezone, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, ".env"))
except ImportError:
    pass

from bizmoney_alert import (
    get_merged_settings, save_from_merged,
    process_one, load_history,
)

KST = timezone(timedelta(hours=9))


def _log(msg: str):
    ts = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def cmd_check(dry_run: bool, customer_id: str | None):
    mode = "DRY-RUN" if dry_run else "SEND"
    _log(f"=== 비즈머니 알림 체크 시작 [{mode}] ===")

    merged = get_merged_settings()
    if not merged:
        _log("등록된 광고주 없음 (clients.json 확인 필요). 종료.")
        return

    if customer_id:
        targets = [s for s in merged if s.get("customer_id") == customer_id]
        if not targets:
            _log(f"Customer ID '{customer_id}' 를 찾을 수 없음. 종료.")
            return
        _log(f"대상: {len(targets)}개 (필터: {customer_id})")
    else:
        targets = [
            s for s in merged
            if s.get("alert_enabled", True)
            and s.get("api_access_license")
            and s.get("secret_key")
        ]
        _log(f"알림 활성 + API 설정 광고주: {len(targets)}개 / 전체 {len(merged)}개")

    total_sent = total_skip = total_fail = 0

    for s in targets:
        name = s.get("advertiser_name") or s.get("customer_id", "?")
        cid  = s.get("customer_id", "")
        _log(f"[{name}] CID={cid} 잔액 조회 중...")

        result  = process_one(s, dry_run=dry_run)
        balance = result.get("balance")
        if balance is None:
            _log(f"[{name}] 잔액 조회 실패")
            total_fail += 1
        else:
            _log(f"[{name}] 잔액: {balance:,}원")

        for action in result.get("actions", []):
            if action.get("type") == "balance_check":
                continue
            status = action.get("status", "")
            detail = action.get("detail", "")
            atype  = action.get("type", "")
            if status in ("success", "dry_run"):
                _log(f"  ✅ [{atype}] {detail}")
                total_sent += 1
            elif status == "skipped":
                _log(f"  ⏭️  [{atype}] {detail}")
                total_skip += 1
            else:
                _log(f"  ❌ [{atype}] {detail}")
                total_fail += 1

    if not dry_run:
        save_from_merged(merged)

    _log(
        f"=== 완료: 발송 {total_sent}건 / "
        f"건너뜀 {total_skip}건 / 실패 {total_fail}건 ==="
    )


def cmd_list():
    merged = get_merged_settings()
    if not merged:
        _log("광고주 없음.")
        return

    print(f"\n{'광고주명':<20} {'CID':<12} {'잔액':>12} {'알림':^5} "
          f"{'API':^5} {'1차':^5} {'2차':^5} {'최종조회'}")
    print("-" * 80)
    for s in merged:
        name  = (s.get("advertiser_name") or "—")[:18]
        cid   = (s.get("customer_id") or "—")[:10]
        bal   = s.get("last_bizmoney_balance")
        bal_s = f"{bal:,}" if bal is not None else "미조회"
        en    = "ON"  if s.get("alert_enabled")        else "OFF"
        api   = "✓"   if s.get("api_access_license")   else "✗"
        f1    = "✓"   if s.get("first_alert_sent")     else "—"
        f2    = "✓"   if s.get("second_alert_sent")    else "—"
        chk   = (s.get("last_checked_at") or "—")[:16].replace("T", " ")
        print(f"{name:<20} {cid:<12} {bal_s:>12} {en:^5} {api:^5} {f1:^5} {f2:^5} {chk}")
    print()


def cmd_history(n: int = 20):
    history = load_history()
    if not history:
        _log("발송 이력 없음.")
        return

    recent = list(reversed(history))[:n]
    print(f"\n{'발송시각':<20} {'광고주':<18} {'단계':<8} "
          f"{'잔액':>10} {'상태':<10} {'비고'}")
    print("-" * 85)
    for h in recent:
        ts    = h.get("sent_at", "—")[:16].replace("T", " ")
        name  = (h.get("advertiser_name") or "—")[:16]
        atype = "1차경고" if h.get("alert_type") == "first" else "소진"
        bal   = h.get("balance", 0)
        bal_s = f"{bal:,}" if bal is not None else "—"
        st    = h.get("status", "—")
        err   = (h.get("error_message") or "")[:30]
        print(f"{ts:<20} {name:<18} {atype:<8} {bal_s:>10} {st:<10} {err}")
    print()


def main():
    parser = argparse.ArgumentParser(description="비즈머니 잔액 감시 CLI")
    parser.add_argument("command",    nargs="?", default="check",
                        choices=["check", "list", "history"],
                        help="실행 명령 (기본: check)")
    parser.add_argument("--dry-run",  action="store_true",
                        help="조회만 하고 실제 발송하지 않음")
    parser.add_argument("--send",     action="store_true",
                        help="실제 알림톡 발송")
    parser.add_argument("--customer", metavar="CUSTOMER_ID",
                        help="특정 Customer ID만 처리")
    parser.add_argument("-n",         type=int, default=20,
                        help="history 출력 건수 (기본 20)")

    args    = parser.parse_args()
    dry_run = args.dry_run or not args.send

    if args.command == "list":
        cmd_list()
    elif args.command == "history":
        cmd_history(n=args.n)
    else:
        cmd_check(dry_run=dry_run, customer_id=args.customer)


if __name__ == "__main__":
    main()
