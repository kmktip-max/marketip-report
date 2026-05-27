#!/usr/bin/env python3
"""
비즈머니 잔액 감시 CLI 스크립트
GitHub Actions 또는 서버 cron에서 실행됩니다.

사용법:
  python scripts/check_bizmoney_alerts.py --dry-run   # 조회만, 실제 발송 안 함
  python scripts/check_bizmoney_alerts.py --send      # 실제 알림톡 발송
  python scripts/check_bizmoney_alerts.py --customer 1234567  # 특정 광고주만
"""

import argparse
import os
import sys
from datetime import datetime, timezone, timedelta

# 프로젝트 루트를 경로에 추가
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# dotenv 로드 (있으면)
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, ".env"))
except ImportError:
    pass

from bizmoney_alert import (
    load_settings, save_settings,
    process_one, load_history,
)

KST = timezone(timedelta(hours=9))


def _log(msg: str):
    ts = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def _mask(key: str) -> str:
    """API 키를 로그에 출력할 때 마스킹."""
    if not key:
        return "(없음)"
    return key[:4] + "****" + key[-4:]


def cmd_check(dry_run: bool, customer_id: str | None):
    """잔액 조회 + 알림 조건 판단 + 발송 (dry_run 시 발송 생략)."""
    mode = "DRY-RUN" if dry_run else "SEND"
    _log(f"=== 비즈머니 알림 체크 시작 [{mode}] ===")

    settings = load_settings()
    if not settings:
        _log("등록된 광고주 설정 없음. 종료.")
        return

    # 특정 광고주 필터
    if customer_id:
        targets = [s for s in settings if s.get("customer_id") == customer_id]
        if not targets:
            _log(f"Customer ID '{customer_id}' 설정 없음. 종료.")
            return
        _log(f"대상 광고주: {len(targets)}개 (필터: {customer_id})")
    else:
        targets = [s for s in settings if s.get("alert_enabled", True)]
        _log(f"알림 활성 광고주: {len(targets)}개 / 전체 {len(settings)}개")

    total_sent = 0
    total_skip = 0
    total_fail = 0

    for s in targets:
        name = s.get("advertiser_name", s.get("customer_id", "?"))
        cid  = s.get("customer_id", "")

        if not s.get("api_access_license") or not s.get("secret_key"):
            _log(f"[{name}] API 키 미설정 — 건너뜀")
            total_skip += 1
            continue

        _log(f"[{name}] CID={cid} 잔액 조회 중...")
        result = process_one(s, dry_run=dry_run)

        balance = result.get("balance")
        if balance is None:
            _log(f"[{name}] 잔액 조회 실패")
            total_fail += 1
        else:
            _log(f"[{name}] 잔액: {balance:,}원")

        for action in result.get("actions", []):
            atype  = action.get("type", "")
            status = action.get("status", "")
            detail = action.get("detail", "")

            if atype == "balance_check":
                continue
            elif status in ("success", "dry_run"):
                _log(f"  ✅ [{atype}] {detail}")
                total_sent += 1
            elif status == "skipped":
                _log(f"  ⏭️  [{atype}] {detail}")
                total_skip += 1
            else:
                _log(f"  ❌ [{atype}] {detail}")
                total_fail += 1

    # 변경된 settings 저장 (플래그 업데이트 포함)
    if not dry_run:
        save_settings(settings)

    _log(f"=== 완료: 발송 {total_sent}건 / 건너뜀 {total_skip}건 / 실패 {total_fail}건 ===")


def cmd_list():
    """등록된 광고주 목록 및 최신 잔액 출력."""
    settings = load_settings()
    if not settings:
        _log("등록된 광고주 없음.")
        return

    print(f"\n{'광고주명':<20} {'CID':<12} {'잔액':>12} {'알림':^6} {'1차':^6} {'2차':^6} {'최종조회'}")
    print("-" * 80)
    for s in settings:
        name  = s.get("advertiser_name", "—")[:18]
        cid   = s.get("customer_id", "—")[:10]
        bal   = s.get("last_bizmoney_balance")
        bal_s = f"{bal:,}" if bal is not None else "미조회"
        en    = "ON" if s.get("alert_enabled") else "OFF"
        f1    = "✓" if s.get("first_alert_sent")  else "—"
        f2    = "✓" if s.get("second_alert_sent") else "—"
        chk   = (s.get("last_checked_at") or "—")[:16].replace("T", " ")
        print(f"{name:<20} {cid:<12} {bal_s:>12} {en:^6} {f1:^6} {f2:^6} {chk}")
    print()


def cmd_history(n: int = 20):
    """최근 발송 이력 출력."""
    history = load_history()
    if not history:
        _log("발송 이력 없음.")
        return

    recent = list(reversed(history))[:n]
    print(f"\n{'발송시각':<20} {'광고주':<18} {'단계':<8} {'잔액':>10} {'상태':<10} {'비고'}")
    print("-" * 85)
    for h in recent:
        ts   = h.get("sent_at", "—")[:16].replace("T", " ")
        name = h.get("advertiser_name", "—")[:16]
        atype = "1차경고" if h.get("alert_type") == "first" else "소진"
        bal  = h.get("balance", 0)
        bal_s = f"{bal:,}" if bal is not None else "—"
        st   = h.get("status", "—")
        err  = h.get("error_message", "")[:30]
        print(f"{ts:<20} {name:<18} {atype:<8} {bal_s:>10} {st:<10} {err}")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="비즈머니 잔액 감시 & 알림톡 발송 CLI"
    )
    subparsers = parser.add_subparsers(dest="command")

    # check 명령 (기본)
    p_check = subparsers.add_parser("check", help="잔액 조회 및 알림 발송")
    p_check.add_argument("--dry-run", action="store_true",
                         help="조회만 하고 실제 발송하지 않음")
    p_check.add_argument("--send",    action="store_true",
                         help="실제 알림톡 발송")
    p_check.add_argument("--customer", metavar="CUSTOMER_ID",
                         help="특정 Customer ID만 처리")

    # list 명령
    subparsers.add_parser("list", help="광고주 목록 및 잔액 출력")

    # history 명령
    p_hist = subparsers.add_parser("history", help="발송 이력 출력")
    p_hist.add_argument("-n", type=int, default=20, help="출력 건수 (기본 20)")

    # 인수 없이 실행 시 --dry-run 호환
    # (python check_bizmoney_alerts.py --dry-run / --send 도 지원)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--send",    action="store_true")
    parser.add_argument("--customer", metavar="CUSTOMER_ID")

    args = parser.parse_args()

    # subcommand 없이 직접 --dry-run / --send 로 실행한 경우
    if args.command is None:
        dry = args.dry_run or not args.send
        cmd_check(dry_run=dry, customer_id=args.customer)
        return

    if args.command == "check":
        dry = args.dry_run or not args.send
        cmd_check(dry_run=dry, customer_id=args.customer)
    elif args.command == "list":
        cmd_list()
    elif args.command == "history":
        cmd_history(n=args.n)


if __name__ == "__main__":
    main()
