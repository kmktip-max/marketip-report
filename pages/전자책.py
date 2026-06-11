"""전자책 · 강의 스토어 — 사이트 이용 → 노하우 구매로 이어지는 수익화 퍼널 랜딩페이지"""
import streamlit as st
import os, sys, json, uuid
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

KMONG_URL = "https://kmong.com/gig/752337"

# ── Supabase (구매/수강 문의 저장) ───────────────────────────────────────────
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

# ══════════════════════════════════════════════════════════════════════════════
# HERO
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("""
<div style="background:linear-gradient(135deg,#1E3A8A 0%,#2563EB 55%,#3B82F6 100%);
            border-radius:20px;padding:46px 40px;color:#fff;margin-bottom:8px;
            box-shadow:0 12px 32px rgba(37,99,235,0.28);">
  <div style="display:inline-block;background:rgba(255,255,255,0.18);border:1px solid rgba(255,255,255,0.35);
              border-radius:100px;padding:6px 16px;font-size:13px;font-weight:700;margin-bottom:18px;">
    📚 마케팁 전자책 · 강의
  </div>
  <div style="font-size:34px;font-weight:900;line-height:1.25;margin-bottom:14px;letter-spacing:-0.5px;">
    광고비 쓰고도<br>돈 버는 구조를 가지세요
  </div>
  <div style="font-size:16px;line-height:1.7;color:rgba(255,255,255,0.92);font-weight:500;max-width:640px;">
    검색광고를 몰라도 괜찮습니다. 이 사이트의 자동화 도구로 <b>전문가처럼 직접 운영</b>하고,<br>
    더 깊은 노하우가 필요할 땐 <b>6년 실전 전자책 377페이지</b>로 한 단계 도약하세요.
  </div>
</div>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# 왜 이 사이트인가 — 3가지 약속
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
  <div style="font-size:18px;font-weight:800;color:#9A3412;margin-bottom:14px;">
    😮‍💨 혹시 이런 상황이신가요?
  </div>
  <div style="font-size:14.5px;line-height:1.9;color:#7C2D12;">
    · 광고비는 매달 쓰는데 <b>매출이 안 나옵니다</b><br>
    · 대행사에 맡겼지만 <b>뭘 해주는지 모르겠습니다</b><br>
    · 직접 하자니 <b>키워드·입찰·소재</b> 어디서 시작할지 막막합니다<br>
    · 광고비의 <b>일부를 돌려받을 수 있다</b>는 걸 몰랐습니다
  </div>
  <div style="border-top:1px dashed #FDBA74;margin:18px 0;"></div>
  <div style="font-size:15px;line-height:1.8;color:#1E3A8A;font-weight:600;">
    👉 광고는 <b>안 팔리는 상품을 팔아주는 마법이 아닙니다.</b><br>
    잘 팔리는 상품을 <b>더 싸게, 더 많이 노출</b>시키는 '구조'를 아는 사람이 이깁니다.<br>
    그 구조를 이 사이트(도구)와 전자책(노하우)이 함께 만들어 드립니다.
  </div>
</div>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# 무엇을 얻나 — 전자책 구성
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("<div style='height:34px;'></div>", unsafe_allow_html=True)
st.markdown("<h3 style='font-weight:900;color:#111827;'>📘 전자책으로 얻는 것</h3>", unsafe_allow_html=True)
st.caption("마케팅 6년 실전 노하우 · 총 377페이지 · 이론서가 아닌 '따라하기 가능한' 실전 가이드")

g1, g2 = st.columns(2)
_parts = [
    ("PART 1 · 기초 다지기", "검색광고 오해와 진실 20가지, 꼭 알아야 할 기초용어 58선"),
    ("PART 2 · 비용의 비밀", "CPC 과금 원리, 품질지수, 캠페인 구조 — 돈이 새는 지점 찾기"),
    ("PART 3 · 실전 세팅", "비즈채널 등록부터 광고 소재 작성까지 단계별 따라하기"),
    ("PART 4 · 고수의 전략", "클릭률 2배·파워링크 300% 노출 등 6년 실전 노하우"),
]
for col, (t, d) in zip([g1, g2, g1, g2], _parts):
    col.markdown(f"""
<div style="background:#F8FAFC;border:1px solid #E5E8ED;border-radius:12px;padding:16px 18px;margin-bottom:12px;">
  <div style="font-size:14px;font-weight:800;color:#2563EB;margin-bottom:5px;">{t}</div>
  <div style="font-size:13px;line-height:1.6;color:#475569;">{d}</div>
</div>""", unsafe_allow_html=True)

st.markdown("""
<div style="background:#EFF6FF;border:1px solid #BFDBFE;border-radius:12px;padding:16px 20px;margin-top:4px;">
  <span style="font-size:14px;color:#1E40AF;font-weight:600;">
  🤖 여기에 더해 — 이 사이트에서 쓰는 <b>AI 키워드·소재·상세페이지·보고서 생성 봇</b>의 활용법까지.
  도구를 '제대로' 쓰는 법을 알려드립니다.
  </span>
</div>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# 가격 3티어 + 크몽 구매
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("<div style='height:34px;'></div>", unsafe_allow_html=True)
st.markdown("<h3 style='font-weight:900;color:#111827;'>💳 구매하기</h3>", unsafe_allow_html=True)
st.caption("아래 버튼을 누르면 안전한 크몽 결제 페이지로 이동합니다. 결제 즉시 자료가 발송됩니다.")

def _tier(badge, badge_bg, badge_fg, name, price, feats, highlight=False):
    border = "2.5px solid #2563EB" if highlight else "1.5px solid #E5E8ED"
    shadow = "0 12px 28px rgba(37,99,235,0.22)" if highlight else "0 2px 8px rgba(0,0,0,0.04)"
    feat_html = "".join(
        f'<div style="font-size:13px;line-height:1.5;color:#374151;margin-bottom:7px;">✓ {f}</div>'
        for f in feats)
    btn_bg = "#2563EB" if highlight else "#111827"
    return f"""
<div style="background:#fff;border:{border};border-radius:18px;padding:24px 22px;height:100%;
            box-shadow:{shadow};display:flex;flex-direction:column;">
  <div style="display:inline-block;align-self:flex-start;background:{badge_bg};color:{badge_fg};
              font-size:11px;font-weight:800;padding:4px 12px;border-radius:100px;margin-bottom:14px;">{badge}</div>
  <div style="font-size:18px;font-weight:900;color:#111827;">{name}</div>
  <div style="font-size:30px;font-weight:900;color:#111827;margin:8px 0 16px;">{price}<span style="font-size:15px;font-weight:600;color:#6B7280;">원</span></div>
  <div style="flex:1;">{feat_html}</div>
  <a href="{KMONG_URL}" target="_blank" style="display:block;text-align:center;background:{btn_bg};color:#fff;
       font-size:14px;font-weight:800;padding:12px;border-radius:10px;text-decoration:none;margin-top:16px;">
    크몽에서 구매하기 →</a>
</div>"""

t1, t2, t3 = st.columns(3)
t1.markdown(_tier("STANDARD", "#F3F4F6", "#374151", "전자책 기본", "39,000",
                  ["전자책 2권 (PDF, 377p)", "AI 키워드 생성 봇", "검색광고 기초~실전"]), unsafe_allow_html=True)
t2.markdown(_tier("DELUXE · 인기", "#DBEAFE", "#1D4ED8", "전자책 + 소재봇", "59,000",
                  ["STANDARD 전체 포함", "AI 소재 생성 봇 추가", "클릭률 2배 전략 가이드"], highlight=True), unsafe_allow_html=True)
t3.markdown(_tier("PREMIUM", "#FEF3C7", "#92400E", "올인원 패키지", "99,000",
                  ["DELUXE 전체 포함", "상세페이지·보고서 생성 봇", "리베이트 구조 심화 + 후기 특전"]), unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# 후기
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("<div style='height:30px;'></div>", unsafe_allow_html=True)
st.markdown("""
<div style="background:#fff;border:1.5px solid #E5E8ED;border-radius:16px;padding:22px 26px;">
  <div style="font-size:16px;font-weight:800;color:#111827;margin-bottom:4px;">
    ⭐ 평점 5.0 <span style="font-size:13px;color:#6B7280;font-weight:600;">(실구매 후기 기준)</span>
  </div>
  <div style="font-size:13.5px;line-height:1.85;color:#475569;margin-top:10px;">
    “복잡한 이론이 아니라 <b>바로 써먹을 수 있는 내용</b>이라 좋았어요.”<br>
    “키워드봇·소재봇 기능이 편하고, <b>찐 노하우가 많았습니다</b>.”<br>
    “설명만 많은 자료가 아니라 <b>따라하기 가능</b>한 가이드네요.”
  </div>
</div>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# 퍼널 안내 — 전자책(단기) + 페이백(장기)
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("<div style='height:30px;'></div>", unsafe_allow_html=True)
st.markdown("""
<div style="background:linear-gradient(135deg,#0F766E 0%,#10B981 100%);border-radius:16px;
            padding:26px 28px;color:#fff;">
  <div style="font-size:18px;font-weight:900;margin-bottom:14px;">💡 두 갈래로 수익이 만들어집니다</div>
  <div style="display:flex;gap:16px;flex-wrap:wrap;">
    <div style="flex:1;min-width:240px;background:rgba(255,255,255,0.14);border-radius:12px;padding:18px;">
      <div style="font-size:14px;font-weight:800;margin-bottom:6px;">① 전자책 · 강의 (단기)</div>
      <div style="font-size:13px;line-height:1.65;color:rgba(255,255,255,0.92);">
        노하우를 배워 <b>직접 운영하거나 대행사로 창업</b> → 바로 수익화.</div>
    </div>
    <div style="flex:1;min-width:240px;background:rgba(255,255,255,0.14);border-radius:12px;padding:18px;">
      <div style="font-size:14px;font-weight:800;margin-bottom:6px;">② 광고비 페이백 (장기)</div>
      <div style="font-size:13px;line-height:1.65;color:rgba(255,255,255,0.92);">
        쓰던 광고비의 <b>일부를 매달 돌려받아</b> → 꾸준한 장기 수익.</div>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

c_pb1, c_pb2 = st.columns([1, 1])
with c_pb1:
    if st.button("💸  광고비 페이백 신청하러 가기", use_container_width=True, type="primary"):
        try:
            st.switch_page("pages/페이백신청.py")
        except Exception:
            st.info("왼쪽 메뉴의 '광고비 페이백신청'에서 신청하실 수 있습니다.")

# ══════════════════════════════════════════════════════════════════════════════
# 구매 · 수강 문의 폼
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("<div style='height:34px;'></div>", unsafe_allow_html=True)
st.markdown("<h3 style='font-weight:900;color:#111827;'>📨 구매 · 수강 문의</h3>", unsafe_allow_html=True)
st.caption("바로 결제가 망설여지신다면, 연락처를 남겨주세요. 가장 맞는 구성을 안내해 드립니다.")

_fcol, _ = st.columns([1, 1])
with _fcol, st.form("ebook_inquiry", clear_on_submit=True):
    q_name  = st.text_input("성함 *", value=_client.get("contact_name", ""))
    q_phone = st.text_input("연락처 *", value=_client.get("phone", ""), placeholder="010-0000-0000")
    q_interest = st.selectbox("관심 상품", ["전자책 기본(STANDARD)", "전자책+소재봇(DELUXE)",
                                          "올인원(PREMIUM)", "강의/컨설팅", "아직 고민 중"])
    q_memo  = st.text_area("문의 내용 (선택)", placeholder="궁금한 점을 자유롭게 적어주세요.", height=80)
    if st.form_submit_button("문의 남기기", type="primary", use_container_width=True):
        if not q_name.strip() or not q_phone.strip():
            st.error("성함과 연락처는 필수입니다.")
        else:
            leads = _load_leads()
            leads.append({
                "id": str(uuid.uuid4())[:12],
                "name": q_name.strip(), "phone": q_phone.strip(),
                "interest": q_interest, "memo": q_memo.strip(),
                "from_user": _username or "비로그인",
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "status": "신규",
            })
            _save_leads(leads)
            st.success("문의가 접수되었습니다. 빠르게 연락드리겠습니다! 🙏")

st.markdown(
    f'<div style="text-align:center;margin-top:18px;font-size:13px;color:#6B7280;">'
    f'바로 결제를 원하시면 <a href="{KMONG_URL}" target="_blank" style="color:#2563EB;font-weight:700;">'
    f'크몽 상품 페이지</a>에서 진행하실 수 있습니다.</div>', unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# 관리자 — 문의 현황
# ══════════════════════════════════════════════════════════════════════════════
if _is_admin:
    st.markdown("<div style='height:30px;'></div>", unsafe_allow_html=True)
    st.divider()
    leads = _load_leads()
    with st.expander(f"🔔 구매·수강 문의 현황 ({len(leads)}건)", expanded=False):
        if not leads:
            st.info("아직 접수된 문의가 없습니다.")
        else:
            for ld in reversed(leads):
                lc1, lc2, lc3 = st.columns([3, 3, 1])
                lc1.markdown(f"**{ld.get('name','')}** · {ld.get('phone','')}")
                lc1.caption(f"{ld.get('interest','')} · {ld.get('created_at','')}")
                lc2.write(ld.get("memo", "") or "—")
                lc2.caption(f"신청자: {ld.get('from_user','')}")
                if lc3.button("삭제", key=f"del_lead_{ld['id']}"):
                    _save_leads([x for x in _load_leads() if x.get("id") != ld["id"]])
                    st.rerun()
                st.divider()
