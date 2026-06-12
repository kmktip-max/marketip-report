"""인증 모듈 — 관리자 및 광고주 계정 관리"""
import base64
import hashlib
import hmac
import json
import os
import time
import uuid
from datetime import date

ROOT       = os.path.dirname(os.path.abspath(__file__))
F_ACCOUNTS = os.path.join(ROOT, "client_accounts.json")

from db import sb_load, sb_save
_SB_ACCOUNTS = "client_accounts"

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, ".env"))
except Exception:
    pass

_SESSION_DAYS = 7

# 광고주 권한 전체 목록 (key → (페이지경로, 표시명, 아이콘))
PERM_CATALOG = {
    "ebook_store":      ("pages/전자책.py",         "전자책·강의",          "📚"),
    "ad_analysis":      ("pages/광고분석컨설팅.py", "광고분석컨설팅",       "📈"),
    "monthly_report":   ("pages/월간보고서.py",     "월간보고서",           "📩"),
    "rebate":           ("pages/페이백신청.py",     "광고비 페이백신청",    "💸"),
    "bid_assist":       ("pages/자동입찰.py",       "자동입찰 관리",    "📊"),
    "keyword_tool":     ("pages/키워드도구.py",     "키워드 추출",          "🔍"),
    "creative_tool":    ("pages/광고소재.py",       "광고소재 추출",        "✍️"),
    "landing_analysis": ("pages/상세페이지.py",     "랜딩페이지 기획/분석", "📐"),
    "bizmoney_alert":   ("pages/비즈머니알림.py",   "비즈머니 알림",        "💰"),
    "fraud_detect":     ("pages/부정클릭관리.py",   "부정클릭 관리",        "🛡️"),
}

# 구권한키 → 신권한키 호환 테이블
_LEGACY_MAP = {
    "structure_consulting": "ad_analysis",
    "report_view":          "monthly_report",
    "payback":              "rebate",
}


# ── 페이백 신청자 판별 + 기능 접근 가드 ────────────────────────────────────────
def is_payback_applicant(username: str) -> bool:
    """페이백 신청자 = rebate_accounts(owner_id) 또는 월간보고서(clients.json owner) 등록."""
    if not username:
        return False
    _st = None
    try:
        import streamlit as _st
        cache = _st.session_state.get("_payback_cache")
        if isinstance(cache, dict) and username in cache:
            return cache[username]
    except Exception:
        cache = None

    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_KEY", "")
    try:
        if _st is not None:
            url = url or str(_st.secrets.get("SUPABASE_URL", ""))
            key = key or str(_st.secrets.get("SUPABASE_KEY", ""))
    except Exception:
        pass

    result = False
    # 1) rebate_accounts — 페이백 신청 기록
    try:
        if url and key:
            from supabase import create_client
            sb = create_client(url, key)
            res = sb.table("rebate_accounts").select("id").eq("owner_id", username).limit(1).execute()
            if res.data:
                result = True
    except Exception:
        pass
    # 2) 월간보고서(clients.json) 등록
    if not result:
        try:
            from report_engine.storage import load_clients
            if any(c.get("owner", "") == username for c in (load_clients() or [])):
                result = True
        except Exception:
            pass

    try:
        if _st is not None:
            cache = cache if isinstance(cache, dict) else {}
            cache[username] = result
            _st.session_state["_payback_cache"] = cache
    except Exception:
        pass
    return result


def feature_access_guard(perm_key: str, label: str = "이 기능"):
    """페이지 상단 가드 — 관리자/페이백 신청자/권한부여 계정만 통과, 그 외엔 안내 후 정지."""
    import streamlit as st
    if st.session_state.get("auth_type") == "admin":
        return
    perms = st.session_state.get("auth_permissions", []) or []
    user  = st.session_state.get("auth_username", "")
    if perm_key in perms or is_payback_applicant(user):
        return
    st.markdown(
        f"""
<div style="background:#FFF7ED;border:1.5px solid #FED7AA;border-radius:16px;
            padding:30px 32px;text-align:center;margin-top:10px;">
  <div style="font-size:34px;margin-bottom:8px;">🔒</div>
  <div style="font-size:18px;font-weight:800;color:#9A3412;margin-bottom:8px;">
    {label}은(는) 광고비 페이백 신청 대상자만 이용할 수 있습니다.
  </div>
  <div style="font-size:14px;color:#7C2D12;line-height:1.7;">
    광고비 페이백을 신청하시면 이 기능이 자동으로 열립니다.<br>
    이미 신청하셨다면 담당자에게 문의해 주세요.
  </div>
</div>
""",
        unsafe_allow_html=True,
    )
    if st.button("💸  광고비 페이백 신청하러 가기", type="primary"):
        try:
            st.switch_page("pages/페이백신청.py")
        except Exception:
            st.info("왼쪽 메뉴 '광고비 페이백신청'에서 신청하실 수 있습니다.")
    st.stop()

def _secret():
    try:
        import streamlit as st
        if hasattr(st, "secrets") and "SESSION_SECRET" in st.secrets:
            return str(st.secrets["SESSION_SECRET"])
    except Exception:
        pass
    return os.getenv("SESSION_SECRET", "mktip_session_key_2026")

# ── 유틸 ──────────────────────────────────────────────────────────────────
def _hash(pw):
    return hashlib.sha256(pw.encode("utf-8")).hexdigest()

def _admin_creds():
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

# ── 권한 정규화 (list→dict, 구키→신키) ────────────────────────────────────
def normalize_permissions(raw):
    """
    구형(list) 또는 신형(dict) 권한을 dict 형식으로 반환.
    모든 키가 PERM_CATALOG 기준으로 정규화됨.
    """
    base = {k: False for k in PERM_CATALOG}
    if isinstance(raw, list):
        for k in raw:
            new_k = _LEGACY_MAP.get(k, k)
            if new_k in base:
                base[new_k] = True
    elif isinstance(raw, dict):
        for k, v in raw.items():
            new_k = _LEGACY_MAP.get(k, k)
            if new_k in base:
                base[new_k] = bool(v)
    return base

def enabled_perm_keys(perms_dict):
    """활성화된 권한 키 리스트 반환"""
    return [k for k, v in perms_dict.items() if v]

# ── 광고주 계정 ────────────────────────────────────────────────────────────
def load_accounts():
    return sb_load(_SB_ACCOUNTS, F_ACCOUNTS) or []

def save_accounts(data):
    sb_save(_SB_ACCOUNTS, data, F_ACCOUNTS)

def verify_client(username, password):
    """유효한(승인된) 광고주 계정 dict 반환, 없으면 None"""
    pw_hash = _hash(password)
    for acc in load_accounts():
        if acc.get("username") == username and acc.get("password_hash") == pw_hash:
            if not acc.get("is_active", True):
                return None
            # approved 필드 없는 구형 계정은 자동 승인 처리
            if not acc.get("approved", True):
                return None
            return acc
    return None

def register_pending(business_name, username, password, contact_name="", phone=""):
    """광고주 자가 가입 — 승인 대기 상태로 저장"""
    accounts = load_accounts()
    if any(a.get("username") == username for a in accounts):
        return False, "이미 사용 중인 아이디입니다."
    cid = f"client_{str(uuid.uuid4())[:8]}"
    accounts.append({
        "client_id":     cid,
        "business_name": business_name.strip(),
        "username":      username.strip(),
        "contact_name":  contact_name.strip(),
        "phone":         phone.strip(),
        "password_hash": _hash(password),
        "is_active":     False,
        "approved":      False,
        "permissions":   {k: False for k in PERM_CATALOG},
        "created_at":    str(date.today()),
    })
    save_accounts(accounts)
    return True, cid

def create_account(business_name, username, password, permissions, client_id=""):
    """관리자가 직접 계정 생성 — 즉시 승인"""
    accounts = load_accounts()
    if any(a.get("username") == username for a in accounts):
        return False, "이미 사용 중인 아이디입니다."
    cid = client_id.strip() or f"client_{str(uuid.uuid4())[:8]}"
    perms_dict = normalize_permissions(permissions)
    accounts.append({
        "client_id":     cid,
        "business_name": business_name.strip(),
        "username":      username.strip(),
        "contact_name":  "",
        "phone":         "",
        "password_hash": _hash(password),
        "is_active":     True,
        "approved":      True,
        "permissions":   perms_dict,
        "created_at":    str(date.today()),
    })
    save_accounts(accounts)
    return True, cid

def approve_account(username, perms_dict):
    """승인 대기 계정 승인 + 권한 설정"""
    accounts = load_accounts()
    for acc in accounts:
        if acc.get("username") == username:
            acc["approved"]    = True
            acc["is_active"]   = True
            acc["permissions"] = normalize_permissions(perms_dict)
            save_accounts(accounts)
            return True
    return False

def reject_account(username):
    """승인 거절 — 계정 삭제"""
    accounts = load_accounts()
    new = [a for a in accounts if a.get("username") != username]
    if len(new) < len(accounts):
        save_accounts(new)
        return True
    return False

def update_account(username, business_name=None, password=None,
                   permissions=None, is_active=None, smartlog_eligible=None):
    accounts = load_accounts()
    for acc in accounts:
        if acc.get("username") == username:
            if business_name is not None:
                acc["business_name"] = business_name
            if password:
                acc["password_hash"] = _hash(password)
            if permissions is not None:
                acc["permissions"] = normalize_permissions(permissions)
            if is_active is not None:
                acc["is_active"] = is_active
            if smartlog_eligible is not None:
                acc["smartlog_eligible"] = smartlog_eligible
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

# ── 세션 관리 (서명 내장 토큰) ─────────────────────────────────────────────
def create_session(username, user_type, permissions, client_data=None):
    payload = {
        "username":    username,
        "user_type":   user_type,
        "permissions": permissions,
        "client_data": client_data or {},
        "expires_at":  time.time() + 86400 * _SESSION_DAYS,
    }
    payload_b64 = base64.urlsafe_b64encode(
        json.dumps(payload, ensure_ascii=False).encode("utf-8")
    ).decode("ascii")
    sig = hmac.new(_secret().encode("utf-8"), payload_b64.encode("ascii"),
                   hashlib.sha256).hexdigest()
    return f"{payload_b64}.{sig}"

def verify_session(token):
    if not token:
        return None
    try:
        payload_b64, sig = token.rsplit(".", 1)
        expected = hmac.new(_secret().encode("utf-8"), payload_b64.encode("ascii"),
                            hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        payload = json.loads(base64.urlsafe_b64decode(payload_b64).decode("utf-8"))
        if payload.get("expires_at", 0) < time.time():
            return None
        return payload
    except Exception:
        return None

def delete_session(token):
    pass
