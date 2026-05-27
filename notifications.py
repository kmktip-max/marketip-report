"""관리자 알림 발송 유틸리티 (이메일 + SMS) v2"""
import os
import json
import uuid
import hmac
import hashlib
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

try:
    import requests as _requests
except ImportError:
    _requests = None

try:
    import pytz
    KST = pytz.timezone("Asia/Seoul")
except ImportError:
    KST = None


def _now_kst():
    if KST:
        from datetime import timezone
        return datetime.now(KST)
    return datetime.now()


def _secret(key, default=""):
    # 1. .streamlit/secrets.toml 직접 파싱 (@st.dialog 등 모든 컨텍스트에서 안전)
    try:
        _root = os.path.dirname(os.path.abspath(__file__))
        _toml = os.path.join(_root, ".streamlit", "secrets.toml")
        if os.path.exists(_toml):
            try:
                import tomllib
            except ImportError:
                try:
                    import tomli as tomllib  # type: ignore[no-redef]
                except ImportError:
                    tomllib = None
            if tomllib is not None:
                with open(_toml, "rb") as _f:
                    _d = tomllib.load(_f)
                val = _d.get(key)
                if val is not None:
                    return str(val)
    except Exception:
        pass
    # 2. st.secrets (Streamlit Cloud)
    try:
        import streamlit as st
        if hasattr(st, "secrets") and key in st.secrets:
            return str(st.secrets[key])
    except Exception:
        pass
    return os.getenv(key, default)


# ── JSON 설정 파일 (admin_phone 등) ─────────────────────────────────────────
def notify_config_path() -> str:
    ROOT = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(ROOT, "data", "notification_config.json")


def get_notify_config() -> dict:
    try:
        p = notify_config_path()
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def save_notify_config(data: dict) -> bool:
    try:
        p = notify_config_path()
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


# ── 설정 상태 ────────────────────────────────────────────────────────────────
def get_notification_config_status() -> dict:
    _cfg = get_notify_config()
    return {
        "ADMIN_ALERT_EMAIL": bool(_cfg.get("smtp_to") or _secret("ADMIN_ALERT_EMAIL")),
        "SMTP_HOST":         bool(_cfg.get("smtp_host") or _secret("SMTP_HOST")),
        "SMTP_USER":         bool(_cfg.get("smtp_user") or _secret("SMTP_USER")),
        "SMTP_PASSWORD":     bool(_cfg.get("smtp_password") or _secret("SMTP_PASSWORD")),
        "ADMIN_ALERT_PHONE": bool(_cfg.get("admin_phone") or _secret("ADMIN_ALERT_PHONE") or _secret("ADMIN_NOTIFY_PHONE")),
        "SOLAPI_API_KEY":    bool(_secret("SOLAPI_API_KEY")),
        "SOLAPI_API_SECRET": bool(_secret("SOLAPI_API_SECRET")),
        "SOLAPI_SENDER_ID":  bool(_secret("SOLAPI_SENDER_ID")),
    }


# ── 이메일 발송 ──────────────────────────────────────────────────────────────
def _build_email_body(record: dict) -> str:
    plat = record.get("platform_label", record.get("platform", "-"))
    rows = [
        "[마케팁 광고 계정 연동 신청]",
        "",
        f"플랫폼    : {plat}",
        f"광고 종류 : {record.get('ad_type', '-')}",
        f"담당자명  : {record.get('manager_name', '-')}",
        f"광고주명  : {record.get('account_name', '-')}",
        f"영문 아이디: {record.get('naver_login_id', '-')}",
        f"숫자 아이디: {record.get('customer_id') or record.get('account_id', '-')}",
        f"업종      : {record.get('business_category', '-')}",
        f"월 예산   : {record.get('monthly_budget', '-')}",
        f"신청일시  : {record.get('created_at', '-')}",
        "",
        "확인 후 1~2영업일 내 연동 처리 필요.",
    ]
    return "\n".join(rows)


def send_admin_email(record: dict) -> dict:
    from bizmoney_alert import _secret as _bz
    _cfg = get_notify_config()

    to_email  = _cfg.get("smtp_to")  or _bz("ADMIN_ALERT_EMAIL")
    smtp_host = _cfg.get("smtp_host") or _bz("SMTP_HOST")
    smtp_port = int(_cfg.get("smtp_port") or _bz("SMTP_PORT") or "465")
    smtp_user = _cfg.get("smtp_user") or _bz("SMTP_USER")
    smtp_pw   = _cfg.get("smtp_password") or _bz("SMTP_PASSWORD")

    if not to_email:
        return {"status": "skipped", "reason": "ADMIN_ALERT_EMAIL 미설정"}
    if not smtp_host or not smtp_user or not smtp_pw:
        return {"status": "skipped", "reason": "SMTP 설정 미완료"}

    adv     = record.get("account_name", "-")
    subject = f"[마케팁] 광고 계정 연동 신청 접수 - {adv}"
    body    = _build_email_body(record)

    try:
        msg = MIMEMultipart()
        msg["From"]    = smtp_user
        msg["To"]      = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain", "utf-8"))

        if smtp_port == 465:
            with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=15) as s:
                s.login(smtp_user, smtp_pw)
                s.send_message(msg)
        else:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as s:
                s.ehlo()
                s.starttls()
                s.login(smtp_user, smtp_pw)
                s.send_message(msg)
        return {"status": "success"}
    except Exception as e:
        return {"status": "failed", "error": str(e)[:300]}


# ── SOLAPI 직접 발송 ──────────────────────────────────────────────────────────
def _solapi_send(to_phone: str, text: str) -> dict:
    if _requests is None:
        return {"status": "failed", "error": "requests 패키지 없음"}
    # bizmoney_alert._secret 우선 (st.secrets 직접 접근, 검증됨)
    # notifications._secret 폴백 (toml 파일 파싱)
    try:
        from bizmoney_alert import _secret as _bz
        api_key    = _bz("SOLAPI_API_KEY")    or _secret("SOLAPI_API_KEY")
        api_secret = _bz("SOLAPI_API_SECRET") or _secret("SOLAPI_API_SECRET")
        sender_id  = _bz("SOLAPI_SENDER_ID")  or _secret("SOLAPI_SENDER_ID")
    except Exception:
        api_key    = _secret("SOLAPI_API_KEY")
        api_secret = _secret("SOLAPI_API_SECRET")
        sender_id  = _secret("SOLAPI_SENDER_ID")
    if not api_key or not api_secret or not sender_id:
        return {"status": "skipped", "reason": f"SOLAPI 미설정 (key={bool(api_key)},secret={bool(api_secret)},sender={bool(sender_id)})"}
    if not to_phone:
        return {"status": "skipped", "reason": "수신번호 없음"}

    now_str   = datetime.now().strftime("%Y-%m-%dT%H:%M:%S+09:00")
    salt      = str(uuid.uuid4()).replace("-", "")
    signature = hmac.new(
        api_secret.encode(), f"{now_str}{salt}".encode(), hashlib.sha256
    ).hexdigest()
    headers = {
        "Authorization": f"HMAC-SHA256 apiKey={api_key}, date={now_str}, salt={salt}, signature={signature}",
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
        resp = _requests.post(
            "https://api.solapi.com/messages/v4/send",
            headers=headers, json=payload, timeout=15,
        )
        resp.raise_for_status()
        return {"status": "success", "response": resp.json()}
    except _requests.HTTPError as e:
        return {"status": "failed", "error": f"HTTP {e.response.status_code}: {e.response.text[:200]}"}
    except Exception as e:
        return {"status": "failed", "error": str(e)[:200]}


# ── SMS 발송 ─────────────────────────────────────────────────────────────────
def send_admin_sms(record: dict, phone: str = "") -> dict:
    if not phone:
        _cfg = get_notify_config()
        phone = (
            _cfg.get("admin_phone", "")
            or _secret("ADMIN_NOTIFY_PHONE")
            or _secret("ADMIN_ALERT_PHONE")
            or _secret("SOLAPI_SENDER_ID")
        )
    if not phone:
        return {"status": "skipped", "reason": "ADMIN_ALERT_PHONE 미설정"}

    plat = record.get("platform_label", record.get("platform", "-"))
    text = "\n".join([
        "[마케팁] 광고계정 연동 신청",
        f"광고주: {record.get('account_name', '-')}",
        f"플랫폼: {plat}",
        f"광고종류: {record.get('ad_type', '-')}",
        f"담당자: {record.get('manager_name', '-')}",
        f"월예산: {record.get('monthly_budget', '-')}",
    ])
    return _solapi_send(phone, text)


# ── 통합 알림 ─────────────────────────────────────────────────────────────────
def send_admin_application_alert(record: dict, admin_phone: str = "") -> dict:
    email_result = {"status": "skipped"}
    sms_result   = {"status": "skipped"}

    try:
        email_result = send_admin_email(record)
    except Exception as e:
        email_result = {"status": "failed", "error": str(e)[:200]}

    try:
        sms_result = send_admin_sms(record, phone=admin_phone)
    except Exception as e:
        sms_result = {"status": "failed", "error": str(e)[:200]}

    return {"email": email_result, "sms": sms_result}


# ── 이력 저장 ─────────────────────────────────────────────────────────────────
def save_alert_history(record: dict, alert_result: dict):
    ROOT     = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(ROOT, "data")
    os.makedirs(data_dir, exist_ok=True)
    path = os.path.join(data_dir, "application_alert_history.json")

    try:
        history = []
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                history = json.load(f)
    except Exception:
        history = []

    entry = {
        "id":             record.get("id", str(uuid.uuid4())),
        "created_at":     record.get("created_at", _now_kst().strftime("%Y-%m-%d %H:%M:%S")),
        "platform":       record.get("platform_label", record.get("platform", "")),
        "advertiser_name": record.get("account_name", ""),
        "manager_name":   record.get("manager_name", ""),
        "customer_id":    record.get("customer_id") or record.get("account_id", ""),
        "alert_email":    bool(_secret("ADMIN_ALERT_EMAIL")),
        "alert_phone":    bool(_secret("ADMIN_ALERT_PHONE") or _secret("ADMIN_NOTIFY_PHONE")),
        "email_status":   alert_result.get("email", {}).get("status", ""),
        "sms_status":     alert_result.get("sms", {}).get("status", ""),
        "error_message":  (
            alert_result.get("email", {}).get("error", "")
            or alert_result.get("sms", {}).get("error", "")
        ),
    }

    history.insert(0, entry)
    history = history[:300]

    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
