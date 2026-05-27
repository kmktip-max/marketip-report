"""
비즈머니 잔액 감시 & 카카오 알림톡 발송 코어 모듈
- get_bizmoney_balance()  : 네이버 검색광고 API 잔액 조회
- send_kakao_alerttalk()  : 알림톡 발송 (solapi provider 기본)
- run_check()             : 전체 광고주 순회 → 조건 판단 → 발송 → 이력 저장
"""

from __future__ import annotations

import hashlib
import hmac
import base64
import json
import os
import time
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

import requests

# ── 상수 ─────────────────────────────────────────────────────────────────────
KST       = timezone(timedelta(hours=9))
NAVER_BASE = "https://api.searchad.naver.com"

ROOT      = os.path.dirname(os.path.abspath(__file__))
F_SETTINGS = os.path.join(ROOT, "data", "bizmoney_settings.json")
F_HISTORY  = os.path.join(ROOT, "data", "bizmoney_alert_history.json")

os.makedirs(os.path.join(ROOT, "data"), exist_ok=True)


# ── 시크릿 로더 ───────────────────────────────────────────────────────────────
def _secret(key: str, default: str = "") -> str:
    try:
        import streamlit as st
        if hasattr(st, "secrets") and key in st.secrets:
            return str(st.secrets[key])
    except Exception:
        pass
    return os.getenv(key, default)


# ── JSON 폴백 저장소 ──────────────────────────────────────────────────────────
def _json_load(path: str, default=None):
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return default if default is not None else []


def _json_save(path: str, data) -> bool:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


# ── Supabase 래퍼 (db.py 재사용) ─────────────────────────────────────────────
def _sb_load(key: str, path: str):
    try:
        from db import sb_load
        result = sb_load(key, path)
        if result is not None:
            return result
    except Exception:
        pass
    return _json_load(path, [])


def _sb_save(key: str, data, path: str):
    try:
        from db import sb_save
        sb_save(key, data, path)
    except Exception:
        pass
    _json_save(path, data)


# ── 설정 로드/저장 ─────────────────────────────────────────────────────────────
def load_settings() -> list[dict]:
    return _sb_load("bizmoney_settings", F_SETTINGS) or []


def save_settings(data: list[dict]):
    _sb_save("bizmoney_settings", data, F_SETTINGS)


def load_history() -> list[dict]:
    return _sb_load("bizmoney_alert_history", F_HISTORY) or []


def save_history(data: list[dict]):
    _sb_save("bizmoney_alert_history", data, F_HISTORY)


def default_setting(advertiser_name: str = "", customer_id: str = "") -> dict:
    return {
        "id":                  str(uuid.uuid4())[:8],
        "advertiser_name":     advertiser_name,
        "customer_id":         customer_id,
        "api_access_license":  "",
        "secret_key":          "",
        "manager_name":        "",
        "manager_phone":       "",
        "advertiser_phone":    "",
        "alert_enabled":       True,
        "first_alert_amount":  50000,
        "second_alert_amount": 0,
        "first_alert_sent":    False,
        "second_alert_sent":   False,
        "last_bizmoney_balance": None,
        "last_checked_at":     None,
        "memo":                "",
    }


# ── 네이버 API 인증 헬퍼 ──────────────────────────────────────────────────────
def _naver_sign(timestamp: str, method: str, path: str, secret_key: str) -> str:
    msg = f"{timestamp}.{method}.{path}"
    return base64.b64encode(
        hmac.new(secret_key.encode(), msg.encode(), hashlib.sha256).digest()
    ).decode()


def _naver_headers(method: str, path: str,
                   api_key: str, secret_key: str, customer_id: str) -> dict:
    ts = str(int(time.time() * 1000))
    return {
        "Content-Type": "application/json; charset=UTF-8",
        "X-Timestamp":  ts,
        "X-API-KEY":    api_key,
        "X-Customer":   str(customer_id),
        "X-Signature":  _naver_sign(ts, method, path, secret_key),
    }


# ── 비즈머니 잔액 조회 ─────────────────────────────────────────────────────────
def get_bizmoney_balance(customer_id: str,
                         api_access_license: str,
                         secret_key: str) -> dict:
    """
    네이버 검색광고 API로 비즈머니 잔액을 조회합니다.
    반환: {"customer_id", "balance", "checked_at", "status"} 또는 에러 포함
    """
    path = "/billing/account/balance/bizmoney"
    checked_at = datetime.now(KST).isoformat()

    if not api_access_license or not secret_key or not customer_id:
        return {
            "customer_id": customer_id,
            "balance":     None,
            "checked_at":  checked_at,
            "status":      "failed",
            "error":       "API 키 또는 Customer ID 누락",
        }

    try:
        headers = _naver_headers(
            "GET", path, api_access_license, secret_key, customer_id
        )
        resp = requests.get(
            NAVER_BASE + path, headers=headers, timeout=15
        )

        if resp.status_code == 401:
            return {
                "customer_id": customer_id,
                "balance":     None,
                "checked_at":  checked_at,
                "status":      "failed",
                "error":       "인증 실패 (401) — API 키 또는 서명 오류",
            }
        if resp.status_code == 403:
            return {
                "customer_id": customer_id,
                "balance":     None,
                "checked_at":  checked_at,
                "status":      "failed",
                "error":       "권한 없음 (403) — Customer ID 확인 필요",
            }

        resp.raise_for_status()
        data = resp.json()

        # 응답 구조: {"bizmoney": {"availBudgetAmt": 123456, ...}}
        bizmoney = data.get("bizmoney") or data
        balance = (
            bizmoney.get("availBudgetAmt")
            or bizmoney.get("balance")
            or bizmoney.get("cashBalance")
            or 0
        )

        return {
            "customer_id": customer_id,
            "balance":     int(balance),
            "checked_at":  checked_at,
            "status":      "success",
        }

    except requests.HTTPError as e:
        return {
            "customer_id": customer_id,
            "balance":     None,
            "checked_at":  checked_at,
            "status":      "failed",
            "error":       f"HTTP {e.response.status_code}: {e.response.text[:200]}",
        }
    except Exception as e:
        return {
            "customer_id": customer_id,
            "balance":     None,
            "checked_at":  checked_at,
            "status":      "failed",
            "error":       str(e)[:300],
        }


# ── 카카오 알림톡 발송 (provider 추상화) ─────────────────────────────────────
def send_kakao_alerttalk(
    phone: str,
    template_code: str,
    variables: dict,
    provider: str = "solapi",
    dry_run: bool = False,
) -> dict:
    """
    카카오 알림톡 발송.
    dry_run=True 이면 실제 발송 없이 결과만 반환.

    필요한 환경변수/secrets:
      SOLAPI_API_KEY, SOLAPI_API_SECRET, SOLAPI_SENDER_ID  (provider=solapi)
    """
    if dry_run:
        return {
            "status":   "dry_run",
            "phone":    phone,
            "template": template_code,
            "vars":     variables,
            "provider": provider,
        }

    if provider == "solapi":
        return _send_solapi(phone, template_code, variables)
    else:
        return {
            "status": "failed",
            "error":  f"지원하지 않는 provider: {provider}",
        }


def _send_solapi(phone: str, template_code: str, variables: dict) -> dict:
    """Solapi(구 메시지허브) 알림톡 발송."""
    api_key    = _secret("SOLAPI_API_KEY")
    api_secret = _secret("SOLAPI_API_SECRET")
    sender_id  = _secret("SOLAPI_SENDER_ID")   # 카카오채널 발신자ID

    if not api_key or not api_secret or not sender_id:
        missing = [k for k, v in {
            "SOLAPI_API_KEY":    api_key,
            "SOLAPI_API_SECRET": api_secret,
            "SOLAPI_SENDER_ID":  sender_id,
        }.items() if not v]
        return {
            "status": "skipped",
            "error":  f"알림톡 설정 없음 — 미설정 키: {', '.join(missing)}",
        }

    # Solapi HMAC 인증
    date_str  = datetime.now(KST).strftime("%Y-%m-%dT%H:%M:%S+09:00")
    salt      = str(uuid.uuid4()).replace("-", "")
    signature = hmac.new(
        api_secret.encode(),
        f"{date_str}{salt}".encode(),
        hashlib.sha256,
    ).hexdigest()

    headers = {
        "Authorization": (
            f'HMAC-SHA256 apiKey={api_key}, date={date_str}, '
            f'salt={salt}, signature={signature}'
        ),
        "Content-Type": "application/json; charset=UTF-8",
    }

    # 변수 → 알림톡 치환자 형식 변환
    content = template_code
    for k, v in variables.items():
        content = content.replace(f"#{{{k}}}", str(v))

    payload = {
        "message": {
            "to":          phone.replace("-", ""),
            "from":        sender_id,
            "kakaoOptions": {
                "pfId":        sender_id,
                "templateId":  template_code,
                "variables":   {f"#{{{k}}}": str(v) for k, v in variables.items()},
            },
        }
    }

    try:
        resp = requests.post(
            "https://api.solapi.com/messages/v4/send",
            headers=headers,
            json=payload,
            timeout=15,
        )
        resp.raise_for_status()
        return {"status": "success", "response": resp.json()}
    except requests.HTTPError as e:
        return {
            "status": "failed",
            "error":  f"HTTP {e.response.status_code}: {e.response.text[:300]}",
        }
    except Exception as e:
        return {"status": "failed", "error": str(e)[:300]}


# ── 알림 템플릿 ───────────────────────────────────────────────────────────────
TEMPLATE_FIRST = (
    "[마케팁 광고비 잔액 안내]\n"
    "#{광고주명}님의 광고 계정 비즈머니 잔액이 #{현재잔액}원입니다.\n"
    "광고 노출 중단 방지를 위해 충전을 권장드립니다.\n"
    "기준금액: #{기준금액}원\n"
    "담당자: #{담당자명} (#{문의연락처})"
)

TEMPLATE_DEPLETED = (
    "[마케팁 광고비 소진 안내]\n"
    "#{광고주명}님의 광고 계정 비즈머니가 소진되었습니다.\n"
    "광고 노출이 중단될 수 있으니 빠른 충전이 필요합니다.\n"
    "현재 잔액: #{현재잔액}원\n"
    "담당자: #{담당자명} (#{문의연락처})"
)

TEMPLATE_CODE_FIRST    = "BM_ALERT_FIRST"
TEMPLATE_CODE_DEPLETED = "BM_ALERT_DEPLETED"


def _build_vars(s: dict, balance: int, threshold: int) -> dict:
    return {
        "광고주명":   s.get("advertiser_name", ""),
        "현재잔액":   f"{balance:,}",
        "기준금액":   f"{threshold:,}",
        "담당자명":   s.get("manager_name", ""),
        "문의연락처": s.get("manager_phone", ""),
    }


# ── 발송 이력 기록 ─────────────────────────────────────────────────────────────
def _record_history(
    s: dict, phone: str, alert_type: str,
    balance: int, threshold: int,
    result: dict,
):
    history = load_history()
    history.append({
        "id":               str(uuid.uuid4())[:12],
        "advertiser_name":  s.get("advertiser_name", ""),
        "customer_id":      s.get("customer_id", ""),
        "phone":            phone,
        "alert_type":       alert_type,
        "balance":          balance,
        "threshold_amount": threshold,
        "sent_at":          datetime.now(KST).isoformat(),
        "status":           result.get("status", "unknown"),
        "provider":         result.get("provider", "solapi"),
        "error_message":    result.get("error", ""),
    })
    # 최근 500건만 유지
    if len(history) > 500:
        history = history[-500:]
    save_history(history)


# ── 중복 발송 체크 ─────────────────────────────────────────────────────────────
def _already_sent_today(history: list[dict],
                         customer_id: str, alert_type: str) -> bool:
    today = datetime.now(KST).strftime("%Y-%m-%d")
    for h in reversed(history):
        if (h.get("customer_id") == customer_id
                and h.get("alert_type") == alert_type
                and h.get("sent_at", "")[:10] == today
                and h.get("status") == "success"):
            return True
    return False


# ── 단일 광고주 알림 처리 ──────────────────────────────────────────────────────
def process_one(s: dict, dry_run: bool = False) -> dict:
    """
    한 광고주의 잔액을 조회하고 조건에 따라 알림을 발송합니다.
    반환: {"customer_id", "balance", "actions": [...]}
    """
    cid     = s.get("customer_id", "")
    actions = []

    # 잔액 조회
    result = get_bizmoney_balance(
        cid,
        s.get("api_access_license", ""),
        s.get("secret_key", ""),
    )

    balance = result.get("balance")
    actions.append({
        "type":   "balance_check",
        "status": result["status"],
        "detail": result.get("error", f"잔액: {balance:,}원" if balance is not None else ""),
    })

    if result["status"] != "success" or balance is None:
        return {"customer_id": cid, "balance": None, "actions": actions}

    history = load_history()

    # 잔액 충전 → 알림 플래그 리셋
    first_amt  = int(s.get("first_alert_amount",  50000))
    second_amt = int(s.get("second_alert_amount", 0))

    if balance > first_amt:
        if s.get("first_alert_sent") or s.get("second_alert_sent"):
            s["first_alert_sent"]  = False
            s["second_alert_sent"] = False
            actions.append({"type": "reset", "detail": "잔액 충전 감지 → 알림 플래그 리셋"})

    phones = []
    if s.get("advertiser_phone"): phones.append(s["advertiser_phone"])
    if s.get("manager_phone"):    phones.append(s["manager_phone"])
    # 중복 번호 제거
    phones = list(dict.fromkeys(phones))

    def _send(alert_type: str, template_code: str, threshold: int):
        for phone in phones:
            if _already_sent_today(history, cid, alert_type):
                actions.append({
                    "type": alert_type, "status": "skipped",
                    "detail": f"{phone} — 오늘 이미 발송됨",
                })
                continue
            vars_ = _build_vars(s, balance, threshold)
            r = send_kakao_alerttalk(phone, template_code, vars_, dry_run=dry_run)
            actions.append({
                "type": alert_type, "status": r.get("status"),
                "detail": r.get("error", f"{phone} 발송"),
            })
            _record_history(s, phone, alert_type, balance, threshold, r)

    # 2차 알림 (소진)
    if balance <= second_amt and not s.get("second_alert_sent"):
        _send("depleted", TEMPLATE_CODE_DEPLETED, second_amt)
        s["second_alert_sent"] = True
        s["first_alert_sent"]  = True  # 1차도 함께 처리된 것으로 표시

    # 1차 알림 (경고)
    elif balance <= first_amt and not s.get("first_alert_sent"):
        _send("first", TEMPLATE_CODE_FIRST, first_amt)
        s["first_alert_sent"] = True

    # 잔액·시간 업데이트
    s["last_bizmoney_balance"] = balance
    s["last_checked_at"]       = result["checked_at"]

    return {"customer_id": cid, "balance": balance, "actions": actions}


# ── 전체 실행 ──────────────────────────────────────────────────────────────────
def run_check(dry_run: bool = False) -> list[dict]:
    """
    등록된 모든 광고주를 순회해 잔액 조회 및 알림 발송.
    settings를 업데이트 후 저장합니다.
    """
    settings = load_settings()
    results  = []

    for s in settings:
        if not s.get("alert_enabled", True):
            continue
        if not s.get("api_access_license") or not s.get("secret_key"):
            continue
        res = process_one(s, dry_run=dry_run)
        results.append(res)

    save_settings(settings)
    return results
