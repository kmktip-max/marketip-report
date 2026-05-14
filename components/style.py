BLUE        = "#0064FF"
BLUE_DARK   = "#0052D9"
BLUE_LIGHT  = "#E8F1FF"

BADGE_STYLES: dict[str, str] = {
    "연동신청":     "background:#E8F1FF; color:#0064FF;",
    "네이버 확인중": "background:#FFF3CD; color:#856404;",
    "이관승인대기": "background:#FFE8D6; color:#CC5500;",
    "연동완료":    "background:#E8F5E9; color:#2E7D32;",
    "반려":       "background:#FFE8E8; color:#C62828;",
}

STATUS_LIST = ["연동신청", "네이버 확인중", "이관승인대기", "연동완료", "반려"]


def badge(status: str) -> str:
    style = BADGE_STYLES.get(status, "background:#eee; color:#555;")
    return f'<span style="display:inline-block;padding:3px 12px;border-radius:100px;font-size:11px;font-weight:700;{style}">{status}</span>'


SIDEBAR_CSS = """
<style>
/* ══ 기본 Streamlit nav 완전 제거 ══════════════════════════════════════ */
[data-testid="stSidebarNav"],
[data-testid="stSidebarNavItems"],
[data-testid="stSidebarNavSeparator"] {
    display: none !important;
    height: 0 !important;
    min-height: 0 !important;
    padding: 0 !important;
    margin: 0 !important;
    overflow: hidden !important;
}

/* ══ 이미지 확대 버튼 제거 ══════════════════════════════════════════════ */
[data-testid="stImageContainer"] button,
button[title="View fullscreen"] { display: none !important; }

/* ══ 사이드바 기본 ══════════════════════════════════════════════════════ */
[data-testid="stSidebar"] {
    background: #fff !important;
    border-right: 1px solid #E5E8ED !important;
}
[data-testid="stSidebar"] > div:first-child {
    padding: 0 !important;
    margin: 0 !important;
}
[data-testid="stSidebarContent"] {
    padding: 0 !important;
    margin: 0 !important;
    gap: 0 !important;
}
[data-testid="stSidebarContent"] > div:first-child {
    padding-top: 0 !important;
    margin-top: 0 !important;
}

/* ══ 로고 ══════════════════════════════════════════════════════════════ */
.sb-logo-wrap {
    padding: 6px 18px 12px;
    border-bottom: 1px solid #E5E8ED;
    margin-bottom: 0;
}

/* ══ 그룹 레이블 (광고 관리 / 정산 관리 / 회원 관리 통일) ══════════════ */
.sb-label {
    display: block !important;
    font-size: 11px !important;
    font-weight: 700 !important;
    color: #9CA3AF !important;
    letter-spacing: .9px !important;
    text-transform: uppercase !important;
    padding: 22px 20px 6px !important;
    margin: 0 !important;
    line-height: 1 !important;
}

/* ══ 구분선 ══════════════════════════════════════════════════════════ */
.sb-divider {
    border: none;
    border-top: 1px solid #E5E8ED;
    margin: 8px 0 0 !important;
    padding: 0 !important;
}

/* ══ st.page_link 스타일 ══════════════════════════════════════════════ */
[data-testid="stPageLink"] {
    padding: 1px 10px !important;
    margin: 0 !important;
    width: 100% !important;
}
[data-testid="stPageLink"] a {
    display: flex !important;
    align-items: center !important;
    height: 44px !important;
    padding: 0 14px !important;
    border-radius: 10px !important;
    color: #374151 !important;
    font-size: 14px !important;
    font-weight: 500 !important;
    text-decoration: none !important;
    transition: background .15s, color .15s !important;
    gap: 10px !important;
    line-height: 1 !important;
    white-space: nowrap !important;
}
[data-testid="stPageLink"] a:hover {
    background: #F0F4FF !important;
    color: #0064FF !important;
}
[data-testid="stPageLink"] a[aria-current="page"] {
    background: #EEF2F7 !important;
    color: #0064FF !important;
    font-weight: 700 !important;
}

/* ══ 페이백신청 상시 강조 ══════════════════════════════════════════════ */
#section-payback ~ div [data-testid="stPageLink"] a {
    font-weight: 700 !important;
    color: #0055E0 !important;
}
#section-payback ~ div [data-testid="stPageLink"] a:hover,
#section-payback ~ div [data-testid="stPageLink"] a[aria-current="page"] {
    background: #EEF2F7 !important;
}

/* ══ 사이드바 하단 영역 ══════════════════════════════════════════════ */
.sb-bottom {
    border-top: 1px solid #E5E8ED;
    padding: 14px 18px 16px;
    margin-top: 32px;
}
.sb-bottom-label {
    display: block !important;
    font-size: 11px !important;
    font-weight: 700 !important;
    color: #9CA3AF !important;
    letter-spacing: .9px !important;
    text-transform: uppercase !important;
    margin-bottom: 8px !important;
}
.sb-user-info {
    font-size: 12px;
    color: #6B7280;
    padding: 4px 0 8px;
    line-height: 1.5;
}
</style>
"""


PAYBACK_CSS = """
<style>
/* ── layout ── */
.block-container {
  max-width: 1400px !important;
  padding-left: 4rem !important;
  padding-right: 4rem !important;
}
/* Streamlit 컬럼 흰 박스 제거 */
[data-testid="stColumn"] {
  background: transparent !important;
  box-shadow: none !important;
  border: none !important;
  padding: 0 !important;
}

/* ── typography ── */
.pb-h1 { font-size:26px; font-weight:800; color:#111; margin:0 0 6px; letter-spacing:-.5px; }
.pb-sub { font-size:15px; color:#666; margin:0 0 20px; }

/* ── info cards ── */
.info-card {
  background:#fff;
  border-radius:16px;
  padding:24px 28px;
  box-shadow:0 1px 10px rgba(0,0,0,.06);
  height:100%;
}
.info-card-ttl {
  font-size:14px; font-weight:700; color:#111; margin-bottom:22px;
}

/* ── step ── */
.steps {
  display:flex; align-items:flex-start; justify-content:space-between; gap:0;
}
.step { display:flex; flex-direction:column; align-items:center; flex:1; }
.step-num {
  width:44px; height:44px; border-radius:50%;
  background:#0064FF; color:#fff;
  font-size:17px; font-weight:800;
  display:flex; align-items:center; justify-content:center;
  margin-bottom:10px;
  box-shadow:0 3px 10px rgba(0,100,255,.25);
}
.step-lbl { font-size:13px; font-weight:700; color:#111; text-align:center; white-space:nowrap; }
.step-desc { font-size:12px; color:#aaa; text-align:center; margin-top:4px; line-height:1.5; white-space:nowrap; }
.step-line { flex:1; height:2px; background:#E0E7FF; margin-top:22px; min-width:16px; }

/* ── notice ── */
.notice-wrap {
  background:#FFFCF0;
  border-radius:12px;
  border-left:3px solid #F5A623;
  padding:18px 20px;
}
.notice-ttl { font-size:13px; font-weight:800; color:#F5A623; margin-bottom:14px; }
.notice-row {
  display:grid;
  grid-template-columns: 80px 1fr;
  gap:12px;
  margin-bottom:10px;
  align-items:baseline;
}
.notice-row:last-child { margin-bottom:0; }
.notice-key { font-size:12px; font-weight:700; color:#555; white-space:nowrap; }
.notice-val { font-size:12px; color:#333; line-height:1.6; word-break:keep-all; }
em-blue { color:#0064FF; font-style:normal; font-weight:700; }
em-red  { color:#CC5500; font-style:normal; font-weight:700; }

/* ── section header ── */
.sec-hdr {
  display:flex; justify-content:space-between; align-items:center;
  margin:32px 0 16px;
}
.sec-ttl { font-size:17px; font-weight:800; color:#111; }
.count-pill {
  background:#E8F1FF; color:#0064FF;
  font-size:12px; font-weight:700;
  padding:2px 10px; border-radius:100px; margin-left:8px;
}

/* ── account card ── */
.acc-card {
  background:#fff;
  border-radius:14px;
  padding:20px 24px;
  border:1.5px solid #F0F2F5;
  margin-bottom:12px;
  display:flex;
  justify-content:space-between;
  align-items:flex-start;
  transition:box-shadow .18s, border-color .18s;
}
.acc-card:hover {
  box-shadow:0 4px 18px rgba(0,100,255,.09);
  border-color:#C8D8FF;
}
.acc-name { font-size:15px; font-weight:700; color:#111; margin-bottom:5px; }
.acc-meta { font-size:12px; color:#999; line-height:1.8; }

/* ── empty ── */
.empty-wrap { text-align:center; padding:64px 0; }
.empty-ico { font-size:42px; margin-bottom:14px; }
.empty-ttl { font-size:14px; font-weight:700; color:#555; margin-bottom:4px; }
.empty-desc { font-size:12px; color:#aaa; }
</style>
"""
