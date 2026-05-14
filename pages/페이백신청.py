import streamlit as st
import json
import os
import sys
import uuid
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from components.style import PAYBACK_CSS, badge, STATUS_LIST

DATA_PATH = os.path.join(ROOT, "rebate_accounts.json")


# ── Storage ───────────────────────────────────────────────────────────────────
def load_accounts():
    try:
        if os.path.exists(DATA_PATH):
            with open(DATA_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return []


def save_accounts(accounts):
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(accounts, f, ensure_ascii=False, indent=2)


# ── Secret helper ─────────────────────────────────────────────────────────────
def get_secret(key, default=""):
    try:
        if hasattr(st, "secrets") and key in st.secrets:
            return str(st.secrets[key])
    except Exception:
        pass
    return os.getenv(key, default)


ADMIN_PW = get_secret("ADMIN_PASSWORD", "mktip")

# ── Styles ────────────────────────────────────────────────────────────────────
st.markdown(PAYBACK_CSS, unsafe_allow_html=True)


# ── Modal: 계정 추가 ──────────────────────────────────────────────────────────
@st.dialog("광고 계정 추가")
def add_account_dialog():
    st.markdown('<p style="color:#666;font-size:13px;margin-bottom:4px;">네이버 광고 계정 정보를 입력해 주세요. 연동 신청 후 1~2 영업일 내 확인됩니다.</p>', unsafe_allow_html=True)
    st.markdown("")

    naver_id     = st.text_input("네이버 로그인 ID *", placeholder="naver_login_id")
    account_name = st.text_input("광고 계정 이름 *",   placeholder="예: 마케팁 검색광고 계정")
    customer_id  = st.text_input("광고 계정 번호 (Customer ID) *", placeholder="예: 2815366",
                                  help="searchad.naver.com 로그인 후 URL의 숫자")
    alias        = st.text_input("별칭 (선택)", placeholder="예: 메인 계정")

    st.markdown("")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("취소", use_container_width=True):
            st.rerun()
    with c2:
        if st.button("연동 신청", type="primary", use_container_width=True):
            if not all([naver_id.strip(), account_name.strip(), customer_id.strip()]):
                st.error("* 필수 항목을 모두 입력해 주세요.")
            else:
                accs = load_accounts()
                accs.append({
                    "id":             str(uuid.uuid4()),
                    "naver_login_id": naver_id.strip(),
                    "account_name":   account_name.strip(),
                    "customer_id":    customer_id.strip(),
                    "alias":          alias.strip(),
                    "status":         "연동신청",
                    "created_at":     datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                })
                save_accounts(accs)
                st.success("✅ 연동 신청이 완료되었습니다!")
                st.rerun()


# ═════════════════════════════════════════════════════════════════════════════
# 페이지 본문
# ═════════════════════════════════════════════════════════════════════════════

# ── 헤더 ──────────────────────────────────────────────────────────────────────
st.markdown('<div class="pb-h1">검색광고 페이백</div>', unsafe_allow_html=True)
st.markdown('<div class="pb-sub">네이버 광고 계정을 연동하고 광고비 페이백을 받아보세요</div>', unsafe_allow_html=True)

b1, b2, _ = st.columns([1, 1, 5])
with b1:
    apply_btn = st.button("신청하기", type="primary", use_container_width=True)
with b2:
    if st.button("내역보기", use_container_width=True):
        st.session_state["payback_tab"] = "전체"

# ── 페이백이란? 안내 ──────────────────────────────────────────────────────────
with st.expander("ℹ️  광고비 페이백이란?"):
    st.markdown("""
<style>
.pb-rate-wrap { display:flex; gap:24px; flex-wrap:wrap; margin-top:4px; }
.pb-rate-card {
  background:#F8FAFF;
  border:1px solid #E0E7FF;
  border-radius:12px;
  padding:18px 22px;
  min-width:200px;
  flex:1;
}
.pb-rate-platform {
  font-size:13px; font-weight:800; color:#111;
  margin-bottom:12px; display:flex; align-items:center; gap:6px;
}
.pb-rate-row {
  display:flex; justify-content:space-between; align-items:center;
  padding:6px 0; border-bottom:1px solid #EEF0F4; font-size:13px;
}
.pb-rate-row:last-child { border-bottom:none; }
.pb-rate-label { color:#555; }
.pb-rate-pct { font-weight:700; color:#0064FF; font-size:14px; }
.pb-intro {
  font-size:15px; font-weight:700; color:#111;
  margin-bottom:16px; line-height:1.6;
}
.pb-pct-hl { color:#0064FF; }
</style>
<div class="pb-intro">
  마케팁 광고 계정을 연동하면,<br>
  광고 비용의 최대 <span class="pb-pct-hl">10%</span>를 돌려받을 수 있는 시스템입니다.
</div>
<div class="pb-rate-wrap">
  <div class="pb-rate-card">
    <div class="pb-rate-platform">🟢 네이버</div>
    <div class="pb-rate-row"><span class="pb-rate-label">검색광고 (파워링크·쇼핑·브랜드)</span><span class="pb-rate-pct">10%</span></div>
    <div class="pb-rate-row"><span class="pb-rate-label">GFA</span><span class="pb-rate-pct">10%</span></div>
    <div class="pb-rate-row"><span class="pb-rate-label">AD Voost</span><span class="pb-rate-pct">5%</span></div>
  </div>
  <div class="pb-rate-card">
    <div class="pb-rate-platform">🟡 카카오</div>
    <div class="pb-rate-row"><span class="pb-rate-label">검색광고</span><span class="pb-rate-pct">10%</span></div>
    <div class="pb-rate-row"><span class="pb-rate-label">배너광고</span><span class="pb-rate-pct">10%</span></div>
  </div>
  <div class="pb-rate-card">
    <div class="pb-rate-platform">🟠 당근</div>
    <div class="pb-rate-row"><span class="pb-rate-label">전문가광고</span><span class="pb-rate-pct">7%</span></div>
  </div>
</div>
""", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ── 안내 카드 2개 ─────────────────────────────────────────────────────────────
left, right = st.columns([2.2, 1], gap="large")

with left:
    st.markdown("""
<div class="info-card">
  <div class="info-card-ttl">연동 절차</div>
  <div class="steps">
    <div class="step">
      <div class="step-num">1</div>
      <div class="step-lbl">연동 신청</div>
      <div class="step-desc">계정 정보 입력</div>
    </div>
    <div class="step-line"></div>
    <div class="step">
      <div class="step-num">2</div>
      <div class="step-lbl">네이버 확인중</div>
      <div class="step-desc">관리자 승인 요청</div>
    </div>
    <div class="step-line"></div>
    <div class="step">
      <div class="step-num">3</div>
      <div class="step-lbl">이관 승인</div>
      <div class="step-desc">광고센터에서 승인</div>
    </div>
    <div class="step-line"></div>
    <div class="step">
      <div class="step-num">4</div>
      <div class="step-lbl">연동 완료</div>
      <div class="step-desc">페이백 수령 가능</div>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

with right:
    st.markdown("""
<div class="info-card">
  <div class="notice-wrap">
    <div class="notice-ttl">⚠️ 필독 안내 사항</div>
    <div class="notice-row">
      <span class="notice-key">정산 일정 안내</span>
      <span class="notice-val">페이백 정산은 <em-red>2달 뒤</em-red> 진행됩니다.<br>
        <span style="font-size:11px;color:#aaa;">(ex. 1월 → 3월 10일)</span>
      </span>
    </div>
    <div class="notice-row">
      <span class="notice-key">네이버 플레이스</span>
      <span class="notice-val">플레이스 광고 페이백은 <em-red>불가</em-red>합니다.</span>
    </div>
    <div class="notice-row">
      <span class="notice-key">문의처 안내</span>
      <span class="notice-val">검색광고 문의는 <em-blue>마케팁</em-blue>으로 부탁드립니다.</span>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ── 계정 리스트 ───────────────────────────────────────────────────────────────
accounts = load_accounts()

h1, h2 = st.columns([4, 1])
with h1:
    st.markdown(
        f'<div class="sec-ttl">내 네이버 광고 계정'
        f'<span class="count-pill">연동된 계정 {len(accounts)}개</span></div>',
        unsafe_allow_html=True
    )
with h2:
    add_btn = st.button("＋ 계정 추가", type="primary", use_container_width=True)

# 상태 탭
tab_options = ["전체"] + STATUS_LIST
default_tab = st.session_state.get("payback_tab", "전체")
default_idx = tab_options.index(default_tab) if default_tab in tab_options else 0

selected_tab = st.radio(
    "상태",
    tab_options,
    index=default_idx,
    horizontal=True,
    label_visibility="collapsed",
)

filtered = accounts if selected_tab == "전체" else [a for a in accounts if a["status"] == selected_tab]

st.markdown("<div style='margin-top:12px;'></div>", unsafe_allow_html=True)

if not filtered:
    st.markdown("""
<div class="empty-wrap">
  <div class="empty-ico">🔗</div>
  <div class="empty-ttl">연동된 광고 계정이 없습니다</div>
  <div class="empty-desc">계정을 추가하여 페이백을 받아보세요</div>
</div>
""", unsafe_allow_html=True)
else:
    for acc in filtered:
        alias_html = (
            f'<span style="margin-left:6px;background:#F5F5F5;color:#888;'
            f'font-size:11px;padding:1px 7px;border-radius:6px;">{acc["alias"]}</span>'
            if acc.get("alias") else ""
        )
        st.markdown(f"""
<div class="acc-card">
  <div>
    <div class="acc-name">
      {acc.get("account_name", "-")}
      {alias_html}
    </div>
    <div class="acc-meta">
      {acc.get("naver_login_id", "-")} &nbsp;·&nbsp;
      Customer ID: <b style="color:#333;">{acc.get("customer_id", "-")}</b> &nbsp;·&nbsp;
      신청일: {acc.get("created_at", "-")[:10]}
    </div>
  </div>
  <div style="margin-top:2px;">{badge(acc.get("status","연동신청"))}</div>
</div>
""", unsafe_allow_html=True)

# ── 모달 트리거 ───────────────────────────────────────────────────────────────
if add_btn or apply_btn:
    add_account_dialog()


# ═════════════════════════════════════════════════════════════════════════════
# 관리자 영역
# ═════════════════════════════════════════════════════════════════════════════
st.markdown("<br>", unsafe_allow_html=True)
st.divider()

with st.expander("🔐 관리자 — 상태 관리"):
    if not st.session_state.get("payback_admin_auth"):
        _, col, _ = st.columns([2, 3, 2])
        with col:
            pw = st.text_input("관리자 비밀번호", type="password", key="pb_admin_pw")
            if st.button("로그인", type="primary", use_container_width=True, key="pb_admin_login"):
                if pw == ADMIN_PW:
                    st.session_state.payback_admin_auth = True
                    st.rerun()
                else:
                    st.error("비밀번호가 틀렸습니다.")
    else:
        st.success("관리자 모드 활성화")
        all_accs = load_accounts()
        if not all_accs:
            st.info("등록된 계정이 없습니다.")
        else:
            import pandas as pd
            for i, acc in enumerate(all_accs):
                with st.container(border=True):
                    c1, c2, c3 = st.columns([4, 2, 1])
                    with c1:
                        st.markdown(
                            f"**{acc['account_name']}** &nbsp; `{acc['customer_id']}`  \n"
                            f"{acc['naver_login_id']} · 신청일: {acc['created_at'][:10]}"
                        )
                        st.markdown(badge(acc["status"]), unsafe_allow_html=True)
                    with c2:
                        new_status = st.selectbox(
                            "상태 변경",
                            STATUS_LIST + ["반려"],
                            index=(STATUS_LIST + ["반려"]).index(acc["status"])
                            if acc["status"] in STATUS_LIST + ["반려"] else 0,
                            key=f"pb_status_{acc['id']}",
                            label_visibility="collapsed",
                        )
                    with c3:
                        if st.button("저장", key=f"pb_save_{acc['id']}", use_container_width=True):
                            all_accs[i]["status"] = new_status
                            save_accounts(all_accs)
                            st.toast(f"✅ {acc['account_name']} 상태 변경 완료")
                            st.rerun()

        if st.button("로그아웃", key="pb_admin_logout"):
            st.session_state.payback_admin_auth = False
            st.rerun()
