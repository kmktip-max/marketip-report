"""광고 소재 생성기 — 플랫폼별 광고 문법 + 소비자 심리 기반 실무형 소재 생성"""
import streamlit as st
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

if not st.session_state.get("authenticated"):
    st.error("🔒 로그인이 필요합니다.")
    st.stop()

# ══════════════════════════════════════════════════════════════════════════════
# 상수
# ══════════════════════════════════════════════════════════════════════════════
_PLATFORMS = [
    ("naver_search",   "1️⃣  네이버 검색광고 (파워링크)"),
    ("naver_shopping", "2️⃣  네이버 쇼핑검색"),
    ("meta",           "3️⃣  메타광고 (인스타그램/페이스북)"),
    ("kakao",          "4️⃣  카카오광고 (톡채널/비즈보드)"),
    ("google",         "5️⃣  구글광고 (GDN/검색/유튜브)"),
    ("etc",            "6️⃣  기타 매체 (당근/틱톡/쓰레드)"),
]

_STYLES = [
    "감성적 + 스토리 중심",
    "숫자·데이터 강조형",
    "소비자 문제 해결형 + 강한 후킹",
    "대화형 / 공감 유도형",
]

_STRENGTHS = ["가격 경쟁력", "후기/평점", "브랜드 신뢰", "전문성", "접근성/편의", "속도/당일", "AS/사후관리"]
_TARGETS   = ["20~30대 여성", "20~30대 남성", "30~40대 직장인", "40~50대 남성",
              "40~50대 여성", "50~60대 (부모님 세대)", "학생/청소년", "소상공인/사업자"]
_GOALS     = ["문의/상담 확보", "예약 증가", "클릭 증가", "브랜드 노출", "구매 전환", "앱 다운로드"]
_BUDGETS   = ["50만원 이하", "100만원 이상", "200만원 이상", "300만원 이상", "500만원 이상"]

_RISK_WORDS = ["문의폭주", "무조건", "100%", "완벽보장", "매출보장", "무제한",
               "최저가보장", "절대", "기적", "100% 환급", "100%환급"]

# ══════════════════════════════════════════════════════════════════════════════
# 헬퍼
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

def _risks(text):
    return [w for w in _RISK_WORDS if w in (text or "")]

def _cn_badge(text, limit):
    n = len(text or "")
    ok = n <= limit
    c  = "#16A34A" if ok else "#DC2626"
    ic = "✅" if ok else "❌ 초과"
    return f'<span style="font-size:11px;color:{c};font-weight:600;">{n}/{limit}자 {ic}</span>'

def _field_row(label, text, limit=None):
    risk = _risks(text)
    risk_str = f'  <span style="color:#DC2626;font-size:11px;">⚠️ 정책 위험: {", ".join(risk)}</span>' if risk else ""
    cn_str = _cn_badge(text, limit) if limit else ""
    st.markdown(
        f'<div style="margin-bottom:10px;">'
        f'<div style="font-size:11px;color:#6B7280;font-weight:600;margin-bottom:2px;">'
        f'{label} {cn_str}{risk_str}</div>'
        f'<div style="font-size:14px;color:#111;background:#F8FAFC;border:1px solid #E5E8ED;'
        f'border-radius:8px;padding:8px 12px;line-height:1.6;">{text or "—"}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

def _txt_dl(content, fname, key):
    st.download_button("⬇️ TXT", content.encode("utf-8"), fname, "text/plain", key=key)

def _csv_dl(rows, fname, key):
    csv = "유형,항목,내용\n" + "\n".join(f'"{t}","{k}","{v}"' for t, k, v in rows)
    st.download_button("⬇️ CSV", csv.encode("utf-8-sig"), fname, "text/csv", key=key)

# ══════════════════════════════════════════════════════════════════════════════
# AI 생성
# ══════════════════════════════════════════════════════════════════════════════
def _build_prompt(inp):
    has = inp["has"]
    plat_str  = ", ".join(inp["platforms"])
    style_str = ", ".join(inp["styles"]) or "자유형"

    naver_rule = (
        "\n[네이버 검색광고 글자수 — 공백 포함, 반드시 준수]\n"
        "제목 15자 이내 / 설명 45자 이내(최대 활용) / "
        "추가제목 15자 이내 / 추가설명 45자 이내 / 홍보문구 14자 이내\n"
    ) if has["naver_search"] else ""

    shopping_rule = (
        "\n[네이버 쇼핑 홍보문구 글자수]\n"
        "짧은 문구 10자 이내 / 긴 문구 30자 이내\n"
    ) if has["naver_shopping"] else ""

    google_rule = (
        "\n[구글광고 글자수]\n"
        "헤드라인 30자 이내 / 설명 90자 이내\n"
    ) if has["google"] else ""

    # 플랫폼별 생성 지시
    sections = []
    industry_ref = inp.get("industry", "")
    if has["naver_search"]:
        sections.append(
            f'"naver_search": [\n'
            f'  업종 "{industry_ref}"에 최적화된 4개 유형을 직접 설계하세요.\n'
            f'  (아래 예시 참고 후 이 업종에 맞게 유형명 직접 작성)\n\n'
            f'  [업종별 유형 예시 — 그대로 쓰지 말고 이 업종에 맞게 변형]\n'
            f'  이혼/법률 → 여성공감형 / 재산분할공포형 / 양육권전략형 / 초기대응형\n'
            f'  광고대행 → 광고비누수형 / 문의부재형 / 구조문제형 / 전환설계형\n'
            f'  병원/의원 → 증상공감형 / 치료지연위험형 / 전문성강조형 / 빠른예약형\n'
            f'  교육/학원 → 성적불안형 / 시간부족형 / 결과중심형 / 무료체험형\n'
            f'  인테리어 → 비용걱정형 / 시공불신형 / 시간절약형 / 무료견적형\n'
            f'  이커머스 → 가격비교형 / 품질보증형 / 빠른배송형 / 후기신뢰형\n\n'
            f'  [유형명 규칙] "형"으로 끝나는 2~5글자 명사. 이 업종 소비자 심리 기반으로 직접 설계.\n\n'
            f'  각 세트 필드: type, title(15자이내), description(45자이내 꽉 채울 것), '
            f'additional_title(15자이내), additional_description(45자이내 꽉 채울 것), promo_text(14자이내)\n'
            f']'
        )
    else:
        sections.append('"naver_search": []')

    if has["naver_shopping"]:
        sections.append(
            '"naver_shopping": [\n'
            '  4세트 (후킹형 / 혜택형 / 신뢰형 / 비교형)\n'
            '  각 세트 필드: type, short_text(10자이내), long_text(30자이내)\n'
            ']'
        )
    else:
        sections.append('"naver_shopping": []')

    if has["meta"]:
        sections.append(
            '"meta": [\n'
            '  3세트 (후킹형 / 공감형 / 데이터형)\n'
            '  각 세트 필드: type, image_recommendation(이미지 추천 1~2문장),\n'
            '  body_copy(5~7줄 설득형. 첫줄 반드시 강한 후킹. 줄바꿈 \\n 사용), title\n'
            ']'
        )
    else:
        sections.append('"meta": []')

    if has["kakao"]:
        sections.append(
            '"kakao": [\n'
            '  3세트 (친근형 / 공감형 / 혜택형)\n'
            '  각 세트 필드: type, main_copy, sub_copy\n'
            ']'
        )
    else:
        sections.append('"kakao": []')

    if has["google"]:
        sections.append(
            '"google": [\n'
            '  3세트 (검색의도형 / USP강조형 / 행동유도형)\n'
            '  각 세트 필드: type, headline1(30자이내), headline2(30자이내), description(90자이내)\n'
            ']'
        )
    else:
        sections.append('"google": []')

    if has["etc"]:
        sections.append(
            '"etc": [\n'
            '  3세트 (생활밀착형 / 공감형 / 후킹형)\n'
            '  각 세트 필드: type, copy\n'
            ']'
        )
    else:
        sections.append('"etc": []')

    sections_str = ",\n  ".join(sections)

    return f"""
[광고 정보]
플랫폼: {plat_str}
소재 스타일: {style_str}
업종: {inp["industry"]}
URL: {inp.get("url") or "없음"}
서비스 강점: {inp.get("strengths") or "없음"}
주 고객층: {inp.get("target") or "없음"}
광고 목표: {inp.get("goal") or "없음"}
광고 예산: {inp.get("budget") or "없음"}
추가 정보: {inp.get("extra") or "없음"}
{naver_rule}{shopping_rule}{google_rule}
━━━ 검색광고 카피 핵심 원칙 ━━━

[절대 금지 표현 — 사용 즉시 실패]
- 최고의 서비스 / 믿을 수 있는 / 전문적인 상담
- 고객 만족 / 풍부한 경험 / 친절한 상담
- 합리적인 가격 / 최선을 다하는
→ 위와 같은 추상적·브랜딩성 표현은 절대 사용 금지.
  누구나 쓰는 표현은 클릭 유인력이 0에 가깝다.

[검색광고 카피 우선순위]
1순위: 검색 의도 직격 — 소비자가 검색창에 치는 맥락 그대로 반영
2순위: 소비자 문제 상황 — 지금 처한 상황 공감
3순위: 손실 회피 — 대응 늦으면 불리하다는 긴급성
4순위: 문의/전환 유도 CTA

[검색광고 카피 예시 — 이 느낌으로 작성]
✅ 이혼 대응 늦으면 불리할 수 있습니다
✅ 재산분할, 초기 전략이 결과를 바꿉니다
✅ 클릭은 나오는데 문의가 없다면 구조 문제
✅ 광고비만 쓰고 전환이 없다면 설계 문제입니다
✅ 지금 상담하지 않으면 더 복잡해질 수 있습니다
✅ 무료 상담 신청 → 3분이면 충분합니다

[생성 톤 기준]
- 짧고 강하게 (15자 제목은 단어 낭비 금지)
- 검색 키워드 중심으로 자연스럽게
- 실전 광고 느낌 (광고 문구처럼 들리면 안 됨)
- 소비자 상황 기반 (업종별 실제 검색자 상황 반영)

[설명·추가설명 45자 활용 원칙]
- 절대 짧게 끝내지 말 것
- 소비자 불안 → 해결 포인트 → CTA 흐름으로 꽉 채울 것
- 예: "재산분할·양육권 경험 풍부. 초기 전략 수립이 결과를 바꿉니다. 무료상담 가능"

[플랫폼별 전략]
네이버 검색: 검색 의도 직격, 15자 제목은 핵심 키워드+소구점만, 설명 45자 꽉 활용
구글 검색: 검색 목적 기반, 명확한 USP + 숫자/증거
메타/인스타: 첫 줄 스크롤 멈추는 강한 후킹, 5~7줄 설득형, CTA 자연스럽게
카카오: 친근한 말투, 생활 밀착, 부담 없는 CTA
당근/기타: 동네 밀착 공감, 가까운 거리감

반드시 아래 JSON 구조로만 응답하세요:
{{
  "analysis": {{
    "consumer_insight": "이 업종 소비자의 핵심 심리·니즈·불안 분석 3~4문장",
    "pain_points": ["구체적 불안요소1", "구체적 불안요소2", "구체적 불안요소3"],
    "conversion_points": ["전환을 만드는 포인트1", "전환을 만드는 포인트2"],
    "platform_strategy": "선택 플랫폼별 실전 전략 2~3문장"
  }},
  {sections_str}
}}
"""

def _generate(client, inp):
    sys_msg = (
        "당신은 10년 이상 경력의 마케팅 전문가이자 소비자 심리 분석 전문가입니다. "
        "검색광고 카피는 '짧은 시간 안에 클릭을 유도'하는 것이 핵심입니다. "
        "평범한 브랜드 문구, 추상적 신뢰 표현, 누구나 쓰는 표현은 절대 사용하지 않습니다. "
        "대신 검색 의도 직격, 소비자 문제 상황, 손실 회피, 긴급성, 문의 유도를 중심으로 "
        "짧고 강하고 실전에서 바로 쓸 수 있는 카피를 생성합니다. "
        "반드시 JSON으로만 응답하세요."
    )
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": sys_msg},
            {"role": "user",   "content": _build_prompt(inp)},
        ],
        response_format={"type": "json_object"},
        temperature=0.7,
    )
    return json.loads(resp.choices[0].message.content)

# ══════════════════════════════════════════════════════════════════════════════
# 결과 렌더러
# ══════════════════════════════════════════════════════════════════════════════
def _render_naver_search(sets):
    if not sets:
        return
    import pandas as pd
    st.markdown("### 🔵 네이버 검색광고 (파워링크)")

    # ── 테이블 ────────────────────────────────────────────────────────────
    _LIMITS = {"제목(15)": 15, "설명(45)": 45, "추가제목(15)": 15, "추가설명(45)": 45, "홍보문구(14)": 14}

    table_rows = []
    for s in sets:
        table_rows.append({
            "유형":         s.get("type",""),
            "제목(15)":     s.get("title",""),
            "설명(45)":     s.get("description",""),
            "추가제목(15)": s.get("additional_title",""),
            "추가설명(45)": s.get("additional_description",""),
            "홍보문구(14)": s.get("promo_text",""),
        })
    df = pd.DataFrame(table_rows)

    def _style_table(df):
        out = pd.DataFrame("", index=df.index, columns=df.columns)
        for col, lim in _LIMITS.items():
            if col in df.columns:
                for idx in df.index:
                    if len(str(df.at[idx, col])) > lim:
                        out.at[idx, col] = "background-color:#FEE2E2;color:#DC2626;font-weight:600;"
        return out

    st.dataframe(
        df.style.apply(_style_table, axis=None),
        use_container_width=True,
        hide_index=True,
    )

    # ── 글자수 요약 ───────────────────────────────────────────────────────
    with st.expander("🔢 글자수 확인", expanded=False):
        for s in sets:
            t = s.get("type","")
            checks = [
                ("제목",     s.get("title",""),                    15),
                ("설명",     s.get("description",""),              45),
                ("추가제목", s.get("additional_title",""),         15),
                ("추가설명", s.get("additional_description",""),   45),
                ("홍보문구", s.get("promo_text",""),               14),
            ]
            badges = []
            for fname, fval, flimit in checks:
                n  = len(fval)
                ok = n <= flimit
                c  = "#16A34A" if ok else "#DC2626"
                ic = "✅" if ok else "❌"
                badges.append(
                    f'<span style="font-size:11px;color:{c};margin-right:10px;">'
                    f'{ic} {fname} {n}/{flimit}자</span>'
                )
            st.markdown(
                f'<div style="margin-bottom:6px;"><b style="font-size:12px;">{t}</b>&nbsp;&nbsp;'
                + "".join(badges) + "</div>",
                unsafe_allow_html=True,
            )

    # ── 전체 복붙용 텍스트 ────────────────────────────────────────────────
    all_txt = ""
    csv_rows = "유형,제목,설명,추가제목,추가설명,홍보문구\n"
    for s in sets:
        t, ti, de, at, ad, pr = (
            s.get("type",""), s.get("title",""), s.get("description",""),
            s.get("additional_title",""), s.get("additional_description",""),
            s.get("promo_text",""),
        )
        all_txt  += f"[{t}]\n제목: {ti}\n설명: {de}\n추가제목: {at}\n추가설명: {ad}\n홍보문구: {pr}\n\n"
        csv_rows += f'"{t}","{ti}","{de}","{at}","{ad}","{pr}"\n'

    st.code(all_txt.strip(), language=None)
    dl1, dl2 = st.columns(2)
    with dl1:
        _txt_dl(all_txt, "naver_search.txt", "ns_all_txt")
    with dl2:
        st.download_button("⬇️ CSV", csv_rows.encode("utf-8-sig"),
                           "naver_search.csv", "text/csv", key="ns_all_csv")

def _render_naver_shopping(sets):
    if not sets:
        return
    st.markdown("### 🟢 네이버 쇼핑검색 홍보문구")
    for i, s in enumerate(sets):
        t     = s.get("type", f"세트 {i+1}")
        short = s.get("short_text","")
        long  = s.get("long_text","")
        rows  = [(t, "짧은 문구", short), (t, "긴 문구", long)]
        txt   = f"[{t}]\n짧은 문구: {short}\n긴 문구: {long}"
        with st.expander(f"**{t}**", expanded=(i == 0)):
            _field_row("짧은 홍보문구 (10자 이내)", short, 10)
            _field_row("긴 홍보문구 (30자 이내)",   long,  30)
            bc1, bc2 = st.columns(2)
            with bc1:
                _txt_dl(txt, f"naver_shopping_{i+1}.txt", f"nsp_txt_{i}")
            with bc2:
                _csv_dl(rows, f"naver_shopping_{i+1}.csv", f"nsp_csv_{i}")

def _render_meta(sets):
    if not sets:
        return
    st.markdown("### 🟣 메타광고 (인스타그램/페이스북)")
    for i, s in enumerate(sets):
        t      = s.get("type", f"세트 {i+1}")
        img    = s.get("image_recommendation","")
        body   = s.get("body_copy","")
        title  = s.get("title","")
        rows   = [(t, "소재 이미지 추천", img), (t, "본문 카피", body), (t, "제목", title)]
        txt    = f"[{t}]\n[소재 이미지] {img}\n\n[본문]\n{body}\n\n[제목] {title}"
        with st.expander(f"**{t}**", expanded=(i == 0)):
            st.markdown(f'<div style="font-size:11px;color:#6B7280;font-weight:600;margin-bottom:4px;">📸 소재 이미지 추천</div>', unsafe_allow_html=True)
            st.info(img)
            _field_row("제목", title)
            st.markdown(f'<div style="font-size:11px;color:#6B7280;font-weight:600;margin-bottom:4px;">📝 본문 카피</div>', unsafe_allow_html=True)
            risk = _risks(body)
            if risk:
                st.warning(f"⚠️ 정책 위험 단어 감지: {', '.join(risk)}")
            st.code(body, language=None)
            bc1, bc2 = st.columns(2)
            with bc1:
                _txt_dl(txt, f"meta_{i+1}.txt", f"meta_txt_{i}")
            with bc2:
                _csv_dl(rows, f"meta_{i+1}.csv", f"meta_csv_{i}")

def _render_kakao(sets):
    if not sets:
        return
    st.markdown("### 🟡 카카오광고")
    for i, s in enumerate(sets):
        t    = s.get("type", f"세트 {i+1}")
        main = s.get("main_copy","")
        sub  = s.get("sub_copy","")
        rows = [(t, "메인 카피", main), (t, "서브 카피", sub)]
        txt  = f"[{t}]\n메인: {main}\n서브: {sub}"
        with st.expander(f"**{t}**", expanded=(i == 0)):
            _field_row("메인 카피", main)
            _field_row("서브 카피", sub)
            bc1, bc2 = st.columns(2)
            with bc1:
                _txt_dl(txt, f"kakao_{i+1}.txt", f"kk_txt_{i}")
            with bc2:
                _csv_dl(rows, f"kakao_{i+1}.csv", f"kk_csv_{i}")

def _render_google(sets):
    if not sets:
        return
    st.markdown("### 🔴 구글광고")
    for i, s in enumerate(sets):
        t   = s.get("type", f"세트 {i+1}")
        h1  = s.get("headline1","")
        h2  = s.get("headline2","")
        d   = s.get("description","")
        rows = [(t, "헤드라인1", h1), (t, "헤드라인2", h2), (t, "설명", d)]
        txt  = f"[{t}]\n헤드라인1: {h1}\n헤드라인2: {h2}\n설명: {d}"
        with st.expander(f"**{t}**", expanded=(i == 0)):
            _field_row("헤드라인1", h1, 30)
            _field_row("헤드라인2", h2, 30)
            _field_row("설명",      d,  90)
            bc1, bc2 = st.columns(2)
            with bc1:
                _txt_dl(txt, f"google_{i+1}.txt", f"gg_txt_{i}")
            with bc2:
                _csv_dl(rows, f"google_{i+1}.csv", f"gg_csv_{i}")

def _render_etc(sets):
    if not sets:
        return
    st.markdown("### ⚫ 기타 매체 (당근/틱톡/쓰레드)")
    for i, s in enumerate(sets):
        t   = s.get("type", f"세트 {i+1}")
        cp  = s.get("copy","")
        txt = f"[{t}]\n{cp}"
        with st.expander(f"**{t}**", expanded=(i == 0)):
            _field_row("카피", cp)
            _txt_dl(txt, f"etc_{i+1}.txt", f"etc_txt_{i}")

# ══════════════════════════════════════════════════════════════════════════════
# PAGE
# ══════════════════════════════════════════════════════════════════════════════
st.title("✍️ 광고 소재 생성기")
st.caption("플랫폼별 광고 문법 + 소비자 심리 기반 | 질문 → 분석 → 생성")

col_in, col_out = st.columns([2, 3], gap="large")

# ── 입력 ─────────────────────────────────────────────────────────────────────
with col_in:
    st.markdown("#### STEP 1.  광고 플랫폼")
    selected_plat_keys = []
    selected_plat_names = []
    for key, label in _PLATFORMS:
        if st.checkbox(label, key=f"plt_{key}"):
            selected_plat_keys.append(key)
            selected_plat_names.append(label)

    st.markdown("---")
    st.markdown("#### STEP 2.  소재 스타일")
    selected_styles = [s for s in _STYLES if st.checkbox(s, key=f"sty_{s}")]

    st.markdown("---")
    st.markdown("#### STEP 3.  업종 정보")
    industry   = st.text_input("업종 *", placeholder="예: 이혼전문변호사, 피부과, 헬스장")
    url        = st.text_input("랜딩페이지 URL (선택)", placeholder="https://...")
    strengths  = st.multiselect("서비스 강점 (복수 가능)", _STRENGTHS)
    target     = st.text_input("주 고객층", placeholder="예: 30~40대 직장인 여성, 이혼 고민 중인 분")
    goal       = st.selectbox("광고 목표", ["선택"] + _GOALS)
    budget     = st.selectbox("광고 예산", ["선택"] + _BUDGETS)
    extra      = st.text_area("추가 정보 (선택)", height=80,
                              placeholder="경쟁 차별점, 현재 광고 고민, 특이사항 등")

    st.markdown("---")
    run_btn = st.button("🚀  소비자 심리 분석 후 광고 소재 생성",
                        type="primary", use_container_width=True, key="run_ad")

# ── 결과 ─────────────────────────────────────────────────────────────────────
with col_out:
    st.markdown("#### 결과")

    if run_btn:
        if not selected_plat_keys:
            st.warning("광고 플랫폼을 하나 이상 선택해주세요.")
        elif not industry.strip():
            st.warning("업종을 입력해주세요.")
        else:
            client = _ai_client()
            if not client:
                st.error("OpenAI API 키가 설정되지 않았습니다. Streamlit Secrets에 OPENAI_API_KEY를 등록해주세요.")
            else:
                inp = {
                    "platforms": selected_plat_names,
                    "styles":    selected_styles,
                    "industry":  industry.strip(),
                    "url":       url.strip(),
                    "strengths": ", ".join(strengths),
                    "target":    ", ".join(target),
                    "goal":      goal if goal != "선택" else "",
                    "budget":    budget if budget != "선택" else "",
                    "extra":     extra.strip(),
                    "has": {k: (k in selected_plat_keys) for k, _ in _PLATFORMS},
                }
                with st.spinner("🔍 소비자 심리 분석 중..."):
                    pass
                with st.spinner("✍️ 플랫폼별 광고 소재 생성 중... (30~60초)"):
                    try:
                        result = _generate(client, inp)
                        st.session_state["ad_result"]    = result
                        st.session_state["ad_plat_keys"] = selected_plat_keys
                    except Exception as e:
                        st.error(f"소재 생성 실패: {e}")

    result    = st.session_state.get("ad_result")
    plat_keys = st.session_state.get("ad_plat_keys", [])

    if not result:
        st.caption("좌측에서 플랫폼·업종을 입력하고 '소재 생성'을 클릭하세요.")
    else:
        # ── 소비자 심리 분석 요약 ─────────────────────────────────────────
        analysis = result.get("analysis", {})
        with st.expander("🧠 소비자 심리 분석", expanded=True):
            st.markdown(
                f'<div style="font-size:13px;color:#111;line-height:1.8;margin-bottom:12px;">'
                f'{analysis.get("consumer_insight","")}</div>',
                unsafe_allow_html=True,
            )
            pp = analysis.get("pain_points", [])
            cp = analysis.get("conversion_points", [])
            pc1, pc2 = st.columns(2)
            with pc1:
                st.markdown("**😟 소비자 불안 요소**")
                for p in pp:
                    st.markdown(f"- {p}")
            with pc2:
                st.markdown("**✅ 전환 포인트**")
                for c in cp:
                    st.markdown(f"- {c}")
            st.markdown("---")
            st.caption(f"📌 플랫폼 전략: {analysis.get('platform_strategy','')}")

        st.markdown("<div style='margin-top:8px;'></div>", unsafe_allow_html=True)

        # ── 플랫폼별 결과 ─────────────────────────────────────────────────
        if "naver_search" in plat_keys:
            _render_naver_search(result.get("naver_search", []))
        if "naver_shopping" in plat_keys:
            _render_naver_shopping(result.get("naver_shopping", []))
        if "meta" in plat_keys:
            _render_meta(result.get("meta", []))
        if "kakao" in plat_keys:
            _render_kakao(result.get("kakao", []))
        if "google" in plat_keys:
            _render_google(result.get("google", []))
        if "etc" in plat_keys:
            _render_etc(result.get("etc", []))
