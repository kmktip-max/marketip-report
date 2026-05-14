import streamlit as st
import json
import os
import sys
import uuid
import pandas as pd
from datetime import datetime, date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# ── 경로 ─────────────────────────────────────────────────────────────────────
F_CLIENTS  = os.path.join(ROOT, "settlement_clients.json")
F_EXPENSES = os.path.join(ROOT, "other_expenses.json")
F_SPEND    = os.path.join(ROOT, "monthly_ad_spend.json")
F_EXTRA    = os.path.join(ROOT, "monthly_extra_revenue.json")

# ── 관리자 인증 ───────────────────────────────────────────────────────────────
def _get_admin_pw():
    try:
        if hasattr(st, "secrets") and "SETTLEMENT_ADMIN_PW" in st.secrets:
            return str(st.secrets["SETTLEMENT_ADMIN_PW"])
    except Exception:
        pass
    return os.getenv("SETTLEMENT_ADMIN_PW", "1471028690")

ADMIN_PW = _get_admin_pw()

def check_auth():
    if st.session_state.get("settlement_auth"):
        return True
    st.title("🔐 정산 관리 — 관리자 전용")
    pw = st.text_input("비밀번호", type="password", key="settlement_pw_input")
    if st.button("로그인", type="primary"):
        if pw == ADMIN_PW:
            st.session_state.settlement_auth = True
            st.rerun()
        else:
            st.error("비밀번호가 틀렸습니다.")
    return False

if not check_auth():
    st.stop()

# ── 스토리지 ──────────────────────────────────────────────────────────────────
def _load(path):
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return []

def _save(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_clients():  return _load(F_CLIENTS)
def save_clients(d): _save(F_CLIENTS, d)
def load_expenses():  return _load(F_EXPENSES)
def save_expenses(d): _save(F_EXPENSES, d)
def load_spend():  return _load(F_SPEND)
def save_spend(d): _save(F_SPEND, d)
def load_extra():  return _load(F_EXTRA)
def save_extra(d): _save(F_EXTRA, d)

def get_spend_for_month(ym):
    return {r["client_id"]: r["ad_spend"] for r in load_spend() if r["year_month"] == ym}

def set_spend(ym, client_id, amount):
    data = load_spend()
    for r in data:
        if r["year_month"] == ym and r["client_id"] == client_id:
            r["ad_spend"] = amount
            save_spend(data)
            return
    data.append({"year_month": ym, "client_id": client_id, "ad_spend": amount})
    save_spend(data)

def get_extra_for_month(ym):
    for r in load_extra():
        if r["year_month"] == ym:
            return r
    return {"year_month": ym, "place_revenue": 0, "blog_revenue": 0, "memo": ""}

def set_extra(ym, place, blog, memo=""):
    data = load_extra()
    for r in data:
        if r["year_month"] == ym:
            r.update({"place_revenue": place, "blog_revenue": blog, "memo": memo})
            save_extra(data)
            return
    data.append({"year_month": ym, "place_revenue": place, "blog_revenue": blog, "memo": memo})
    save_extra(data)

def get_expenses_for_month(ym):
    return [e for e in load_expenses() if e["year_month"] == ym]

# ── 정산 계산 ─────────────────────────────────────────────────────────────────
def calc(client, ad_spend):
    cr   = client.get("commission_rate", 0) / 100
    fbr  = client.get("freelancer_base_rate", 0) / 100
    rr   = client.get("rebate_rate", 0) / 100
    commission = ad_spend * cr
    rebate_payout = ad_spend * rr
    is_direct = client.get("is_direct", False)
    if is_direct or not client.get("freelancer", "").strip():
        fer = 0.0
        fl_payout = 0.0
        rep_revenue = commission - rebate_payout
    else:
        fer = fbr - rr
        fl_payout = ad_spend * max(fer, 0)
        rep_revenue = commission - fl_payout - rebate_payout
    return {
        "commission":             round(commission),
        "freelancer_effective_rate": round(fer * 100, 2),
        "freelancer_payout":      round(fl_payout),
        "rebate_payout":          round(rebate_payout),
        "rep_revenue":            round(rep_revenue),
        "warning":                fer < 0,
    }

# ── UI ───────────────────────────────────────────────────────────────────────
st.title("📊 정산 관리")
c1, c2 = st.columns([5, 1])
with c2:
    if st.button("로그아웃", key="settle_logout"):
        st.session_state.settlement_auth = False
        st.rerun()

tab0, tab1, tab2, tab3 = st.tabs(["⚙️ 광고주 설정", "📋 정산표", "💰 기타비용", "📈 월 손익"])

# ═══════════════════════════════════════════════════════════════
# TAB 0: 광고주 설정
# ═══════════════════════════════════════════════════════════════
with tab0:
    st.subheader("광고주 / 프리랜서 설정")
    clients = load_clients()

    with st.form("add_client_form", clear_on_submit=True):
        st.markdown("**새 업체 추가**")
        c1, c2, c3 = st.columns(3)
        with c1:
            new_name = st.text_input("업체명 *")
            new_fl   = st.text_input("담당 프리랜서 (없으면 비워두기)")
        with c2:
            new_cr  = st.number_input("상위대행사 수수료율 (%)", 0.0, 100.0, 15.0, step=0.5)
            new_fbr = st.number_input("프리랜서 기본 정산율 (%)", 0.0, 100.0, 12.0, step=0.5)
        with c3:
            new_rr     = st.number_input("광고주 리베이트율 (%)", 0.0, 100.0, 0.0, step=0.5)
            new_direct = st.checkbox("대표 직접 운영 계정")
            new_memo   = st.text_input("메모")

        if st.form_submit_button("➕ 추가", type="primary"):
            if not new_name:
                st.error("업체명을 입력하세요.")
            else:
                clients.append({
                    "id": str(uuid.uuid4()),
                    "name": new_name.strip(),
                    "freelancer": new_fl.strip(),
                    "commission_rate": new_cr,
                    "freelancer_base_rate": new_fbr,
                    "rebate_rate": new_rr,
                    "is_direct": new_direct,
                    "memo": new_memo.strip(),
                    "created_at": date.today().isoformat(),
                })
                save_clients(clients)
                st.success(f"✅ {new_name} 추가 완료")
                st.rerun()

    st.divider()
    if not clients:
        st.info("등록된 업체가 없습니다.")
    else:
        for i, c in enumerate(clients):
            with st.expander(f"**{c['name']}** | {c.get('freelancer','대표 직접') or '대표 직접'} | "
                             f"수수료 {c['commission_rate']}% | 정산 {c['freelancer_base_rate']}% | 리베이트 {c['rebate_rate']}%"):
                cc1, cc2, cc3, cc4 = st.columns([2,2,2,1])
                with cc1:
                    v_name = st.text_input("업체명", c["name"],       key=f"name_{i}")
                    v_fl   = st.text_input("프리랜서", c.get("freelancer",""), key=f"fl_{i}")
                with cc2:
                    v_cr  = st.number_input("수수료율(%)",    value=float(c["commission_rate"]),       key=f"cr_{i}", step=0.5)
                    v_fbr = st.number_input("프리랜서 정산율(%)", value=float(c["freelancer_base_rate"]), key=f"fbr_{i}", step=0.5)
                with cc3:
                    v_rr     = st.number_input("리베이트율(%)", value=float(c["rebate_rate"]), key=f"rr_{i}", step=0.5)
                    v_direct = st.checkbox("대표 직접 운영", c.get("is_direct", False), key=f"dir_{i}")
                    v_memo   = st.text_input("메모", c.get("memo",""), key=f"memo_{i}")
                with cc4:
                    if st.button("저장", key=f"save_{i}"):
                        clients[i].update({
                            "name": v_name, "freelancer": v_fl,
                            "commission_rate": v_cr, "freelancer_base_rate": v_fbr,
                            "rebate_rate": v_rr, "is_direct": v_direct, "memo": v_memo,
                        })
                        save_clients(clients)
                        st.toast("✅ 저장됨")
                        st.rerun()
                    if st.button("🗑️ 삭제", key=f"del_{i}"):
                        clients.pop(i)
                        save_clients(clients)
                        st.rerun()

# ═══════════════════════════════════════════════════════════════
# TAB 1: 정산표
# ═══════════════════════════════════════════════════════════════
with tab1:
    st.subheader("월별 정산표")
    clients = load_clients()
    if not clients:
        st.warning("광고주 설정 탭에서 업체를 먼저 등록해주세요.")
    else:
        sel_ym = st.selectbox(
            "정산 월 선택",
            [f"{y}-{m:02d}" for y in range(2025, 2028) for m in range(1, 13)],
            index=None, placeholder="YYYY-MM 선택...", key="settle_ym"
        )
        if sel_ym:
            spend_map = get_spend_for_month(sel_ym)
            rows = []
            warnings = []

            st.markdown("**광고비 공급가 입력 (VAT 제외)**")
            with st.form(f"spend_form_{sel_ym}"):
                cols = st.columns(min(len(clients), 4))
                spend_inputs = {}
                for idx, c in enumerate(clients):
                    with cols[idx % 4]:
                        spend_inputs[c["id"]] = st.number_input(
                            c["name"],
                            value=float(spend_map.get(c["id"], 0)),
                            step=10000.0, format="%.0f",
                            key=f"spend_{c['id']}_{sel_ym}"
                        )
                if st.form_submit_button("💾 저장", type="primary"):
                    for cid, amt in spend_inputs.items():
                        set_spend(sel_ym, cid, int(amt))
                    st.toast("✅ 저장됨")
                    st.rerun()

            st.divider()
            # 계산
            for c in clients:
                ad_spend = spend_map.get(c["id"], 0)
                r = calc(c, ad_spend)
                if r["warning"]:
                    warnings.append(f"⚠️ **{c['name']}**: 프리랜서 실지급 정산율이 음수입니다! "
                                    f"(리베이트 {c['rebate_rate']}% > 정산율 {c['freelancer_base_rate']}%)")
                rows.append({
                    "업체명":              c["name"],
                    "담당 프리랜서":        c.get("freelancer","") or "대표 직접",
                    "광고비 공급가":        ad_spend,
                    "수수료율(%)":         c["commission_rate"],
                    "수수료 공급가":        r["commission"],
                    "프리랜서 기본 정산율(%)": c.get("freelancer_base_rate", 0) if not c.get("is_direct") else "-",
                    "광고주 리베이트율(%)":  c.get("rebate_rate", 0),
                    "프리랜서 실지급 정산율(%)": r["freelancer_effective_rate"] if not c.get("is_direct") else "-",
                    "프리랜서 지급액":       r["freelancer_payout"],
                    "광고주 리베이트 지급액": r["rebate_payout"],
                    "대표 수익":            r["rep_revenue"],
                })

            for w in warnings:
                st.warning(w)

            df = pd.DataFrame(rows)
            totals = {
                "업체명": "합계", "담당 프리랜서": "",
                "광고비 공급가": df["광고비 공급가"].sum(),
                "수수료율(%)": "", "수수료 공급가": df["수수료 공급가"].sum(),
                "프리랜서 기본 정산율(%)": "", "광고주 리베이트율(%)": "",
                "프리랜서 실지급 정산율(%)": "",
                "프리랜서 지급액": df["프리랜서 지급액"].sum(),
                "광고주 리베이트 지급액": df["광고주 리베이트 지급액"].sum(),
                "대표 수익": df["대표 수익"].sum(),
            }
            df_display = pd.concat([df, pd.DataFrame([totals])], ignore_index=True)
            st.dataframe(df_display, use_container_width=True, hide_index=True)

            # CSV 다운로드
            st.download_button(
                "📥 CSV 다운로드",
                df_display.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig"),
                file_name=f"정산표_{sel_ym}.csv",
                mime="text/csv",
            )

# ═══════════════════════════════════════════════════════════════
# TAB 2: 기타비용
# ═══════════════════════════════════════════════════════════════
with tab2:
    st.subheader("기타비용 관리")
    exp_ym = st.selectbox(
        "월 선택",
        [f"{y}-{m:02d}" for y in range(2025, 2028) for m in range(1, 13)],
        index=None, placeholder="YYYY-MM...", key="exp_ym"
    )

    if exp_ym:
        with st.form("add_expense", clear_on_submit=True):
            ec1, ec2, ec3 = st.columns([2, 2, 3])
            with ec1: exp_name = st.text_input("비용명 *", placeholder="세무비")
            with ec2: exp_amt  = st.number_input("금액 (원)", 0, step=1000)
            with ec3: exp_memo = st.text_input("메모")
            if st.form_submit_button("➕ 추가"):
                if not exp_name:
                    st.error("비용명을 입력하세요.")
                else:
                    exps = load_expenses()
                    exps.append({
                        "id": str(uuid.uuid4()),
                        "year_month": exp_ym,
                        "name": exp_name.strip(),
                        "amount": int(exp_amt),
                        "memo": exp_memo.strip(),
                        "created_at": date.today().isoformat(),
                    })
                    save_expenses(exps)
                    st.rerun()

        month_exps = get_expenses_for_month(exp_ym)
        if month_exps:
            all_exps = load_expenses()
            for e in month_exps:
                ec1, ec2, ec3, ec4, ec5 = st.columns([2, 2, 3, 1, 1])
                ec1.markdown(f"**{e['name']}**")
                new_amt  = ec2.number_input("금액", value=e["amount"], step=1000, key=f"ea_{e['id']}", label_visibility="collapsed")
                new_memo = ec3.text_input("메모", value=e.get("memo",""), key=f"em_{e['id']}", label_visibility="collapsed")
                if ec4.button("저장", key=f"esave_{e['id']}"):
                    for x in all_exps:
                        if x["id"] == e["id"]:
                            x["amount"] = int(new_amt)
                            x["memo"] = new_memo
                    save_expenses(all_exps)
                    st.rerun()
                if ec5.button("🗑️", key=f"edel_{e['id']}"):
                    save_expenses([x for x in all_exps if x["id"] != e["id"]])
                    st.rerun()

            st.divider()
            total_exp = sum(e["amount"] for e in month_exps)
            st.metric(f"{exp_ym} 기타비용 합계", f"{total_exp:,}원")
        else:
            st.info("이 달의 기타비용이 없습니다.")

# ═══════════════════════════════════════════════════════════════
# TAB 3: 월 손익
# ═══════════════════════════════════════════════════════════════
with tab3:
    st.subheader("월별 손익 현황")
    pnl_ym = st.selectbox(
        "월 선택",
        [f"{y}-{m:02d}" for y in range(2025, 2028) for m in range(1, 13)],
        index=None, placeholder="YYYY-MM...", key="pnl_ym"
    )

    if pnl_ym:
        clients    = load_clients()
        spend_map  = get_spend_for_month(pnl_ym)
        month_exps = get_expenses_for_month(pnl_ym)
        extra      = get_extra_for_month(pnl_ym)

        # 검색광고 대표 수익 합산
        search_rep = sum(calc(c, spend_map.get(c["id"], 0))["rep_revenue"] for c in clients)
        total_exp  = sum(e["amount"] for e in month_exps)

        st.markdown("**기타 수익 입력**")
        with st.form("extra_revenue_form"):
            xc1, xc2, xc3 = st.columns(3)
            with xc1: place = st.number_input("플레이스 수익 (원)", value=float(extra["place_revenue"]), step=10000.0)
            with xc2: blog  = st.number_input("블로그 수익 (원)",   value=float(extra["blog_revenue"]),  step=10000.0)
            with xc3: x_memo = st.text_input("메모", value=extra.get("memo",""))
            if st.form_submit_button("💾 저장"):
                set_extra(pnl_ym, int(place), int(blog), x_memo)
                st.rerun()

        place_rev = extra["place_revenue"]
        blog_rev  = extra["blog_revenue"]
        net = search_rep + place_rev + blog_rev - total_exp

        st.divider()
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("검색광고 대표 수익",  f"{search_rep:,}원")
        c2.metric("플레이스 수익",        f"{place_rev:,}원")
        c3.metric("블로그 수익",          f"{blog_rev:,}원")
        c4.metric("기타비용 합계",        f"{total_exp:,}원", delta=f"-{total_exp:,}")
        c5.metric("**월 최종 순수익**",   f"{net:,}원",
                  delta=f"{'▲' if net>=0 else '▼'}{abs(net):,}")

        st.divider()
        st.markdown("**기타비용 내역**")
        if month_exps:
            st.dataframe(pd.DataFrame(month_exps)[["name","amount","memo"]]
                         .rename(columns={"name":"비용명","amount":"금액","memo":"메모"}),
                         use_container_width=True, hide_index=True)
        else:
            st.info("이 달의 기타비용이 없습니다.")

        st.markdown("**검색광고 정산 내역**")
        if clients:
            rows = []
            for c in clients:
                ad_spend = spend_map.get(c["id"], 0)
                r = calc(c, ad_spend)
                rows.append({"업체명": c["name"], "광고비": ad_spend,
                             "수수료": r["commission"], "대표 수익": r["rep_revenue"]})
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
