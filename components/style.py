# ── 브랜드 컬러 토큰 ──────────────────────────────────────────────────────────
C_NAVY       = "#111827"   # Deep Navy — 주 색상
C_NAVY_MED   = "#1F2937"   # 사이드바 호버 배경
C_BLUE       = "#0D47A1"   # Primary Blue — 버튼/강조
C_BLUE_LIGHT = "#E8EAF6"   # 블루 배경 연하게
C_SUCCESS    = "#28B463"   # 성과 우수
C_WARNING    = "#F59E0B"   # 주의
C_DANGER     = "#DC2626"   # 위험/삭제
C_BG         = "#F8FAFC"   # 앱 배경
C_CARD       = "#FFFFFF"   # 카드 배경
C_BORDER     = "#E5E7EB"   # 테두리
C_TEXT       = "#111827"   # 본문 제목
C_TEXT_SUB   = "#374151"   # 본문
C_TEXT_MUTED = "#6B7280"   # 보조 텍스트

BADGE_STYLES: dict[str, str] = {
    "연동신청":      f"background:{C_BLUE_LIGHT}; color:{C_BLUE};",
    "네이버 확인중": "background:#FEF3C7; color:#92400E;",
    "이관승인대기":  "background:#FEE2E2; color:#991B1B;",
    "연동완료":      f"background:#D1FAE5; color:#065F46;",
    "반려":          "background:#FEE2E2; color:#991B1B;",
}

STATUS_LIST = ["연동신청", "네이버 확인중", "이관승인대기", "연동완료", "반려"]


def badge(status: str) -> str:
    style = BADGE_STYLES.get(status, "background:#F3F4F6; color:#374151;")
    return (
        f'<span style="display:inline-block;padding:3px 12px;border-radius:100px;'
        f'font-size:11px;font-weight:700;{style}">{status}</span>'
    )


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

/* ══ 이미지 확대/풀스크린 버튼 제거 ════════════════════════════════════ */
button[title="View fullscreen"],
[data-testid="stImageContainer"] button,
[data-testid="stImage"] button,
[data-testid="StyledFullScreenButton"],
[data-testid="stBaseButton-headerNoPadding"],
button[aria-label="View fullscreen"] { display: none !important; }

/* ══ 앱 전체 배경 ══════════════════════════════════════════════════════ */
[data-testid="stAppViewContainer"] > section.main,
.stApp {
    background: #F8FAFC !important;
}
[data-testid="stMain"] > div,
.main .block-container {
    background: #F8FAFC !important;
}

/* ══ 사이드바 — 흰색 ══════════════════════════════════════════════════ */
[data-testid="stSidebar"] {
    background: #ffffff !important;
    border-right: 1px solid #E5E8ED !important;
}
[data-testid="stSidebar"] > div,
[data-testid="stSidebar"] > div > div,
[data-testid="stSidebarContent"],
[data-testid="stSidebarContent"] > div,
[data-testid="stSidebarUserContent"],
[data-testid="stSidebarUserContent"] > div {
    padding-top: 0 !important;
    margin-top: 0 !important;
    padding-left: 0 !important;
    padding-right: 0 !important;
    gap: 0 !important;
}

/* ══ 로고 영역 ══════════════════════════════════════════════════════════ */
.sb-logo-wrap {
    padding: 10px 18px 10px;
    border-bottom: 1px solid #E5E8ED;
    margin: 0;
}
.sb-logo-wrap img { display: block; }
.sb-logo-wrap button,
.sb-logo-wrap [data-testid="stImageContainer"] > div > button { display: none !important; }

/* ══ 그룹 레이블 ══════════════════════════════════════════════════════ */
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
    color: #0D47A1 !important;
}
[data-testid="stPageLink"] a[aria-current="page"] {
    background: #EEF2F7 !important;
    color: #0D47A1 !important;
    font-weight: 700 !important;
}

/* ══ 페이백신청 강조 ══════════════════════════════════════════════════ */
[data-testid="stPageLink"] a[href*="%ED%8E%98%EC%9D%B4%EB%B0%B1"],
[data-testid="stPageLink"] a[href*="페이백"] {
    color: #0D47A1 !important;
    font-weight: 700 !important;
}

/* ══ 사이드바 하단 ══════════════════════════════════════════════════════ */
.sb-bottom {
    border-top: 1px solid #E5E8ED;
    padding: 14px 18px 16px;
    margin-top: 32px;
}
.sb-user-info {
    font-size: 12px;
    color: #6B7280;
    padding: 4px 0 8px;
    line-height: 1.5;
}

/* ══ 전역 Primary 버튼 ══════════════════════════════════════════════════ */
[data-testid="stBaseButton-primary"] {
    background: #0D47A1 !important;
    border: none !important;
    color: #fff !important;
    font-weight: 600 !important;
}
[data-testid="stBaseButton-primary"]:hover {
    background: #1565C0 !important;
}

/* ══ 전역 카드 느낌 (metric, expander) ══════════════════════════════════ */
[data-testid="stMetric"] {
    background: #ffffff;
    border: 1px solid #E5E7EB;
    border-radius: 10px;
    padding: 16px 20px !important;
}
[data-testid="stMetricLabel"] { color: #6B7280 !important; font-size: 12px !important; font-weight: 600 !important; }
[data-testid="stMetricValue"] { color: #111827 !important; font-weight: 800 !important; }
[data-testid="stMetricDelta"] svg { display: none; }

/* ══ expander 카드화 ══════════════════════════════════════════════════ */
[data-testid="stExpander"] {
    border: 1px solid #E5E7EB !important;
    border-radius: 10px !important;
    background: #ffffff !important;
}
[data-testid="stExpander"] summary {
    color: #111827 !important;
    font-weight: 600 !important;
}

/* ══ 탭 스타일 ══════════════════════════════════════════════════════════ */
[data-baseweb="tab-list"] {
    border-bottom: 2px solid #E5E7EB !important;
    gap: 0 !important;
}
[data-baseweb="tab"] {
    color: #6B7280 !important;
    font-weight: 500 !important;
    font-size: 14px !important;
    padding: 10px 20px !important;
    border-bottom: 2px solid transparent !important;
    margin-bottom: -2px !important;
}
[aria-selected="true"][data-baseweb="tab"] {
    color: #0D47A1 !important;
    font-weight: 700 !important;
    border-bottom-color: #0D47A1 !important;
    background: transparent !important;
}

/* ══ dataframe / 테이블 헤더 ══════════════════════════════════════════ */
[data-testid="stDataFrame"] thead th,
.stDataFrame thead th {
    background: #111827 !important;
    color: #ffffff !important;
    font-weight: 600 !important;
    font-size: 12px !important;
}
[data-testid="stDataFrame"] tbody tr:hover {
    background: #F0F4FF !important;
}

/* ══ info/success/warning/error 박스 ══════════════════════════════════ */
[data-testid="stAlert"] {
    border-radius: 8px !important;
    font-size: 13px !important;
}
</style>
"""


PAYBACK_CSS = """
<style>
.block-container {
  max-width: 1400px !important;
  padding-left: 4rem !important;
  padding-right: 4rem !important;
}
[data-testid="stColumn"],
[data-testid="stHorizontalBlock"] > div,
[data-testid="stVerticalBlock"],
[data-testid="stVerticalBlockBorderWrapper"],
[data-testid="stElementContainer"] {
  background: transparent !important;
  box-shadow: none !important;
  border: none !important;
}
[data-testid="stHorizontalBlock"]:has(.sec-ttl) {
  align-items: center !important;
  margin: 28px 0 8px !important;
}
[data-testid="stHorizontalBlock"]:has(.sec-ttl) [data-testid="stColumn"]:first-child {
  display: flex;
  align-items: center;
}

.pb-h1 { font-size:26px; font-weight:800; color:#111827; margin:0 0 6px; letter-spacing:-.5px; }
.pb-sub { font-size:15px; color:#6B7280; margin:0 0 20px; }

.info-card {
  background:#fff;
  border-radius:12px;
  padding:24px 28px;
  border:1px solid #E5E7EB;
  box-shadow:0 1px 4px rgba(0,0,0,.05);
  height:100%;
}
.info-card-ttl {
  font-size:14px; font-weight:700; color:#111827; margin-bottom:20px;
}

.steps {
  display:flex; align-items:flex-start; justify-content:space-between; gap:0;
}
.step { display:flex; flex-direction:column; align-items:center; flex:1; }
.step-num {
  width:44px; height:44px; border-radius:50%;
  background:#0D47A1; color:#fff;
  font-size:17px; font-weight:800;
  display:flex; align-items:center; justify-content:center;
  margin-bottom:10px;
  box-shadow:0 3px 10px rgba(13,71,161,.25);
}
.step-lbl { font-size:13px; font-weight:700; color:#111827; text-align:center; white-space:nowrap; }
.step-desc { font-size:12px; color:#9CA3AF; text-align:center; margin-top:4px; line-height:1.5; white-space:nowrap; }
.step-line { flex:1; height:2px; background:#E5E7EB; margin-top:22px; min-width:16px; }

.notice-wrap {
  background:#FFFBEB;
  border-radius:10px;
  border-left:3px solid #F59E0B;
  padding:18px 20px;
}
.notice-ttl { font-size:13px; font-weight:800; color:#B45309; margin-bottom:14px; }
.notice-row {
  display:grid;
  grid-template-columns: 80px 1fr;
  gap:12px;
  margin-bottom:10px;
  align-items:baseline;
}
.notice-row:last-child { margin-bottom:0; }
.notice-key { font-size:12px; font-weight:700; color:#374151; white-space:nowrap; }
.notice-val { font-size:12px; color:#374151; line-height:1.6; word-break:keep-all; }
em-blue { color:#0D47A1; font-style:normal; font-weight:700; }
em-red  { color:#DC2626; font-style:normal; font-weight:700; }

.sec-hdr {
  display:flex; justify-content:space-between; align-items:center;
  margin:32px 0 16px;
}
.sec-ttl { font-size:17px; font-weight:800; color:#111827; }
.count-pill {
  background:#E8EAF6; color:#0D47A1;
  font-size:12px; font-weight:700;
  padding:2px 10px; border-radius:100px; margin-left:8px;
}

.acc-card {
  background:#fff;
  border-radius:12px;
  padding:20px 24px;
  border:1px solid #E5E7EB;
  margin-bottom:12px;
  display:flex;
  justify-content:space-between;
  align-items:flex-start;
  transition:box-shadow .18s, border-color .18s;
}
.acc-card:hover {
  box-shadow:0 4px 16px rgba(13,71,161,.08);
  border-color:#BFDBFE;
}
.acc-name { font-size:15px; font-weight:700; color:#111827; margin-bottom:5px; }
.acc-meta { font-size:12px; color:#9CA3AF; line-height:1.8; }

.empty-wrap { text-align:center; padding:64px 0; }
.empty-ico { font-size:42px; margin-bottom:14px; }
.empty-ttl { font-size:14px; font-weight:700; color:#374151; margin-bottom:4px; }
.empty-desc { font-size:12px; color:#9CA3AF; }
</style>
"""


# ── 공통 유틸 CSS (개별 페이지에서 추가 주입 가능) ─────────────────────────────
CARD_CSS = """
<style>
.mk-card {
    background: #ffffff;
    border: 1px solid #E5E7EB;
    border-radius: 12px;
    padding: 20px 24px;
    margin-bottom: 12px;
    box-shadow: 0 1px 3px rgba(0,0,0,.04);
}
.mk-card-title {
    font-size: 13px;
    font-weight: 700;
    color: #6B7280;
    text-transform: uppercase;
    letter-spacing: .6px;
    margin-bottom: 6px;
}
.mk-card-value {
    font-size: 26px;
    font-weight: 800;
    color: #111827;
    line-height: 1.2;
}
.mk-card-delta-up   { font-size:12px; color:#28B463; font-weight:600; }
.mk-card-delta-down { font-size:12px; color:#DC2626; font-weight:600; }

.mk-section-title {
    font-size: 16px;
    font-weight: 700;
    color: #111827;
    border-left: 3px solid #0D47A1;
    padding-left: 10px;
    margin: 24px 0 14px;
}

.mk-badge-blue    { display:inline-block;padding:2px 10px;border-radius:100px;font-size:11px;font-weight:700;background:#E8EAF6;color:#0D47A1; }
.mk-badge-green   { display:inline-block;padding:2px 10px;border-radius:100px;font-size:11px;font-weight:700;background:#D1FAE5;color:#065F46; }
.mk-badge-yellow  { display:inline-block;padding:2px 10px;border-radius:100px;font-size:11px;font-weight:700;background:#FEF3C7;color:#92400E; }
.mk-badge-red     { display:inline-block;padding:2px 10px;border-radius:100px;font-size:11px;font-weight:700;background:#FEE2E2;color:#991B1B; }
.mk-badge-gray    { display:inline-block;padding:2px 10px;border-radius:100px;font-size:11px;font-weight:700;background:#F3F4F6;color:#374151; }
</style>
"""
