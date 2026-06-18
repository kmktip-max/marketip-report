"""랜딩페이지 기획/분석 — 전용 GPT 연결 허브"""
import streamlit as st
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

if not st.session_state.get("authenticated"):
    st.error("🔒 로그인이 필요합니다.")
    st.stop()

GPT_URL = "https://chatgpt.com/g/g-69afedf65af48191b61a2d6e306770cb-ai-sangsepeiji-maketib"

st.title("📐 랜딩페이지 기획/분석")

st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)

# ── 중앙 카드 레이아웃 ────────────────────────────────────────────────────────
_, card, _ = st.columns([1, 4, 1])
with card:

    # 설명
    st.markdown(
        """
<div style="font-size:15px;color:#374151;line-height:2.0;margin-bottom:24px;">
전환 중심 랜딩페이지 분석 및 기획을 전문 GPT 기반으로 진행합니다.<br><br>
아래 항목을 분석해드립니다.
</div>
""",
        unsafe_allow_html=True,
    )

    # 분석 항목 리스트
    items = [
        ("🔍", "상세페이지 구조 분석"),
        ("📊", "구매 퍼널 분석"),
        ("🔔", "CTA 개선 방향"),
        ("📈", "전환율 개선 전략"),
        ("✍️", "카피라이팅 개선 제안"),
        ("🖼️", "이미지 구성 방향"),
    ]
    cols = st.columns(2)
    for i, (icon, label) in enumerate(items):
        cols[i % 2].markdown(
            f'<div style="background:#F8FAFC;border:1px solid #E5E8ED;border-radius:10px;'
            f'padding:12px 16px;margin-bottom:10px;font-size:14px;color:#111;">'
            f'{icon}&nbsp;&nbsp;{label}</div>',
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height:20px;'></div>", unsafe_allow_html=True)

    # 안내 박스
    st.markdown(
        """
<div style="background:#EFF6FF;border:1.5px solid #BFDBFE;border-radius:12px;
padding:18px 22px;margin-bottom:28px;">
<div style="font-size:13px;font-weight:700;color:#1D4ED8;margin-bottom:8px;">
📌 분석 전 준비사항
</div>
<div style="font-size:13px;color:#1F2937;line-height:1.9;">
현재 사용 중인 <b>상세페이지, 스마트스토어, 랜딩페이지 URL</b>을 준비해주세요.<br>
이미지 캡처 파일이 있으면 함께 첨부하면 더욱 정확한 분석이 가능합니다.
</div>
</div>
""",
        unsafe_allow_html=True,
    )

    # CTA 버튼
    st.markdown(
        f"""
<div style="text-align:center;">
  <a href="{GPT_URL}" target="_blank" style="
    display:inline-block;
    background:#0D47A1;
    color:#ffffff;
    font-size:16px;
    font-weight:700;
    padding:16px 48px;
    border-radius:12px;
    text-decoration:none;
    letter-spacing:-.3px;
    box-shadow:0 4px 16px rgba(0,102,51,0.25);
    transition:background .15s;
  ">GPT로 랜딩페이지 분석하기 →</a>
</div>
""",
        unsafe_allow_html=True,
    )

    st.markdown("<div style='height:16px;'></div>", unsafe_allow_html=True)
    st.caption("전용 분석 페이지에서 결과를 확인합니다.")
