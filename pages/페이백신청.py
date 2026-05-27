import streamlit as st
import os
import sys
import uuid
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from components.style import PAYBACK_CSS, badge, STATUS_LIST

# ── Storage (Supabase) ────────────────────────────────────────────────────────
def _get_sb():
    from supabase import create_client
    return create_client(get_secret("SUPABASE_URL"), get_secret("SUPABASE_KEY"))


def load_accounts(owner_id=None):
    try:
        q = _get_sb().table("rebate_accounts").select("*").order("created_at", desc=True)
        if owner_id is not None:
            q = q.eq("owner_id", owner_id)
        res = q.execute()
        return res.data or []
    except Exception:
        return []


def delete_account(account_id: str) -> bool:
    try:
        _get_sb().table("rebate_accounts").delete().eq("id", account_id).execute()
        return True
    except Exception:
        return False


# ── Secret helper ─────────────────────────────────────────────────────────────
def get_secret(key, default=""):
    try:
        if hasattr(st, "secrets") and key in st.secrets:
            return str(st.secrets[key])
    except Exception:
        pass
    return os.getenv(key, default)


ADMIN_PW = get_secret("ADMIN_PASSWORD", "mktip")

# ─── Platform config ──────────────────────────────────────────────────────────
_PLAT_CFG = {
    "네이버": {
        "accent": "#03C75A", "light": "#E8F9EF", "border": "#A5D6A7",
        "text": "#014E24", "tab_fg": "#fff", "key": "naver",
        "icon": "🟢", "desc": "검색광고 · GFA · 애드부스트",
    },
    "당근": {
        "accent": "#FF6F0F", "light": "#FFF3EA", "border": "#FFCBA4",
        "text": "#7C3300", "tab_fg": "#fff", "key": "daangn",
        "icon": "🟠", "desc": "당근 전문가광고",
    },
    "카카오": {
        "accent": "#FAD400", "light": "#FFFDE7", "border": "#FFF176",
        "text": "#3A1D1D", "tab_fg": "#3A1D1D", "key": "kakao",
        "icon": "🟡", "desc": "모먼트 · 키워드 · 브랜드검색 · 카톡채널",
    },
}

_DIALOG_CSS = """
<style>
/* ══════════════════════════════════════════════
   DIALOG — 컨테이너 폭 제한 & 레이아웃
══════════════════════════════════════════════ */
div[data-testid="stDialog"] *,
div[data-testid="stDialog"] *::before,
div[data-testid="stDialog"] *::after { box-sizing: border-box !important; }

/* 모달 패널 폭 제한 */
div[data-testid="stDialog"] > div > div,
div[data-testid="stDialogContent"] {
    max-width: min(840px, calc(100vw - 48px)) !important;
    width: min(840px, calc(100vw - 48px)) !important;
}
div[data-testid="stDialog"] > div > div > div {
    width: 100% !important; max-width: 100% !important; overflow-x: hidden !important;
}

/* ══════════════════════════════════════════════
   PLATFORM TABS — 3등분 균등 버튼형 탭
══════════════════════════════════════════════ */
div[data-testid="stDialog"] [data-testid="stTabs"] {
    width: 100% !important; overflow-x: hidden !important;
}
/* tablist: 3등분 grid */
div[data-testid="stDialog"] div[role="tablist"] {
    display: grid !important;
    grid-template-columns: repeat(3, 1fr) !important;
    width: 100% !important;
    background: #F3F4F6 !important;
    border-radius: 14px !important;
    padding: 5px !important;
    gap: 6px !important;
    border: none !important;
    border-bottom: none !important;
    overflow: hidden !important;
}
/* tab 버튼 — 균등 높이, 중앙 정렬 */
div[data-testid="stDialog"] button[role="tab"] {
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    width: 100% !important;
    min-width: 0 !important;
    height: 44px !important;
    border-radius: 10px !important;
    font-size: 14px !important;
    font-weight: 700 !important;
    padding: 0 !important;
    transition: all 0.2s ease !important;
    border: none !important;
    letter-spacing: -0.3px;
    color: #9CA3AF !important;
    background: transparent !important;
    cursor: pointer !important;
}
div[data-testid="stDialog"] button[role="tab"][aria-selected="true"] {
    background: #fff !important;
    box-shadow: 0 2px 10px rgba(0,0,0,0.10) !important;
}
/* 플랫폼별 활성 색상 */
div[data-testid="stDialog"] button[role="tab"]:nth-child(1)[aria-selected="true"] { color: #03C75A !important; }
div[data-testid="stDialog"] button[role="tab"]:nth-child(2)[aria-selected="true"] { color: #E05E00 !important; }
div[data-testid="stDialog"] button[role="tab"]:nth-child(3)[aria-selected="true"] { color: #9A7D00 !important; }
/* 탭 언더라인 완전 제거 */
div[data-testid="stDialog"] button[role="tab"]::after,
div[data-testid="stDialog"] button[role="tab"]::before,
div[data-testid="stDialog"] [data-testid="stTabs"] > div:first-child::after,
div[data-testid="stDialog"] [data-testid="stTabs"] > div:first-child::before {
    display: none !important; content: none !important; border: none !important;
}

/* ══════════════════════════════════════════════
   TAB CONTENT — fade-in 전환 애니메이션
══════════════════════════════════════════════ */
@keyframes dlgFadeSlide {
    from { opacity: 0; transform: translateY(7px); }
    to   { opacity: 1; transform: translateY(0px); }
}
div[data-testid="stDialog"] [data-testid="stTabsContent"] {
    width: 100% !important; max-width: 100% !important; overflow-x: hidden !important;
}
div[data-testid="stDialog"] [data-testid="stTabsContent"] > div {
    animation: dlgFadeSlide 0.28s cubic-bezier(.22,.68,0,1.2) !important;
}

/* ══════════════════════════════════════════════
   PLATFORM HEADER CARD
══════════════════════════════════════════════ */
.pb-plat-header {
    display: flex; align-items: center; gap: 14px;
    border-radius: 14px; padding: 14px 18px;
    margin: 10px 0 18px; width: 100%;
}
.pb-plat-logo { font-size: 28px; line-height: 1; flex-shrink: 0; }
.pb-plat-info  { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
.pb-plat-name  { font-size: 15px; font-weight: 700; letter-spacing: -0.3px; }
.pb-plat-desc  { font-size: 12px; color: #6B7280; }

/* ══════════════════════════════════════════════
   WIDGET LABELS
══════════════════════════════════════════════ */
div[data-testid="stDialog"] label[data-testid="stWidgetLabel"] p,
div[data-testid="stDialog"] label[data-testid="stWidgetLabel"] > div > p {
    font-size: 13px !important; font-weight: 600 !important;
    color: #374151 !important; letter-spacing: -0.2px;
}

/* ══════════════════════════════════════════════
   TEXT INPUT — border + focus ring
══════════════════════════════════════════════ */
div[data-testid="stDialog"] [data-baseweb="input"],
div[data-testid="stDialog"] div[data-testid="stTextInputRootElement"] {
    border: 1.5px solid #E5E7EB !important;
    border-radius: 10px !important;
    background: #FAFAFA !important;
    transition: border-color 0.18s ease, box-shadow 0.18s ease !important;
    overflow: hidden !important;
    min-height: 46px !important;
}
div[data-testid="stDialog"] [data-baseweb="input"]:focus-within,
div[data-testid="stDialog"] div[data-testid="stTextInputRootElement"]:focus-within {
    border-color: #0D47A1 !important;
    box-shadow: 0 0 0 3px rgba(13,71,161,0.09) !important;
    background: #fff !important;
}
div[data-testid="stDialog"] [data-baseweb="input"] input,
div[data-testid="stDialog"] div[data-testid="stTextInputRootElement"] input {
    background: transparent !important; border: none !important;
    font-size: 14px !important; color: #111 !important;
    padding: 10px 14px !important; line-height: 1.4 !important;
}
div[data-testid="stDialog"] input::placeholder { color: #9CA3AF !important; font-size: 13px !important; }

/* ══════════════════════════════════════════════
   SELECTBOX — 텍스트 클리핑 완전 방지
══════════════════════════════════════════════ */
div[data-testid="stDialog"] [data-baseweb="select"] {
    overflow: visible !important;
}
/* 외곽 컨트롤 박스 */
div[data-testid="stDialog"] [data-baseweb="select"] > div:first-child {
    display: flex !important;
    align-items: center !important;
    min-height: 46px !important;
    height: auto !important;
    padding: 0 14px !important;
    border: 1.5px solid #E5E7EB !important;
    border-radius: 10px !important;
    background: #FAFAFA !important;
    transition: border-color 0.18s, box-shadow 0.18s !important;
    overflow: visible !important;
}
/* 내부 값 텍스트 컨테이너 */
div[data-testid="stDialog"] [data-baseweb="select"] > div:first-child > div {
    overflow: visible !important;
    height: auto !important;
    line-height: 1.5 !important;
    font-size: 14px !important;
    color: #111 !important;
    display: flex !important;
    align-items: center !important;
    flex: 1 !important;
    min-width: 0 !important;
}
/* 선택된 값 텍스트 */
div[data-testid="stDialog"] [data-baseweb="select"] [data-baseweb="value"],
div[data-testid="stDialog"] [data-baseweb="select"] span[data-value] {
    font-size: 14px !important;
    line-height: 1.5 !important;
    overflow: visible !important;
    white-space: nowrap !important;
    color: #111 !important;
}
div[data-testid="stDialog"] [data-baseweb="select"]:focus-within > div:first-child {
    border-color: #0D47A1 !important;
    box-shadow: 0 0 0 3px rgba(13,71,161,0.09) !important;
    background: #fff !important;
}

/* ══════════════════════════════════════════════
   COLUMNS & FULL-WIDTH CONTROLS
══════════════════════════════════════════════ */
div[data-testid="stDialog"] input,
div[data-testid="stDialog"] select,
div[data-testid="stDialog"] textarea {
    width: 100% !important; max-width: 100% !important;
}
div[data-testid="stDialog"] [data-testid="stHorizontalBlock"] {
    width: 100% !important; max-width: 100% !important;
    gap: 12px !important; margin-top: 8px !important;
}
div[data-testid="stDialog"] [data-testid="stHorizontalBlock"] > div {
    flex: 1 1 0 !important; min-width: 0 !important;
}

/* ══════════════════════════════════════════════
   BUTTONS — 높이 50px + hover
══════════════════════════════════════════════ */
div[data-testid="stDialog"] .stButton > button {
    width: 100% !important;
    height: 50px !important;
    border-radius: 12px !important;
    font-size: 14px !important;
    font-weight: 700 !important;
    padding: 0 !important;
    transition: all 0.22s cubic-bezier(.22,.68,0,1.2) !important;
    letter-spacing: -0.2px;
}
div[data-testid="stDialog"] .stButton > button[kind="secondary"] {
    border: 1.5px solid #E5E7EB !important;
    color: #6B7280 !important;
    background: #F9FAFB !important;
}
div[data-testid="stDialog"] .stButton > button[kind="secondary"]:hover {
    background: #F3F4F6 !important; border-color: #D1D5DB !important; color: #374151 !important;
}
div[data-testid="stDialog"] .stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #0D47A1 0%, #1A5DCC 100%) !important;
    border: none !important; color: #fff !important;
    box-shadow: 0 4px 16px rgba(13,71,161,0.28) !important;
}
div[data-testid="stDialog"] .stButton > button[kind="primary"]:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 8px 24px rgba(13,71,161,0.38) !important;
    filter: brightness(1.06) !important;
}
div[data-testid="stDialog"] .stButton > button[kind="primary"]:active {
    transform: translateY(0px) !important; box-shadow: 0 2px 8px rgba(13,71,161,0.25) !important;
}

/* ══════════════════════════════════════════════
   HELPER / CAPTION
══════════════════════════════════════════════ */
div[data-testid="stDialog"] [data-testid="InputInstructions"],
div[data-testid="stDialog"] small,
div[data-testid="stDialog"] .stCaption { font-size: 11px !important; color: #9CA3AF !important; }

/* ══════════════════════════════════════════════
   모바일 대응 (640px 이하)
══════════════════════════════════════════════ */
@media (max-width: 640px) {
    div[data-testid="stDialog"] > div > div {
        width: 100vw !important; max-width: 100vw !important; margin: 0 !important;
        border-radius: 20px 20px 0 0 !important; bottom: 0 !important;
        top: auto !important; position: fixed !important;
    }
    div[data-testid="stDialog"] button[role="tab"] { font-size: 12px !important; height: 40px !important; }
    .pb-plat-header { padding: 12px 14px !important; }
}
</style>
"""


def _render_naver_form() -> dict:
    manager_name = st.text_input(
        "담당자명 *", placeholder="예: 홍길동", key="dlg_naver_manager",
    )
    ad_type = st.selectbox(
        "네이버 광고 종류 *",
        ["검색광고", "GFA", "애드부스트"],
        key="dlg_naver_ad_type",
    )
    account_name = st.text_input(
        "광고주명 *", placeholder="예: 마케팁", key="dlg_naver_acname",
    )
    naver_id = st.text_input(
        "광고 영문 아이디 *",
        placeholder="로그인시 사용하는 영문 ID",
        key="dlg_naver_id",
    )
    customer_id = st.text_input(
        "광고 숫자 아이디 (Customer ID) *",
        placeholder="예: 2815366",
        help="searchad.naver.com 로그인 후 우상단에서 확인",
        key="dlg_naver_cid",
    )
    monthly_budget = st.text_input(
        "대략적 월 예산", placeholder="예: 5,000,000원", key="dlg_naver_budget",
    )
    return {
        "manager_name": manager_name,
        "ad_type": ad_type,
        "account_name": account_name,
        "naver_login_id": naver_id,
        "customer_id": customer_id,
        "monthly_budget": monthly_budget,
    }


def _render_daangn_form() -> dict:
    manager_name = st.text_input(
        "담당자명 *", placeholder="예: 홍길동", key="dlg_daangn_manager",
    )
    account_name = st.text_input(
        "광고주명 *", placeholder="예: 마케팁", key="dlg_daangn_acname",
    )
    account_id = st.text_input(
        "계정번호 *", placeholder="예: 12345678", key="dlg_daangn_id",
    )
    monthly_budget = st.text_input(
        "대략적인 월 예산", placeholder="예: 2,000,000원", key="dlg_daangn_budget",
    )
    return {
        "manager_name": manager_name,
        "account_name": account_name,
        "account_id": account_id,
        "monthly_budget": monthly_budget,
    }


def _render_kakao_form() -> dict:
    manager_name = st.text_input(
        "담당자명 *", placeholder="예: 홍길동", key="dlg_kakao_manager",
    )
    ad_type = st.selectbox(
        "카카오 광고 종류 *",
        ["모먼트", "키워드", "브랜드검색", "카톡채널"],
        key="dlg_kakao_ad_type",
    )
    account_name = st.text_input(
        "브랜드명 *", placeholder="예: 마케팁", key="dlg_kakao_acname",
    )
    business_category = st.text_input(
        "업종 *", placeholder="예: 마케팅/광고", key="dlg_kakao_category",
    )
    account_id = st.text_input(
        "아이디 (숫자) *", placeholder="예: 123456789", key="dlg_kakao_id",
    )
    monthly_budget = st.text_input(
        "대략적인 월 예산", placeholder="예: 3,000,000원", key="dlg_kakao_budget",
    )
    return {
        "manager_name": manager_name,
        "ad_type": ad_type,
        "account_name": account_name,
        "business_category": business_category,
        "account_id": account_id,
        "monthly_budget": monthly_budget,
    }


def _handle_submit(plat_key: str, fd: dict, admin_phone: str = ""):
    plat_label = next(k for k, v in _PLAT_CFG.items() if v["key"] == plat_key)
    name = fd.get("account_name", "").strip()
    if not name:
        st.error("광고주명(브랜드명)은 필수 입력 항목입니다.")
        return
    if plat_key == "naver":
        required = ["manager_name", "naver_login_id", "customer_id"]
    elif plat_key == "daangn":
        required = ["manager_name", "account_id"]
    else:  # kakao
        required = ["manager_name", "business_category", "account_id"]
    if any(not str(fd.get(f, "")).strip() for f in required):
        st.error("* 표시된 필수 항목을 모두 입력해 주세요.")
        return
    _client_info = st.session_state.get("auth_client", {})
    record = {
        "id": str(uuid.uuid4()),
        "platform": plat_key,
        "platform_label": plat_label,
        "status": "연동신청",
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "owner_id": st.session_state.get("auth_username", ""),
        "owner_name": (
            _client_info.get("contact_name", "")
            or st.session_state.get("auth_username", "")
        ),
    }
    record.update({k: (v.strip() if isinstance(v, str) else v) for k, v in fd.items()})
    _get_sb().table("rebate_accounts").insert(record).execute()

    # ── 관리자 알림 발송 (실패해도 신청은 정상 처리) ──────────────────────────
    _alert_result = {"email": {"status": "skipped"}, "sms": {"status": "skipped"}}
    _alert_err    = ""
    try:
        from notifications import send_admin_application_alert, save_alert_history
        _alert_result = send_admin_application_alert(record, admin_phone=admin_phone)
        save_alert_history(record, _alert_result)
    except Exception as _e:
        _alert_err = str(_e)

    # 결과를 session_state에 저장 → 다이얼로그 닫힌 뒤 메인 페이지에서 표시
    st.session_state["_pb_submit_result"] = {
        "alert": _alert_result,
        "err":   _alert_err,
        "name":  name,
    }
    st.rerun()


# ── Styles ────────────────────────────────────────────────────────────────────
st.markdown(PAYBACK_CSS, unsafe_allow_html=True)

# ── 신청 완료 결과 표시 (다이얼로그 닫힌 후) ──────────────────────────────────
if "_pb_submit_result" in st.session_state:
    _res = st.session_state.pop("_pb_submit_result")
    _ar  = _res.get("alert", {})
    _err = _res.get("err", "")
    _nm  = _res.get("name", "")

    st.toast(f"✅ {_nm} 연동 신청 완료!", icon="✅")

    _email_st = _ar.get("email", {}).get("status", "")
    _sms_st   = _ar.get("sms",   {}).get("status", "")
    _e        = _ar.get("email", {})
    _s        = _ar.get("sms",   {})

    if _email_st == "success":
        st.toast("이메일 발송 완료", icon="📧")
    elif _email_st == "failed":
        st.toast(f"이메일 실패: {_e.get('error','')[:60]}", icon="⚠️")

    if _sms_st == "success":
        st.toast("SMS 발송 완료", icon="📱")
    elif _sms_st == "failed":
        st.toast(f"SMS 실패: {_s.get('error','')[:60]}", icon="⚠️")
    elif _sms_st == "skipped":
        st.toast(f"SMS 건너뜀: {_s.get('reason','')}", icon="ℹ️")

    if _err:
        st.toast(f"알림 오류: {_err[:80]}", icon="🚨")

    # 관리자에게만 상세 디버그 표시
    if st.session_state.get("auth_type") == "admin":
        st.info(
            f"**알림 결과**  \n"
            f"이메일: `{_email_st}` {_e.get('error','') or _e.get('reason','')}  \n"
            f"SMS: `{_sms_st}` {_s.get('error','') or _s.get('reason','')}  \n"
            + (f"오류: `{_err}`" if _err else "")
        )


# ── 페이지 로드 시 시크릿 미리 캐시 (dialog 내부에서 st.secrets 접근 불가 문제 우회) ──
if not st.session_state.get("_admin_notify_phone"):
    st.session_state["_admin_notify_phone"] = (
        get_secret("ADMIN_NOTIFY_PHONE") or get_secret("ADMIN_ALERT_PHONE")
    )

# ── Modal: 계정 추가 ──────────────────────────────────────────────────────────
def _plat_header(plat_name: str) -> None:
    cfg = _PLAT_CFG[plat_name]
    st.markdown(f"""
<div class="pb-plat-header" style="background:{cfg['light']};border:1.5px solid {cfg['border']};">
  <div class="pb-plat-logo">{cfg['icon']}</div>
  <div class="pb-plat-info">
    <div class="pb-plat-name" style="color:{cfg['text']};">{plat_name} 광고 계정 연동</div>
    <div class="pb-plat-desc">{cfg['desc']}</div>
  </div>
</div>""", unsafe_allow_html=True)


def _tab_buttons(plat_key: str, fd: dict, admin_phone: str = "") -> None:
    c1, c2 = st.columns(2)
    with c1:
        if st.button("취소", use_container_width=True, key=f"dlg_cancel_{plat_key}"):
            st.rerun()
    with c2:
        if st.button(
            f"연동 신청하기  →",
            type="primary",
            use_container_width=True,
            key=f"dlg_submit_{plat_key}",
        ):
            _handle_submit(plat_key, fd, admin_phone=admin_phone)


@st.dialog("광고 계정 추가", width="large")
def add_account_dialog(admin_phone=""):
    st.markdown(_DIALOG_CSS, unsafe_allow_html=True)

    tab_n, tab_d, tab_k = st.tabs(["🟢 네이버", "🟠 당근", "🟡 카카오"])

    with tab_n:
        _plat_header("네이버")
        fd = _render_naver_form()
        st.markdown("<br>", unsafe_allow_html=True)
        _tab_buttons("naver", fd, admin_phone)

    with tab_d:
        _plat_header("당근")
        fd = _render_daangn_form()
        st.markdown("<br>", unsafe_allow_html=True)
        _tab_buttons("daangn", fd, admin_phone)

    with tab_k:
        _plat_header("카카오")
        fd = _render_kakao_form()
        st.markdown("<br>", unsafe_allow_html=True)
        _tab_buttons("kakao", fd, admin_phone)


# ═════════════════════════════════════════════════════════════════════════════
# 페이지 본문
# ═════════════════════════════════════════════════════════════════════════════

# ── 헤더 ──────────────────────────────────────────────────────────────────────
st.markdown('<div class="pb-h1">검색광고 페이백</div>', unsafe_allow_html=True)
st.markdown('<div class="pb-sub">네이버 광고 계정을 연동하고 광고비 페이백을 받아보세요</div>', unsafe_allow_html=True)

b1, b2, _ = st.columns([1, 1, 5])
with b1:
    apply_btn = st.button("신청하기", type="primary", use_container_width=True)
with b2:
    if st.button("내역보기", use_container_width=True):
        st.session_state["payback_tab"] = "전체"

# ── 페이백이란? 안내 ──────────────────────────────────────────────────────────
with st.expander("ℹ️  광고비 페이백이란?"):
    st.markdown("""
<style>
.pb-rate-wrap { display:flex; gap:24px; flex-wrap:wrap; margin-top:4px; }
.pb-rate-card {
  background:#F8FAFF;
  border:1px solid #E0E7FF;
  border-radius:12px;
  padding:18px 22px;
  min-width:200px;
  flex:1;
}
.pb-rate-platform {
  font-size:13px; font-weight:800; color:#111;
  margin-bottom:12px; display:flex; align-items:center; gap:6px;
}
.pb-rate-row {
  display:flex; justify-content:space-between; align-items:center;
  padding:6px 0; border-bottom:1px solid #EEF0F4; font-size:13px;
}
.pb-rate-row:last-child { border-bottom:none; }
.pb-rate-label { color:#555; }
.pb-rate-pct { font-weight:700; color:#0D47A1; font-size:14px; }
.pb-intro {
  font-size:15px; font-weight:700; color:#111;
  margin-bottom:16px; line-height:1.6;
}
.pb-pct-hl { color:#0D47A1; }
</style>
<div class="pb-intro">
  마케팁 광고 계정을 연동하면,<br>
  광고 비용의 최대 <span class="pb-pct-hl">10%</span>를 돌려받을 수 있는 시스템입니다.
</div>
<div class="pb-rate-wrap">
  <div class="pb-rate-card">
    <div class="pb-rate-platform">🟢 네이버</div>
    <div class="pb-rate-row"><span class="pb-rate-label">검색광고 (파워링크·쇼핑·브랜드)</span><span class="pb-rate-pct">10%</span></div>
    <div class="pb-rate-row"><span class="pb-rate-label">GFA</span><span class="pb-rate-pct">10%</span></div>
    <div class="pb-rate-row"><span class="pb-rate-label">AD Voost</span><span class="pb-rate-pct">5%</span></div>
  </div>
  <div class="pb-rate-card">
    <div class="pb-rate-platform">🟡 카카오</div>
    <div class="pb-rate-row"><span class="pb-rate-label">검색광고</span><span class="pb-rate-pct">10%</span></div>
    <div class="pb-rate-row"><span class="pb-rate-label">배너광고</span><span class="pb-rate-pct">10%</span></div>
  </div>
  <div class="pb-rate-card">
    <div class="pb-rate-platform">🟠 당근</div>
    <div class="pb-rate-row"><span class="pb-rate-label">전문가광고</span><span class="pb-rate-pct">7%</span></div>
  </div>
</div>
""", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ── 안내 카드 2개 ─────────────────────────────────────────────────────────────
left, right = st.columns([2.2, 1], gap="large")

with left:
    st.markdown("""
<div class="info-card">
  <div class="info-card-ttl">연동 절차</div>
  <div class="steps">
    <div class="step">
      <div class="step-num">1</div>
      <div class="step-lbl">연동 신청</div>
      <div class="step-desc">계정 정보 입력</div>
    </div>
    <div class="step-line"></div>
    <div class="step">
      <div class="step-num">2</div>
      <div class="step-lbl">네이버 확인중</div>
      <div class="step-desc">관리자 승인 요청</div>
    </div>
    <div class="step-line"></div>
    <div class="step">
      <div class="step-num">3</div>
      <div class="step-lbl">이관 승인</div>
      <div class="step-desc">광고센터에서 승인</div>
    </div>
    <div class="step-line"></div>
    <div class="step">
      <div class="step-num">4</div>
      <div class="step-lbl">연동 완료</div>
      <div class="step-desc">페이백 수령 가능</div>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

with right:
    st.markdown("""
<div class="info-card">
  <div class="notice-wrap">
    <div class="notice-ttl">⚠️ 필독 안내 사항</div>
    <div class="notice-row">
      <span class="notice-key">정산 일정</span>
      <span class="notice-val">페이백 정산은 <em-red>2달 뒤</em-red> 진행됩니다. <span style="font-size:11px;color:#aaa;">(ex. 1월 → 3월 20~25일)</span></span>
    </div>
    <div class="notice-row">
      <span class="notice-key">페이백 불가</span>
      <span class="notice-val">네이버 플레이스, 파워컨텐츠는 <em-red>불가</em-red>합니다.</span>
    </div>
    <div class="notice-row">
      <span class="notice-key">문의처</span>
      <span class="notice-val">검색광고 대행문의는 <a href="https://pf.kakao.com/_wMLIn" target="_blank" style="color:#0D47A1;font-weight:700;text-decoration:none;">마케팁 카카오채널</a>로 부탁드립니다.</span>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ── 계정 리스트 (로그인 사용자 기준 필터링) ───────────────────────────────────
_is_admin = st.session_state.get("auth_type") == "admin"
_owner_id  = None if _is_admin else st.session_state.get("auth_username", "")
accounts = load_accounts(owner_id=_owner_id)

col_title, col_btn = st.columns([4, 1])
with col_title:
    st.markdown(
        f'<div class="sec-ttl">내 광고 계정'
        f'<span class="count-pill">연동된 계정 {len(accounts)}개</span></div>',
        unsafe_allow_html=True
    )
with col_btn:
    add_btn = st.button("＋ 계정 추가", type="primary", use_container_width=True)

# 상태 탭
tab_options = ["전체"] + STATUS_LIST
default_tab = st.session_state.get("payback_tab", "전체")
default_idx = tab_options.index(default_tab) if default_tab in tab_options else 0

selected_tab = st.radio(
    "상태",
    tab_options,
    index=default_idx,
    horizontal=True,
    label_visibility="collapsed",
)

filtered = accounts if selected_tab == "전체" else [a for a in accounts if a["status"] == selected_tab]

st.markdown("<div style='margin-top:12px;'></div>", unsafe_allow_html=True)

if not filtered:
    st.markdown("""
<div class="empty-wrap">
  <div class="empty-ico">🔗</div>
  <div class="empty-ttl">연동된 광고 계정이 없습니다</div>
  <div class="empty-desc">계정을 추가하여 페이백을 받아보세요</div>
</div>
""", unsafe_allow_html=True)
else:
    _PLAT_COLORS = {"naver": "#03C75A", "daangn": "#FF6F0F", "kakao": "#FAD400"}
    _PLAT_FG     = {"naver": "#fff",    "daangn": "#fff",    "kakao": "#3A1D1D"}

    # ── 전체선택 / 선택삭제 툴바 ─────────────────────────────────────────────
    _chk_all_key = f"chk_all_{selected_tab}"
    _tb_l, _tb_m, _tb_r = st.columns([1, 3, 2])
    with _tb_l:
        _all_checked = st.checkbox("전체 선택", key=_chk_all_key)
    with _tb_r:
        if _all_checked:
            _selected_ids = [acc["id"] for acc in filtered]
        else:
            _selected_ids = [
                acc["id"] for acc in filtered
                if st.session_state.get(f"chk_{acc['id']}", False)
            ]
        _n_sel = len(_selected_ids)
        _del_btn_label = f"🗑️ 선택 삭제 ({_n_sel}개)" if _n_sel else "🗑️ 선택 삭제"
        if st.button(_del_btn_label, disabled=(_n_sel == 0),
                     use_container_width=True, key="bulk_del_btn"):
            st.session_state["bulk_del_confirm"] = True
            st.rerun()

    if st.session_state.get("bulk_del_confirm") and _n_sel:
        _ids_to_del = [
            acc["id"] for acc in filtered
            if st.session_state.get(f"chk_{acc['id']}", False)
        ]
        st.warning(f"정말 {len(_ids_to_del)}개 계정을 삭제하시겠습니까?")
        _cf1, _cf2, _ = st.columns([1, 1, 3])
        with _cf1:
            if st.button("삭제 확인", type="primary", key="bulk_del_confirm_btn",
                         use_container_width=True):
                for _did in _ids_to_del:
                    delete_account(_did)
                    st.session_state.pop(f"chk_{_did}", None)
                st.session_state.pop("bulk_del_confirm", None)
                st.session_state.pop(_chk_all_key, None)
                st.toast(f"🗑️ {len(_ids_to_del)}개 계정 삭제 완료")
                st.rerun()
        with _cf2:
            if st.button("취소", key="bulk_del_cancel_btn", use_container_width=True):
                st.session_state.pop("bulk_del_confirm", None)
                st.rerun()

    st.markdown("<div style='margin-top:4px;'></div>", unsafe_allow_html=True)

    for acc in filtered:
        # 전체선택 상태에 따라 체크박스 동기화
        if _all_checked:
            st.session_state[f"chk_{acc['id']}"] = True

        plat     = acc.get("platform", "naver")
        plat_lbl = acc.get("platform_label", "네이버")
        pbg = _PLAT_COLORS.get(plat, "#03C75A")
        pfg = _PLAT_FG.get(plat, "#fff")
        plat_badge = (
            f'<span style="background:{pbg};color:{pfg};font-size:11px;font-weight:700;'
            f'padding:2px 8px;border-radius:6px;margin-right:6px;">{plat_lbl}</span>'
        )
        if plat == "naver":
            ad = f"{acc.get('ad_type','')} &nbsp;·&nbsp; " if acc.get('ad_type') else ""
            meta = (
                f"{ad}{acc.get('naver_login_id','-')} &nbsp;·&nbsp;"
                f" Customer ID: <b style='color:#333;'>{acc.get('customer_id','-')}</b>"
            )
        elif plat == "daangn":
            meta = f"계정 ID: <b style='color:#333;'>{acc.get('account_id','-')}</b>"
        else:  # kakao
            ad = f"{acc.get('ad_type','')} &nbsp;·&nbsp; " if acc.get('ad_type') else ""
            cat = acc.get('business_category') or acc.get('brand_name', '-')
            meta = (
                f"{ad}업종: {cat} &nbsp;·&nbsp;"
                f" 계정 ID: <b style='color:#333;'>{acc.get('account_id','-')}</b>"
            )
        alias_html = (
            f'<span style="margin-left:6px;background:#F5F5F5;color:#888;'
            f'font-size:11px;padding:1px 7px;border-radius:6px;">{acc["alias"]}</span>'
            if acc.get("alias") else ""
        )
        col_chk, col_card = st.columns([0.4, 5.6])
        with col_chk:
            st.markdown("<div style='padding-top:22px;'></div>", unsafe_allow_html=True)
            st.checkbox("", key=f"chk_{acc['id']}", label_visibility="collapsed")
        with col_card:
            st.markdown(f"""
<div class="acc-card">
  <div>
    <div class="acc-name">
      {plat_badge}{acc.get("account_name", "-")}{alias_html}
    </div>
    <div class="acc-meta">
      {meta} &nbsp;·&nbsp; 신청일: {acc.get("created_at", "-")[:10]}
    </div>
  </div>
  <div style="margin-top:2px;">{badge(acc.get("status","연동신청"))}</div>
</div>
""", unsafe_allow_html=True)

# ── 모달 트리거 ───────────────────────────────────────────────────────────────
if add_btn or apply_btn:
    _pre_phone = (
        get_secret("ADMIN_NOTIFY_PHONE")
        or get_secret("ADMIN_ALERT_PHONE")
        or st.session_state.get("_admin_notify_phone", "")
    )
    add_account_dialog(admin_phone=_pre_phone)


# ═════════════════════════════════════════════════════════════════════════════
# 관리자 영역
# ═════════════════════════════════════════════════════════════════════════════
st.markdown("<br>", unsafe_allow_html=True)
st.divider()

with st.expander("🔐 관리자 — 상태 관리"):
    if not st.session_state.get("payback_admin_auth"):
        _, col, _ = st.columns([2, 3, 2])
        with col:
            pw = st.text_input("관리자 비밀번호", type="password", key="pb_admin_pw")
            if st.button("로그인", type="primary", use_container_width=True, key="pb_admin_login"):
                if pw == ADMIN_PW:
                    st.session_state.payback_admin_auth = True
                    st.rerun()
                else:
                    st.error("비밀번호가 틀렸습니다.")
    else:
        st.success("관리자 모드 활성화")
        all_accs = load_accounts()  # 관리자는 owner_id 필터 없이 전체 조회
        if not all_accs:
            st.info("등록된 계정이 없습니다.")
        else:
            for i, acc in enumerate(all_accs):
                with st.container(border=True):
                    c1, c2, c3, c4 = st.columns([5, 2, 1, 1])
                    with c1:
                        plat_info  = acc.get("platform_label", "네이버")
                        plat_key   = acc.get("platform", "naver")
                        owner_disp = acc.get("owner_name") or acc.get("owner_id") or "⚠️ 미지정"

                        # 플랫폼별 ID 라인
                        if plat_key == "naver":
                            id_line = (
                                f"영문ID: `{acc.get('naver_login_id','-')}` &nbsp;|&nbsp; "
                                f"숫자ID: `{acc.get('customer_id','-')}`"
                            )
                        else:
                            id_line = f"계정ID: `{acc.get('account_id','-')}`"

                        budget   = acc.get("monthly_budget") or "-"
                        ad_type  = acc.get("ad_type") or "-"
                        biz_cat  = acc.get("business_category") or ""
                        biz_line = f" &nbsp;|&nbsp; 업종: {biz_cat}" if biz_cat else ""

                        st.markdown(
                            f"**{acc.get('account_name','-')}** &nbsp; "
                            f"<span style='font-size:12px;color:#6B7280;'>{plat_info} · {ad_type}</span>",
                            unsafe_allow_html=True
                        )
                        st.markdown(
                            f"<span style='font-size:12px;color:#374151;'>"
                            f"👤 담당자: **{acc.get('manager_name','-')}** &nbsp;|&nbsp; "
                            f"신청자 계정: `{owner_disp}`"
                            f"</span>",
                            unsafe_allow_html=True
                        )
                        st.markdown(
                            f"<span style='font-size:12px;color:#6B7280;'>"
                            f"{id_line}{biz_line} &nbsp;|&nbsp; "
                            f"월예산: {budget} &nbsp;|&nbsp; "
                            f"신청일: {acc.get('created_at','-')[:10]}"
                            f"</span>",
                            unsafe_allow_html=True
                        )
                        st.markdown(badge(acc["status"]), unsafe_allow_html=True)
                    with c2:
                        new_status = st.selectbox(
                            "상태 변경",
                            STATUS_LIST,
                            index=STATUS_LIST.index(acc["status"])
                            if acc["status"] in STATUS_LIST else 0,
                            key=f"pb_status_{acc['id']}",
                            label_visibility="collapsed",
                        )
                    with c3:
                        if st.button("저장", key=f"pb_save_{acc['id']}", use_container_width=True):
                            _get_sb().table("rebate_accounts").update({"status": new_status}).eq("id", acc["id"]).execute()
                            st.toast(f"✅ {acc['account_name']} 상태 변경 완료")
                            st.rerun()
                    with c4:
                        _adm_del_key = f"adm_confirm_del_{acc['id']}"
                        if st.session_state.get(_adm_del_key):
                            if st.button("삭제 확인", key=f"adm_del_ok_{acc['id']}",
                                         type="primary", use_container_width=True):
                                if delete_account(acc["id"]):
                                    st.session_state.pop(_adm_del_key, None)
                                    st.toast(f"🗑️ '{acc['account_name']}' 삭제 완료")
                                    st.rerun()
                        else:
                            if st.button("🗑️ 삭제", key=f"adm_del_{acc['id']}",
                                         use_container_width=True):
                                st.session_state[_adm_del_key] = True
                                st.rerun()

        st.divider()

        # ── 알림 설정 상태 ──────────────────────────────────────────────────
        st.markdown("**알림 설정 상태**")
        try:
            from notifications import get_notification_config_status
            _cfg = get_notification_config_status()
            _rows = [
                ("ADMIN_ALERT_EMAIL", "이메일 수신"),
                ("SMTP_HOST",         "SMTP 호스트"),
                ("SMTP_USER",         "SMTP 계정"),
                ("SMTP_PASSWORD",     "SMTP 비밀번호"),
                ("ADMIN_ALERT_PHONE", "SMS 수신번호"),
                ("SOLAPI_API_KEY",    "SOLAPI 키"),
            ]
            _cols = st.columns(3)
            for idx, (k, label) in enumerate(_rows):
                ok = _cfg.get(k, False)
                _cols[idx % 3].metric(label, "✅ 설정됨" if ok else "❌ 미설정")
        except Exception as e:
            st.caption(f"설정 조회 오류: {e}")

        # ── 테스트 발송 ──────────────────────────────────────────────────────
        st.markdown("**테스트 발송**")
        _tc1, _tc2 = st.columns(2)
        with _tc1:
            if st.button("이메일 테스트 발송", use_container_width=True, key="pb_test_email"):
                try:
                    from notifications import send_admin_email
                    _r = send_admin_email({
                        "account_name": "테스트 광고주",
                        "platform_label": "테스트",
                        "platform": "test",
                        "ad_type": "-",
                        "manager_name": "테스트",
                        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    })
                    if _r.get("status") == "success":
                        st.toast("✅ 이메일 테스트 발송 완료")
                    else:
                        st.warning(_r.get("reason") or _r.get("error", "발송 실패"))
                except Exception as e:
                    st.error(str(e)[:200])
        with _tc2:
            if st.button("문자 테스트 발송", use_container_width=True, key="pb_test_sms"):
                try:
                    from notifications import send_admin_sms
                    _r = send_admin_sms({
                        "account_name": "테스트",
                        "platform_label": "테스트",
                        "ad_type": "-",
                        "manager_name": "테스트",
                        "monthly_budget": "-",
                    })
                    if _r.get("status") == "success":
                        st.toast("✅ 문자 테스트 발송 완료")
                    else:
                        st.warning(_r.get("reason") or _r.get("error", "발송 실패"))
                except Exception as e:
                    st.error(str(e)[:200])

        st.divider()
        if st.button("로그아웃", key="pb_admin_logout"):
            st.session_state.payback_admin_auth = False
            st.rerun()
