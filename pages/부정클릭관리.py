"""스마트로그 서비스 안내 및 신청"""
import os
import sys
import uuid
from datetime import datetime

import streamlit as st

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, ".env"))
except ImportError:
    pass

# ── Supabase 헬퍼 ─────────────────────────────────────────────────────────────
def _get_sb():
    try:
        import streamlit as _st
        secrets = getattr(_st, "secrets", {}) or {}
        url = secrets.get("SUPABASE_URL", "") or os.getenv("SUPABASE_URL", "")
        key = secrets.get("SUPABASE_KEY", "") or os.getenv("SUPABASE_KEY", "")
    except Exception:
        url = os.getenv("SUPABASE_URL", "")
        key = os.getenv("SUPABASE_KEY", "")
    if not url or not key:
        return None
    try:
        from supabase import create_client
        return create_client(url, key)
    except Exception:
        return None


def _sb_load(key):
    sb = _get_sb()
    if not sb:
        return None
    r = sb.table("app_data").select("data").eq("key", key).execute()
    return r.data[0]["data"] if r.data else None


def _sb_save(key, data):
    sb = _get_sb()
    if not sb:
        return
    sb.table("app_data").upsert({
        "key": key,
        "data": data,
        "updated_at": datetime.utcnow().isoformat() + "Z",
    }).execute()


def _has_rebate(owner_id: str) -> bool:
    sb = _get_sb()
    if not sb:
        return False
    try:
        r = sb.table("rebate_accounts").select("id").eq("owner_id", owner_id).limit(1).execute()
        return bool(r.data)
    except Exception:
        return False


def _load_applications() -> list:
    return _sb_load("smartlog_applications") or []


def _save_application(app: dict):
    apps = _load_applications()
    apps.append(app)
    _sb_save("smartlog_applications", apps)


# ══════════════════════════════════════════════════════════════════════════════
# 세션 정보
# ══════════════════════════════════════════════════════════════════════════════
is_admin    = st.session_state.get("auth_type") == "admin"
username    = st.session_state.get("auth_username", "")
client_info = st.session_state.get("auth_client", {})
biz_name    = client_info.get("business_name", username)
contact     = client_info.get("contact_name", "")
phone       = client_info.get("phone", "")
created_at  = client_info.get("created_at", "")

# ── 자격 조건 체크 ─────────────────────────────────────────────────────────────
cond_payback  = True
cond_smartlog = True
cond_age      = True
months_elapsed = 99

if not is_admin:
    cond_payback  = _has_rebate(username)
    cond_smartlog = bool(client_info.get("smartlog_eligible", False))

    if created_at:
        try:
            join_dt = datetime.strptime(created_at[:10], "%Y-%m-%d")
            months_elapsed = (datetime.now().year - join_dt.year) * 12 + \
                             (datetime.now().month - join_dt.month)
            cond_age = months_elapsed >= 2
        except Exception:
            cond_age = False
    else:
        cond_age = False

eligible = cond_payback and cond_smartlog and cond_age

# ══════════════════════════════════════════════════════════════════════════════
# 레이아웃
# ══════════════════════════════════════════════════════════════════════════════
st.title("🔍 스마트로그")
st.caption("네이버 파워링크 부정클릭 탐지 서비스")

if is_admin:
    TAB_INTRO, TAB_APPLY, TAB_ADMIN = st.tabs(["서비스 소개", "신청 현황", "대상자 관리"])
else:
    TAB_INTRO, TAB_APPLY = st.tabs(["서비스 소개", "서비스 신청"])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — 서비스 소개
# ══════════════════════════════════════════════════════════════════════════════
with TAB_INTRO:
    st.markdown("""
<div style="background:#EFF6FF;border-left:4px solid #3B82F6;
            padding:16px 20px;border-radius:8px;margin-bottom:20px;">
  <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:16px;flex-wrap:wrap;">
    <div style="flex:1;min-width:260px;">
      <div style="font-size:16px;font-weight:700;color:#1E40AF;margin-bottom:6px;">
        네이버 스마트로그란?
      </div>
      <div style="font-size:14px;color:#1E3A8A;line-height:1.7;">
        네이버 공식 광고 로그 분석 도구입니다. 파워링크 광고를 클릭한 방문자의
        <b>IP · 방문시간 · 체류시간 · 전환여부</b>를 자동으로 수집하고,
        의심 클릭 패턴을 탐지해 네이버에 IP 차단 신청까지 연동합니다.
      </div>
    </div>
    <a href="https://smlog.co.kr/2020/prevent.html" target="_blank"
       style="display:inline-flex;align-items:center;gap:6px;white-space:nowrap;
              background:#3B82F6;color:#fff;font-size:13px;font-weight:700;
              padding:10px 18px;border-radius:8px;text-decoration:none;
              box-shadow:0 2px 8px rgba(59,130,246,.35);align-self:center;">
      🔗 공식 소개 보기
    </a>
  </div>
</div>
""", unsafe_allow_html=True)

    c1, c2, c3 = st.columns(3)
    cards = [
        ("#F0FDF4", "#BBF7D0", "#166534", "#15803D", "📊", "클릭 로그 자동 수집",
         "방문 IP, 체류시간, 전환여부 실시간 기록"),
        ("#FFF7ED", "#FED7AA", "#9A3412", "#C2410C", "🚨", "부정클릭 자동 탐지",
         "반복 클릭·단시간 이탈 등 의심 패턴 필터링"),
        ("#F5F3FF", "#DDD6FE", "#5B21B6", "#6D28D9", "🛡️", "네이버 직접 차단 연동",
         "탐지 IP를 네이버 광고 시스템에 직접 차단 신청"),
    ]
    for col, (bg, bd, h, t, ico, title, desc) in zip([c1, c2, c3], cards):
        with col:
            st.markdown(f"""
<div style="background:{bg};border:1px solid {bd};border-radius:10px;
            padding:16px;text-align:center;">
  <div style="font-size:28px;">{ico}</div>
  <div style="font-weight:700;margin:8px 0 4px;color:{h};">{title}</div>
  <div style="font-size:13px;color:{t};">{desc}</div>
</div>
""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("#### 제공 혜택")

    img_col, tbl_col = st.columns([1, 1], gap="large")
    with tbl_col:
        st.markdown("""
| 항목 | 일반 광고주 | 마케팁 스마트로그 |
|------|:----------:|:---------------:|
| 클릭 로그 조회 | 제한적 | **상세 전체 열람** |
| 부정클릭 탐지 | 수동 | **자동 탐지 + 알림** |
| IP 차단 신청 | 직접 신청 | **대행 처리** |
| 월간 리포트 | 없음 | **부정클릭 분석 리포트** |
| 비용 | 별도 | **별도 비용 없음** |
""")
    with img_col:
        import base64 as _b64, os as _os
        _img_path = _os.path.join(ROOT, "static", "smlog_preview.png")
        try:
            with open(_img_path, "rb") as _f:
                _img_b64 = _b64.b64encode(_f.read()).decode()
            st.markdown(f"""
<a href="https://smlog.co.kr/2020/prevent.html" target="_blank"
   style="display:block;border-radius:10px;overflow:hidden;
          box-shadow:0 4px 20px rgba(0,0,0,0.13);border:1px solid #E5E7EB;">
  <img src="data:image/png;base64,{_img_b64}"
       style="width:100%;display:block;" />
</a>
<div style="text-align:center;margin-top:6px;font-size:11px;color:#9CA3AF;">
  ▲ 부정클릭 IP 분석 화면 (클릭 시 공식 페이지)
</div>
""", unsafe_allow_html=True)
        except Exception:
            st.markdown("[![스마트로그](https://smlog.co.kr/2020/img/sub01/p_sub_box02_img.png)](https://smlog.co.kr/2020/prevent.html)")

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("""
<div style="background:#FFFBEB;border:1px solid #FDE68A;border-radius:8px;padding:14px 18px;">
  <div style="font-size:13px;color:#92400E;line-height:2;">
    <b>신청 조건</b><br>
    ✅ 마케팁 페이백(수수료 환급) 계정 연동 완료<br>
    ✅ 전월 네이버 광고비 300만원 이상 소진<br>
    <br>
    <span style="color:#B45309;">
      두 조건 모두 충족하면 <b>서비스 신청 탭</b>이 자동으로 열립니다.<br>
      일반적으로 가입 후 <b>2개월 이후</b>부터 신청 가능합니다.
    </span>
  </div>
</div>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — 서비스 신청 (클라이언트)
# ══════════════════════════════════════════════════════════════════════════════
if not is_admin:
    with TAB_APPLY:
        if not eligible:
            st.markdown("""
<div style="background:#F9FAFB;border:1px solid #E5E7EB;border-radius:12px;
            padding:28px 32px;text-align:center;margin:20px 0;">
  <div style="font-size:40px;margin-bottom:12px;">🔒</div>
  <div style="font-size:17px;font-weight:700;color:#374151;margin-bottom:8px;">
    아직 신청 조건이 충족되지 않았습니다
  </div>
  <div style="font-size:14px;color:#6B7280;line-height:1.8;">
    아래 조건을 모두 충족하면 신청폼이 자동으로 열립니다.
  </div>
</div>
""", unsafe_allow_html=True)

            cc1, cc2, cc3 = st.columns(3)
            cond_items = [
                (cc1, cond_payback,
                 "페이백 연동 완료" if cond_payback else "페이백 연동 필요",
                 "완료" if cond_payback else "페이백신청 메뉴에서 계정 등록"),
                (cc2, cond_age,
                 f"가입 {months_elapsed}개월 (충족)" if cond_age else f"가입 {months_elapsed}개월",
                 "충족" if cond_age else "가입 2개월 후 자동 충족"),
                (cc3, cond_smartlog,
                 "광고비 조건 충족" if cond_smartlog else "전월 광고비 300만원 이상",
                 "충족" if cond_smartlog else "전월 소진액 기준 자동 확인"),
            ]
            for col, ok, label, sub in cond_items:
                with col:
                    bg  = "#D1FAE5" if ok else "#FEF3C7"
                    bd  = "#6EE7B7" if ok else "#FDE68A"
                    tc  = "#065F46" if ok else "#92400E"
                    ico = "✅" if ok else ("❌" if not ok and label.endswith("필요") else "⏳")
                    st.markdown(f"""
<div style="background:{bg};border:1px solid {bd};border-radius:10px;
            padding:16px;text-align:center;">
  <div style="font-size:24px;">{ico}</div>
  <div style="font-size:13px;font-weight:700;color:{tc};margin-top:6px;">{label}</div>
  <div style="font-size:11px;color:{tc};margin-top:4px;opacity:.8;">{sub}</div>
</div>
""", unsafe_allow_html=True)

            st.markdown("<br>", unsafe_allow_html=True)
            if not cond_payback:
                st.info("💡 **광고비 페이백신청** 메뉴에서 네이버 광고 계정을 먼저 연동해주세요.")

        else:
            apps   = _load_applications()
            my_app = next((a for a in apps if a.get("client_id") == username), None)

            if my_app:
                status = my_app.get("status", "대기중")
                palettes = {
                    "대기중": ("#FEF3C7", "#92400E", "⏳"),
                    "처리중": ("#DBEAFE", "#1E40AF", "🔄"),
                    "완료":   ("#D1FAE5", "#065F46", "✅"),
                }
                bg, tc, ico = palettes.get(status, ("#F3F4F6", "#374151", "📋"))
                st.markdown(f"""
<div style="background:{bg};border-radius:10px;padding:24px 32px;
            text-align:center;margin:16px 0;">
  <div style="font-size:36px;">{ico}</div>
  <div style="font-size:17px;font-weight:700;color:{tc};margin:10px 0 6px;">
    신청 완료 — {status}
  </div>
  <div style="font-size:13px;color:{tc};">신청일: {my_app.get('created_at','')[:10]}</div>
</div>
""", unsafe_allow_html=True)
                tips = {
                    "대기중": "담당자가 확인 후 2~3 영업일 내 안내드립니다.",
                    "처리중": "스마트로그 세팅 진행 중입니다. 완료 시 별도 안내드립니다.",
                    "완료":   "스마트로그 서비스가 활성화되었습니다.",
                }
                st.caption(tips.get(status, ""))

            else:
                st.markdown("#### 스마트로그 서비스 신청")
                st.caption("신청 후 담당자가 2~3 영업일 내 연락드립니다.")
                with st.form("smartlog_form"):
                    f_biz   = st.text_input("업체명 *",   value=biz_name)
                    f_name  = st.text_input("담당자명 *", value=contact)
                    f_phone = st.text_input("연락처 *",   value=phone, placeholder="010-0000-0000")
                    f_memo  = st.text_area("요청사항 (선택)",
                                           placeholder="광고 계정 ID, 주요 키워드 등 자유롭게 적어주세요.",
                                           height=100)
                    if st.form_submit_button("신청하기", type="primary", use_container_width=True):
                        if not f_biz.strip() or not f_name.strip() or not f_phone.strip():
                            st.error("업체명, 담당자명, 연락처는 필수입니다.")
                        else:
                            _save_application({
                                "id":            str(uuid.uuid4()),
                                "client_id":     username,
                                "business_name": f_biz.strip(),
                                "contact_name":  f_name.strip(),
                                "phone":         f_phone.strip(),
                                "memo":          f_memo.strip(),
                                "status":        "대기중",
                                "created_at":    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            })
                            st.success("신청이 완료됐습니다. 2~3 영업일 내 연락드립니다.")
                            st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# TAB 2/3 — 어드민 전용
# ══════════════════════════════════════════════════════════════════════════════
if is_admin:
    with TAB_APPLY:
        apps = _load_applications()
        st.caption(f"총 {len(apps)}건")
        if not apps:
            st.info("아직 신청이 없습니다.")
        else:
            for app in sorted(apps, key=lambda x: x.get("created_at", ""), reverse=True):
                status = app.get("status", "대기중")
                with st.expander(
                    f"{app.get('business_name','')}  ·  {app.get('contact_name','')}  ·  "
                    f"{app.get('created_at','')[:10]}  ·  {status}",
                    expanded=(status == "대기중"),
                ):
                    col_l, col_r = st.columns([2, 1])
                    with col_l:
                        st.markdown(f"**업체명:** {app.get('business_name','')}")
                        st.markdown(f"**담당자:** {app.get('contact_name','')}  |  {app.get('phone','')}")
                        st.markdown(f"**계정 ID:** `{app.get('client_id','')}`")
                        if app.get("memo"):
                            st.markdown(f"**요청사항:** {app.get('memo','')}")
                    with col_r:
                        new_st = st.selectbox(
                            "처리 상태",
                            ["대기중", "처리중", "완료"],
                            index=["대기중", "처리중", "완료"].index(status),
                            key=f"sl_st_{app['id']}",
                        )
                        if st.button("저장", key=f"sl_sv_{app['id']}"):
                            all_apps = _load_applications()
                            for a in all_apps:
                                if a["id"] == app["id"]:
                                    a["status"] = new_st
                            _sb_save("smartlog_applications", all_apps)
                            st.success("저장됨")
                            st.rerun()

    with TAB_ADMIN:
        st.markdown("#### 스마트로그 대상자 현황")
        st.caption("계정관리에서 '스마트로그 대상' 체크 시 해당 광고주 신청폼이 열립니다.")

        from auth import load_accounts as _load_accs
        all_accs = [a for a in _load_accs() if a.get("approved", True)]
        apps     = _load_applications()
        app_ids  = {a.get("client_id") for a in apps}

        rows = []
        for acc in all_accs:
            uid = acc.get("username", "")
            jd  = acc.get("created_at", "")
            try:
                jdt = datetime.strptime(jd[:10], "%Y-%m-%d")
                mo  = (datetime.now().year - jdt.year) * 12 + (datetime.now().month - jdt.month)
            except Exception:
                mo = 0
            rows.append({
                "계정":          uid,
                "업체명":        acc.get("business_name", ""),
                "가입":          f"{mo}개월",
                "페이백":        "✅" if _has_rebate(uid) else "❌",
                "스마트로그 대상": "✅" if acc.get("smartlog_eligible") else "-",
                "신청":          "✅" if uid in app_ids else "-",
            })

        if rows:
            import pandas as pd
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
