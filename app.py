import streamlit as st
import os

try:
    from PIL import Image
except ImportError:
    Image = None


def _load_favicon():
    for fname in ["logo.png", "logo.jpg", "logo.jpeg", "logo.webp", "favicon.ico", "favicon.png"]:
        path = os.path.join(os.path.dirname(__file__), fname)
        if os.path.exists(path) and Image:
            try:
                return Image.open(path)
            except Exception:
                pass
    return "📊"


st.set_page_config(
    page_title="마케팁",
    page_icon=_load_favicon(),
    layout="wide",
    initial_sidebar_state="expanded",
)

pg = st.navigation([
    st.Page("pages/광고분석컨설팅.py", title="광고분석컨설팅"),
    st.Page("pages/월간보고서.py",    title="월간보고서"),
    st.Page("pages/페이백신청.py",    title="페이백신청"),
])
pg.run()
