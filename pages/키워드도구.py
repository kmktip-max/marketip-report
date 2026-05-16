"""광고 운영 — 키워드 추출 / 조합 / 정리"""
import streamlit as st
import re
import os
import sys
import json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# ══════════════════════════════════════════════════════════════════════════════
# 지역 DB
# ══════════════════════════════════════════════════════════════════════════════
REGION_DB = {
    "서울": {
        "강남/서초":   ["강남", "역삼", "삼성", "서초", "반포", "방배"],
        "송파/강동":   ["송파", "잠실", "문정", "위례", "강동", "천호"],
        "마포/용산":   ["마포", "홍대", "합정", "상암", "용산", "이태원", "한남"],
        "강서/양천":   ["강서", "마곡", "목동", "신정", "화곡"],
        "광진/성동":   ["광진", "건대", "구의", "성수", "왕십리"],
        "노원/도봉":   ["노원", "상계", "중계", "도봉", "창동", "쌍문"],
        "관악/동작":   ["관악", "신림", "봉천", "동작", "사당", "이수"],
        "성북/강북":   ["성북", "길음", "미아", "강북", "수유"],
        "영등포/구로": ["영등포", "여의도", "구로", "신도림", "대림"],
        "은평/서대문": ["은평", "연신내", "불광", "신촌", "연희"],
        "종로/중구":   ["종로", "광화문", "인사동", "명동", "을지로"],
    },
    "경기": {
        "수원":      ["수원", "영통", "권선", "팔달", "장안"],
        "성남/판교": ["성남", "분당", "판교", "야탑", "서현", "미금"],
        "고양/일산": ["고양", "일산", "장항", "화정", "대화"],
        "용인":      ["용인", "기흥", "수지", "보정"],
        "부천":      ["부천", "상동", "중동", "소사"],
        "안양/군포": ["안양", "평촌", "군포", "산본"],
        "안산":      ["안산", "단원", "상록"],
        "남양주":    ["남양주", "다산", "별내"],
        "화성/동탄": ["화성", "동탄", "봉담"],
        "파주/운정": ["파주", "운정", "금촌"],
        "김포":      ["김포", "장기", "풍무"],
        "평택":      ["평택", "동삭", "비전"],
        "하남/광명": ["하남", "미사", "광명", "철산"],
        "의정부":    ["의정부", "금오"],
    },
    "인천": {
        "남동구":      ["남동", "구월", "간석"],
        "부평구":      ["부평", "삼산", "갈산"],
        "연수구/송도": ["연수", "송도"],
        "서구/청라":   ["서구", "청라", "검단"],
        "계양구":      ["계양", "계산", "작전"],
        "미추홀구":    ["미추홀", "주안", "숭의"],
        "중구/동구":   ["중구", "신포", "동인천"],
    },
    "부산": {
        "해운대/수영": ["해운대", "광안", "민락", "수영", "남천"],
        "동래/연제":   ["동래", "온천", "연산", "거제"],
        "사상/사하":   ["사상", "주례", "사하", "하단"],
        "북구/금정":   ["북구", "화명", "만덕", "금정", "부산대"],
        "남구":        ["남구", "대연", "용호"],
        "부산진구":    ["부산진", "부전", "전포", "가야"],
        "중구/동구":   ["중구", "남포", "광복", "초량"],
        "강서/기장":   ["강서", "명지", "기장", "정관"],
    },
    "대구": {
        "수성구":    ["수성", "범어", "만촌", "황금", "시지"],
        "달서구":    ["달서", "성서", "상인", "진천"],
        "북구":      ["북구", "칠곡", "읍내"],
        "중구/동구": ["중구", "동성로", "동구", "신암"],
        "달성군":    ["달성", "화원", "테크노폴리스"],
    },
    "광주": {
        "광산구":    ["광산", "첨단", "수완", "운남"],
        "북구":      ["북구", "용봉", "운암"],
        "서구":      ["서구", "상무", "화정"],
        "남구/동구": ["남구", "봉선", "동구", "충장로"],
    },
    "대전": {
        "유성구":    ["유성", "노은", "전민"],
        "서구":      ["서구", "둔산", "갈마"],
        "중구/동구": ["중구", "은행", "동구", "판암"],
        "대덕구":    ["대덕", "신탄진"],
    },
    "울산": {
        "남구":  ["남구", "삼산", "달동", "무거"],
        "중구":  ["중구", "성남", "태화"],
        "북구":  ["북구", "매곡"],
        "울주군":["울주", "언양", "온양"],
    },
    "경남": {
        "창원": ["창원", "마산", "진해", "의창", "성산"],
        "진주": ["진주"],
        "김해": ["김해"],
        "양산": ["양산", "물금", "웅상"],
        "거제": ["거제"],
        "통영": ["통영"],
    },
    "경북": {
        "포항": ["포항"],
        "구미": ["구미"],
        "경주": ["경주"],
        "안동": ["안동"],
        "경산": ["경산"],
    },
    "충남": {
        "천안": ["천안", "불당", "신부", "두정"],
        "아산": ["아산", "배방"],
        "서산": ["서산"],
    },
    "충북": {
        "청주": ["청주", "흥덕", "서원"],
        "충주": ["충주"],
    },
    "전북": {
        "전주": ["전주", "덕진", "완산"],
        "군산": ["군산"],
        "익산": ["익산"],
    },
    "전남": {
        "순천": ["순천"],
        "목포": ["목포"],
        "여수": ["여수"],
    },
    "강원": {
        "춘천": ["춘천"],
        "원주": ["원주"],
        "강릉": ["강릉"],
    },
    "제주": {
        "제주시": ["제주", "제주시", "노형", "연동"],
        "서귀포": ["서귀포", "중문"],
    },
    "세종": {
        "세종": ["세종", "어진", "새롬", "한솔"],
    },
}

# ══════════════════════════════════════════════════════════════════════════════
# 접미어 DB
# ══════════════════════════════════════════════════════════════════════════════
CONV_SFXS = [
    "가격", "비용", "견적", "추천", "업체", "잘하는곳",
    "추천업체", "상담", "어디가좋아", "비교",
]
QUEST_SFXS = [
    "뭐야", "어때", "어떻게해", "뭐가좋아",
    "어디서", "추천해줘", "알려줘", "하는법",
]
INFO_SFXS = [
    "종류", "효과", "특징", "차이", "장단점",
    "리뷰", "후기", "이란", "뜻", "방법",
]
LONGTAIL_PFXS = ["저렴한", "빠른", "당일", "24시간", "주말", "야간", "전문", "믿을만한"]
LONGTAIL_SFXS = ["후기추천", "싸게파는곳", "최저가", "무료상담", "잘하는데"]
BRAND_SFXS    = ["공식", "정품", "공식사이트"]
COMP_SFXS     = ["보다나은", "vs", "비교", "대신", "차이"]

_NUM_KOR = {"1":"일","2":"이","3":"삼","4":"사","5":"오",
            "6":"육","7":"칠","8":"팔","9":"구","0":"영"}
_NUM_ENG = {"1":"원","2":"투","3":"쓰리","4":"포","5":"파이브",
            "6":"식스","7":"세븐","8":"에이트","9":"나인"}

# ══════════════════════════════════════════════════════════════════════════════
# 키워드 생성기
# ══════════════════════════════════════════════════════════════════════════════
def _gen_conv(kw):
    return [(f"{kw}{s}", "🟢") for s in CONV_SFXS]

def _gen_quest(kw):
    result = []
    for s in QUEST_SFXS:
        if s.startswith("뭐") or s.startswith("어") or s.startswith("추") or s.startswith("알"):
            result.append((f"{kw} {s}", "🟢"))
        else:
            result.append((f"{kw}{s}", "🟢"))
    return result

def _gen_info(kw):
    return [(f"{kw} {s}", "🟡") for s in INFO_SFXS]

def _gen_longtail(kw):
    result = []
    for p in LONGTAIL_PFXS:
        result.append((f"{p} {kw}", "🟡"))
    for s in LONGTAIL_SFXS:
        result.append((f"{kw} {s}", "🟡"))
    return result

def _gen_brand(kw, brand_name):
    if not brand_name:
        return []
    return ([(f"{brand_name} {kw}", "🟡"), (f"{kw} {brand_name}", "🟡")]
            + [(f"{kw} {brand_name} {s}", "🟡") for s in BRAND_SFXS])

def _gen_competitor(kw, comp_name):
    if not comp_name:
        return []
    return [(f"{comp_name} {kw} {s}", "🔴") for s in COMP_SFXS]

def _gen_regional(kw, areas):
    result = []
    for area in areas:
        result.append((f"{area} {kw}", "🟢"))
        result.append((f"{area}{kw}", "🟢"))
    return result

def _gen_expansion(kw):
    result = []
    for digit, kor in _NUM_KOR.items():
        if digit in kw:
            result.append((kw.replace(digit, kor), "🟡"))
    for digit, eng in _NUM_ENG.items():
        if digit in kw:
            result.append((kw.replace(digit, eng), "🟡"))
    stripped = re.sub(r"\s", "", kw)
    if len(stripped) >= 4:
        mid = len(stripped) // 2
        result.append((stripped[:mid] + " " + stripped[mid:], "🟡"))
    if " " in kw:
        result.append((kw.replace(" ", ""), "🟡"))
    seen, deduped = set(), []
    for item in result:
        if item[0] not in seen:
            seen.add(item[0])
            deduped.append(item)
    return deduped

# ══════════════════════════════════════════════════════════════════════════════
# 키워드 정리기
# ══════════════════════════════════════════════════════════════════════════════
_RE_SPECIAL = re.compile(r"[^\w\s가-힣ㄱ-ㅎㅏ-ㅣa-zA-Z0-9]")

def _normalize(kw):
    return re.sub(r"\s+", "", kw).lower()

def _sim_ratio(a, b):
    if not a or not b:
        return 0.0
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    matches = sum(1 for c in shorter if c in longer)
    return matches / max(len(longer), 1)

def clean_keywords(raw_lines, opts):
    seen_norm   = {}   # normalized → original
    seen_sim    = []
    cleaned, removed = [], []

    for line in raw_lines:
        kw = line.strip()
        if not kw:
            continue
        original = kw

        if opts.get("special_remove"):
            kw = _RE_SPECIAL.sub("", kw).strip()
            if not kw:
                removed.append((original, "특수문자만 구성됨"))
                continue

        kw = re.sub(r" +", " ", kw).strip()

        norm = _normalize(kw)

        if opts.get("exact_dedup") and kw in seen_norm.values():
            removed.append((original, "완전 중복"))
            continue

        if opts.get("space_dedup") and norm in seen_norm:
            removed.append((original, f"공백 무시 중복 (→ {seen_norm[norm]})"))
            continue

        if opts.get("length_check"):
            char_len = len(kw.replace(" ", ""))
            if char_len > opts.get("max_len", 15):
                removed.append((original, f"글자수 초과 ({char_len}자)"))
                continue

        if opts.get("similar_remove"):
            threshold = opts.get("sim_threshold", 0.85)
            is_similar = False
            for prev in seen_sim:
                sim = _sim_ratio(norm, prev)
                if sim >= threshold and norm != prev:
                    removed.append((original, f"유사 키워드 (유사도 {sim:.0%})"))
                    is_similar = True
                    break
            if is_similar:
                continue

        seen_norm[norm] = kw
        seen_sim.append(norm)
        cleaned.append(kw)

    return cleaned, removed

# ══════════════════════════════════════════════════════════════════════════════
# UI 헬퍼
# ══════════════════════════════════════════════════════════════════════════════
def _section(title, pairs):
    if not pairs:
        return
    kws = [k for k, _ in pairs] if isinstance(pairs[0], tuple) else list(pairs)
    tag = pairs[0][1] if isinstance(pairs[0], tuple) else ""
    st.markdown(
        f'<div style="display:flex;align-items:center;gap:8px;margin:12px 0 4px;">'
        f'<span style="font-size:13px;font-weight:700;color:#111;">{title}</span>'
        f'<span style="font-size:11px;color:#6B7280;background:#F3F4F6;'
        f'padding:1px 8px;border-radius:100px;">{len(kws)}개</span>'
        + (f'<span style="font-size:13px;">{tag}</span>' if tag else "")
        + '</div>',
        unsafe_allow_html=True,
    )
    st.code("\n".join(kws), language=None)

def _txt_bytes(kws):
    return "\n".join(kws).encode("utf-8")

def _csv_bytes(sections):
    lines = ["유형,키워드,추천도"]
    for sname, pairs in sections.items():
        if pairs and isinstance(pairs[0], tuple):
            for kw, rec in pairs:
                lines.append(f"{sname},{kw},{rec}")
        else:
            for kw in (pairs or []):
                lines.append(f"{sname},{kw},")
    return "\n".join(lines).encode("utf-8-sig")

def _all_kws(sections):
    result = []
    for pairs in sections.values():
        if pairs and isinstance(pairs[0], tuple):
            result.extend(k for k, _ in pairs)
        else:
            result.extend(pairs)
    return result

def _kpi_bar(before, after, removed):
    return (
        f'<div style="display:flex;gap:10px;margin-bottom:14px;">'
        f'<div style="flex:1;background:#EFF6FF;border:1.5px solid #93C5FD;'
        f'border-radius:10px;padding:12px;text-align:center;">'
        f'<div style="font-size:11px;color:#6B7280;">정리 전</div>'
        f'<div style="font-size:22px;font-weight:800;color:#1D4ED8;">{before}</div></div>'
        f'<div style="flex:1;background:#F0FFF4;border:1.5px solid #86EFAC;'
        f'border-radius:10px;padding:12px;text-align:center;">'
        f'<div style="font-size:11px;color:#6B7280;">정리 후</div>'
        f'<div style="font-size:22px;font-weight:800;color:#16A34A;">{after}</div></div>'
        f'<div style="flex:1;background:#FFF5F5;border:1.5px solid #FCA5A5;'
        f'border-radius:10px;padding:12px;text-align:center;">'
        f'<div style="font-size:11px;color:#6B7280;">제거됨</div>'
        f'<div style="font-size:22px;font-weight:800;color:#DC2626;">{removed}</div></div>'
        f'</div>'
    )

# ══════════════════════════════════════════════════════════════════════════════
# AI 헬퍼 (키워드 추출기용)
# ══════════════════════════════════════════════════════════════════════════════
def _get_ai_client():
    try:
        api_key = ""
        if hasattr(st, "secrets"):
            api_key = st.secrets.get("OPENAI_API_KEY", "")
        if not api_key:
            api_key = os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            return None
        from openai import OpenAI
        return OpenAI(api_key=api_key)
    except Exception:
        return None

def _fetch_page(url, timeout=8):
    try:
        import requests as _req
        resp = _req.get(url, timeout=timeout,
                        headers={"User-Agent": "Mozilla/5.0 (compatible; KeywordResearch/1.0)"})
        resp.raise_for_status()
        text = resp.text
        text = re.sub(r'<style[^>]*>.*?</style>', ' ', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<script[^>]*>.*?</script>', ' ', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'&[a-zA-Z]+;', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text[:4000]
    except Exception as e:
        return f"(URL 접속 실패: {e})"

def _ai_extract(client, business_name, url, industry, hints, location, page_text):
    sys_msg = (
        "당신은 네이버 검색광고 전문 키워드 플래너입니다. "
        "업체 정보와 사이트 내용을 분석해 실무에 바로 쓸 수 있는 "
        "한국어 검색광고 키워드를 정확하게 생성합니다. 반드시 JSON으로만 응답하세요."
    )
    loc_line  = f"\n지역 타깃: {location}" if location else ""
    hint_line = f"\n키워드 요청: {hints}" if hints else ""
    page_snip = page_text[:3000] if page_text and not page_text.startswith("(URL") else "(내용 추출 불가)"

    usr_msg = f"""
업체명: {business_name}
URL: {url}
업종: {industry or '자동 분석'}{loc_line}{hint_line}

사이트 내용 (자동 추출):
{page_snip}

━━━ 출력 형식 (반드시 이 JSON 구조만 반환) ━━━

{{
  "service_summary": "서비스/상품 분석 결과 2~3문장",
  "target_customer": "타깃 고객 분석 1문장",
  "ad_categories": [
    {{"name": "카테고리명", "desc": "이 카테고리를 광고그룹으로 나눠야 하는 이유 1문장"}},
    ...
  ],
  "핵심키워드": ["키워드1", "키워드2", ...],
  "롱테일키워드": ["키워드1", "키워드2", ...],
  "질문형키워드": ["키워드1", "키워드2", ...],
  "정보성키워드": ["키워드1", "키워드2", ...],
  "계절트렌드키워드": ["키워드1", ...],
  "경쟁사키워드": ["키워드1", ...]
}}

━━━ 키워드 요청 반영 원칙 ━━━

"키워드 요청"이 입력된 경우, 요청 의도·업종·URL 분석 결과·타깃 고객을 함께 분석하여
키워드 생성 방향에 우선 반영하세요.
예:
- "양육권 키워드 위주로" → 양육권/친권/양육비 관련 그룹 강화
- "문의형 키워드" → 전환 중심 키워드 비중 높임
- "검색량 높은 키워드" → 메인 숏테일 우선 강화

━━━ 각 항목 규칙 ━━━

[ad_categories] 3~5개만 생성
- 광고그룹을 나눌 서비스/문제 영역 기준 (키워드 유형이 아님)
- 예: 이혼소송, 양육권/양육비, 재산분할/위자료, 상간소송
- 단어 나열 금지. 반드시 name + desc 형식

[핵심키워드] 20개
- 짧고 강한 숏테일 전환형 키워드만
- 전환 가능성 높고 광고 집행 효율 높은 키워드 위주
- 불필요한 긴 문장형 키워드 제외
- 지역명 포함 키워드 절대 금지 (지역 조합은 조합기에서 처리)
- 상담/추천/비용/후기 등 확장어 포함 금지
- 질문형 금지, 정보성 금지
- 예: 이혼변호사, 이혼전문변호사, 가사전문변호사, 재산분할변호사

[롱테일키워드] 30개
- 구체적 니즈 + 서비스 조합. 2~4단어
- 지역명 포함 금지
- 예: 재산분할 이혼변호사, 양육권 소송 변호사, 협의이혼 상담 변호사

[질문형키워드] 30개
- 실제 검색자가 질문처럼 입력할 법한 자연스러운 형태
- 예: 이혼소송 변호사 꼭 필요할까, 재산분할은 어떻게 나누나요

[정보성키워드] 30개
- 블로그/콘텐츠/SEO 활용 목적
- 예: 이혼소송 절차, 재산분할 기준, 양육권 결정 방법

[계절트렌드키워드] 30개
- 업종에 시즌성/이슈성이 약하면 10개 이하 생성 가능. 억지로 만들지 말 것
- 생성할 내용이 없으면 빈 배열 [] 반환

[경쟁사키워드] 10개
- 동종업계 실제 업체명/브랜드명 기반 키워드
- 확실하지 않으면 생략. "(후보)" 표시 절대 금지
"""
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": sys_msg},
            {"role": "user",   "content": usr_msg},
        ],
        response_format={"type": "json_object"},
        temperature=0.5,
    )
    return json.loads(resp.choices[0].message.content)

# ══════════════════════════════════════════════════════════════════════════════
# PAGE
# ══════════════════════════════════════════════════════════════════════════════
st.title("🔍 키워드 도구")
st.caption("키워드 추출 → 조합 → 정리 순서로 사용하면 광고 등록 직전까지 완성됩니다.")

t_extract, t_combine, t_clean = st.tabs([
    "📌 키워드 추출기",
    "🔗 키워드 조합기",
    "🧹 키워드 정리기",
])

# ════════════════════════════════════════════════════════════════════════════
# TAB 1 · 키워드 추출기
# ════════════════════════════════════════════════════════════════════════════
with t_extract:
    col_in, col_opts, col_out = st.columns([2, 2, 3], gap="large")

    # ── 입력 ─────────────────────────────────────────────────────────────
    with col_in:
        st.markdown("#### 입력")
        ex_biz  = st.text_input("업체명 *", placeholder="예: 법무법인 마케팁", key="ex_biz")
        ex_url  = st.text_input("URL *",    placeholder="https://example.com",  key="ex_url")
        ex_industry = st.text_input("업종 (선택)",
                                    placeholder="예: 법률, 성형외과, 인테리어",
                                    key="ex_industry")
        ex_hints = st.text_area(
            "키워드 요청 (선택)",
            placeholder="예:\n- 이혼 관련 키워드 뽑아줘\n- 양육권 키워드 위주로\n- 광고대행 문의형 키워드\n- 피부과 시술 관련 키워드\n- 강남 지역 병원 키워드\n- 검색량 높은 변호사 키워드\n\n비워도 URL 기반으로 자동 분석됩니다.",
            height=160, key="ex_hints",
        )

    # ── 옵션 ─────────────────────────────────────────────────────────────
    with col_opts:
        st.markdown("#### 분석 옵션")
        ex_location = st.text_input("지역 타깃 (선택)",
                                    placeholder="예: 서울, 인천, 전국",
                                    key="ex_location")
        st.markdown("---")
        st.markdown(
            '<div style="font-size:12px;color:#6B7280;line-height:2.2;">'
            '<b style="color:#111;">생성 항목</b><br>'
            '📊 광고그룹 카테고리 3~5개<br>'
            '🟢 핵심 키워드 20개<br>'
            '🟢 롱테일 키워드 30개<br>'
            '🟢 질문형 키워드 30개<br>'
            '🟡 정보성 키워드 30개 <span style="color:#9CA3AF;">(콘텐츠용)</span><br>'
            '🟡 계절/트렌드 키워드 30개<br>'
            '🔴 경쟁사 키워드 10개'
            '</div>',
            unsafe_allow_html=True,
        )
        st.markdown("---")
        run_extract = st.button("🚀 URL 분석 후 키워드 생성", type="primary",
                                use_container_width=True, key="run_extract")

    # ── 결과 ─────────────────────────────────────────────────────────────
    with col_out:
        st.markdown("#### 결과")

        if run_extract:
            if not ex_biz.strip():
                st.warning("업체명을 입력해주세요.")
            elif not ex_url.strip():
                st.warning("URL을 입력해주세요.")
            else:
                client = _get_ai_client()
                if not client:
                    st.error("OpenAI API 키가 없습니다. Streamlit Secrets에 OPENAI_API_KEY를 등록해주세요.")
                else:
                    with st.spinner("🔍 사이트 내용 분석 중..."):
                        page_text = _fetch_page(ex_url.strip())
                    with st.spinner("🤖 AI 키워드 생성 중... (30~60초 소요)"):
                        try:
                            result = _ai_extract(
                                client,
                                ex_biz.strip(), ex_url.strip(),
                                ex_industry.strip(), ex_hints.strip(),
                                ex_location.strip(), page_text,
                            )
                            st.session_state["ex_ai_result"]  = result
                            st.session_state.pop("ex_sections", None)
                        except Exception as e:
                            st.error(f"키워드 생성 실패: {e}")

        result = st.session_state.get("ex_ai_result")
        if not result:
            st.caption("업체명·URL을 입력하고 '키워드 생성'을 누르세요.")
        else:
            # ── 서비스 분석 요약 ─────────────────────────────────────────
            st.markdown(
                f'<div style="background:#F8FAFC;border:1.5px solid #E5E8ED;border-radius:12px;'
                f'padding:14px 18px;margin-bottom:12px;">'
                f'<div style="font-size:11px;font-weight:700;color:#6B7280;margin-bottom:6px;">🔍 사이트 분석 결과</div>'
                f'<div style="font-size:13px;color:#111;line-height:1.7;">{result.get("service_summary","")}</div>'
                f'<div style="margin-top:8px;font-size:12px;color:#6B7280;">'
                f'🎯 타깃: {result.get("target_customer","")}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

            # ── 카테고리 추천 (기본 펼침) ─────────────────────────────────
            cats_raw = result.get("ad_categories", [])
            # 구형(문자열 리스트)과 신형(dict 리스트) 모두 처리
            cat_items = []
            for c in cats_raw:
                if isinstance(c, dict):
                    cat_items.append((c.get("name",""), c.get("desc","")))
                else:
                    cat_items.append((str(c), ""))

            with st.expander(f"📊 광고그룹 카테고리 추천  ·  {len(cat_items)}개", expanded=True):
                st.caption("아래 카테고리를 기준으로 광고그룹을 나누세요.")
                for cat_name, cat_desc in cat_items:
                    st.markdown(
                        f'<div style="background:#EFF6FF;border:1px solid #BFDBFE;'
                        f'border-radius:10px;padding:12px 16px;margin-bottom:8px;">'
                        f'<div style="font-size:14px;font-weight:700;color:#1D4ED8;">{cat_name}</div>'
                        + (f'<div style="font-size:12px;color:#6B7280;margin-top:4px;">{cat_desc}</div>'
                           if cat_desc else '')
                        + '</div>',
                        unsafe_allow_html=True,
                    )
                if cat_items:
                    cat_names = [n for n, _ in cat_items]
                    st.download_button("⬇️ TXT", _txt_bytes(cat_names),
                                       "categories.txt", "text/plain", key="ex_cat_txt")

            # ── 키워드 섹션 정의 ──────────────────────────────────────────
            _SECS = [
                ("핵심키워드",       "🟢", "핵심 키워드",        "전환 의도 높음 — 광고 ON 필수"),
                ("롱테일키워드",     "🟢", "롱테일 키워드",      "구체적 니즈 — 볼륨 낮고 경쟁 약함"),
                ("질문형키워드",     "🟢", "질문형 키워드",      "탐색 → 전환 흐름 — 랜딩 최적화 필요"),
                ("정보성키워드",     "🟡", "정보성 키워드",      "블로그/콘텐츠/SEO 활용"),
                ("계절트렌드키워드", "🟡", "계절/트렌드 키워드", "시즌·이슈 기반 — 선제적 세팅 권장"),
                ("경쟁사키워드",     "🔴", "경쟁사 키워드",       "⚠️ 등록 전 광고 정책·법적 검토 필수"),
            ]

            all_kws = []
            for data_key, tag, display, desc in _SECS:
                raw = result.get(data_key, [])

                if isinstance(raw, str):
                    with st.expander(f"{tag} {display}  ·  추천없음", expanded=False):
                        st.caption("해당 업종은 이 유형의 키워드가 적합하지 않습니다.")
                    continue
                if not isinstance(raw, list) or not raw:
                    continue

                all_kws.extend(raw)
                preview = ", ".join(raw[:5]) + (f" 외 {len(raw)-5}개" if len(raw) > 5 else "")

                with st.expander(f"{tag} {display}  ·  {len(raw)}개", expanded=False):
                    st.caption(f"대표: {preview}")
                    st.markdown(
                        f'<div style="background:#F8FAFC;border-radius:6px;padding:5px 12px;'
                        f'font-size:12px;color:#6B7280;margin-bottom:8px;">{tag} {desc}</div>',
                        unsafe_allow_html=True,
                    )
                    st.code("\n".join(raw), language=None)

                    bc1, bc2, bc3 = st.columns(3)
                    with bc1:
                        st.download_button("⬇️ TXT", _txt_bytes(raw),
                                           f"{display}.txt", "text/plain",
                                           key=f"ex_dtxt_{data_key}")
                    with bc2:
                        st.download_button(
                            "⬇️ CSV",
                            ("키워드\n" + "\n".join(raw)).encode("utf-8-sig"),
                            f"{display}.csv", "text/csv",
                            key=f"ex_dcsv_{data_key}",
                        )
                    with bc3:
                        if st.button("➡️ 정리기로", key=f"ex_clean_{data_key}",
                                     use_container_width=True):
                            existing = st.session_state.get("clean_import", "")
                            new_text = "\n".join(raw)
                            st.session_state["clean_import"] = (
                                existing + "\n" + new_text if existing else new_text
                            )
                            st.success(f"{display} → 정리기에 추가했습니다.")

            # ── 전체 다운로드 + 조합기 보내기 ─────────────────────────────
            if all_kws:
                st.markdown("---")
                gc1, gc2, gc3 = st.columns(3)
                with gc1:
                    st.download_button("⬇️ 전체 TXT", _txt_bytes(all_kws),
                                       "keywords_all.txt", "text/plain", key="ex_all_txt")
                with gc2:
                    st.download_button(
                        "⬇️ 전체 CSV",
                        ("키워드\n" + "\n".join(all_kws)).encode("utf-8-sig"),
                        "keywords_all.csv", "text/csv", key="ex_all_csv",
                    )
                with gc3:
                    if st.button("➡️ 핵심→조합기", use_container_width=True, key="ex_to_comb"):
                        core = result.get("핵심키워드", [])
                        if isinstance(core, list):
                            st.session_state["comb_import"] = "\n".join(core)
                            st.success("핵심 키워드 → 조합기에 전달했습니다.")


# ════════════════════════════════════════════════════════════════════════════
# TAB 2 · 키워드 조합기
# ════════════════════════════════════════════════════════════════════════════
with t_combine:
    col_in, col_opts, col_out = st.columns([2, 2, 3], gap="large")

    with col_in:
        st.markdown("#### 입력")
        comb_default = st.session_state.get("comb_import", "")
        comb_kws_raw = st.text_area(
            "메인 키워드 (줄바꿈 구분)",
            value=comb_default,
            placeholder="이혼변호사\n상간녀소송\n재산분할",
            height=180, key="comb_kws_raw",
        )
        comb_sfx_raw = st.text_area(
            "추가 접미사 (줄바꿈, 선택)",
            placeholder="추천\n잘하는곳\n전문",
            height=100, key="comb_sfx_raw",
        )

    with col_opts:
        st.markdown("#### 지역 선택")
        sido = st.selectbox("시/도", ["선택 안함"] + list(REGION_DB.keys()), key="comb_sido")
        selected_areas = []
        if sido and sido != "선택 안함":
            districts = REGION_DB[sido]
            sel_dist = st.multiselect("구/지역 (복수 선택)", list(districts.keys()),
                                      key="comb_district")
            for d in sel_dist:
                selected_areas.extend(districts[d])
            if selected_areas:
                preview = ", ".join(selected_areas[:6])
                if len(selected_areas) > 6:
                    preview += f" 외 {len(selected_areas)-6}개"
                st.caption(f"선택 지역: {preview}")

        st.markdown("---")
        st.markdown("#### 조합 옵션")
        opt_regional = st.checkbox("지역 확장",          value=True,  key="comb_regional")
        opt_c_conv   = st.checkbox("전환형 생성",        value=True,  key="comb_conv")
        opt_c_quest  = st.checkbox("질문형 생성",        value=False, key="comb_quest")
        opt_c_long   = st.checkbox("롱테일 생성",        value=False, key="comb_long")
        opt_c_base   = st.checkbox("단순 조합 포함",     value=True,  key="comb_base")

        st.markdown("---")
        run_combine = st.button("🚀 조합 생성", type="primary",
                                use_container_width=True, key="run_combine")

    with col_out:
        st.markdown("#### 결과")

        if run_combine:
            seeds = [k.strip() for k in comb_kws_raw.splitlines() if k.strip()]
            custom_sfxs = [s.strip() for s in comb_sfx_raw.splitlines() if s.strip()]
            if not seeds:
                st.warning("메인 키워드를 입력해주세요.")
            else:
                csec = {}
                sfxs = CONV_SFXS + custom_sfxs if custom_sfxs else CONV_SFXS

                for kw in seeds:
                    if opt_c_base:
                        csec.setdefault("기본", []).append((kw, "🟢"))
                    if opt_regional and selected_areas:
                        for area in selected_areas:
                            csec.setdefault("지역형", []).append((f"{area}{kw}", "🟢"))
                    if opt_c_conv:
                        for s in sfxs:
                            csec.setdefault("전환형", []).append((f"{kw}{s}", "🟢"))
                        if opt_regional and selected_areas:
                            for area in selected_areas:
                                for s in sfxs:
                                    csec.setdefault("지역×전환형", []).append((f"{area}{kw}{s}", "🟢"))
                    if opt_c_quest:
                        for s in QUEST_SFXS:
                            csec.setdefault("질문형", []).append((f"{kw} {s}", "🟢"))
                        if opt_regional and selected_areas:
                            for area in selected_areas:
                                for s in QUEST_SFXS[:4]:
                                    csec.setdefault("지역×질문형", []).append((f"{area}{kw} {s}", "🟡"))
                    if opt_c_long:
                        for p in LONGTAIL_PFXS:
                            csec.setdefault("롱테일", []).append((f"{p} {kw}", "🟡"))
                        for s in LONGTAIL_SFXS:
                            csec.setdefault("롱테일", []).append((f"{kw} {s}", "🟡"))
                        if opt_regional and selected_areas:
                            for area in selected_areas[:4]:
                                for p in LONGTAIL_PFXS[:4]:
                                    csec.setdefault("지역×롱테일", []).append((f"{p} {area}{kw}", "🟡"))

                st.session_state["comb_sections"] = csec

        csec = st.session_state.get("comb_sections", {})
        if csec:
            ctotal = sum(len(v) for v in csec.values())
            parts  = " · ".join(f"{k} {len(v)}개" for k, v in csec.items())
            st.markdown(
                f'<div style="background:#F0FFF4;border:1.5px solid #86EFAC;border-radius:10px;'
                f'padding:10px 16px;margin-bottom:8px;">'
                f'<b style="color:#16A34A;">총 {ctotal}개</b>'
                f'<span style="color:#6B7280;font-size:12px;margin-left:8px;">{parts}</span></div>',
                unsafe_allow_html=True,
            )
            for sname, pairs in csec.items():
                _section(sname, pairs)

            call_kws = _all_kws(csec)
            dc1, dc2, dc3 = st.columns(3)
            with dc1:
                st.download_button("⬇️ TXT", _txt_bytes(call_kws),
                                   "combined.txt", "text/plain", key="comb_dl_txt")
            with dc2:
                st.download_button("⬇️ CSV", _csv_bytes(csec),
                                   "combined.csv", "text/csv", key="comb_dl_csv")
            with dc3:
                if st.button("➡️ 정리기로 보내기", use_container_width=True, key="comb_to_clean"):
                    st.session_state["clean_import"] = "\n".join(call_kws)
                    st.success("정리기 탭에 전달했습니다.")


# ════════════════════════════════════════════════════════════════════════════
# TAB 3 · 키워드 정리기
# ════════════════════════════════════════════════════════════════════════════
with t_clean:
    col_in, col_opts, col_out = st.columns([2, 2, 3], gap="large")

    with col_in:
        st.markdown("#### 입력")
        clean_default = st.session_state.get("clean_import", "")
        clean_raw = st.text_area(
            "원본 키워드 (줄바꿈 구분)",
            value=clean_default,
            placeholder="여기에 키워드를 붙여넣거나\n조합기에서 '정리기로 보내기'를 사용하세요.",
            height=340, key="clean_raw",
        )
        raw_count = len([l for l in clean_raw.splitlines() if l.strip()])
        st.caption(f"입력: {raw_count}개")

    with col_opts:
        st.markdown("#### 정리 옵션")
        opt_exact   = st.checkbox("완전 중복 제거",      value=True,  key="cl_exact")
        opt_space   = st.checkbox("공백 무시 중복 제거", value=True,  key="cl_space")
        opt_special = st.checkbox("특수문자 제거",        value=False, key="cl_special")
        opt_length  = st.checkbox("글자수 제한",          value=False, key="cl_length")
        max_len = 15
        if opt_length:
            max_len = st.slider("최대 글자수 (공백 제외)", 5, 30, 15, key="cl_max_len")
        opt_similar = st.checkbox("유사 키워드 제거",     value=False, key="cl_similar")
        sim_thr = 0.85
        if opt_similar:
            sim_thr = st.slider("유사도 임계값", 0.6, 1.0, 0.85, 0.05, key="cl_sim_thr",
                                help="높을수록 엄격. 0.85 권장")

        st.markdown("---")
        st.markdown("#### 출력 형식")
        opt_ad_fmt = st.checkbox("광고 등록용 포맷\n(앞뒤 공백 제거, 한 줄씩)", value=True, key="cl_ad_fmt")

        st.markdown("---")
        run_clean = st.button("🧹 정리 실행", type="primary",
                              use_container_width=True, key="run_clean")

    with col_out:
        st.markdown("#### 결과")

        if run_clean:
            raw_lines = clean_raw.splitlines()
            opts = {
                "exact_dedup":    opt_exact,
                "space_dedup":    opt_space,
                "special_remove": opt_special,
                "length_check":   opt_length,
                "max_len":        max_len,
                "similar_remove": opt_similar,
                "sim_threshold":  sim_thr,
            }
            cleaned, removed = clean_keywords(raw_lines, opts)
            if opt_ad_fmt:
                cleaned = [kw.strip() for kw in cleaned]
            st.session_state["clean_result"]  = cleaned
            st.session_state["clean_removed"] = removed
            st.session_state["clean_before"]  = len([l for l in raw_lines if l.strip()])

        cleaned = st.session_state.get("clean_result", [])
        removed = st.session_state.get("clean_removed", [])
        before  = st.session_state.get("clean_before", 0)

        if cleaned or removed:
            st.markdown(
                _kpi_bar(before, len(cleaned), len(removed)),
                unsafe_allow_html=True,
            )

            if cleaned:
                st.markdown(
                    f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">'
                    f'<span style="font-size:13px;font-weight:700;">✅ 최종 키워드</span>'
                    f'<span style="font-size:11px;color:#6B7280;background:#F3F4F6;'
                    f'padding:1px 8px;border-radius:100px;">{len(cleaned)}개</span></div>',
                    unsafe_allow_html=True,
                )
                st.code("\n".join(cleaned), language=None)
                dc1, dc2 = st.columns(2)
                with dc1:
                    st.download_button("⬇️ TXT", _txt_bytes(cleaned),
                                       "cleaned.txt", "text/plain", key="cl_dl_txt")
                with dc2:
                    csv_content = ("키워드\n" + "\n".join(cleaned)).encode("utf-8-sig")
                    st.download_button("⬇️ CSV", csv_content,
                                       "cleaned.csv", "text/csv", key="cl_dl_csv")

            if removed:
                with st.expander(f"🗑️ 제거된 키워드 {len(removed)}개 — 제거 로그", expanded=False):
                    log = "\n".join(f"{kw}  ←  {reason}" for kw, reason in removed)
                    st.code(log, language=None)

        elif run_clean:
            st.info("입력 키워드를 확인해주세요.")
