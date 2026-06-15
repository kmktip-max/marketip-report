"""
비즈머니 잔액 감시 & 카카오 알림톡 발송 코어 모듈

광고주 정보(customer_id, api_key, secret_key, name)는
기존 report_engine/storage.py (clients.json) 에서 읽습니다.

비즈머니 알림 전용 설정(기준금액, 연락처, 발송 플래그 등)만
data/bizmoney_settings.json 에 별도 저장합니다.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import time
import uuid
from datetime import datetime, timedelta, timezone

import requests

# ── 상수 ──────────────────────────────────────────────────────────────────────
KST        = timezone(timedelta(hours=9))
NAVER_BASE = "https://api.searchad.naver.com"

ROOT       = os.path.dirname(os.path.abspath(__file__))
F_SETTINGS = os.path.join(ROOT, "data", "bizmoney_settings.json")
F_HISTORY  = os.path.join(ROOT, "data", "bizmoney_alert_history.json")

os.makedirs(os.path.join(ROOT, "data"), exist_ok=True)

# 알림 설정에서 저장할 필드 목록 (API 키·광고주명 제외)
_ALERT_FIELDS = (
    "customer_id", "alert_enabled",
    "first_alert_amount", "second_alert_amount",
    "first_alert_sent", "second_alert_sent",
    "advertiser_phone", "manager_name", "manager_phone",
    "last_bizmoney_balance", "last_checked_at", "memo",
)


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


# ── 광고주 목록 로드 (기존 저장소 재사용) ─────────────────────────────────────
def load_clients() -> list[dict]:
    """
    월간보고서에서 등록한 광고주 목록을 반환합니다.
    report_engine/storage.py → 실패 시 clients.json 직접 읽기
    """
    try:
        from report_engine.storage import load_clients as _load
        result = _load()
        if result:
            return result
    except Exception:
        pass
    return _json_load(os.path.join(ROOT, "clients.json"), [])


# ── 알림 설정 로드/저장 ────────────────────────────────────────────────────────
def _load_alert_map() -> dict[str, dict]:
    """customer_id → 알림 설정 딕셔너리."""
    items = _sb_load("bizmoney_settings", F_SETTINGS) or []
    return {s["customer_id"]: s for s in items if "customer_id" in s}


def _save_alert_map(alert_map: dict[str, dict]):
    items = list(alert_map.values())
    _sb_save("bizmoney_settings", items, F_SETTINGS)


def _default_alert(customer_id: str = "") -> dict:
    return {
        "customer_id":           customer_id,
        "alert_enabled":         True,
        "first_alert_amount":    50000,
        "second_alert_amount":   0,
        "first_alert_sent":      False,
        "second_alert_sent":     False,
        "advertiser_phone":      "",
        "manager_name":          "",
        "manager_phone":         "",
        "last_bizmoney_balance": None,
        "last_checked_at":       None,
        "memo":                  "",
    }


# ── 병합 뷰 (UI/run_check 공통 사용) ──────────────────────────────────────────
def get_merged_settings() -> list[dict]:
    """
    기존 광고주 목록 + 비즈머니 알림 설정 병합.
    API 키/Customer ID 는 clients.json 에서,
    알림 설정은 bizmoney_settings.json 에서 읽습니다.
    """
    clients   = load_clients()
    alert_map = _load_alert_map()

    merged = []
    for c in clients:
        cid = str(c.get("customer_id", "")).strip()
        if not cid:
            continue
        alert = alert_map.get(cid, _default_alert(cid))
        merged.append({
            # 광고주 정보 (읽기 전용, clients.json)
            "advertiser_name":     c.get("name", ""),
            "customer_id":         cid,
            "owner":               c.get("owner", ""),
            "api_access_license":  c.get("api_key", ""),
            "secret_key":          c.get("secret_key", ""),
            "client_email":        c.get("email", ""),
            # 알림 설정 (편집 가능, bizmoney_settings.json)
            "alert_enabled":          alert.get("alert_enabled",         True),
            "first_alert_amount":     alert.get("first_alert_amount",    50000),
            "second_alert_amount":    alert.get("second_alert_amount",   0),
            "first_alert_sent":       alert.get("first_alert_sent",      False),
            "second_alert_sent":      alert.get("second_alert_sent",     False),
            # 광고주 연락처는 월간보고서(clients.json)의 phone 을 기본값으로 자동 사용
            "advertiser_phone":       alert.get("advertiser_phone") or c.get("phone", "") or "",
            "manager_name":           alert.get("manager_name",          ""),
            "manager_phone":          alert.get("manager_phone",         ""),
            "last_bizmoney_balance":  alert.get("last_bizmoney_balance", None),
            "last_checked_at":        alert.get("last_checked_at",       None),
            "memo":                   alert.get("memo",                  ""),
        })
    return merged


def save_from_merged(merged_list: list[dict]):
    """병합된 설정 리스트에서 알림 설정만 추출해 저장합니다."""
    alert_map = {}
    for s in merged_list:
        cid = s.get("customer_id", "")
        if not cid:
            continue
        alert_map[cid] = {f: s.get(f) for f in _ALERT_FIELDS}
    _save_alert_map(alert_map)


def save_one_alert(s: dict):
    """단일 광고주 알림 설정만 저장합니다 (병합 뷰의 일부)."""
    cid = s.get("customer_id", "")
    if not cid:
        return
    alert_map = _load_alert_map()
    alert_map[cid] = {f: s.get(f) for f in _ALERT_FIELDS}
    _save_alert_map(alert_map)


# ── 발송 이력 ─────────────────────────────────────────────────────────────────
def load_history() -> list[dict]:
    return _sb_load("bizmoney_alert_history", F_HISTORY) or []


def save_history(data: list[dict]):
    _sb_save("bizmoney_alert_history", data, F_HISTORY)


# ── 네이버 API 인증 ───────────────────────────────────────────────────────────
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


# ── SOLAPI 설정 상태 조회 (값 미노출) ─────────────────────────────────────────
def get_solapi_config_status() -> dict[str, bool]:
    """SOLAPI 환경변수 설정 여부를 반환합니다. 값은 노출하지 않습니다."""
    keys = ("SOLAPI_API_KEY", "SOLAPI_API_SECRET", "SOLAPI_SENDER_ID", "SOLAPI_KAKAO_PF_ID")
    return {k: bool(_secret(k)) for k in keys}


# ── 비즈머니 잔액 조회 ─────────────────────────────────────────────────────────
def get_bizmoney_balance(customer_id: str,
                         api_access_license: str,
                         secret_key: str) -> dict:
    """
    네이버 검색광고 API로 비즈머니 잔액을 조회합니다.
    반환: {"customer_id", "balance", "checked_at", "status", "endpoint", "status_code"}
    """
    path       = "/billing/bizmoney"
    checked_at = datetime.now(KST).isoformat()

    if not api_access_license or not secret_key or not customer_id:
        return {
            "customer_id": customer_id,
            "balance":     None,
            "checked_at":  checked_at,
            "status":      "failed",
            "error":       "API 키 또는 Customer ID 누락",
            "endpoint":    path,
        }

    try:
        headers = _naver_headers(
            "GET", path, api_access_license, secret_key, customer_id
        )
        resp = requests.get(NAVER_BASE + path, headers=headers, timeout=15)
        sc   = resp.status_code
        body = resp.text[:400] if resp.text else "(empty)"

        if sc == 401:
            return {"customer_id": customer_id, "balance": None,
                    "checked_at": checked_at, "status": "failed",
                    "status_code": 401, "endpoint": path,
                    "error": f"인증 실패 (401) — API 키 또는 서명 오류\n응답: {body}"}
        if sc == 403:
            return {"customer_id": customer_id, "balance": None,
                    "checked_at": checked_at, "status": "failed",
                    "status_code": 403, "endpoint": path,
                    "error": f"권한 없음 (403) — Customer ID 확인 필요\n응답: {body}"}
        if sc == 404:
            return {"customer_id": customer_id, "balance": None,
                    "checked_at": checked_at, "status": "failed",
                    "status_code": 404, "endpoint": path,
                    "error": (
                        f"경로 없음 (404) — 해당 계정에서 잔액 조회 API를 지원하지 않거나 "
                        f"경로가 잘못되었을 수 있습니다.\n"
                        f"호출 경로: GET {NAVER_BASE}{path}\n"
                        f"응답: {body}"
                    )}

        resp.raise_for_status()
        data    = resp.json()
        # 응답: {"customerId":..., "bizmoney":752.87, "budgetLock":..., ...}
        balance = data.get("bizmoney") or 0
        return {"customer_id": customer_id, "balance": int(balance),
                "checked_at": checked_at, "status": "success",
                "status_code": 200, "endpoint": path}

    except requests.HTTPError as e:
        sc   = e.response.status_code
        body = e.response.text[:400] if e.response.text else "(empty)"
        return {"customer_id": customer_id, "balance": None,
                "checked_at": checked_at, "status": "failed",
                "status_code": sc, "endpoint": path,
                "error": f"HTTP {sc}: {body}"}
    except Exception as e:
        return {"customer_id": customer_id, "balance": None,
                "checked_at": checked_at, "status": "failed",
                "endpoint": path,
                "error": str(e)[:300]}


# ── 단순 SMS 발송 (템플릿 불필요) ────────────────────────────────────────────
def send_sms_notification(to_phone: str, text: str) -> dict:
    """관리자 SMS 알림. 알림톡 템플릿 없이 즉시 사용 가능."""
    api_key    = _secret("SOLAPI_API_KEY")
    api_secret = _secret("SOLAPI_API_SECRET")
    sender_id  = _secret("SOLAPI_SENDER_ID")

    if not api_key or not api_secret or not sender_id:
        return {"status": "skipped", "error": "SOLAPI 미설정"}
    if not to_phone:
        return {"status": "skipped", "error": "수신번호 없음"}

    date_str  = datetime.now(KST).strftime("%Y-%m-%dT%H:%M:%S+09:00")
    salt      = str(uuid.uuid4()).replace("-", "")
    signature = hmac.new(
        api_secret.encode(), f"{date_str}{salt}".encode(), hashlib.sha256
    ).hexdigest()

    headers = {
        "Authorization": (
            f'HMAC-SHA256 apiKey={api_key}, date={date_str}, '
            f'salt={salt}, signature={signature}'
        ),
        "Content-Type": "application/json; charset=UTF-8",
    }
    payload = {
        "message": {
            "to":   to_phone.replace("-", ""),
            "from": sender_id.replace("-", ""),
            "text": text,
        }
    }
    try:
        resp = requests.post(
            "https://api.solapi.com/messages/v4/send",
            headers=headers, json=payload, timeout=15,
        )
        resp.raise_for_status()
        return {"status": "success", "response": resp.json()}
    except requests.HTTPError as e:
        return {"status": "failed",
                "error": f"HTTP {e.response.status_code}: {e.response.text[:200]}"}
    except Exception as e:
        return {"status": "failed", "error": str(e)[:200]}


# ── 카카오 알림톡 ─────────────────────────────────────────────────────────────
def send_kakao_alerttalk(
    phone: str,
    template_code: str,
    variables: dict,
    provider: str = "solapi",
    dry_run: bool = False,
) -> dict:
    if dry_run:
        preview = template_code
        for k, v in variables.items():
            preview = preview.replace(f"#{{{k}}}", str(v))
        return {
            "status":       "dry_run",
            "phone":        phone,
            "template":     template_code,
            "vars":         variables,
            "preview_text": preview,
        }
    if provider == "solapi":
        return _send_solapi(phone, template_code, variables)
    return {"status": "failed", "error": f"지원하지 않는 provider: {provider}"}


def _send_solapi(phone: str, template_code: str, variables: dict) -> dict:
    api_key    = _secret("SOLAPI_API_KEY")
    api_secret = _secret("SOLAPI_API_SECRET")
    sender_id  = _secret("SOLAPI_SENDER_ID")
    pf_id      = _secret("SOLAPI_KAKAO_PF_ID")   # 카카오채널 프로필 ID

    required = {"SOLAPI_API_KEY": api_key, "SOLAPI_API_SECRET": api_secret,
                "SOLAPI_SENDER_ID": sender_id}
    missing  = [k for k, v in required.items() if not v]
    if missing:
        return {"status": "skipped",
                "error": f"알림톡 설정 없음 — 미설정 키: {', '.join(missing)}"}

    date_str  = datetime.now(KST).strftime("%Y-%m-%dT%H:%M:%S+09:00")
    salt      = str(uuid.uuid4()).replace("-", "")
    signature = hmac.new(
        api_secret.encode(), f"{date_str}{salt}".encode(), hashlib.sha256
    ).hexdigest()

    headers = {
        "Authorization": (
            f'HMAC-SHA256 apiKey={api_key}, date={date_str}, '
            f'salt={salt}, signature={signature}'
        ),
        "Content-Type": "application/json; charset=UTF-8",
    }

    # pfId 없으면 SMS로 fallback
    if pf_id:
        msg = {
            "to":   phone.replace("-", ""),
            "from": sender_id,
            "kakaoOptions": {
                "pfId":       pf_id,
                "templateId": template_code,
                "variables":  {f"#{{{k}}}": str(v) for k, v in variables.items()},
            },
        }
    else:
        # 알림톡 채널 미설정 → SMS 발송
        text = template_code  # 호출 측에서 실제 메시지 본문을 넘겨야 함
        for k, v in variables.items():
            text = text.replace(f"#{{{k}}}", str(v))
        msg = {
            "to":   phone.replace("-", ""),
            "from": sender_id,
            "text": text,
        }

    payload = {"message": msg}
    try:
        resp = requests.post(
            "https://api.solapi.com/messages/v4/send",
            headers=headers, json=payload, timeout=15,
        )
        resp.raise_for_status()
        return {"status": "success", "response": resp.json()}
    except requests.HTTPError as e:
        return {"status": "failed",
                "error": f"HTTP {e.response.status_code}: {e.response.text[:300]}"}
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


def check_template_vars(template_text: str, variables: dict) -> list:
    """템플릿 텍스트의 #{변수명} 패턴 중 variables에 없는 누락 키 목록 반환"""
    required = set(re.findall(r'#\{([^}]+)\}', template_text))
    return sorted(required - set(variables.keys()))


# ── 발송 이력 기록 ─────────────────────────────────────────────────────────────
def _record_history(s: dict, phone: str, alert_type: str,
                    balance: int, threshold: int, result: dict):
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
    if len(history) > 500:
        history = history[-500:]
    save_history(history)


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


# ── 단일 광고주 처리 ──────────────────────────────────────────────────────────
def process_one(s: dict, dry_run: bool = False) -> dict:
    """잔액 조회 → 알림 조건 판단 → 발송. s 는 get_merged_settings() 의 항목."""
    cid     = s.get("customer_id", "")
    actions = []

    result  = get_bizmoney_balance(
        cid, s.get("api_access_license", ""), s.get("secret_key", "")
    )
    balance = result.get("balance")
    actions.append({
        "type":   "balance_check",
        "status": result["status"],
        "detail": result.get("error", f"잔액: {balance:,}원" if balance is not None else ""),
    })

    if result["status"] != "success" or balance is None:
        return {"customer_id": cid, "balance": None, "actions": actions}

    history    = load_history()
    first_amt  = int(s.get("first_alert_amount",  50000))
    second_amt = int(s.get("second_alert_amount", 0))

    # 잔액 충전 감지 → 플래그 리셋
    if balance > first_amt:
        if s.get("first_alert_sent") or s.get("second_alert_sent"):
            s["first_alert_sent"]  = False
            s["second_alert_sent"] = False
            actions.append({"type": "reset", "detail": "잔액 충전 감지 → 알림 플래그 리셋"})

    phones = list(dict.fromkeys(filter(None, [
        s.get("advertiser_phone"), s.get("manager_phone")
    ])))
    admin_phone = _secret("ADMIN_NOTIFY_PHONE", "010-2797-3164")

    def _send(alert_type: str, template_code: str, threshold: int):
        # 중복 체크는 광고주 단위 1일 1회 (수신자별로 중복 적용하지 않음 — 담당자 스킵 버그 수정)
        if _already_sent_today(history, cid, alert_type):
            actions.append({"type": alert_type, "status": "skipped",
                             "detail": "오늘 이미 발송됨"})
            return
        # 광고주 + 담당자 알림톡
        for phone in phones:
            r = send_kakao_alerttalk(
                phone, template_code, _build_vars(s, balance, threshold),
                dry_run=dry_run
            )
            actions.append({"type": alert_type, "status": r.get("status"),
                             "detail": r.get("error", f"{phone} 발송")})
            _record_history(s, phone, alert_type, balance, threshold, r)
        # 관리자 동시 알림 — 광고주에게 보낸 것과 동일한 알림톡(카카오)을 관리자도 수신.
        # 수신자 목록에 관리자 번호가 이미 있으면(담당자=관리자) 중복 발송하지 않음.
        _admin_norm = admin_phone.replace("-", "")
        if admin_phone and _admin_norm not in [p.replace("-", "") for p in phones]:
            ar = send_kakao_alerttalk(
                admin_phone, template_code, _build_vars(s, balance, threshold),
                dry_run=dry_run
            )
            actions.append({"type": "admin_copy", "status": ar.get("status"),
                             "detail": ar.get("error", f"관리자({admin_phone}) 알림톡 사본")})

    # notification_config.json 에서 실제 Kakao 템플릿 ID 로드
    try:
        from notifications import get_notify_config as _gnc_bm
        _nc_bm = _gnc_bm()
        tmpl_first    = _nc_bm.get("bm_template_first",    TEMPLATE_CODE_FIRST)
        tmpl_depleted = _nc_bm.get("bm_template_depleted", TEMPLATE_CODE_DEPLETED)
    except Exception:
        tmpl_first    = TEMPLATE_CODE_FIRST
        tmpl_depleted = TEMPLATE_CODE_DEPLETED

    if balance <= second_amt and not s.get("second_alert_sent"):
        _send("depleted", tmpl_depleted, second_amt)
        s["second_alert_sent"] = True
        s["first_alert_sent"]  = True
    elif balance <= first_amt and not s.get("first_alert_sent"):
        _send("first", tmpl_first, first_amt)
        s["first_alert_sent"] = True

    s["last_bizmoney_balance"] = balance
    s["last_checked_at"]       = result["checked_at"]
    return {"customer_id": cid, "balance": balance, "actions": actions}


# ── 전체 실행 ──────────────────────────────────────────────────────────────────
def run_check(dry_run: bool = False) -> list[dict]:
    """등록된 모든 광고주 순회 → 잔액 조회 → 알림 발송 → 설정 저장."""
    merged  = get_merged_settings()
    results = []
    for s in merged:
        if not s.get("alert_enabled", True):
            continue
        if not s.get("api_access_license") or not s.get("secret_key"):
            continue
        results.append(process_one(s, dry_run=dry_run))
    save_from_merged(merged)
    return results
