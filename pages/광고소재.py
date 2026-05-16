"""광고소재 추출 — 전용 GPT 연결 허브"""
import streamlit as st
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

if not st.session_state.get("authenticated"):
    st.error("🔒 로그인이 필요합니다.")
    st.stop()

GPT_URL = "https://chatgpt.com/g/g-68713ccc4b188191ad7bbc50247c7287-aisojaesaengseong-maketib"

st.title("✍️ 광고소재 추출")

st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)

_, card, _ = st.columns([1, 4, 1])
with card:

    st.markdown(
        """
<div style="font-size:15px;color:#374151;line-height:2.0;margin-bottom:24px;">
플랫폼별 광고 문구 및 소비자 심리 기반 소재를 전문 GPT 기반으로 생성합니다.<br><br>
지원 플랫폼 및 분석 항목입니다.
</div>
""",
        unsafe_allow_html=True,
    )

    platforms = [
        ("1️⃣", "네이버 검색광고"),
        ("2️⃣", "메타광고 (인스타/페이스북)"),
        ("3️⃣", "카카오광고"),
        ("4️⃣", "구글광고"),
        ("5️⃣", "당근 / 쓰레드 / 틱톡"),
    ]
    analysis = [
        ("🧠", "소비자 심리 분석"),
        ("🎯", "후킹 구조 설계"),
        ("🔔", "CTA 최적화"),
        ("💬", "문제 해결형 카피"),
        ("📈", "전환 중심 소재"),
    ]

    col_p, col_a = st.columns(2)
    with col_p:
        st.markdown(
            '<div style="font-size:11px;font-weight:700;color:#6B7280;'
            'letter-spacing:.8px;margin-bottom:8px;">지원 플랫폼</div>',
            unsafe_allow_html=True,
        )
        for icon, label in platforms:
            st.markdown(
                f'<div style="background:#F8FAFC;border:1px solid #E5E8ED;border-radius:10px;'
                f'padding:11px 14px;margin-bottom:8px;font-size:13px;color:#111;">'
                f'{icon}&nbsp;&nbsp;{label}</div>',
                unsafe_allow_html=True,
            )
    with col_a:
        st.markdown(
            '<div style="font-size:11px;font-weight:700;color:#6B7280;'
            'letter-spacing:.8px;margin-bottom:8px;">분석 항목</div>',
            unsafe_allow_html=True,
        )
        for icon, label in analysis:
            st.markdown(
                f'<div style="background:#F8FAFC;border:1px solid #E5E8ED;border-radius:10px;'
                f'padding:11px 14px;margin-bottom:8px;font-size:13px;color:#111;">'
                f'{icon}&nbsp;&nbsp;{label}</div>',
                unsafe_allow_html=True,
            )

    st.markdown("<div style='height:20px;'></div>", unsafe_allow_html=True)

    st.markdown(
        """
<div style="background:#EFF6FF;border:1.5px solid #BFDBFE;border-radius:12px;
padding:18px 22px;margin-bottom:28px;">
<div style="font-size:13px;font-weight:700;color:#1D4ED8;margin-bottom:8px;">
📌 소재 생성 전 준비사항
</div>
<div style="font-size:13px;color:#1F2937;line-height:1.9;">
<b>업종, 랜딩페이지 URL, 광고 목적, 타겟 고객</b> 정보를 준비해주세요.<br>
구체적인 정보를 제공할수록 더 정밀한 소재가 생성됩니다.
</div>
</div>
""",
        unsafe_allow_html=True,
    )

    st.markdown(
        f"""
<div style="text-align:center;">
  <a href="{GPT_URL}" target="_blank" style="
    display:inline-block;
    background:#006633;
    color:#ffffff;
    font-size:16px;
    font-weight:700;
    padding:16px 48px;
    border-radius:12px;
    text-decoration:none;
    letter-spacing:-.3px;
    box-shadow:0 4px 16px rgba(0,102,51,0.25);
  ">GPT로 광고소재 생성하기 →</a>
</div>
""",
        unsafe_allow_html=True,
    )

    st.markdown("<div style='height:16px;'></div>", unsafe_allow_html=True)
    st.caption("클릭 시 전용 GPT 소재 생성 페이지로 새 창 이동합니다.")
