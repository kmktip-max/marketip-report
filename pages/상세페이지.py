"""상세페이지 기획/분석 — 전환 중심 기획·분석 시스템"""
import streamlit as st
import json
import os
import sys
import re
import base64

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

if not st.session_state.get("authenticated"):
    st.error("🔒 로그인이 필요합니다.")
    st.stop()

# ══════════════════════════════════════════════════════════════════════════════
# 공통 헬퍼
# ══════════════════════════════════════════════════════════════════════════════
def _ai_client():
    try:
        key = ""
        if hasattr(st, "secrets"):
            key = st.secrets.get("OPENAI_API_KEY", "")
        if not key:
            key = os.getenv("OPENAI_API_KEY", "")
        if not key:
            return None
        from openai import OpenAI
        return OpenAI(api_key=key)
    except Exception:
        return None

def _fetch_page(url, timeout=8):
    try:
        import requests as _req
        resp = _req.get(url, timeout=timeout,
                        headers={"User-Agent": "Mozilla/5.0 (compatible; PageAnalyzer/1.0)"})
        resp.raise_for_status()
        text = resp.text
        text = re.sub(r'<style[^>]*>.*?</style>', ' ', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<script[^>]*>.*?</script>', ' ', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'&[a-zA-Z]+;', ' ', text)
        return re.sub(r'\s+', ' ', text).strip()[:4000]
    except Exception as e:
        return f"(URL 접속 실패: {e})"

def _txt_dl(text, fname, key):
    st.download_button("⬇️ TXT", text.encode("utf-8"), fname, "text/plain", key=key)

def _score_bar(label, score):
    pct  = score * 10
    c    = "#16A34A" if score >= 7 else ("#F59E0B" if score >= 5 else "#DC2626")
    st.markdown(
        f'<div style="margin-bottom:8px;">'
        f'<div style="display:flex;justify-content:space-between;margin-bottom:3px;">'
        f'<span style="font-size:12px;color:#374151;">{label}</span>'
        f'<span style="font-size:12px;font-weight:700;color:{c};">{score}/10</span></div>'
        f'<div style="background:#E5E8ED;border-radius:100px;height:6px;">'
        f'<div style="background:{c};border-radius:100px;height:6px;width:{pct}%;"></div>'
        f'</div></div>',
        unsafe_allow_html=True,
    )

def _color_chip(hex_val, name):
    return (
        f'<span style="display:inline-block;width:16px;height:16px;border-radius:4px;'
        f'background:{hex_val};border:1px solid #E5E8ED;vertical-align:middle;margin-right:6px;"></span>'
        f'<b>{hex_val}</b>  {name}'
    )

# ══════════════════════════════════════════════════════════════════════════════
# 기획 생성
# ══════════════════════════════════════════════════════════════════════════════
def _plan(client, inp):
    sys_msg = (
        "당신은 전환율 최적화 전문가이자 상세페이지 기획 전문가, 이커머스 마케팅 전략가입니다. "
        "단순히 예쁜 상세페이지가 아닌, 구매·문의 전환을 높이는 구조와 카피를 설계합니다. "
        "AIDA·PASONA·FAB 프레임워크와 손실회피 심리, 가격 프레이밍, 구매 장벽 제거를 반드시 활용합니다. "
        "반드시 JSON으로만 응답하세요."
    )
    usr_msg = f"""
상품/서비스: {inp['product']}
상세페이지 목표: {inp['goal']}
주요 타겟: {inp['target']}
USP 강점: {inp['usp']}
판매 채널: {inp['channel']}
가격대: {inp.get('price') or '없음'}
경쟁사/참고: {inp.get('competitor') or '없음'}
추가 정보: {inp.get('extra') or '없음'}

[적용 프레임워크]
AIDA (주의→관심→욕구→행동) / PASONA (문제→공감→해결→제안→좁히기→행동) / FAB (특징→이점→혜택)
손실회피 심리 / 가격 프레이밍 / 구매 장벽 제거 / CTA 최적화

반드시 아래 JSON만 반환하세요:
{{
  "strategy": "핵심 전략 2~3문장",
  "target_psychology": "타겟 구매 심리 분석 3~4문장",
  "core_problem": "소비자 관점 핵심 문제 정의",
  "page_structure": [
    {{
      "section": "1️⃣ 히어로 섹션",
      "purpose": "이 섹션의 목적",
      "copy": "실제 카피라이팅 전체 (헤드라인·서브카피·버튼CTA 포함)",
      "image_guide": "필요한 이미지 종류·구성·강조 포인트",
      "point": "핵심 설계 포인트"
    }}
  ],
  "color_tone": {{
    "type": "유형 (예: 신뢰형/프리미엄형/감성형)",
    "main_color": "#컬러코드",
    "main_color_name": "컬러명",
    "sub_color": "#컬러코드",
    "sub_color_name": "컬러명",
    "cta_color": "#컬러코드",
    "cta_color_name": "컬러명",
    "tone": "톤앤매너 방향",
    "mood": "추천 분위기 설명"
  }},
  "conversion_strategy": ["전략1","전략2","전략3","전략4","전략5"]
}}

page_structure는 반드시 아래 9개 섹션 전부 포함:
1️⃣ 히어로 섹션 (첫 화면 헤드카피, 강한 후킹, 손실회피)
2️⃣ 문제 공감 ("이거 내 이야기다" 설계)
3️⃣ 해결 제안 (제품이 어떻게 해결하는지)
4️⃣ USP 강조 (FAB 구조)
5️⃣ 제품 특징 설명 (성능/품질/구성/장점)
6️⃣ 타겟 고객 강조 (이런 분께 딱 맞습니다)
7️⃣ 가격 설득 (프레이밍, 장기 비용 구조)
8️⃣ 신뢰 확보 (후기/테스트/사용사례/생산구조)
9️⃣ CTA (구매/문의 행동 유도, 긴급성 부여)
"""
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": sys_msg},
            {"role": "user",   "content": usr_msg},
        ],
        response_format={"type": "json_object"},
        temperature=0.7,
    )
    return json.loads(resp.choices[0].message.content)

# ══════════════════════════════════════════════════════════════════════════════
# 분석 생성
# ══════════════════════════════════════════════════════════════════════════════
def _analyze(client, inp, page_text="", image_b64=None):
    sys_msg = (
        "당신은 전환율 최적화 컨설턴트이자 상세페이지 분석 전문가입니다. "
        "구매·문의 전환율을 저해하는 구조적 문제를 찾아내고 구체적 개선안을 제시합니다. "
        "AIDA·PASONA·FAB 관점에서 분석하며 구매 퍼널 전체를 평가합니다. "
        "반드시 JSON으로만 응답하세요."
    )
    page_snip = page_text[:3000] if page_text and not page_text.startswith("(URL") else "(내용 추출 불가)"
    text_content = f"""
상품/서비스: {inp.get('product') or '없음'}
URL: {inp.get('url') or '없음'}
페이지 내용 (자동 추출): {page_snip}
추가 정보: {inp.get('extra') or '없음'}

[분석 기준]
1. 상세페이지 구조 (AIDA/PASONA 흐름)
2. 구매 설득 구조
3. 전환율 저해 요소
4. 경쟁 대비 차별성
5. 구매 장벽
6. CTA 위치·강도
7. 전체 구매 퍼널

반드시 아래 JSON만 반환하세요:
{{
  "problems": [
    {{"rank": 1, "issue": "문제점", "reason": "왜 문제인지", "impact": "전환에 미치는 영향"}}
  ],
  "conversion_issues": "전환율이 낮은 핵심 이유 3~4문장",
  "structure_improvement": [
    {{"section": "섹션명", "current_problem": "현재 문제", "suggestion": "구체적 개선안"}}
  ],
  "copy_improvement": [
    {{"location": "위치", "current": "현재 카피/문제", "improved": "개선 카피", "reason": "이유"}}
  ],
  "image_improvement": [
    {{"section": "섹션", "issue": "현재 문제", "suggestion": "개선안"}}
  ],
  "color_improvement": {{
    "current_issue": "현재 문제",
    "suggestion": "개선 방향",
    "recommended_main": "#컬러코드",
    "recommended_cta": "#컬러코드"
  }},
  "cta_improvement": [
    {{"location": "위치", "current": "현재", "improved": "개선안", "reason": "이유"}}
  ],
  "funnel_analysis": {{
    "hero_score": 7,
    "problem_empathy_score": 5,
    "usp_score": 6,
    "trust_score": 4,
    "barrier_score": 3,
    "cta_score": 5,
    "overall_score": 5,
    "summary": "종합 평가 2~3문장"
  }},
  "conversion_strategy": ["전략1","전략2","전략3","전략4","전략5"]
}}

problems는 반드시 10개 생성 (전환율 영향 큰 순으로).
"""
    content = [{"type": "text", "text": text_content}]
    if image_b64:
        content.append({
            "type":      "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
        })
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": sys_msg},
            {"role": "user",   "content": content},
        ],
        response_format={"type": "json_object"},
        temperature=0.7,
    )
    return json.loads(resp.choices[0].message.content)

# ══════════════════════════════════════════════════════════════════════════════
# 렌더 — 기획 결과
# ══════════════════════════════════════════════════════════════════════════════
def _render_plan(result):
    # ── 핵심 전략 ─────────────────────────────────────────────────────────
    with st.expander("🎯 핵심 전략", expanded=True):
        st.markdown(
            f'<div style="font-size:14px;color:#111;line-height:1.8;">'
            f'{result.get("strategy","")}</div>',
            unsafe_allow_html=True,
        )
        st.markdown("---")
        st.markdown("**🧠 타겟 구매 심리 분석**")
        st.markdown(
            f'<div style="font-size:13px;color:#374151;line-height:1.8;">'
            f'{result.get("target_psychology","")}</div>',
            unsafe_allow_html=True,
        )
        st.markdown("---")
        st.markdown("**❗ 핵심 문제 정의**")
        st.info(result.get("core_problem",""))

    # ── 섹션별 구조 + 카피 ────────────────────────────────────────────────
    structures = result.get("page_structure", [])
    all_copy_txt = ""
    for i, sec in enumerate(structures):
        sname = sec.get("section","")
        copy  = sec.get("copy","")
        img   = sec.get("image_guide","")
        point = sec.get("point","")
        all_copy_txt += f"\n\n{'='*40}\n{sname}\n{'='*40}\n{copy}"

        with st.expander(f"{sname}", expanded=(i == 0)):
            st.markdown(f'<div style="font-size:11px;color:#6B7280;margin-bottom:4px;">📌 설계 목적: {sec.get("purpose","")}</div>', unsafe_allow_html=True)
            st.markdown("**📝 카피라이팅**")
            st.code(copy, language=None)
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**📸 이미지 구성 가이드**")
                st.markdown(
                    f'<div style="background:#F8FAFC;border:1px solid #E5E8ED;border-radius:8px;'
                    f'padding:10px 14px;font-size:13px;color:#374151;line-height:1.7;">{img}</div>',
                    unsafe_allow_html=True,
                )
            with col2:
                st.markdown("**⚡ 핵심 설계 포인트**")
                st.markdown(
                    f'<div style="background:#EFF6FF;border:1px solid #BFDBFE;border-radius:8px;'
                    f'padding:10px 14px;font-size:13px;color:#1D4ED8;line-height:1.7;">{point}</div>',
                    unsafe_allow_html=True,
                )

    # ── 전체 카피 다운로드 ─────────────────────────────────────────────────
    if all_copy_txt:
        _txt_dl(all_copy_txt.strip(), "상세페이지_전체카피.txt", "plan_all_copy")

    # ── 컬러 및 톤앤매너 ──────────────────────────────────────────────────
    ct = result.get("color_tone", {})
    if ct:
        with st.expander("🎨 컬러 및 톤앤매너", expanded=False):
            st.markdown(f"**유형: {ct.get('type','')}**")
            cc1, cc2, cc3 = st.columns(3)
            with cc1:
                st.markdown("메인 컬러")
                st.markdown(
                    f'<div style="background:{ct.get("main_color","#000")};height:40px;border-radius:8px;margin-bottom:6px;"></div>'
                    f'<code>{ct.get("main_color","")}</code>  {ct.get("main_color_name","")}',
                    unsafe_allow_html=True,
                )
            with cc2:
                st.markdown("서브 컬러")
                st.markdown(
                    f'<div style="background:{ct.get("sub_color","#000")};height:40px;border-radius:8px;margin-bottom:6px;"></div>'
                    f'<code>{ct.get("sub_color","")}</code>  {ct.get("sub_color_name","")}',
                    unsafe_allow_html=True,
                )
            with cc3:
                st.markdown("CTA 버튼")
                st.markdown(
                    f'<div style="background:{ct.get("cta_color","#000")};height:40px;border-radius:8px;margin-bottom:6px;"></div>'
                    f'<code>{ct.get("cta_color","")}</code>  {ct.get("cta_color_name","")}',
                    unsafe_allow_html=True,
                )
            st.markdown("---")
            st.markdown(f"**톤앤매너:** {ct.get('tone','')}")
            st.markdown(f"**분위기:** {ct.get('mood','')}")

    # ── 전환율 상승 전략 ──────────────────────────────────────────────────
    strategies = result.get("conversion_strategy", [])
    if strategies:
        with st.expander("🚀 전환율 상승 전략", expanded=False):
            for i, s in enumerate(strategies, 1):
                st.markdown(
                    f'<div style="background:#F0FFF4;border-left:4px solid #16A34A;'
                    f'padding:10px 14px;border-radius:0 8px 8px 0;margin-bottom:8px;">'
                    f'<b>전략 {i}.</b> {s}</div>',
                    unsafe_allow_html=True,
                )

# ══════════════════════════════════════════════════════════════════════════════
# 렌더 — 분석 결과
# ══════════════════════════════════════════════════════════════════════════════
def _render_analysis(result):
    # ── 구매 퍼널 점수 ────────────────────────────────────────────────────
    funnel = result.get("funnel_analysis", {})
    if funnel:
        with st.expander("📊 구매 퍼널 분석", expanded=True):
            overall = funnel.get("overall_score", 0)
            oc = "#16A34A" if overall >= 7 else ("#F59E0B" if overall >= 5 else "#DC2626")
            st.markdown(
                f'<div style="text-align:center;padding:16px 0 8px;">'
                f'<div style="font-size:13px;color:#6B7280;margin-bottom:4px;">종합 전환 점수</div>'
                f'<div style="font-size:42px;font-weight:900;color:{oc};">{overall}<span style="font-size:20px;">/10</span></div>'
                f'</div>',
                unsafe_allow_html=True,
            )
            st.caption(funnel.get("summary", ""))
            st.markdown("---")
            fc1, fc2 = st.columns(2)
            with fc1:
                _score_bar("첫 화면 구매 유도력",  funnel.get("hero_score", 0))
                _score_bar("문제 공감 설계",        funnel.get("problem_empathy_score", 0))
                _score_bar("USP 전달력",             funnel.get("usp_score", 0))
            with fc2:
                _score_bar("신뢰 구조",             funnel.get("trust_score", 0))
                _score_bar("구매 장벽 제거",         funnel.get("barrier_score", 0))
                _score_bar("CTA 위치/강도",          funnel.get("cta_score", 0))

    # ── 문제점 TOP10 ──────────────────────────────────────────────────────
    problems = result.get("problems", [])
    if problems:
        with st.expander(f"🚨 전환율 저해 문제점 TOP {len(problems)}", expanded=True):
            for p in problems:
                rank   = p.get("rank", "")
                issue  = p.get("issue", "")
                reason = p.get("reason", "")
                impact = p.get("impact", "")
                bg = "#FFF5F5" if rank <= 3 else "#FFFBEB" if rank <= 6 else "#F8FAFC"
                bc = "#FCA5A5" if rank <= 3 else "#FDE68A" if rank <= 6 else "#E5E8ED"
                st.markdown(
                    f'<div style="background:{bg};border:1px solid {bc};border-radius:10px;'
                    f'padding:12px 16px;margin-bottom:8px;">'
                    f'<div style="font-size:13px;font-weight:700;color:#111;margin-bottom:4px;">'
                    f'#{rank}  {issue}</div>'
                    f'<div style="font-size:12px;color:#6B7280;">이유: {reason}</div>'
                    f'<div style="font-size:12px;color:#DC2626;margin-top:3px;">전환 영향: {impact}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

    # ── 전환율이 낮은 이유 ────────────────────────────────────────────────
    ci = result.get("conversion_issues", "")
    if ci:
        with st.expander("📉 전환율이 낮은 핵심 이유", expanded=False):
            st.markdown(
                f'<div style="font-size:14px;color:#111;line-height:1.8;">{ci}</div>',
                unsafe_allow_html=True,
            )

    # ── 구조 개선 제안 ────────────────────────────────────────────────────
    struct_impr = result.get("structure_improvement", [])
    if struct_impr:
        with st.expander("🏗️ 구조 개선 제안", expanded=False):
            for s in struct_impr:
                st.markdown(f"**{s.get('section','')}**")
                sc1, sc2 = st.columns(2)
                with sc1:
                    st.markdown(
                        f'<div style="background:#FFF5F5;border:1px solid #FCA5A5;border-radius:8px;'
                        f'padding:10px 12px;font-size:12px;color:#374151;">❌ {s.get("current_problem","")}</div>',
                        unsafe_allow_html=True,
                    )
                with sc2:
                    st.markdown(
                        f'<div style="background:#F0FFF4;border:1px solid #86EFAC;border-radius:8px;'
                        f'padding:10px 12px;font-size:12px;color:#374151;">✅ {s.get("suggestion","")}</div>',
                        unsafe_allow_html=True,
                    )
                st.markdown("<div style='margin-bottom:8px;'></div>", unsafe_allow_html=True)

    # ── 카피 개선 제안 ────────────────────────────────────────────────────
    copy_impr = result.get("copy_improvement", [])
    if copy_impr:
        with st.expander("✍️ 카피 개선 제안", expanded=False):
            for c in copy_impr:
                st.markdown(f"**📍 {c.get('location','')}**")
                st.markdown(
                    f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:12px;">'
                    f'<div style="background:#FFF5F5;border:1px solid #FCA5A5;border-radius:8px;padding:10px 12px;font-size:13px;">❌ {c.get("current","")}</div>'
                    f'<div style="background:#F0FFF4;border:1px solid #86EFAC;border-radius:8px;padding:10px 12px;font-size:13px;">✅ {c.get("improved","")}</div>'
                    f'</div>'
                    f'<div style="font-size:11px;color:#6B7280;margin-bottom:16px;">이유: {c.get("reason","")}</div>',
                    unsafe_allow_html=True,
                )

    # ── 이미지·컬러·CTA 개선 ─────────────────────────────────────────────
    img_impr = result.get("image_improvement", [])
    if img_impr:
        with st.expander("📸 이미지 개선 제안", expanded=False):
            for im in img_impr:
                st.markdown(
                    f'<div style="background:#F8FAFC;border:1px solid #E5E8ED;border-radius:8px;'
                    f'padding:10px 14px;margin-bottom:8px;">'
                    f'<b>{im.get("section","")}</b><br>'
                    f'<span style="color:#DC2626;font-size:12px;">❌ {im.get("issue","")}</span><br>'
                    f'<span style="color:#16A34A;font-size:12px;">✅ {im.get("suggestion","")}</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

    color_impr = result.get("color_improvement", {})
    cta_impr   = result.get("cta_improvement", [])
    if color_impr or cta_impr:
        with st.expander("🎨 컬러/CTA 개선 제안", expanded=False):
            if color_impr:
                st.markdown("**컬러 개선**")
                st.markdown(
                    f'<div style="background:#FFFBEB;border:1px solid #FDE68A;border-radius:8px;padding:12px;">'
                    f'문제: {color_impr.get("current_issue","")}<br>'
                    f'방향: {color_impr.get("suggestion","")}<br>'
                    f'추천 메인: <code>{color_impr.get("recommended_main","")}</code>  '
                    f'CTA: <code>{color_impr.get("recommended_cta","")}</code>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                st.markdown("")
            if cta_impr:
                st.markdown("**CTA 개선**")
                for ct in cta_impr:
                    st.markdown(
                        f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:8px;">'
                        f'<div style="background:#FFF5F5;border:1px solid #FCA5A5;border-radius:8px;padding:10px 12px;font-size:12px;">[{ct.get("location","")}]<br>❌ {ct.get("current","")}</div>'
                        f'<div style="background:#F0FFF4;border:1px solid #86EFAC;border-radius:8px;padding:10px 12px;font-size:12px;">✅ {ct.get("improved","")}</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

    # ── 전환율 상승 전략 ──────────────────────────────────────────────────
    strategies = result.get("conversion_strategy", [])
    if strategies:
        with st.expander("🚀 전환율 상승 전략", expanded=False):
            for i, s in enumerate(strategies, 1):
                st.markdown(
                    f'<div style="background:#EFF6FF;border-left:4px solid #1D4ED8;'
                    f'padding:10px 14px;border-radius:0 8px 8px 0;margin-bottom:8px;">'
                    f'<b>전략 {i}.</b> {s}</div>',
                    unsafe_allow_html=True,
                )

# ══════════════════════════════════════════════════════════════════════════════
# PAGE
# ══════════════════════════════════════════════════════════════════════════════
st.title("📐 상세페이지 기획/분석")
st.caption("전환 중심 상세페이지 기획·제작 및 현재 페이지 분석·컨설팅")

col_in, col_out = st.columns([2, 3], gap="large")

# ── 입력 ─────────────────────────────────────────────────────────────────────
with col_in:
    st.markdown("#### STEP 1. 진행 방식")
    mode = st.radio(
        "",
        ["1️⃣  상세페이지 기획 및 제작", "2️⃣  현재 상세페이지 분석 및 컨설팅"],
        key="sp_mode",
        label_visibility="collapsed",
    )
    is_plan = "기획" in mode

    st.markdown("---")

    if is_plan:
        st.markdown("#### STEP 2. 상품/서비스 정보")
        sp_product    = st.text_input("상품/서비스명 *", placeholder="예: 마케팁 광고 컨설팅 서비스")
        sp_goal       = st.selectbox("상세페이지 목표 *",
                                     ["구매 전환", "상담 신청", "문의 확보", "강의 신청", "예약", "기타"])
        sp_target     = st.text_input("주요 타겟 고객 *",
                                      placeholder="예: 광고비 낭비 중인 스마트스토어 판매자")
        sp_usp        = st.text_area("USP 강점 3가지 *",
                                     placeholder="1. 10년 이상 광고 운영 경험\n2. 전환율 중심 구조 설계\n3. 합리적인 월 관리비",
                                     height=100)
        sp_channel    = st.selectbox("판매 채널",
                                     ["스마트스토어", "쿠팡", "자사몰", "카카오스토어", "기타"])
        sp_price      = st.text_input("가격대 (선택)", placeholder="예: 월 30만원~")
        sp_competitor = st.text_input("경쟁사/참고 URL (선택)")
        sp_extra      = st.text_area("추가 정보 (규격·용량·구성 등, 선택)", height=80)

        run_btn = st.button("🚀 상세페이지 기획 생성",
                            type="primary", use_container_width=True, key="sp_run_plan")

    else:
        st.markdown("#### STEP 2. 분석할 상세페이지 정보")
        sp_product = st.text_input("상품/서비스명 (선택)", placeholder="예: 법무법인 재현 이혼 상담")
        sp_url     = st.text_input("상세페이지 URL *", placeholder="https://smartstore.naver.com/...")
        sp_image   = st.file_uploader(
            "상세페이지 이미지 업로드 (선택, URL과 함께 사용 가능)",
            type=["jpg","jpeg","png","webp"],
            help="상세페이지 캡처 이미지를 업로드하면 더 정확한 분석이 가능합니다."
        )
        sp_extra = st.text_area("추가 정보/분석 요청사항 (선택)", height=80,
                                placeholder="전환율이 낮다, 특정 섹션이 약한 것 같다 등")

        run_btn = st.button("🔍 상세페이지 분석 시작",
                            type="primary", use_container_width=True, key="sp_run_analyze")

# ── 결과 ─────────────────────────────────────────────────────────────────────
with col_out:
    st.markdown("#### 결과")

    if run_btn:
        client = _ai_client()
        if not client:
            st.error("OpenAI API 키가 설정되지 않았습니다.")
        elif is_plan and not st.session_state.get("sp_plan_product","") and not locals().get("sp_product","").strip():
            st.warning("상품/서비스명을 입력해주세요.")
        else:
            if is_plan:
                inp = {
                    "product":    sp_product.strip(),
                    "goal":       sp_goal,
                    "target":     sp_target.strip(),
                    "usp":        sp_usp.strip(),
                    "channel":    sp_channel,
                    "price":      sp_price.strip(),
                    "competitor": sp_competitor.strip(),
                    "extra":      sp_extra.strip(),
                }
                with st.spinner("🧠 구매 퍼널 분석 및 상세페이지 기획 중... (30~90초)"):
                    try:
                        result = _plan(client, inp)
                        st.session_state["sp_result"]      = result
                        st.session_state["sp_result_mode"] = "plan"
                    except Exception as e:
                        st.error(f"기획 생성 실패: {e}")
            else:
                if not sp_url.strip() and not sp_image:
                    st.warning("URL 또는 이미지를 입력해주세요.")
                else:
                    page_text  = ""
                    image_b64  = None
                    if sp_url.strip():
                        with st.spinner("🔍 페이지 내용 분석 중..."):
                            page_text = _fetch_page(sp_url.strip())
                    if sp_image:
                        image_b64 = base64.b64encode(sp_image.read()).decode("utf-8")
                    inp = {
                        "product": sp_product.strip(),
                        "url":     sp_url.strip(),
                        "extra":   sp_extra.strip(),
                    }
                    with st.spinner("🔍 전환율 저해 요소 분석 중... (30~90초)"):
                        try:
                            result = _analyze(client, inp, page_text, image_b64)
                            st.session_state["sp_result"]      = result
                            st.session_state["sp_result_mode"] = "analyze"
                        except Exception as e:
                            st.error(f"분석 실패: {e}")

    result      = st.session_state.get("sp_result")
    result_mode = st.session_state.get("sp_result_mode")

    if not result:
        st.caption("좌측에서 정보를 입력하고 실행하세요.")
    elif result_mode == "plan":
        _render_plan(result)
    else:
        _render_analysis(result)
