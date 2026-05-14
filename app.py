import streamlit as st
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from components.style import SIDEBAR_CSS

try:
    from PIL import Image
except ImportError:
    Image = None

LOGO_PATH = next(
    (os.path.join(ROOT, f) for f in ["logo2.png", "logo.png", "logo.jpg", "logo.jpeg", "logo.webp"]
     if os.path.exists(os.path.join(ROOT, f))),
    None,
)


def _load_favicon():
    if LOGO_PATH and Image:
        try:
            return Image.open(LOGO_PATH)
        except Exception:
            pass
    return "📊"


st.set_page_config(
    page_title="마케팁",
    page_icon=_load_favicon(),
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── 사이드바 CSS 주입 ─────────────────────────────────────────────────────────
st.markdown(SIDEBAR_CSS, unsafe_allow_html=True)

# ── 커스텀 사이드바 ────────────────────────────────────────────────────────────
with st.sidebar:

    # 로고
    st.markdown('<div class="sb-logo-wrap">', unsafe_allow_html=True)
    if LOGO_PATH:
        st.image(LOGO_PATH, width=160)
    else:
        st.markdown(
            '<div style="font-size:20px;font-weight:900;color:#006633;'
            'letter-spacing:-.5px;">마케팁</div>',
            unsafe_allow_html=True,
        )
    st.markdown('</div>', unsafe_allow_html=True)

    # ── 광고 관리 ──────────────────────────────────────────────────────────
    st.markdown('<span class="sb-label">광고 관리</span>', unsafe_allow_html=True)
    st.page_link("pages/광고분석컨설팅.py", label="📈  광고분석컨설팅", use_container_width=True)
    st.page_link("pages/월간보고서.py",     label="📩  월간보고서",      use_container_width=True)

    st.markdown('<hr class="sb-divider">', unsafe_allow_html=True)

    # ── 정산 관리 (id="section-payback" → CSS 강조 트리거) ─────────────────
    st.markdown('<span class="sb-label" id="section-payback">정산 관리</span>',
                unsafe_allow_html=True)
    st.page_link("pages/페이백신청.py", label="💸  광고비 페이백신청", use_container_width=True)

# ── 라우팅 ────────────────────────────────────────────────────────────────────
pg = st.navigation([
    st.Page("pages/광고분석컨설팅.py", title="광고분석컨설팅"),
    st.Page("pages/월간보고서.py",    title="월간보고서"),
    st.Page("pages/페이백신청.py",    title="광고비 페이백신청"),
])
pg.run()
