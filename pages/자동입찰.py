"""광고 운영 — 목표순위 자동입찰 보조 시스템"""
import streamlit as st
import os, sys, uuid, hmac, hashlib, base64, time, re
import requests
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from db import sb_load, sb_save

# ── 인증 ─────────────────────────────────────────────────────────────────────
auth_type     = st.session_state.get("auth_type", "")
auth_username = st.session_state.get("auth_username", "")

if auth_type not in ("admin", "client"):
    st.error("🔒 로그인이 필요합니다.")
    st.stop()

# ── 클라이언트 ID 결정 ─────────────────────────────────────────────────────
if auth_type == "admin":
    accounts  = sb_load("client_accounts", os.path.join(ROOT, "client_accounts.json")) or []
    options   = ["admin"] + [a.get("username","") for a in accounts if a.get("username")]
    client_id = st.selectbox(
        "클라이언트 선택",
        options=options,
        format_func=lambda x: f"[관리자] {x}" if x == "admin" else x,
        key="bid_client",
    )
else:
    client_id = auth_username

SB_KEY        = f"bidding_{client_id}"
FALLBACK_JSON = os.path.join(ROOT, f"bidding_{client_id}.json")
MAX_GROUPS    = 5
MAX_KEYWORDS  = 30

STATUS_ICON = {
    "증액중":       "🔴",
    "감액중":       "🔵",
    "유지":         "🟢",
    "데이터 부족":  "⚪",
    "최대입찰 도달":"🟠",
    "최소입찰 도달":"🟡",
}

# ── 데이터 ────────────────────────────────────────────────────────────────
def load_data():
    raw = sb_load(SB_KEY, FALLBACK_JSON)
    return raw if isinstance(raw, dict) and "groups" in raw else {"groups": []}

def save_data(d):
    sb_save(SB_KEY, d, FALLBACK_JSON)

def new_kw_obj(keyword, current_bid=None):
    return {
        "keyword":         keyword,
        "current_rank":    None,
        "current_bid":     current_bid,
        "recommended_bid": None,
        "status":          "데이터 부족",
        "last_checked":    None,
    }

# ── 입찰 계산 ─────────────────────────────────────────────────────────────
def calc_bid(current_rank, target_rank, current_bid, bid_unit, min_bid, max_bid):
    MAX_SINGLE = 500
    if current_rank is None or current_bid is None:
        return current_bid, "데이터 부족"
    diff = current_rank - target_rank
    if diff > 0.5:
        delta   = min(bid_unit, MAX_SINGLE)
        new_bid = min(current_bid + delta, max_bid)
        status  = "최대입찰 도달" if new_bid >= max_bid else "증액중"
    elif diff < -0.5:
        delta   = min(bid_unit // 2 or bid_unit, MAX_SINGLE)
        new_bid = max(current_bid - delta, min_bid)
        status  = "최소입찰 도달" if new_bid <= min_bid else "감액중"
    else:
        new_bid = current_bid
        status  = "유지"
    return round(new_bid / 10) * 10, status

# ── 네이버 검색광고 API ───────────────────────────────────────────────────
# 정확한 API Base URL: api.searchad.naver.com (api.naver.com 아님)
NAVER_API_BASE = "https://api.searchad.naver.com"

CREDS_SB_KEY = f"naver_creds_{client_id}"
CREDS_FB     = os.path.join(ROOT, f"naver_creds_{client_id}.json")

def load_creds():
    raw = sb_load(CREDS_SB_KEY, CREDS_FB)
    return raw if isinstance(raw, dict) else {}

def save_creds(d):
    sb_save(CREDS_SB_KEY, d, CREDS_FB)

def _naver_sig(secret_key, timestamp, method, uri):
    msg = f"{timestamp}.{method}.{uri}"
    h   = hmac.new(secret_key.encode(), msg.encode(), hashlib.sha256)
    return base64.b64encode(h.digest()).decode()

def _naver_get(uri, api_key, secret_key, customer_id, params=None):
    ts  = str(int(time.time() * 1000))
    sig = _naver_sig(secret_key, ts, "GET", uri)
    headers = {
        "X-Timestamp": ts, "X-API-KEY": api_key,
        "X-Customer":  str(customer_id), "X-Signature": sig,
        "Content-Type": "application/json; charset=UTF-8",
    }
    r = requests.get(NAVER_API_BASE + uri, headers=headers, params=params, timeout=10)
    r.raise_for_status()
    return r.json()

def naver_campaigns(api_key, secret_key, cid):
    return _naver_get("/ncc/campaigns", api_key, secret_key, cid) or []

def naver_adgroups(api_key, secret_key, cid, campaign_id):
    return _naver_get("/ncc/adgroups", api_key, secret_key, cid,
                      params={"nccCampaignId": campaign_id}) or []

def naver_keywords(api_key, secret_key, cid, adgroup_id):
    return _naver_get("/ncc/keywords", api_key, secret_key, cid,
                      params={"nccAdgroupId": adgroup_id}) or []

def _get_id(obj, *keys):
    """여러 키 이름 중 값이 있는 첫 번째 반환 (API 버전별 키 이름 차이 대응)"""
    for k in keys:
        v = obj.get(k)
        if v:
            return str(v)
    return ""

def _naver_creds():
    return (
        st.session_state.get("n_api_key","").strip(),
        st.session_state.get("n_secret","").strip(),
        st.session_state.get("n_cid","").strip(),
    )

def _naver_connected():
    return all(_naver_creds())

# 저장된 인증 정보 세션에 주입 — 업체 전환 시 재로드
_creds_flag = f"n_creds_loaded_{client_id}"
if _creds_flag not in st.session_state:
    for _k in ("n_api_key", "n_secret", "n_cid"):
        st.session_state.pop(_k, None)
    _saved = load_creds()
    if _saved:
        st.session_state["n_api_key"] = _saved.get("api_key", "")
        st.session_state["n_secret"]  = _saved.get("secret_key", "")
        st.session_state["n_cid"]     = _saved.get("customer_id", "")
    st.session_state[_creds_flag] = True

# ════════════════════════════════════════════════════════════════════════════
# UI
# ════════════════════════════════════════════════════════════════════════════
st.title("📊 목표순위 자동입찰")
st.caption("목표순위 근접 유지를 위한 입찰가 조정 보조 시스템")

data   = load_data()
groups = data.get("groups", [])

tab1, tab2, tab3 = st.tabs(["입찰 현황", "그룹 관리", "키워드 관리"])

# ════════════════════════════════════════════════════════════════════════════
# 탭1: 입찰 현황
# ════════════════════════════════════════════════════════════════════════════
with tab1:
    rows = []
    for g in groups:
        for kw in g.get("keywords", []):
            rows.append({
                "_gid":      g["id"],
                "_kw":       kw["keyword"],
                "그룹명":    g["name"],
                "키워드":    kw["keyword"],
                "현재순위":  kw.get("current_rank"),
                "목표순위":  g["target_rank"],
                "현재입찰가":kw.get("current_bid"),
                "추천입찰가":kw.get("recommended_bid"),
                "상태":      (STATUS_ICON.get(kw.get("status","데이터 부족"),"⚪")
                              + " " + kw.get("status","데이터 부족")),
                "마지막체크":kw.get("last_checked","") or "",
            })

    if not rows:
        st.info("등록된 키워드가 없습니다. [그룹 관리] 탭에서 그룹을 추가하세요.")
    else:
        import pandas as pd
        df      = pd.DataFrame(rows)
        HIDDEN  = {"_gid","_kw"}
        disp_df = df[[c for c in df.columns if c not in HIDDEN]].copy()

        edited = st.data_editor(
            disp_df,
            use_container_width=True, hide_index=True, num_rows="fixed",
            column_config={
                "그룹명":    st.column_config.TextColumn(disabled=True),
                "키워드":    st.column_config.TextColumn(disabled=True),
                "현재순위":  st.column_config.NumberColumn("현재순위", format="%.1f"),
                "목표순위":  st.column_config.NumberColumn(disabled=True),
                "현재입찰가":st.column_config.NumberColumn("현재입찰가", format="%d"),
                "추천입찰가":st.column_config.NumberColumn(disabled=True, format="%d"),
                "상태":      st.column_config.TextColumn(disabled=True),
                "마지막체크":st.column_config.TextColumn(disabled=True),
            },
            key="bid_editor",
        )

        st.markdown(
            "**상태:** 🔴 증액중 &nbsp;🔵 감액중 &nbsp;🟢 유지 &nbsp;"
            "⚪ 데이터 부족 &nbsp;🟠 최대입찰 도달 &nbsp;🟡 최소입찰 도달",
            unsafe_allow_html=True,
        )

        c1, c2 = st.columns(2)
        with c1:
            if st.button("🔄 입찰가 계산", use_container_width=True):
                now_str = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
                recs = edited.to_dict(orient="records")
                for i, rec in enumerate(recs):
                    gid    = df.iloc[i]["_gid"]
                    kw_str = df.iloc[i]["_kw"]
                    g      = next((x for x in groups if x["id"] == gid), None)
                    if not g: continue
                    kw_obj = next((x for x in g["keywords"] if x["keyword"] == kw_str), None)
                    if not kw_obj: continue
                    kw_obj["current_rank"] = rec.get("현재순위")
                    raw = rec.get("현재입찰가")
                    kw_obj["current_bid"] = int(raw) if raw is not None else None
                    nb, st_ = calc_bid(
                        kw_obj["current_rank"], g["target_rank"],
                        kw_obj["current_bid"],  g["bid_unit"],
                        g["min_bid"], g["max_bid"],
                    )
                    kw_obj["recommended_bid"] = nb
                    kw_obj["status"]          = st_
                    kw_obj["last_checked"]    = now_str
                data["groups"] = groups
                save_data(data)
                st.success("계산 완료")
                st.rerun()
        with c2:
            if st.button("✅ 추천가 적용", use_container_width=True):
                for g in groups:
                    for kw_obj in g.get("keywords", []):
                        if kw_obj.get("recommended_bid") is not None:
                            kw_obj["current_bid"] = kw_obj["recommended_bid"]
                data["groups"] = groups
                save_data(data)
                st.success("추천입찰가 → 현재입찰가 적용 완료")
                st.rerun()

# ════════════════════════════════════════════════════════════════════════════
# 탭2: 그룹 관리
# ════════════════════════════════════════════════════════════════════════════
with tab2:

    # ── 기존 그룹 목록 ──────────────────────────────────────────────────────
    if groups:
        st.subheader("등록된 그룹")
        for g in groups:
            kw_count = len(g.get("keywords", []))
            with st.expander(
                f"**{g['name']}** — 목표순위 {g['target_rank']}위 / "
                f"키워드 {kw_count}개 / 입찰 {g['min_bid']:,}~{g['max_bid']:,}원",
                expanded=False,
            ):
                with st.form(f"edit_g_{g['id']}"):
                    c1, c2 = st.columns(2)
                    with c1:
                        g_name  = st.text_input("그룹명",        value=g["name"])
                        g_rank  = st.number_input("목표순위",     value=g["target_rank"],    min_value=1, max_value=15)
                        g_min   = st.number_input("최소입찰가",   value=g["min_bid"],        min_value=10, step=10)
                        g_max   = st.number_input("최대입찰가",   value=g["max_bid"],        min_value=10, step=10)
                    with c2:
                        g_unit  = st.number_input("증감단위(원)", value=g["bid_unit"],       min_value=10, step=10)
                        g_intvl = st.number_input("체크주기(분)", value=g["check_interval"], min_value=1)
                        g_auto  = st.checkbox("자동적용",         value=g.get("auto_apply", False))

                    cs, cd = st.columns(2)
                    with cs:
                        if st.form_submit_button("수정 저장", use_container_width=True):
                            if not g_name.strip():
                                st.error("그룹명 필수")
                            elif g_min >= g_max:
                                st.error("최소입찰가 < 최대입찰가")
                            else:
                                g.update({
                                    "name": g_name.strip(), "target_rank": int(g_rank),
                                    "min_bid": int(g_min), "max_bid": int(g_max),
                                    "bid_unit": int(g_unit), "check_interval": int(g_intvl),
                                    "auto_apply": g_auto,
                                })
                                save_data(data)
                                st.success("수정 완료")
                                st.rerun()
                    with cd:
                        if st.form_submit_button("삭제", use_container_width=True):
                            data["groups"] = [x for x in groups if x["id"] != g["id"]]
                            save_data(data)
                            st.rerun()

        st.divider()

    # ── 새 그룹 추가 ──────────────────────────────────────────────────────
    if len(groups) >= MAX_GROUPS:
        st.warning(f"그룹은 최대 {MAX_GROUPS}개까지 등록 가능합니다.")
    else:
        st.subheader("새 그룹 추가")

        add_method = st.radio(
            "그룹 추가 방식",
            ["📋 키워드 직접 입력", "📡 네이버 광고그룹 불러오기"],
            horizontal=True,
            key="add_method",
        )

        # ── 방식 1: 직접 입력 ─────────────────────────────────────────────
        if add_method == "📋 키워드 직접 입력":
            with st.form("add_group_direct", clear_on_submit=True):
                st.markdown("**그룹 기본 설정**")
                c1, c2 = st.columns(2)
                with c1:
                    n_name  = st.text_input("그룹명 *", placeholder="예: 이혼메인")
                    n_rank  = st.number_input("목표순위", value=3, min_value=1, max_value=15)
                    n_min   = st.number_input("최소입찰가", value=10000, min_value=10, step=10)
                    n_max   = st.number_input("최대입찰가", value=35000, min_value=10, step=10)
                with c2:
                    n_unit  = st.number_input("증감단위(원)", value=100, min_value=10, step=10)
                    n_intvl = st.number_input("체크주기(분)", value=15, min_value=1)
                    n_auto  = st.checkbox("자동적용", value=False)

                st.markdown("**키워드 입력** (줄바꿈 또는 쉼표로 구분)")
                kw_input = st.text_area(
                    "키워드",
                    placeholder="이혼변호사\n이혼전문변호사\n위자료변호사",
                    height=140,
                    label_visibility="collapsed",
                )

                if st.form_submit_button("그룹 생성", type="primary", use_container_width=True):
                    if not n_name.strip():
                        st.error("그룹명을 입력해주세요.")
                    elif n_min >= n_max:
                        st.error("최소입찰가는 최대입찰가보다 작아야 합니다.")
                    else:
                        # 키워드 파싱 (줄바꿈 + 쉼표)
                        raw_kws = re.split(r"[\n,]+", kw_input or "")
                        kws     = [k.strip() for k in raw_kws if k.strip()][:MAX_KEYWORDS]

                        new_group = {
                            "id":             str(uuid.uuid4()),
                            "name":           n_name.strip(),
                            "target_rank":    int(n_rank),
                            "min_bid":        int(n_min),
                            "max_bid":        int(n_max),
                            "bid_unit":       int(n_unit),
                            "check_interval": int(n_intvl),
                            "auto_apply":     n_auto,
                            "keywords":       [new_kw_obj(k) for k in kws],
                        }
                        data["groups"].append(new_group)
                        save_data(data)
                        st.success(
                            f"그룹 **{n_name.strip()}** 생성 완료 "
                            f"(키워드 {len(kws)}개)"
                        )
                        st.rerun()

        # ── 방식 2: 네이버 광고그룹 불러오기 ─────────────────────────────
        else:
            # API 인증 정보 입력 + 저장
            with st.expander("🔑 네이버 검색광고 API 인증 정보", expanded=not _naver_connected()):
                st.caption(
                    "네이버 광고 관리시스템 → 도구 → API 관리에서 발급한 정보를 입력하세요."
                )
                c1, c2, c3 = st.columns(3)
                with c1:
                    st.text_input("API Key (라이선스)", key="n_api_key", type="password",
                                  placeholder="발급된 API 라이선스 키")
                with c2:
                    st.text_input("Secret Key", key="n_secret", type="password",
                                  placeholder="비밀 키")
                with c3:
                    st.text_input("고객 ID", key="n_cid",
                                  placeholder="숫자 고객 ID")

                # 저장 버튼 — 클릭 시 Supabase에 인증 정보 저장
                if st.button("💾 인증 정보 저장", key="save_creds", use_container_width=True):
                    ak, sk, ci = _naver_creds()
                    if not all([ak, sk, ci]):
                        st.error("세 항목을 모두 입력해주세요.")
                    else:
                        save_creds({"api_key": ak, "secret_key": sk, "customer_id": ci})
                        st.success("✅ 저장 완료 — 다음 방문 시 자동으로 불러옵니다.")

            if not _naver_connected():
                st.info(
                    "📡 API 인증 정보를 입력하고 **💾 인증 정보 저장**을 클릭하면 "
                    "다음부터 자동으로 불러옵니다.\n\n"
                    "지금은 **📋 키워드 직접 입력** 방식을 사용하세요."
                )
            else:
                api_key, secret_key, cid = _naver_creds()

                # 캠페인
                if st.button("📥 캠페인 목록 불러오기", key="load_camps"):
                    with st.spinner("캠페인 조회 중..."):
                        try:
                            st.session_state["n_camps"] = naver_campaigns(api_key, secret_key, cid)
                            # 캠페인 바뀌면 하위 데이터 초기화
                            for _k in ("n_ags", "n_ags_camp_id", "n_kws", "n_kws_ag_id"):
                                st.session_state.pop(_k, None)
                        except Exception as e:
                            st.error(f"API 오류: {e}")

                camps = st.session_state.get("n_camps", [])
                if not camps:
                    st.stop()

                camp_map = {f"{c.get('name','(이름없음)')}": c for c in camps}
                sel_camp = camp_map[
                    st.selectbox("캠페인 선택", list(camp_map.keys()), key="n_sel_camp")
                ]
                camp_id = _get_id(sel_camp, "nccCampaignId", "campaignId", "id")

                # 광고그룹 — 캠페인 변경 시 자동 로드
                if camp_id and st.session_state.get("n_ags_camp_id") != camp_id:
                    with st.spinner("광고그룹 조회 중..."):
                        try:
                            st.session_state["n_ags"] = naver_adgroups(
                                api_key, secret_key, cid, camp_id
                            )
                            st.session_state["n_ags_camp_id"] = camp_id
                            st.session_state.pop("n_kws", None)
                            st.session_state.pop("n_kws_ag_id", None)
                        except Exception as e:
                            st.error(f"API 오류: {e}")

                ags = st.session_state.get("n_ags", [])
                if not ags:
                    st.stop()

                ag_map = {f"{a.get('name','(이름없음)')}": a for a in ags}
                sel_ag  = ag_map[
                    st.selectbox("광고그룹 선택", list(ag_map.keys()), key="n_sel_ag")
                ]
                ag_id = _get_id(sel_ag, "nccAdgroupId", "adgroupId", "adGroupId", "id")

                if not ag_id:
                    st.warning(f"광고그룹 ID를 찾을 수 없습니다. API 응답 키: {list(sel_ag.keys())}")
                    st.stop()

                # 키워드 — 광고그룹 변경 시 자동 로드
                if ag_id and st.session_state.get("n_kws_ag_id") != ag_id:
                    with st.spinner("키워드 조회 중..."):
                        try:
                            st.session_state["n_kws"] = naver_keywords(
                                api_key, secret_key, cid, ag_id
                            )
                            st.session_state["n_kws_ag_id"] = ag_id
                        except Exception as e:
                            st.error(f"API 오류: {e}")

                n_kws = st.session_state.get("n_kws", [])
                if not n_kws:
                    st.info("키워드가 없는 광고그룹입니다.")
                    st.stop()

                # 광고그룹 기본 입찰가 (키워드가 "기본" 설정일 때 fallback)
                ag_default_bid = sel_ag.get("bidAmt") or 0

                def _resolve_bid(k):
                    """키워드 입찰가: 70(최소=기본설정)이면 그룹 기본입찰가로 대체"""
                    raw = k.get("bidAmt") or k.get("bid") or 0
                    try:
                        raw = int(raw)
                    except (TypeError, ValueError):
                        raw = 0
                    return ag_default_bid if raw <= 70 and ag_default_bid > 70 else raw or None

                # 불러온 키워드 미리보기
                kw_texts = []
                for k in n_kws:
                    t = k.get("keyword") or k.get("keywordText") or k.get("text","")
                    if t:
                        kw_texts.append(t)

                st.markdown(f"**불러온 키워드 {len(kw_texts)}개**")
                import pandas as pd
                preview = pd.DataFrame([{
                    "키워드": k.get("keyword") or k.get("keywordText",""),
                    "현재입찰가": _resolve_bid(k) or "",
                    "상태": k.get("statusDesc") or k.get("userLock",""),
                } for k in n_kws])
                st.dataframe(preview, use_container_width=True, hide_index=True)

                # 그룹 설정 후 등록
                st.markdown("**그룹 설정**")
                with st.form("add_group_naver", clear_on_submit=True):
                    default_name = sel_ag.get("name","")
                    c1, c2 = st.columns(2)
                    with c1:
                        n_name  = st.text_input("그룹명 *", value=default_name)
                        n_rank  = st.number_input("목표순위", value=3, min_value=1, max_value=15)
                        n_min   = st.number_input("최소입찰가", value=10000, min_value=10, step=10)
                        n_max   = st.number_input("최대입찰가", value=35000, min_value=10, step=10)
                    with c2:
                        n_unit  = st.number_input("증감단위(원)", value=100, min_value=10, step=10)
                        n_intvl = st.number_input("체크주기(분)", value=15, min_value=1)
                        n_auto  = st.checkbox("자동적용", value=False)

                    if st.form_submit_button(
                        f"✅ 그룹 생성 (키워드 {len(kw_texts)}개 포함)",
                        type="primary", use_container_width=True,
                    ):
                        if not n_name.strip():
                            st.error("그룹명 필수")
                        elif n_min >= n_max:
                            st.error("최소입찰가 < 최대입찰가")
                        else:
                            existing_kws = {kw["keyword"] for g in groups for kw in g.get("keywords",[])}
                            kw_objs = []
                            for k in n_kws:
                                t   = k.get("keyword") or k.get("keywordText","")
                                bid = _resolve_bid(k)
                                if t and t not in existing_kws:
                                    kw_objs.append(new_kw_obj(t, bid))
                                    if len(kw_objs) >= MAX_KEYWORDS:
                                        break

                            data["groups"].append({
                                "id":             str(uuid.uuid4()),
                                "name":           n_name.strip(),
                                "target_rank":    int(n_rank),
                                "min_bid":        int(n_min),
                                "max_bid":        int(n_max),
                                "bid_unit":       int(n_unit),
                                "check_interval": int(n_intvl),
                                "auto_apply":     n_auto,
                                "keywords":       kw_objs,
                                "naver_campaign_id": camp_id,
                                "naver_adgroup_id":  ag_id,
                            })
                            save_data(data)
                            for k in ["n_camps","n_ags","n_kws"]:
                                st.session_state.pop(k, None)
                            st.success(
                                f"그룹 **{n_name.strip()}** 생성 완료 "
                                f"(키워드 {len(kw_objs)}개)"
                            )
                            st.rerun()

# ════════════════════════════════════════════════════════════════════════════
# 탭3: 키워드 관리 (그룹 선택 후 키워드 추가/삭제)
# ════════════════════════════════════════════════════════════════════════════
with tab3:
    if not groups:
        st.info("그룹을 먼저 추가하세요. ([그룹 관리] 탭)")
        st.stop()

    group_map = {g["name"]: g for g in groups}
    sel_name  = st.selectbox("그룹 선택", list(group_map.keys()), key="kw_tab_grp")
    sel_g     = group_map[sel_name]
    kw_list   = sel_g.get("keywords", [])
    existing  = {k["keyword"] for k in kw_list}

    st.markdown(f"**{sel_name}** — {len(kw_list)} / {MAX_KEYWORDS}개")

    # 키워드 추가
    if len(kw_list) < MAX_KEYWORDS:
        kw_text = st.text_area(
            "키워드 추가 (줄바꿈 또는 쉼표로 구분)",
            placeholder="이혼변호사\n이혼전문변호사",
            height=120,
            key="kw_tab_input",
        )
        if st.button("추가", type="primary", key="kw_tab_add"):
            raw = re.split(r"[\n,]+", kw_text or "")
            new = [k.strip() for k in raw if k.strip() and k.strip() not in existing]
            new = new[:MAX_KEYWORDS - len(kw_list)]
            if not new:
                st.warning("추가할 새 키워드가 없습니다.")
            else:
                for k in new:
                    sel_g["keywords"].append(new_kw_obj(k))
                save_data(data)
                st.success(f"{len(new)}개 추가 완료")
                st.rerun()
    else:
        st.warning(f"키워드 최대 {MAX_KEYWORDS}개 도달")

    st.divider()

    # 현재 키워드 목록
    st.markdown("**등록 키워드**")
    if not kw_list:
        st.info("등록된 키워드가 없습니다.")
    else:
        del_check = {}
        h1, h2, h3, h4 = st.columns([3, 2, 2, 1])
        h1.markdown("**키워드**")
        h2.markdown("**현재입찰가**")
        h3.markdown("**상태**")
        h4.markdown("**삭제**")

        for kw_obj in kw_list:
            kw = kw_obj["keyword"]
            c1, c2, c3, c4 = st.columns([3, 2, 2, 1])
            c1.write(kw)
            c2.write(f"{kw_obj['current_bid']:,}" if kw_obj.get("current_bid") else "—")
            c3.write(
                STATUS_ICON.get(kw_obj.get("status","데이터 부족"),"⚪")
                + " " + kw_obj.get("status","데이터 부족")
            )
            del_check[kw] = c4.checkbox(
                "", key=f"del_{sel_g['id']}_{kw}",
                label_visibility="collapsed",
            )

        if st.button("선택 삭제", key="kw_del_btn"):
            to_del = {k for k, v in del_check.items() if v}
            if not to_del:
                st.warning("삭제할 항목을 선택하세요.")
            else:
                sel_g["keywords"] = [k for k in kw_list if k["keyword"] not in to_del]
                save_data(data)
                st.success(f"{len(to_del)}개 삭제 완료")
                st.rerun()
