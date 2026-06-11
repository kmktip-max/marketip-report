"""전자책·강의 + 세팅/대행 상품 스토어 — 상품별 구매 → 계좌이체 입금/신청 퍼널"""
import streamlit as st
import streamlit.components.v1 as components
import os, sys, json, uuid, base64
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# ── 입금 계좌 정보 ────────────────────────────────────────────────────────────
BANK_NAME   = "카카오뱅크"
BANK_NUM    = "3333-30-3495145"
BANK_HOLDER = "권혁우(마케팁)"
BANK_TYPE   = "개인사업자"

# ── 상품 카탈로그 (라벨, 가격표시, 입금액) ────────────────────────────────────
_CATALOG = [
    ("전자책 · 구조이해(STEP1)",     "39,000원",        "39,000"),
    ("전자책 · 기초세팅(STEP2)",     "79,000원",        "79,000"),
    ("전자책 · 심화세팅(STEP3)",     "129,000원",       "129,000"),
    ("전자책 · 올인원 패키지",       "199,000원",       "199,000"),
    ("세팅 · 광고 무상점검(무료)",   "무료",            "0"),
    ("세팅 · 초기 광고세팅(신규)",   "330,000원",       "330,000"),
    ("세팅 · 광고최적화세팅(기존)",  "220,000원",       "220,000"),
    ("대행 · 성과보장 광고운영대행", "월 50만원~ (협의)", "협의"),
    ("기타 상담",                    "-",               ""),
]
_LABELS = [c[0] for c in _CATALOG]
_AMT    = {c[0]: c[2] for c in _CATALOG}

# ── 프로필 이미지 ─────────────────────────────────────────────────────────────
def _img_b64(path):
    try:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except Exception:
        return ""
_PROFILE = _img_b64(os.path.join(ROOT, "profile_nobg.png"))

# ── Supabase (구매/상담 신청 저장) ───────────────────────────────────────────
def _get_sb():
    try:
        url = (getattr(st, "secrets", {}).get("SUPABASE_URL", "") or os.getenv("SUPABASE_URL", ""))
        key = (getattr(st, "secrets", {}).get("SUPABASE_KEY", "") or os.getenv("SUPABASE_KEY", ""))
        if not url or not key:
            return None
        from supabase import create_client
        return create_client(url, key)
    except Exception:
        return None

_SB_KEY = "ebook_leads"
_F_LEADS = os.path.join(ROOT, "data", "ebook_leads.json")

def _load_leads():
    sb = _get_sb()
    if sb:
        try:
            res = sb.table("app_data").select("data").eq("key", _SB_KEY).execute()
            if res.data:
                return res.data[0]["data"]
        except Exception:
            pass
    try:
        if os.path.exists(_F_LEADS):
            with open(_F_LEADS, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return []

def _save_leads(leads):
    sb = _get_sb()
    if sb:
        try:
            sb.table("app_data").upsert(
                {"key": _SB_KEY, "data": leads,
                 "updated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S")},
                on_conflict="key").execute()
        except Exception:
            pass
    try:
        os.makedirs(os.path.dirname(_F_LEADS), exist_ok=True)
        with open(_F_LEADS, "w", encoding="utf-8") as f:
            json.dump(leads, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

_is_admin = st.session_state.get("auth_type") == "admin"
_username = st.session_state.get("auth_username", "")
_client   = st.session_state.get("auth_client", {})

if "buy_sel" not in st.session_state:
    st.session_state["buy_sel"] = _LABELS[0]

def _buy(label):
    """구매하기 버튼 → 상품 선택 + 입금/신청란으로 스크롤."""
    st.session_state["buy_sel"] = label
    st.session_state["_scroll_buy"] = True
    st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# HERO (프로필 사진 포함)
# ══════════════════════════════════════════════════════════════════════════════
_photo_html = (
    f'<img src="data:image/png;base64,{_PROFILE}" '
    f'style="width:210px;height:auto;filter:drop-shadow(0 8px 20px rgba(0,0,0,0.35));" />'
) if _PROFILE else ""

st.markdown(f"""
<div style="background:linear-gradient(135deg,#1E3A8A 0%,#2563EB 55%,#3B82F6 100%);
            border-radius:20px;padding:40px 40px 0;color:#fff;margin-bottom:8px;
            box-shadow:0 12px 32px rgba(37,99,235,0.28);display:flex;align-items:flex-end;
            gap:20px;flex-wrap:wrap;overflow:hidden;">
  <div style="flex:1;min-width:320px;padding-bottom:40px;">
    <div style="display:inline-block;background:rgba(255,255,255,0.18);border:1px solid rgba(255,255,255,0.35);
                border-radius:100px;padding:6px 16px;font-size:13px;font-weight:700;margin-bottom:18px;">
      📚 마케팁 전자책 · 강의 · 광고 서비스
    </div>
    <div style="font-size:33px;font-weight:900;line-height:1.25;margin-bottom:14px;letter-spacing:-0.5px;">
      광고비 쓰고도<br>돈 버는 구조를 가지세요
    </div>
    <div style="font-size:15.5px;line-height:1.7;color:rgba(255,255,255,0.92);font-weight:500;max-width:600px;word-break:keep-all;">
      검색광고를 몰라도 괜찮습니다. 자동화 도구로 <b>전문가처럼 직접 운영</b>하고,
      더 깊은 노하우는 <b>6년 실전 전자책</b>으로. 직접 하기 어렵다면 <b>세팅·성과보장 대행</b>까지.
    </div>
  </div>
  <div style="flex:0 0 auto;align-self:flex-end;">{_photo_html}</div>
</div>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# 3가지 약속
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("<div style='height:18px;'></div>", unsafe_allow_html=True)
c1, c2, c3 = st.columns(3)
_cards = [
    ("🔰", "검색광고 초보자도", "복잡한 세팅·입찰은 도구가 자동으로.<br>클릭 몇 번이면 전문가급 운영이 됩니다."),
    ("💼", "프리랜서·예비창업자도", "광고를 몰라도 이 툴 하나로 <b>광고대행사 창업</b>까지.<br>키워드·소재·보고서 자동 생성."),
    ("📈", "광고주도", "맡기지 않고도 전문가처럼.<br><b>광고비 낭비는 줄이고</b> 성과는 직접."),
]
for col, (ic, t, d) in zip([c1, c2, c3], _cards):
    col.markdown(f"""
<div style="background:#fff;border:1.5px solid #E5E8ED;border-radius:16px;padding:22px 20px;height:100%;">
  <div style="font-size:30px;margin-bottom:10px;">{ic}</div>
  <div style="font-size:16px;font-weight:800;color:#111827;margin-bottom:8px;word-break:keep-all;">{t}</div>
  <div style="font-size:13.5px;line-height:1.7;color:#4B5563;word-break:keep-all;">{d}</div>
</div>""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# 문제 → 해결
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("<div style='height:30px;'></div>", unsafe_allow_html=True)
st.markdown("""
<div style="background:#FFF7ED;border:1.5px solid #FED7AA;border-radius:16px;padding:26px 28px;">
  <div style="font-size:18px;font-weight:800;color:#9A3412;margin-bottom:14px;">😮‍💨 혹시 이런 상황이신가요?</div>
  <div style="font-size:14.5px;line-height:1.9;color:#7C2D12;word-break:keep-all;">
    · 광고비는 매달 쓰는데 <b>매출이 안 나옵니다</b><br>
    · 대행사에 맡겼지만 <b>뭘 해주는지 모르겠습니다</b><br>
    · 직접 하자니 <b>키워드·입찰·소재</b> 어디서 시작할지 막막합니다<br>
    · 광고비의 <b>일부를 돌려받을 수 있다</b>는 걸 몰랐습니다
  </div>
  <div style="border-top:1px dashed #FDBA74;margin:18px 0;"></div>
  <div style="font-size:15px;line-height:1.8;color:#1E3A8A;font-weight:600;word-break:keep-all;">
    👉 광고는 <b>안 팔리는 상품을 팔아주는 마법이 아닙니다.</b>
    잘 팔리는 상품을 <b>더 싸게, 더 많이 노출</b>시키는 '구조'를 아는 사람이 이깁니다.
  </div>
</div>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# 1) 전자책 · 강의 — 구조이해 / 기초세팅 / 심화세팅
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("<div style='height:36px;'></div>", unsafe_allow_html=True)
st.markdown("<h3 style='font-weight:900;color:#111827;'>📚 전자책 · 강의 <span style='font-size:13px;color:#9CA3AF;font-weight:600;'>· 제안가(조정 가능)</span></h3>", unsafe_allow_html=True)
st.caption("마케팅 6년 실전 노하우를 단계별로. 이론서가 아닌 '따라하기 가능한' 실전 가이드.")

def _ebook_card(grad, step, name, price, feats):
    fh = "".join(f'<div style="font-size:12.5px;line-height:1.5;color:#374151;margin-bottom:6px;">· {f}</div>' for f in feats)
    return f"""
<div style="background:#fff;border:1.5px solid #E5E8ED;border-radius:16px 16px 0 0;overflow:hidden;
            box-shadow:0 2px 10px rgba(0,0,0,0.05);">
  <div style="background:{grad};padding:20px;color:#fff;">
    <div style="font-size:12px;font-weight:700;opacity:0.9;">{step}</div>
    <div style="font-size:19px;font-weight:900;margin-top:4px;">{name}</div>
  </div>
  <div style="padding:18px 20px 14px;">
    <div style="font-size:24px;font-weight:900;color:#111827;margin-bottom:14px;">{price}</div>
    {fh}
  </div>
</div>"""

e1, e2, e3 = st.columns(3)
e1.markdown(_ebook_card("linear-gradient(135deg,#64748B,#94A3B8)", "STEP 1 · 입문", "구조 이해", "39,000원",
    ["검색광고 오해와 진실 20가지", "꼭 아는 기초용어 58선", "CPC·품질지수 등 비용 구조"]), unsafe_allow_html=True)
if e1.button("🛒 구매하기", key="b_e1", use_container_width=True): _buy("전자책 · 구조이해(STEP1)")
e2.markdown(_ebook_card("linear-gradient(135deg,#2563EB,#3B82F6)", "STEP 2 · 실전", "기초 세팅", "79,000원",
    ["비즈채널·캠페인·그룹 세팅", "키워드 발굴 + 광고 소재 작성", "AI 키워드·소재 봇 활용법"]), unsafe_allow_html=True)
if e2.button("🛒 구매하기", key="b_e2", use_container_width=True): _buy("전자책 · 기초세팅(STEP2)")
e3.markdown(_ebook_card("linear-gradient(135deg,#7C3AED,#A855F7)", "STEP 3 · 고수", "심화 세팅", "129,000원",
    ["입찰 전략·자동입찰 최적화", "클릭률 2배·파워링크 300% 전략", "리베이트 구조 심화 활용"]), unsafe_allow_html=True)
if e3.button("🛒 구매하기", key="b_e3", use_container_width=True): _buy("전자책 · 심화세팅(STEP3)")

pa1, pa2 = st.columns([3, 1])
pa1.markdown("""
<div style="background:#EFF6FF;border:1px solid #BFDBFE;border-radius:12px;padding:14px 18px;">
  <span style="font-size:13.5px;color:#1E40AF;font-weight:700;">📦 3단계 올인원 패키지 — 199,000원</span>
  <span style="font-size:12.5px;color:#3B82F6;"> (개별 합계 247,000원 → 약 19% 할인)</span>
</div>""", unsafe_allow_html=True)
if pa2.button("🛒 패키지 구매", key="b_eall", use_container_width=True, type="primary"): _buy("전자책 · 올인원 패키지")

# ══════════════════════════════════════════════════════════════════════════════
# 2) 광고 세팅 상품
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("<div style='height:36px;'></div>", unsafe_allow_html=True)
st.markdown("<h3 style='font-weight:900;color:#111827;'>🛠 광고 세팅 상품 <span style='font-size:13px;color:#9CA3AF;font-weight:600;'>· 제안가(조정 가능)</span></h3>", unsafe_allow_html=True)
st.caption("직접 하기 어렵다면, 전문가가 계정을 세팅해 드립니다.")

def _svc_card(badge, badge_bg, badge_fg, name, price, sub, feats, highlight=False):
    border = "2px solid #10B981" if highlight else "1.5px solid #E5E8ED"
    fh = "".join(f'<div style="font-size:12.5px;line-height:1.5;color:#374151;margin-bottom:6px;">✓ {f}</div>' for f in feats)
    return f"""
<div style="background:#fff;border:{border};border-radius:16px 16px 0 0;padding:22px 20px 16px;">
  <div style="display:inline-block;background:{badge_bg};color:{badge_fg};font-size:11px;font-weight:800;
              padding:4px 11px;border-radius:100px;margin-bottom:12px;">{badge}</div>
  <div style="font-size:17px;font-weight:900;color:#111827;">{name}</div>
  <div style="font-size:12px;color:#6B7280;margin:3px 0 10px;">{sub}</div>
  <div style="font-size:23px;font-weight:900;color:#111827;margin-bottom:14px;">{price}</div>
  {fh}
</div>"""

s1, s2, s3 = st.columns(3)
s1.markdown(_svc_card("무료", "#DCFCE7", "#16A34A", "광고 무상 점검", "누구나 신청 가능", "0원",
    ["현재 계정 구조 진단", "광고비 누수 지점 분석", "맞춤 개선 리포트 제공"], highlight=True), unsafe_allow_html=True)
if s1.button("🔍 무료 점검 신청", key="b_s1", use_container_width=True, type="primary"): _buy("세팅 · 광고 무상점검(무료)")
s2.markdown(_svc_card("신규 광고주", "#DBEAFE", "#1D4ED8", "초기 광고 세팅", "처음 시작하는 분", "330,000원",
    ["계정·비즈채널 세팅", "캠페인·그룹·키워드 구성", "광고 소재 + 랜딩 점검"]), unsafe_allow_html=True)
if s2.button("🛒 구매하기", key="b_s2", use_container_width=True): _buy("세팅 · 초기 광고세팅(신규)")
s3.markdown(_svc_card("기존 광고주", "#FEF3C7", "#92400E", "광고 최적화 세팅", "운영 중인 분", "220,000원",
    ["기존 계정 구조 재정비", "제외키워드·입찰 최적화", "성과 저하 원인 교정"]), unsafe_allow_html=True)
if s3.button("🛒 구매하기", key="b_s3", use_container_width=True): _buy("세팅 · 광고최적화세팅(기존)")

# ══════════════════════════════════════════════════════════════════════════════
# 3) 성과보장 광고대행
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("<div style='height:36px;'></div>", unsafe_allow_html=True)
st.markdown("<h3 style='font-weight:900;color:#111827;'>🤝 성과보장 광고 운영대행 <span style='font-size:13px;color:#9CA3AF;font-weight:600;'>· 제안가(조정 가능)</span></h3>", unsafe_allow_html=True)
st.markdown("""
<div style="background:#0F766E;border-radius:18px;
            padding:28px 30px;color:#fff;box-shadow:0 10px 28px rgba(15,118,110,0.25);">
  <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:16px;">
    <div style="flex:1;min-width:280px;">
      <div style="display:inline-block;background:rgba(255,255,255,0.2);border-radius:100px;
                  padding:5px 14px;font-size:12px;font-weight:800;margin-bottom:12px;">💎 성과보장형</div>
      <div style="font-size:22px;font-weight:900;margin-bottom:10px;">2개월 성과개선 미흡 시,<br>리베이트로 돌려드립니다</div>
      <div style="font-size:14px;line-height:1.75;color:rgba(255,255,255,0.92);word-break:keep-all;">
        키워드·입찰·소재·랜딩까지 전 과정을 직접 운영합니다.
        <b>2개월 내 성과 개선이 미흡하면, 받은 대행료 일부를 리베이트(수수료 환급)로 보전</b>해
        리스크를 저희가 함께 집니다.
      </div>
    </div>
    <div style="flex:0 0 auto;text-align:right;">
      <div style="font-size:13px;opacity:0.85;">월 운영대행료</div>
      <div style="font-size:30px;font-weight:900;">월 50만원~</div>
      <div style="font-size:12px;opacity:0.85;">또는 광고비의 15% (협의)</div>
    </div>
  </div>
  <div style="border-top:1px solid rgba(255,255,255,0.25);margin:18px 0 14px;"></div>
  <div style="font-size:13px;line-height:1.7;color:rgba(255,255,255,0.95);word-break:keep-all;">
    ✓ 전담 운영 + 주간 리포트　✓ 2개월 성과보장 + 미흡 시 리베이트　✓ 광고비 페이백 병행 가능
  </div>
</div>
""", unsafe_allow_html=True)
ag1, ag2 = st.columns([3, 1])
if ag2.button("🤝 대행 상담 신청", key="b_agency", use_container_width=True, type="primary"): _buy("대행 · 성과보장 광고운영대행")

# ══════════════════════════════════════════════════════════════════════════════
# 후기
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("<div style='height:30px;'></div>", unsafe_allow_html=True)
st.markdown("""
<div style="background:#fff;border:1.5px solid #E5E8ED;border-radius:16px;padding:22px 26px;">
  <div style="font-size:16px;font-weight:800;color:#111827;">⭐ 평점 5.0 <span style="font-size:13px;color:#6B7280;font-weight:600;">(실구매 후기 기준)</span></div>
  <div style="font-size:13.5px;line-height:1.85;color:#475569;margin-top:10px;word-break:keep-all;">
    “복잡한 이론이 아니라 <b>바로 써먹을 수 있는 내용</b>이라 좋았어요.”<br>
    “키워드봇·소재봇 기능이 편하고, <b>찐 노하우가 많았습니다</b>.”<br>
    “설명만 많은 자료가 아니라 <b>따라하기 가능</b>한 가이드네요.”
  </div>
</div>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# 입금 · 신청 (계좌이체 — 계좌 직접 노출)
# ══════════════════════════════════════════════════════════════════════════════
st.markdown('<div id="apply_anchor"></div>', unsafe_allow_html=True)
st.markdown("<div style='height:24px;'></div>", unsafe_allow_html=True)
st.markdown("<h3 style='font-weight:900;color:#111827;'>💳 입금 후 신청</h3>", unsafe_allow_html=True)

_sel    = st.session_state.get("buy_sel", _LABELS[0])
_sel_amt = _AMT.get(_sel, "")

# 계좌 안내 (통장 사본)
st.markdown(f"""
<div style="background:#FFFBEB;border:1.5px solid #FDE68A;border-radius:16px;padding:22px 26px;">
  <div style="font-size:13px;font-weight:700;color:#92400E;margin-bottom:12px;">🏦 입금 계좌</div>
  <div style="display:flex;align-items:center;gap:14px;flex-wrap:wrap;">
    <div style="font-size:23px;font-weight:900;color:#111827;letter-spacing:0.5px;">{BANK_NAME} {BANK_NUM}</div>
    <div style="background:#FEF3C7;color:#92400E;font-size:12px;font-weight:700;padding:4px 12px;border-radius:100px;">예금주 {BANK_HOLDER} · {BANK_TYPE}</div>
  </div>
  <div style="font-size:13px;color:#78716C;margin-top:12px;line-height:1.6;">
    위 계좌로 입금 후 <b>아래 신청서</b>를 작성해 주세요. 빠르게 확인 후 자료 발송·일정 안내드립니다.<br>
    <b>입금자명</b>을 꼭 기재해 주시면 확인이 빠릅니다. (무상 점검은 입금 없이 바로 신청)
  </div>
</div>
""", unsafe_allow_html=True)

st.markdown(f"""
<div style="background:#EFF6FF;border:1px solid #BFDBFE;border-radius:10px;padding:12px 16px;margin:14px 0;">
  <span style="font-size:13.5px;color:#1E40AF;">선택한 상품: <b>{_sel}</b> · 입금액 <b>{_sel_amt or '—'}{'원' if _sel_amt not in ('', '0', '협의') else ''}</b></span>
</div>
""", unsafe_allow_html=True)

_fcol, _ = st.columns([1, 1])
with _fcol, st.form("ebook_inquiry", clear_on_submit=True):
    _idx = _LABELS.index(_sel) if _sel in _LABELS else 0
    q_product = st.selectbox("신청 상품", _LABELS, index=_idx)
    q_amount  = st.text_input("입금액", value=_AMT.get(_sel, ""), help="상품 변경 시 금액을 확인해 주세요.")
    q_depositor = st.text_input("입금자명 *", value=_client.get("contact_name", ""), placeholder="입금하신 분 성함")
    q_phone     = st.text_input("연락처 *", value=_client.get("phone", ""), placeholder="010-0000-0000")
    q_memo      = st.text_area("문의 내용 (선택)", placeholder="궁금한 점이나 현재 광고 상황을 적어주세요.", height=70)
    if st.form_submit_button("신청 완료", type="primary", use_container_width=True):
        if not q_depositor.strip() or not q_phone.strip():
            st.error("입금자명과 연락처는 필수입니다.")
        else:
            leads = _load_leads()
            leads.append({
                "id": str(uuid.uuid4())[:12],
                "name": q_depositor.strip(), "phone": q_phone.strip(),
                "interest": q_product, "amount": q_amount.strip(),
                "memo": q_memo.strip(),
                "from_user": _username or "비로그인",
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "status": "신규",
            })
            _save_leads(leads)
            st.success("신청이 접수되었습니다. 입금 확인 후 빠르게 안내드리겠습니다! 🙏")

# 구매하기 클릭 시 입금/신청란으로 부드럽게 스크롤
if st.session_state.pop("_scroll_buy", False):
    components.html(
        "<script>const a=window.parent.document.getElementById('apply_anchor');"
        "if(a){a.scrollIntoView({behavior:'smooth',block:'start'});}</script>",
        height=0,
    )

# ══════════════════════════════════════════════════════════════════════════════
# 광고비 페이백 안내 (색상 구분 — 앰버)
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("<div style='height:30px;'></div>", unsafe_allow_html=True)
st.markdown("""
<div style="background:#D97706;border-radius:16px;
            padding:24px 28px;color:#fff;box-shadow:0 8px 22px rgba(217,119,6,0.22);">
  <div style="font-size:20px;font-weight:900;margin-bottom:8px;">💸 광고비, 그냥 쓰지 마세요</div>
  <div style="font-size:14.5px;line-height:1.75;color:rgba(255,255,255,0.96);word-break:keep-all;max-width:680px;">
    이미 집행 중인 광고비의 <b>일부를 매달 돌려받을 수 있습니다.</b>
    추가 비용도, 복잡한 절차도 없이 — 신청만 하시면 됩니다.
  </div>
</div>
""", unsafe_allow_html=True)
if st.button("💸  광고비 페이백 신청하러 가기", type="primary"):
    try:
        st.switch_page("pages/페이백신청.py")
    except Exception:
        st.info("왼쪽 메뉴 '광고비 페이백신청'에서 신청하실 수 있습니다.")

# ══════════════════════════════════════════════════════════════════════════════
# 관리자 — 신청 현황
# ══════════════════════════════════════════════════════════════════════════════
if _is_admin:
    st.markdown("<div style='height:24px;'></div>", unsafe_allow_html=True)
    st.divider()
    leads = _load_leads()
    with st.expander(f"🔔 구매·상담 신청 현황 ({len(leads)}건)", expanded=False):
        if not leads:
            st.info("아직 접수된 신청이 없습니다.")
        else:
            for ld in reversed(leads):
                lc1, lc2, lc3 = st.columns([3, 3, 1])
                lc1.markdown(f"**{ld.get('name','')}** · {ld.get('phone','')}")
                lc1.caption(f"{ld.get('interest','')} · 입금액 {ld.get('amount','-')} · {ld.get('created_at','')}")
                lc2.write(ld.get("memo", "") or "—")
                lc2.caption(f"신청자: {ld.get('from_user','')}")
                if lc3.button("삭제", key=f"del_lead_{ld['id']}"):
                    _save_leads([x for x in _load_leads() if x.get("id") != ld["id"]])
                    st.rerun()
                st.divider()
