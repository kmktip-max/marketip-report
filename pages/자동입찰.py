"""광고 운영 — 목표순위 자동입찰 보조 시스템"""
import streamlit as st
import os
import sys
import uuid
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from db import sb_load, sb_save

# ── 인증 확인 ─────────────────────────────────────────────────────────────────
auth_type = st.session_state.get("auth_type", "")
auth_username = st.session_state.get("auth_username", "")

if auth_type not in ("admin", "client"):
    st.error("🔒 로그인이 필요합니다.")
    st.stop()

# ── 클라이언트 ID 결정 ────────────────────────────────────────────────────────
def _load_client_accounts():
    fallback = os.path.join(ROOT, "client_accounts.json")
    raw = sb_load("client_accounts", fallback)
    return raw if isinstance(raw, list) else []

if auth_type == "admin":
    accounts = _load_client_accounts()
    client_options = ["admin"] + [a.get("username", "") for a in accounts if a.get("username")]
    selected_client = st.selectbox(
        "클라이언트 선택",
        options=client_options,
        format_func=lambda x: f"[관리자] {x}" if x == "admin" else x,
        key="bid_selected_client",
    )
    client_id = selected_client
else:
    client_id = auth_username

FALLBACK_JSON = os.path.join(ROOT, f"bidding_{client_id}.json")
SB_KEY = f"bidding_{client_id}"

MAX_GROUPS = 5
MAX_KEYWORDS = 30

# ── 데이터 로드/저장 ──────────────────────────────────────────────────────────
def load_data():
    raw = sb_load(SB_KEY, FALLBACK_JSON)
    if isinstance(raw, dict) and "groups" in raw:
        return raw
    return {"groups": []}

def save_data(data):
    sb_save(SB_KEY, data, FALLBACK_JSON)

# ── 입찰 계산 ─────────────────────────────────────────────────────────────────
def calc_bid(current_rank, target_rank, current_bid, bid_unit, min_bid, max_bid):
    MAX_SINGLE = 500
    if current_rank is None or current_bid is None:
        return current_bid, "데이터 부족"
    diff = current_rank - target_rank
    if diff > 0.5:
        delta = min(bid_unit, MAX_SINGLE)
        new_bid = min(current_bid + delta, max_bid)
        status = "최대입찰 도달" if new_bid >= max_bid else "증액중"
    elif diff < -0.5:
        delta = min(bid_unit // 2 or bid_unit, MAX_SINGLE)
        new_bid = max(current_bid - delta, min_bid)
        status = "최소입찰 도달" if new_bid <= min_bid else "감액중"
    else:
        new_bid = current_bid
        status = "유지"
    new_bid = round(new_bid / 10) * 10
    return new_bid, status

STATUS_ICON = {
    "증액중":      "🔴",
    "감액중":      "🔵",
    "유지":        "🟢",
    "데이터 부족": "⚪",
    "최대입찰 도달": "🟠",
    "최소입찰 도달": "🟡",
}

# ── UI ────────────────────────────────────────────────────────────────────────
st.title("📊 목표순위 자동입찰")
st.caption("목표순위 근접 유지를 위한 입찰가 조정 보조 시스템입니다.")

data = load_data()
groups = data.get("groups", [])

tab1, tab2, tab3 = st.tabs(["입찰 현황", "그룹 관리", "키워드 관리"])

# ════════════════════════════════════════════════════════════════════════════════
# 탭1: 입찰 현황
# ════════════════════════════════════════════════════════════════════════════════
with tab1:
    if not groups:
        st.info("등록된 그룹이 없습니다. [그룹 관리] 탭에서 그룹을 추가하세요.")
    else:
        rows = []
        for g in groups:
            for kw in g.get("keywords", []):
                rows.append({
                    "_group_id":    g["id"],
                    "_kw_keyword":  kw["keyword"],
                    "그룹명":       g["name"],
                    "키워드":       kw["keyword"],
                    "현재순위":     kw.get("current_rank"),
                    "목표순위":     g["target_rank"],
                    "현재입찰가":   kw.get("current_bid"),
                    "추천입찰가":   kw.get("recommended_bid"),
                    "상태":         STATUS_ICON.get(kw.get("status", "데이터 부족"), "⚪") + " " + kw.get("status", "데이터 부족"),
                    "마지막체크":   kw.get("last_checked", ""),
                })

        import pandas as pd

        df = pd.DataFrame(rows)
        hidden_cols = ["_group_id", "_kw_keyword"]

        display_df = df.drop(columns=hidden_cols)

        column_config = {
            "그룹명":     st.column_config.TextColumn("그룹명",     disabled=True),
            "키워드":     st.column_config.TextColumn("키워드",     disabled=True),
            "현재순위":   st.column_config.NumberColumn("현재순위", format="%.1f"),
            "목표순위":   st.column_config.NumberColumn("목표순위", disabled=True),
            "현재입찰가": st.column_config.NumberColumn("현재입찰가", format="%d"),
            "추천입찰가": st.column_config.NumberColumn("추천입찰가", disabled=True, format="%d"),
            "상태":       st.column_config.TextColumn("상태",       disabled=True),
            "마지막체크": st.column_config.TextColumn("마지막체크", disabled=True),
        }

        edited = st.data_editor(
            display_df,
            column_config=column_config,
            use_container_width=True,
            hide_index=True,
            key="bid_table_editor",
            num_rows="fixed",
        )

        # 상태 범례
        st.markdown(
            "**상태 범례:** "
            "🔴 증액중 &nbsp; 🔵 감액중 &nbsp; 🟢 유지 &nbsp; "
            "⚪ 데이터 부족 &nbsp; 🟠 최대입찰 도달 &nbsp; 🟡 최소입찰 도달",
            unsafe_allow_html=True,
        )

        col_calc, col_apply = st.columns(2)

        with col_calc:
            if st.button("🔄 입찰가 계산", use_container_width=True):
                now_str = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
                edited_rows = edited.to_dict(orient="records")
                for i, row in enumerate(edited_rows):
                    orig_group_id = df.iloc[i]["_group_id"]
                    orig_kw       = df.iloc[i]["_kw_keyword"]
                    g = next((g for g in groups if g["id"] == orig_group_id), None)
                    if g is None:
                        continue
                    kw_obj = next((k for k in g["keywords"] if k["keyword"] == orig_kw), None)
                    if kw_obj is None:
                        continue
                    kw_obj["current_rank"] = row.get("현재순위")
                    kw_obj["current_bid"]  = int(row["현재입찰가"]) if row.get("현재입찰가") is not None else None
                    new_bid, status = calc_bid(
                        kw_obj.get("current_rank"),
                        g["target_rank"],
                        kw_obj.get("current_bid"),
                        g["bid_unit"],
                        g["min_bid"],
                        g["max_bid"],
                    )
                    kw_obj["recommended_bid"] = new_bid
                    kw_obj["status"]          = status
                    kw_obj["last_checked"]    = now_str
                data["groups"] = groups
                save_data(data)
                st.success("입찰가 계산 완료.")
                st.rerun()

        with col_apply:
            if st.button("✅ 추천가 적용", use_container_width=True):
                for g in groups:
                    for kw_obj in g.get("keywords", []):
                        if kw_obj.get("recommended_bid") is not None:
                            kw_obj["current_bid"] = kw_obj["recommended_bid"]
                data["groups"] = groups
                save_data(data)
                st.success("추천입찰가를 현재입찰가로 적용했습니다.")
                st.rerun()

# ════════════════════════════════════════════════════════════════════════════════
# 탭2: 그룹 관리
# ════════════════════════════════════════════════════════════════════════════════
with tab2:
    st.subheader("그룹 목록")

    if not groups:
        st.info("등록된 그룹이 없습니다.")
    else:
        for g in groups[:]:
            with st.expander(f"**{g['name']}** — 목표순위 {g['target_rank']}위", expanded=False):
                with st.form(key=f"edit_group_{g['id']}"):
                    g_name    = st.text_input("그룹명",       value=g["name"],            key=f"g_name_{g['id']}")
                    g_rank    = st.number_input("목표순위",    value=g["target_rank"],     min_value=1, max_value=15, key=f"g_rank_{g['id']}")
                    g_min     = st.number_input("최소입찰가",  value=g["min_bid"],         min_value=10, step=10,     key=f"g_min_{g['id']}")
                    g_max     = st.number_input("최대입찰가",  value=g["max_bid"],         min_value=10, step=10,     key=f"g_max_{g['id']}")
                    g_unit    = st.number_input("증감단위(원)",value=g["bid_unit"],        min_value=10, step=10,     key=f"g_unit_{g['id']}")
                    g_interval= st.number_input("체크주기(분)",value=g["check_interval"],  min_value=1,              key=f"g_int_{g['id']}")
                    g_auto    = st.checkbox("자동적용",        value=g.get("auto_apply", False),                     key=f"g_auto_{g['id']}")

                    col_save, col_del = st.columns(2)
                    with col_save:
                        if st.form_submit_button("수정", use_container_width=True):
                            if not g_name.strip():
                                st.error("그룹명을 입력하세요.")
                            elif g_min >= g_max:
                                st.error("최소입찰가는 최대입찰가보다 작아야 합니다.")
                            else:
                                g["name"]           = g_name.strip()
                                g["target_rank"]    = int(g_rank)
                                g["min_bid"]        = int(g_min)
                                g["max_bid"]        = int(g_max)
                                g["bid_unit"]       = int(g_unit)
                                g["check_interval"] = int(g_interval)
                                g["auto_apply"]     = g_auto
                                save_data(data)
                                st.success("그룹이 수정되었습니다.")
                                st.rerun()
                    with col_del:
                        if st.form_submit_button("삭제", use_container_width=True, type="secondary"):
                            data["groups"] = [x for x in groups if x["id"] != g["id"]]
                            save_data(data)
                            st.success("그룹이 삭제되었습니다.")
                            st.rerun()

    st.divider()
    st.subheader("새 그룹 추가")

    if len(groups) >= MAX_GROUPS:
        st.warning(f"그룹은 최대 {MAX_GROUPS}개까지 등록 가능합니다.")
    else:
        with st.form("add_group_form", clear_on_submit=True):
            new_name     = st.text_input("그룹명 *",       placeholder="예: 이혼메인")
            new_rank     = st.number_input("목표순위",      value=3,     min_value=1, max_value=15)
            new_min      = st.number_input("최소입찰가",    value=10000, min_value=10, step=10)
            new_max      = st.number_input("최대입찰가",    value=35000, min_value=10, step=10)
            new_unit     = st.number_input("증감단위(원)",  value=100,   min_value=10, step=10)
            new_interval = st.number_input("체크주기(분)",  value=15,    min_value=1)
            new_auto     = st.checkbox("자동적용",          value=False)

            if st.form_submit_button("그룹 추가", type="primary", use_container_width=True):
                if not new_name.strip():
                    st.error("그룹명을 입력하세요.")
                elif new_min >= new_max:
                    st.error("최소입찰가는 최대입찰가보다 작아야 합니다.")
                else:
                    new_group = {
                        "id":             str(uuid.uuid4()),
                        "name":           new_name.strip(),
                        "target_rank":    int(new_rank),
                        "min_bid":        int(new_min),
                        "max_bid":        int(new_max),
                        "bid_unit":       int(new_unit),
                        "check_interval": int(new_interval),
                        "auto_apply":     new_auto,
                        "keywords":       [],
                    }
                    data["groups"].append(new_group)
                    save_data(data)
                    st.success(f"그룹 '{new_name.strip()}' 추가 완료.")
                    st.rerun()

# ════════════════════════════════════════════════════════════════════════════════
# 탭3: 키워드 관리
# ════════════════════════════════════════════════════════════════════════════════
with tab3:
    if not groups:
        st.info("그룹을 먼저 추가하세요.")
    else:
        group_names  = [g["name"] for g in groups]
        sel_g_name   = st.selectbox("그룹 선택", options=group_names, key="kw_mgmt_group")
        sel_group    = next((g for g in groups if g["name"] == sel_g_name), None)

        if sel_group:
            kw_list = sel_group.get("keywords", [])
            st.markdown(f"**키워드 수:** {len(kw_list)} / {MAX_KEYWORDS}")

            if kw_list:
                st.markdown("**키워드 목록**")
                del_flags = {}
                for kw_obj in kw_list:
                    kw = kw_obj["keyword"]
                    del_flags[kw] = st.checkbox(kw, key=f"del_kw_{sel_group['id']}_{kw}")

                if st.button("선택 삭제", key="del_kw_btn"):
                    to_del = {k for k, v in del_flags.items() if v}
                    if not to_del:
                        st.warning("삭제할 키워드를 선택하세요.")
                    else:
                        sel_group["keywords"] = [k for k in kw_list if k["keyword"] not in to_del]
                        save_data(data)
                        st.success(f"{len(to_del)}개 키워드 삭제 완료.")
                        st.rerun()
            else:
                st.info("등록된 키워드가 없습니다.")

            st.divider()
            st.markdown("**키워드 추가** (줄바꿈으로 구분)")

            if len(kw_list) >= MAX_KEYWORDS:
                st.warning(f"키워드는 그룹당 최대 {MAX_KEYWORDS}개까지 등록 가능합니다.")
            else:
                new_kw_text = st.text_area(
                    "키워드 입력",
                    placeholder="이혼변호사\n위자료변호사\n재산분할변호사",
                    height=120,
                    key="new_kw_area",
                )
                if st.button("키워드 추가", key="add_kw_btn", type="primary"):
                    existing = {k["keyword"] for k in kw_list}
                    new_kws  = [
                        line.strip()
                        for line in new_kw_text.splitlines()
                        if line.strip() and line.strip() not in existing
                    ]
                    slots = MAX_KEYWORDS - len(kw_list)
                    new_kws = new_kws[:slots]
                    if not new_kws:
                        st.warning("추가할 키워드가 없거나 이미 등록된 키워드입니다.")
                    else:
                        for kw in new_kws:
                            sel_group["keywords"].append({
                                "keyword":          kw,
                                "current_rank":     None,
                                "current_bid":      None,
                                "recommended_bid":  None,
                                "status":           "데이터 부족",
                                "last_checked":     None,
                            })
                        save_data(data)
                        st.success(f"{len(new_kws)}개 키워드 추가 완료.")
                        st.rerun()

                if len(kw_list) + len(new_kw_text.splitlines() if new_kw_text else []) > MAX_KEYWORDS:
                    st.warning(f"키워드 최대 {MAX_KEYWORDS}개 제한 초과. 일부만 추가됩니다.")
