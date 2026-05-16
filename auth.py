"""인증 모듈 — 관리자 및 광고주 계정 관리"""
import hashlib
import json
import os
import uuid
from datetime import date

ROOT = os.path.dirname(os.path.abspath(__file__))
F_ACCOUNTS = os.path.join(ROOT, "client_accounts.json")

# .env 로드 (app.py 로드보다 먼저 실행될 수 있으므로 여기서도 독립 로드)
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, ".env"))
except Exception:
    pass

# ── 유틸 ──────────────────────────────────────────────────────────────────
def _hash(pw):
    return hashlib.sha256(pw.encode("utf-8")).hexdigest()

def _admin_creds():
    """Streamlit secrets → .env 순서로 관리자 자격증명 조회"""
    try:
        import streamlit as st
        if hasattr(st, "secrets") and "ADMIN_ID" in st.secrets:
            return str(st.secrets["ADMIN_ID"]), str(st.secrets.get("ADMIN_PASSWORD", ""))
    except Exception:
        pass
    return os.getenv("ADMIN_ID", "mktip"), os.getenv("ADMIN_PASSWORD", "")

# ── 관리자 인증 ───────────────────────────────────────────────────────────
def verify_admin(username, password):
    aid, apw = _admin_creds()
    return username == aid and password == apw

# ── 광고주 계정 ────────────────────────────────────────────────────────────
def load_accounts():
    try:
        if os.path.exists(F_ACCOUNTS):
            with open(F_ACCOUNTS, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return []

def save_accounts(data):
    with open(F_ACCOUNTS, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def verify_client(username, password):
    """유효한 광고주 계정 dict 반환, 없으면 None"""
    pw_hash = _hash(password)
    for acc in load_accounts():
        if acc.get("username") == username and acc.get("password_hash") == pw_hash:
            if acc.get("is_active", True):
                return acc
    return None

def create_account(business_name, username, password, permissions, client_id=""):
    accounts = load_accounts()
    if any(a.get("username") == username for a in accounts):
        return False, "이미 사용 중인 아이디입니다."
    cid = client_id.strip() or f"client_{str(uuid.uuid4())[:8]}"
    accounts.append({
        "client_id":     cid,
        "business_name": business_name.strip(),
        "username":      username.strip(),
        "password_hash": _hash(password),
        "permissions":   permissions,
        "is_active":     True,
        "created_at":    str(date.today()),
    })
    save_accounts(accounts)
    return True, cid

def update_account(username, business_name=None, password=None,
                   permissions=None, is_active=None):
    accounts = load_accounts()
    for acc in accounts:
        if acc.get("username") == username:
            if business_name is not None:
                acc["business_name"] = business_name
            if password:
                acc["password_hash"] = _hash(password)
            if permissions is not None:
                acc["permissions"] = permissions
            if is_active is not None:
                acc["is_active"] = is_active
            save_accounts(accounts)
            return True
    return False

def delete_account(username):
    accounts = load_accounts()
    new = [a for a in accounts if a.get("username") != username]
    if len(new) < len(accounts):
        save_accounts(new)
        return True
    return False
