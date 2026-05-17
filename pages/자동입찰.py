"""광고 운영 — 목표순위 자동입찰 보조 시스템"""
import streamlit as st
import os, sys, uuid, hmac, hashlib, base64, time
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

# ── 클라이언트 ID 결정 ────────────────────────────────────────────────────────
if auth_type == "admin":
    accounts = sb_load("client_accounts", os.path.join(ROOT, "client_accounts.json")) or []
    options  = ["admin"] + [a.get("username","") for a in accounts if a.get("username")]
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

# ── 데이터 ───────────────────────────────────────────────────────────────────
def load_data():
    raw = sb_load(SB_KEY, FALLBACK_JSON)
    return raw if isinstance(raw, dict) and "groups" in raw else {"groups": []}

def save_data(d):
    sb_save(SB_KEY, d, FALLBACK_JSON)

# ── 입찰 계산 ─────────────────────────────────────────────────────────────────
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

# ── 네이버 검색광고 API ───────────────────────────────────────────────────────
NAVER_API_BASE = "https://api.naver.com"

def _naver_sig(secret_key: str, timestamp: str, method: str, uri: str) -> str:
    msg = f"{timestamp}.{method}.{uri}"
    h   = hmac.new(secret_key.encode(), msg.encode(), hashlib.sha256)
    return base64.b64encode(h.digest()).decode()

def _naver_get(uri, api_key, secret_key, customer_id, params=None):
    ts  = str(int(time.time() * 1000))
    sig = _naver_sig(secret_key, ts, "GET", uri)
    headers = {
        "X-Timestamp":  ts,
        "X-API-KEY":    api_key,
        "X-Customer":   str(customer_id),
        "X-Signature":  sig,
        "Content-Type": "application/json; charset=UTF-8",
    }
    r = requests.get(NAVER_API_BASE + uri, headers=headers, params=params, timeout=10)
    r.raise_for_status()
    return r.json()

def naver_get_campaigns(api_key, secret_key, customer_id):
    return _naver_get("/ncc/campaigns", api_key, secret_key, customer_id) or []

def naver_get_adgroups(api_key, secret_key, customer_id, campaign_id):
    return _naver_get("/ncc/adgroups", api_key, secret_key, customer_id,
                      params={"campaignId": campaign_id}) or []

def naver_get_keywords(api_key, secret_key, customer_id, adgroup_id):
    return _naver_get("/ncc/keywords", api_key, secret_key, customer_id,
                      params={"adgroupId": adgroup_id}) or []

# ══════════════════════════════════════════════════════════════════════════════
# UI
# ══════════════════════════════════════════════════════════════════════════════
st.title("📊 목표순위 자동입찰")
st.caption("목표순위 근접 유지를 위한 입찰가 조정 보조 시스템")

data   = load_data()
groups = data.get("groups", [])

tab1, tab2, tab3 = st.tabs(["입찰 현황", "그룹 관리", "키워드 관리"])

# ════════════════════════════════════════════════════════════════════════════
# 탭1: 입찰 현황
# ════════════════════════════════════════════════════════════════════════════
with tab1:
    # 모든 키워드 수집
    rows = []
    for g in groups:
        for kw in g.get("keywords", []):
            rows.append({
                "_gid":     g["id"],
                "_kw":      kw["keyword"],
                "그룹명":   g["name"],
                "키워드":   kw["keyword"],
                "현재순위": kw.get("current_rank"),
                "목표순위": g["target_rank"],
                "현재입찰가": kw.get("current_bid"),
                "추천입찰가": kw.get("recommended_bid"),
                "상태":     (STATUS_ICON.get(kw.get("status","데이터 부족"),"⚪")
                             + " " + kw.get("status","데이터 부족")),
                "마지막체크": kw.get("last_checked","") or "",
            })

    if not rows:
        st.info("등록된 키워드가 없습니다. [그룹 관리] → [키워드 관리] 탭에서 먼저 추가하세요.")
    else:
        import pandas as pd
        df        = pd.DataFrame(rows)
        HIDDEN    = ["_gid","_kw"]
        disp_cols = [c for c in df.columns if c not in HIDDEN]
        disp_df   = df[disp_cols].copy()

        edited = st.data_editor(
            disp_df,
            use_container_width=True,
            hide_index=True,
            num_rows="fixed",
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
                edited_records = edited.to_dict(orient="records")
                for i, rec in enumerate(edited_records):
                    gid = df.iloc[i]["_gid"]
                    kw  = df.iloc[i]["_kw"]
                    g   = next((x for x in groups if x["id"] == gid), None)
                    if not g: continue
                    kw_obj = next((x for x in g["keywords"] if x["keyword"] == kw), None)
                    if not kw_obj: continue
                    kw_obj["current_rank"] = rec.get("현재순위")
                    raw_bid = rec.get("현재입찰가")
                    kw_obj["current_bid"] = int(raw_bid) if raw_bid is not None else None
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
                st.success("계산 완료.")
                st.rerun()

        with c2:
            if st.button("✅ 추천가 적용", use_container_width=True):
                for g in groups:
                    for kw_obj in g.get("keywords", []):
                        if kw_obj.get("recommended_bid") is not None:
                            kw_obj["current_bid"] = kw_obj["recommended_bid"]
                data["groups"] = groups
                save_data(data)
                st.success("추천입찰가를 현재입찰가로 적용했습니다.")
                st.rerun()

# ════════════════════════════════════════════════════════════════════════════
# 탭2: 그룹 관리
# ════════════════════════════════════════════════════════════════════════════
with tab2:
    st.subheader("그룹 목록")
    if not groups:
        st.info("등록된 그룹이 없습니다.")
    else:
        for g in groups:
            with st.expander(f"**{g['name']}** — 목표순위 {g['target_rank']}위", expanded=False):
                with st.form(f"edit_g_{g['id']}"):
                    c1, c2 = st.columns(2)
                    with c1:
                        g_name  = st.text_input("그룹명",       value=g["name"])
                        g_rank  = st.number_input("목표순위",    value=g["target_rank"], min_value=1, max_value=15)
                        g_min   = st.number_input("최소입찰가",  value=g["min_bid"],     min_value=10, step=10)
                        g_max   = st.number_input("최대입찰가",  value=g["max_bid"],     min_value=10, step=10)
                    with c2:
                        g_unit  = st.number_input("증감단위(원)",value=g["bid_unit"],    min_value=10, step=10)
                        g_intvl = st.number_input("체크주기(분)",value=g["check_interval"], min_value=1)
                        g_auto  = st.checkbox("자동적용",        value=g.get("auto_apply", False))
                        st.markdown(f"키워드 **{len(g.get('keywords',[]))}개** 등록됨")

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
    st.subheader("새 그룹 추가")
    if len(groups) >= MAX_GROUPS:
        st.warning(f"최대 {MAX_GROUPS}개 그룹까지 등록 가능합니다.")
    else:
        with st.form("add_group", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                n_name  = st.text_input("그룹명 *",       placeholder="예: 이혼메인")
                n_rank  = st.number_input("목표순위",      value=3,     min_value=1, max_value=15)
                n_min   = st.number_input("최소입찰가",    value=10000, min_value=10, step=10)
                n_max   = st.number_input("최대입찰가",    value=35000, min_value=10, step=10)
            with c2:
                n_unit  = st.number_input("증감단위(원)",  value=100,   min_value=10, step=10)
                n_intvl = st.number_input("체크주기(분)",  value=15,    min_value=1)
                n_auto  = st.checkbox("자동적용",          value=False)

            if st.form_submit_button("그룹 추가", type="primary", use_container_width=True):
                if not n_name.strip():
                    st.error("그룹명 필수")
                elif n_min >= n_max:
                    st.error("최소입찰가 < 최대입찰가")
                else:
                    data["groups"].append({
                        "id": str(uuid.uuid4()), "name": n_name.strip(),
                        "target_rank": int(n_rank), "min_bid": int(n_min),
                        "max_bid": int(n_max), "bid_unit": int(n_unit),
                        "check_interval": int(n_intvl), "auto_apply": n_auto,
                        "keywords": [],
                    })
                    save_data(data)
                    st.success(f"'{n_name.strip()}' 추가 완료")
                    st.rerun()

# ════════════════════════════════════════════════════════════════════════════
# 탭3: 키워드 관리
# ════════════════════════════════════════════════════════════════════════════
with tab3:
    if not groups:
        st.info("그룹을 먼저 추가하세요.")
        st.stop()

    group_map = {g["name"]: g for g in groups}
    sel_name  = st.selectbox("그룹 선택", list(group_map.keys()), key="kw_grp")
    sel_g     = group_map[sel_name]
    kw_list   = sel_g.get("keywords", [])
    existing  = {k["keyword"] for k in kw_list}

    st.markdown(f"**{sel_name}** — 키워드 {len(kw_list)} / {MAX_KEYWORDS}개")

    # ── 방법 선택 ─────────────────────────────────────────────────────────────
    method = st.radio(
        "키워드 추가 방법",
        ["직접 입력", "네이버 광고그룹 불러오기"],
        horizontal=True,
        key="kw_method",
    )

    # ── 방법1: 직접 입력 ─────────────────────────────────────────────────────
    if method == "직접 입력":
        if len(kw_list) < MAX_KEYWORDS:
            kw_text = st.text_area(
                "키워드 입력 (줄바꿈으로 구분)",
                placeholder="이혼변호사\n이혼전문변호사\n위자료변호사",
                height=140,
                key="kw_direct_input",
            )
            if st.button("키워드 추가", type="primary", key="add_kw_direct"):
                new_kws = [
                    ln.strip() for ln in kw_text.splitlines()
                    if ln.strip() and ln.strip() not in existing
                ]
                slots   = MAX_KEYWORDS - len(kw_list)
                new_kws = new_kws[:slots]
                if not new_kws:
                    st.warning("추가할 새 키워드가 없습니다.")
                else:
                    for kw in new_kws:
                        sel_g["keywords"].append({
                            "keyword": kw, "current_rank": None,
                            "current_bid": None, "recommended_bid": None,
                            "status": "데이터 부족", "last_checked": None,
                        })
                    save_data(data)
                    st.success(f"{len(new_kws)}개 추가 완료")
                    st.rerun()
        else:
            st.warning(f"키워드 최대 {MAX_KEYWORDS}개 도달")

    # ── 방법2: 네이버 광고 API ────────────────────────────────────────────────
    else:
        st.markdown("#### 🔑 네이버 검색광고 API 연결")
        st.caption("네이버 광고 관리시스템 > 도구 > API 관리에서 발급한 정보를 입력하세요.")

        with st.expander("API 인증 정보 입력", expanded=True):
            c1, c2, c3 = st.columns(3)
            with c1:
                api_key = st.text_input(
                    "API Key (라이선스)",
                    value=st.session_state.get("naver_api_key",""),
                    type="password",
                    key="naver_api_key",
                    placeholder="발급된 API 라이선스 키",
                )
            with c2:
                secret_key = st.text_input(
                    "Secret Key",
                    value=st.session_state.get("naver_secret_key",""),
                    type="password",
                    key="naver_secret_key",
                    placeholder="비밀 키",
                )
            with c3:
                customer_id = st.text_input(
                    "고객 ID",
                    value=st.session_state.get("naver_customer_id",""),
                    key="naver_customer_id",
                    placeholder="숫자 고객 ID",
                )

        connected = all([api_key, secret_key, customer_id])

        if not connected:
            st.info("API 인증 정보를 모두 입력하면 캠페인을 불러올 수 있습니다.")
        else:
            # 캠페인 불러오기
            if st.button("📥 캠페인 불러오기", key="load_campaigns"):
                with st.spinner("캠페인 목록 조회 중..."):
                    try:
                        camps = naver_get_campaigns(api_key, secret_key, customer_id)
                        st.session_state["naver_campaigns"] = camps
                        st.success(f"캠페인 {len(camps)}개 로드됨")
                    except Exception as e:
                        st.error(f"API 오류: {e}")

            campaigns = st.session_state.get("naver_campaigns", [])

            if campaigns:
                st.markdown("#### 캠페인 선택")
                camp_opts = {
                    f"{c.get('name','(이름없음)')} [{c.get('campaignId','')}]": c
                    for c in campaigns
                }
                sel_camp_label = st.selectbox(
                    "캠페인",
                    list(camp_opts.keys()),
                    key="naver_sel_camp",
                )
                sel_camp = camp_opts[sel_camp_label]

                if st.button("📂 광고그룹 불러오기", key="load_adgroups"):
                    with st.spinner("광고그룹 목록 조회 중..."):
                        try:
                            adgroups = naver_get_adgroups(
                                api_key, secret_key, customer_id,
                                sel_camp.get("campaignId",""),
                            )
                            st.session_state["naver_adgroups"] = adgroups
                            st.success(f"광고그룹 {len(adgroups)}개 로드됨")
                        except Exception as e:
                            st.error(f"API 오류: {e}")

                adgroups = st.session_state.get("naver_adgroups", [])

                if adgroups:
                    st.markdown("#### 광고그룹 선택")
                    ag_opts = {
                        f"{a.get('name','(이름없음)')} [{a.get('adgroupId','')}]": a
                        for a in adgroups
                    }
                    sel_ag_label = st.selectbox(
                        "광고그룹",
                        list(ag_opts.keys()),
                        key="naver_sel_ag",
                    )
                    sel_ag = ag_opts[sel_ag_label]

                    if st.button("🔍 키워드 불러오기", key="load_kws"):
                        with st.spinner("키워드 목록 조회 중..."):
                            try:
                                kws = naver_get_keywords(
                                    api_key, secret_key, customer_id,
                                    sel_ag.get("adgroupId",""),
                                )
                                st.session_state["naver_keywords"] = kws
                                st.success(f"키워드 {len(kws)}개 로드됨")
                            except Exception as e:
                                st.error(f"API 오류: {e}")

                    nav_kws = st.session_state.get("naver_keywords", [])

                    if nav_kws:
                        st.markdown("#### 불러온 키워드")
                        # 키워드 텍스트 추출 (키 이름은 API 응답에 따라 다름)
                        kw_texts = [
                            k.get("keyword") or k.get("keywordText") or k.get("text","")
                            for k in nav_kws
                            if k.get("keyword") or k.get("keywordText") or k.get("text","")
                        ]
                        new_kws = [k for k in kw_texts if k not in existing]
                        new_kws = new_kws[:MAX_KEYWORDS - len(kw_list)]

                        st.markdown(
                            f"총 **{len(kw_texts)}개** 중 신규 **{len(new_kws)}개** "
                            f"(이미 등록: {len(kw_texts)-len(new_kws)}개)"
                        )
                        st.write(kw_texts[:20])  # 미리보기 최대 20개

                        if new_kws and len(kw_list) < MAX_KEYWORDS:
                            if st.button(
                                f"✅ 신규 {len(new_kws)}개 그룹에 추가",
                                type="primary", key="import_naver_kws",
                            ):
                                for kw in new_kws:
                                    sel_g["keywords"].append({
                                        "keyword": kw, "current_rank": None,
                                        "current_bid": None, "recommended_bid": None,
                                        "status": "데이터 부족", "last_checked": None,
                                    })
                                save_data(data)
                                st.session_state.pop("naver_keywords", None)
                                st.success(f"{len(new_kws)}개 추가 완료")
                                st.rerun()
                        elif not new_kws:
                            st.info("모든 키워드가 이미 등록되어 있습니다.")

    # ── 현재 키워드 목록 ──────────────────────────────────────────────────────
    st.divider()
    st.markdown(f"**현재 등록 키워드 ({len(kw_list)}개)**")

    if not kw_list:
        st.info("등록된 키워드가 없습니다.")
    else:
        del_check = {}
        cols = st.columns([3, 2, 2, 1])
        cols[0].markdown("**키워드**")
        cols[1].markdown("**현재입찰가**")
        cols[2].markdown("**상태**")
        cols[3].markdown("**삭제**")

        for kw_obj in kw_list:
            kw  = kw_obj["keyword"]
            rc, bc, sc, dc = st.columns([3, 2, 2, 1])
            rc.write(kw)
            bc.write(f"{kw_obj.get('current_bid','—'):,}" if kw_obj.get('current_bid') else "—")
            sc.write(
                STATUS_ICON.get(kw_obj.get("status","데이터 부족"),"⚪")
                + " " + kw_obj.get("status","데이터 부족")
            )
            del_check[kw] = dc.checkbox("", key=f"del_{sel_g['id']}_{kw}", label_visibility="collapsed")

        if st.button("선택 항목 삭제", key="del_kw_btn"):
            to_del = {k for k, v in del_check.items() if v}
            if not to_del:
                st.warning("삭제할 항목을 선택하세요.")
            else:
                sel_g["keywords"] = [k for k in kw_list if k["keyword"] not in to_del]
                save_data(data)
                st.success(f"{len(to_del)}개 삭제 완료")
                st.rerun()
