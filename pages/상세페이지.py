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

def _step_header(num, title):
    st.markdown(
        f'<div style="display:flex;align-items:center;gap:12px;margin:28px 0 14px;">'
        f'<div style="background:#111;color:#fff;font-size:11px;font-weight:800;'
        f'padding:4px 10px;border-radius:100px;white-space:nowrap;">STEP {num}</div>'
        f'<div style="font-size:16px;font-weight:800;color:#111;">{title}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

def _consulting_block(text):
    st.markdown(
        f'<div style="font-size:14px;color:#1F2937;line-height:2.0;'
        f'background:#F8FAFC;border-left:4px solid #1D4ED8;'
        f'padding:16px 20px;border-radius:0 10px 10px 0;margin-bottom:12px;">'
        f'{text.replace(chr(10), "<br>")}</div>',
        unsafe_allow_html=True,
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
        "당신은 10년 이상 경력의 상세페이지 전환율 컨설턴트입니다. "
        "목표는 '광고 유입 사용자가 왜 문의·구매하지 않는가'를 밝히는 것입니다. "
        "AI 자동 리포트가 아닌 실제 컨설팅처럼 분석합니다. "
        "반드시 해당 페이지 내용을 기반으로 구체적으로 분석하고, "
        "일반론 나열은 절대 금지입니다. "
        "문체는 직설적·설명형·소비자 심리 중심으로 작성합니다. "
        "부족합니다 한 줄 요약 절대 금지. 반드시 JSON으로만 응답하세요."
    )
    page_snip = page_text[:3000] if page_text and not page_text.startswith("(URL") else "(내용 추출 불가)"
    text_content = (
        f"상품/서비스: {inp.get('product') or '없음'}\n"
        f"URL: {inp.get('url') or '없음'}\n"
        f"페이지 내용 (자동 추출):\n{page_snip}\n"
        f"추가 정보: {inp.get('extra') or '없음'}\n\n"
        "분석 원칙:\n"
        "1. 반드시 위 페이지 내용을 기반으로 구체적으로 분석. 일반론 금지.\n"
        "2. 각 항목마다 왜 문제인지 / 소비자가 어떻게 느끼는지 / 왜 이탈하는지를 충분히 설명.\n"
        "3. 카피 예시는 실제 바로 쓸 수 있는 수준으로 구체적으로.\n"
        "4. 부족합니다 개선이 필요합니다 같은 짧은 요약 절대 금지.\n"
        "5. 전환 중심 관점: 예쁜 UI 평가가 아닌 문의 구매 전환 관점으로만 분석.\n\n"
        "반드시 아래 JSON만 반환하세요:\n"
        "{\n"
        '  "top_problems": [\n'
        "    {\n"
        '      "rank": 1,\n'
        '      "title": "문제 제목 (명확하고 구체적으로)",\n'
        '      "description": "현재 어떤 문제가 있는지 + 왜 문제가 되는지 + 소비자는 어떻게 느끼는지 + 왜 이탈하는지 (4~6문장으로 충분히 설명. 실제 컨설팅 문체)"\n'
        "    }\n"
        "  ],\n"
        '  "conversion_analysis": "전환율이 낮아지는 핵심 원인을 소비자 심리 기반으로 설명 (6~10문장. 왜 클릭 후 이탈하는가 / 왜 문의가 안 나오는가 / 왜 신뢰가 약한가 / 왜 CTA가 약한가. 이 페이지에 실제로 해당하는 내용으로 구체적으로)",\n'
        '  "structure_improvement": [\n'
        "    {\n"
        '      "section": "1️⃣ 히어로 섹션",\n'
        '      "why_needed": "이 섹션이 전환에서 하는 역할 설명",\n'
        '      "current_problem": "현재 이 페이지의 해당 섹션 문제점 (구체적으로)",\n'
        '      "ideal_flow": "어떤 흐름이어야 하는지",\n'
        '      "copy_direction": "어떤 방향의 카피가 효과적인지"\n'
        "    }\n"
        "  ],\n"
        '  "copy_improvement": [\n'
        "    {\n"
        '      "location": "위치 (예: 메인 헤드카피)",\n'
        '      "current": "현재 문구 또는 현재 문제 상황",\n'
        '      "improved": "개선 카피 예시 (실제 쓸 수 있는 수준으로)",\n'
        '      "reason": "왜 이 카피가 효과적인지 (소비자 심리 기반)"\n'
        "    }\n"
        "  ],\n"
        '  "image_improvement": [\n'
        "    {\n"
        '      "priority": "1순위",\n'
        '      "what": "어떤 이미지/콘텐츠가 필요한지",\n'
        '      "why": "왜 이 이미지가 전환에 필요한지 (소비자 심리 기반으로 설명)",\n'
        '      "description": "구체적인 이미지 구성 방향"\n'
        "    }\n"
        "  ],\n"
        '  "conversion_strategy": [\n'
        "    {\n"
        '      "priority": "1순위",\n'
        '      "action": "실행 액션 (짧고 명확하게)",\n'
        '      "description": "구체적 실행 방법 (2~3문장)",\n'
        '      "expected_effect": "기대 효과"\n'
        "    }\n"
        "  ],\n"
        '  "overall_verdict": {\n'
        '    "type": "현재 페이지 유형 (예: 회사소개형 / 브랜딩형 / 정보전달형 / 전환형 미완성 등)",\n'
        '    "summary": "현재 페이지 상태 총평 (3~5문장. 직설적으로)",\n'
        '    "urgent_action": "지금 당장 해야 할 1가지 액션 (구체적으로)"\n'
        "  }\n"
        "}\n\n"
        "top_problems는 반드시 10개 (전환 영향 큰 순).\n"
        "structure_improvement는 아래 6개 섹션 반드시 포함:\n"
        "  1번 히어로 섹션 / 2번 문제 공감 / 3번 실패 경험 자극 / 4번 해결 구조 / 5번 실제 사례 후기 / 6번 CTA\n"
        "copy_improvement는 6개 이상 (히어로/문제공감/CTA/신뢰/후기 위치 반드시 포함).\n"
        "image_improvement는 5개 이상 (각각 이유 포함).\n"
        "conversion_strategy는 6개 이상 (우선순위 기반).\n"
    )
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
    if all_copy_txt:
        _txt_dl(all_copy_txt.strip(), "상세페이지_전체카피.txt", "plan_all_copy")

    ct = result.get("color_tone", {})
    if ct:
        with st.expander("🎨 컬러 및 톤앤매너", expanded=False):
            st.markdown(f"**유형: {ct.get('type','')}**")
            cc1, cc2, cc3 = st.columns(3)
            for col, key_c, key_n, label in [
                (cc1, "main_color", "main_color_name", "메인 컬러"),
                (cc2, "sub_color",  "sub_color_name",  "서브 컬러"),
                (cc3, "cta_color",  "cta_color_name",  "CTA 버튼"),
            ]:
                col.markdown(
                    f'<div style="background:{ct.get(key_c,"#000")};height:40px;border-radius:8px;margin-bottom:6px;"></div>'
                    f'<code>{ct.get(key_c,"")}</code>  {ct.get(key_n,"")}',
                    unsafe_allow_html=True,
                )
            st.markdown("---")
            st.markdown(f"**톤앤매너:** {ct.get('tone','')}")
            st.markdown(f"**분위기:** {ct.get('mood','')}")

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
# 렌더 — 분석 결과 (7단계 컨설팅)
# ══════════════════════════════════════════════════════════════════════════════
def _render_analysis(result):

    # ── STEP 1: 문제점 TOP 10 ────────────────────────────────────────────
    _step_header(1, "상세페이지 문제점 TOP 10")
    problems = result.get("top_problems", [])
    for p in problems:
        rank  = int(p.get("rank", 99))
        title = p.get("title", "")
        desc  = p.get("description", "")
        if rank <= 3:
            bg, bc, rc = "#FFF5F5", "#FCA5A5", "#DC2626"
        elif rank <= 6:
            bg, bc, rc = "#FFFBEB", "#FDE68A", "#92400E"
        else:
            bg, bc, rc = "#F8FAFC", "#E5E8ED", "#374151"
        st.markdown(
            f'<div style="background:{bg};border:1.5px solid {bc};border-radius:12px;'
            f'padding:16px 20px;margin-bottom:12px;">'
            f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:10px;">'
            f'<span style="background:{rc};color:#fff;font-size:12px;font-weight:800;'
            f'min-width:28px;height:28px;border-radius:50%;display:flex;align-items:center;'
            f'justify-content:center;">#{rank}</span>'
            f'<span style="font-size:14px;font-weight:800;color:#111;">{title}</span>'
            f'</div>'
            f'<div style="font-size:13px;color:#1F2937;line-height:2.0;">'
            f'{desc.replace(chr(10), "<br>")}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # ── STEP 2: 전환율이 낮아지는 이유 ──────────────────────────────────
    _step_header(2, "전환율이 낮아지는 이유")
    ci = result.get("conversion_analysis", "")
    if ci:
        _consulting_block(ci)

    # ── STEP 3: 상세페이지 구조 개선 제안 ────────────────────────────────
    _step_header(3, "상세페이지 구조 개선 제안")
    structures = result.get("structure_improvement", [])
    for sec in structures:
        label = sec.get("section", "")
        with st.expander(f"{label}", expanded=False):
            st.markdown(
                f'<div style="margin-bottom:12px;">'
                f'<div style="font-size:11px;font-weight:700;color:#6B7280;margin-bottom:4px;">이 섹션의 역할</div>'
                f'<div style="font-size:13px;color:#374151;line-height:1.9;">{sec.get("why_needed","")}</div>'
                f'</div>'
                f'<div style="background:#FFF5F5;border-left:3px solid #DC2626;padding:12px 16px;'
                f'border-radius:0 8px 8px 0;margin-bottom:12px;">'
                f'<div style="font-size:11px;font-weight:700;color:#DC2626;margin-bottom:4px;">현재 문제점</div>'
                f'<div style="font-size:13px;color:#1F2937;line-height:1.9;">{sec.get("current_problem","")}</div>'
                f'</div>'
                f'<div style="margin-bottom:12px;">'
                f'<div style="font-size:11px;font-weight:700;color:#92400E;margin-bottom:4px;">이상적인 흐름</div>'
                f'<div style="font-size:13px;color:#374151;line-height:1.9;">{sec.get("ideal_flow","")}</div>'
                f'</div>'
                f'<div style="background:#EFF6FF;border-left:3px solid #1D4ED8;padding:12px 16px;border-radius:0 8px 8px 0;">'
                f'<div style="font-size:11px;font-weight:700;color:#1D4ED8;margin-bottom:4px;">카피 방향</div>'
                f'<div style="font-size:13px;color:#1F2937;line-height:1.9;">{sec.get("copy_direction","")}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    # ── STEP 4: 카피라이팅 개선 제안 ─────────────────────────────────────
    _step_header(4, "카피라이팅 개선 제안")
    copy_impr = result.get("copy_improvement", [])
    all_copy_txt = ""
    for c in copy_impr:
        loc      = c.get("location", "")
        current  = c.get("current", "")
        improved = c.get("improved", "")
        reason   = c.get("reason", "")
        all_copy_txt += f"[{loc}]\n현재: {current}\n개선: {improved}\n\n"
        with st.expander(f"📍 {loc}", expanded=False):
            st.markdown(
                f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px;">'
                f'<div style="background:#FFF5F5;border:1.5px solid #FCA5A5;border-radius:8px;'
                f'padding:12px 14px;">'
                f'<div style="font-size:11px;font-weight:700;color:#DC2626;margin-bottom:6px;">현재</div>'
                f'<div style="font-size:13px;color:#374151;line-height:1.8;">{current}</div>'
                f'</div>'
                f'<div style="background:#F0FFF4;border:1.5px solid #86EFAC;border-radius:8px;'
                f'padding:12px 14px;">'
                f'<div style="font-size:11px;font-weight:700;color:#16A34A;margin-bottom:6px;">개선 카피</div>'
                f'<div style="font-size:13px;color:#111;line-height:1.8;font-weight:600;">{improved}</div>'
                f'</div></div>'
                f'<div style="font-size:12px;color:#6B7280;line-height:1.8;">💡 {reason}</div>',
                unsafe_allow_html=True,
            )
    if all_copy_txt:
        _txt_dl(all_copy_txt.strip(), "카피_개선제안.txt", "analyze_copy_dl")

    # ── STEP 5: 이미지 개선 제안 ─────────────────────────────────────────
    _step_header(5, "이미지 개선 제안")
    img_impr = result.get("image_improvement", [])
    for ig in img_impr:
        priority = ig.get("priority", "")
        st.markdown(
            f'<div style="background:#F8FAFC;border:1.5px solid #E5E8ED;border-radius:12px;'
            f'padding:14px 18px;margin-bottom:10px;">'
            f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:8px;">'
            f'<span style="background:#111;color:#fff;font-size:11px;font-weight:700;'
            f'padding:2px 10px;border-radius:100px;">{priority}</span>'
            f'<span style="font-size:14px;font-weight:700;color:#111;">{ig.get("what","")}</span>'
            f'</div>'
            f'<div style="font-size:13px;color:#1F2937;line-height:1.9;margin-bottom:6px;">'
            f'<b style="color:#374151;">필요한 이유</b><br>{ig.get("why","")}</div>'
            f'<div style="font-size:12px;color:#6B7280;line-height:1.8;">{ig.get("description","")}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # ── STEP 6: 전환율 상승 전략 ─────────────────────────────────────────
    _step_header(6, "전환율 상승 전략")
    strategies = result.get("conversion_strategy", [])
    for s in strategies:
        priority = s.get("priority", "")
        st.markdown(
            f'<div style="background:#F8FAFC;border:1.5px solid #E5E8ED;border-radius:12px;'
            f'padding:14px 18px;margin-bottom:10px;">'
            f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:8px;">'
            f'<span style="background:#1D4ED8;color:#fff;font-size:11px;font-weight:700;'
            f'padding:2px 10px;border-radius:100px;">{priority}</span>'
            f'<span style="font-size:14px;font-weight:700;color:#111;">{s.get("action","")}</span>'
            f'</div>'
            f'<div style="font-size:13px;color:#1F2937;line-height:1.9;margin-bottom:6px;">{s.get("description","")}</div>'
            f'<div style="font-size:12px;color:#16A34A;font-weight:600;">기대 효과: {s.get("expected_effect","")}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # ── STEP 7: 최종 총평 ─────────────────────────────────────────────────
    _step_header(7, "최종 총평")
    verdict = result.get("overall_verdict", {})
    if verdict:
        vtype   = verdict.get("type", "")
        summary = verdict.get("summary", "")
        urgent  = verdict.get("urgent_action", "")
        st.markdown(
            f'<div style="background:#F8FAFC;border:1.5px solid #E5E8ED;border-radius:14px;'
            f'padding:20px 24px;margin-bottom:12px;">'
            f'<div style="display:inline-block;background:#374151;color:#fff;font-size:12px;'
            f'font-weight:700;padding:3px 12px;border-radius:100px;margin-bottom:14px;">'
            f'현재 페이지 유형: {vtype}</div>'
            f'<div style="font-size:14px;color:#1F2937;line-height:2.0;margin-bottom:16px;">'
            f'{summary.replace(chr(10), "<br>")}</div>'
            f'<div style="background:#FFFBEB;border:1.5px solid #FDE68A;border-radius:10px;'
            f'padding:14px 18px;">'
            f'<div style="font-size:12px;font-weight:700;color:#92400E;margin-bottom:6px;">'
            f'⚡ 지금 당장 해야 할 1가지</div>'
            f'<div style="font-size:14px;color:#111;font-weight:600;line-height:1.8;">{urgent}</div>'
            f'</div></div>',
            unsafe_allow_html=True,
        )

# ══════════════════════════════════════════════════════════════════════════════
# PAGE
# ══════════════════════════════════════════════════════════════════════════════
st.title("📐 랜딩페이지 기획/분석")
st.caption("전환 중심 랜딩페이지 기획·제작 및 현재 페이지 분석·컨설팅")

col_in, col_out = st.columns([2, 3], gap="large")

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

with col_out:
    st.markdown("#### 결과")

    if run_btn:
        client = _ai_client()
        if not client:
            st.error("OpenAI API 키가 설정되지 않았습니다.")
        else:
            if is_plan:
                if not sp_product.strip():
                    st.warning("상품/서비스명을 입력해주세요.")
                else:
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
                    page_text = ""
                    image_b64 = None
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
