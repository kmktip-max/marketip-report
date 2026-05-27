"""관리자 알림 발송 유틸리티 (이메일 + SMS)"""
import os
import json
import uuid
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

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
    try:
        import streamlit as st
        if hasattr(st, "secrets") and key in st.secrets:
            return str(st.secrets[key])
    except Exception:
        pass
    return os.getenv(key, default)


# ── 설정 상태 ────────────────────────────────────────────────────────────────
def get_notification_config_status() -> dict:
    return {
        "ADMIN_ALERT_EMAIL": bool(_secret("ADMIN_ALERT_EMAIL")),
        "SMTP_HOST":         bool(_secret("SMTP_HOST")),
        "SMTP_USER":         bool(_secret("SMTP_USER")),
        "SMTP_PASSWORD":     bool(_secret("SMTP_PASSWORD")),
        "ADMIN_ALERT_PHONE": bool(_secret("ADMIN_ALERT_PHONE") or _secret("ADMIN_NOTIFY_PHONE")),
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
    to_email  = _secret("ADMIN_ALERT_EMAIL")
    smtp_host = _secret("SMTP_HOST")
    smtp_port = int(_secret("SMTP_PORT", "587"))
    smtp_user = _secret("SMTP_USER")
    smtp_pw   = _secret("SMTP_PASSWORD")

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


# ── SMS 발송 (bizmoney_alert 위임) ───────────────────────────────────────────
def send_admin_sms(record: dict) -> dict:
    phone = _secret("ADMIN_ALERT_PHONE") or _secret("ADMIN_NOTIFY_PHONE")
    if not phone:
        return {"status": "skipped", "reason": "ADMIN_ALERT_PHONE 미설정"}

    if not _secret("SOLAPI_API_KEY"):
        return {"status": "skipped", "reason": "SOLAPI 미설정"}

    plat = record.get("platform_label", record.get("platform", "-"))
    text = "\n".join([
        "[마케팁] 광고계정 연동 신청",
        f"광고주: {record.get('account_name', '-')}",
        f"플랫폼: {plat}",
        f"광고종류: {record.get('ad_type', '-')}",
        f"담당자: {record.get('manager_name', '-')}",
        f"월예산: {record.get('monthly_budget', '-')}",
    ])

    from bizmoney_alert import send_sms_notification
    return send_sms_notification(phone, text)


# ── 통합 알림 ─────────────────────────────────────────────────────────────────
def send_admin_application_alert(record: dict) -> dict:
    email_result = {"status": "skipped"}
    sms_result   = {"status": "skipped"}

    try:
        email_result = send_admin_email(record)
    except Exception as e:
        email_result = {"status": "failed", "error": str(e)[:200]}

    try:
        if _secret("SOLAPI_API_KEY"):
            sms_result = send_admin_sms(record)
        else:
            sms_result = {"status": "skipped", "reason": "SOLAPI 미설정"}
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
