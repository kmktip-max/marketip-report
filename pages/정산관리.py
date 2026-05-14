import streamlit as st
import json, os, sys, uuid
import pandas as pd
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# ── 상수 ─────────────────────────────────────────────────────────────────────
FREELANCERS = [
    "미분류", "권혁우", "최은성", "조성지", "임예솔", "홍선기",
    "안주희", "이승준", "문성빈", "김하린", "김주훈", "대표 직접",
]

# ── 경로 ─────────────────────────────────────────────────────────────────────
F_MAPPING  = os.path.join(ROOT, "freelancer_mapping.json")
F_EXPENSES = os.path.join(ROOT, "other_expenses.json")
F_EXTRA    = os.path.join(ROOT, "monthly_extra_revenue.json")

# ── 관리자 인증 ───────────────────────────────────────────────────────────────
def _get_admin_pw():
    try:
        if hasattr(st, "secrets") and "SETTLEMENT_ADMIN_PW" in st.secrets:
            return str(st.secrets["SETTLEMENT_ADMIN_PW"])
    except Exception:
        pass
    return os.getenv("SETTLEMENT_ADMIN_PW", "1471028690")

if not st.session_state.get("settlement_auth"):
    st.title("🔐 정산 관리 — 관리자 전용")
    pw = st.text_input("비밀번호", type="password")
    if st.button("로그인", type="primary"):
        if pw == _get_admin_pw():
            st.session_state.settlement_auth = True
            st.rerun()
        else:
            st.error("비밀번호가 틀렸습니다.")
    st.stop()

# ── 스토리지 ──────────────────────────────────────────────────────────────────
def _load(p):
    try:
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return []

def _save(p, d):
    with open(p, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)

load_mapping  = lambda: _load(F_MAPPING)
save_mapping  = lambda d: _save(F_MAPPING, d)
load_expenses = lambda: _load(F_EXPENSES)
save_expenses = lambda d: _save(F_EXPENSES, d)
load_extra    = lambda: _load(F_EXTRA)
save_extra    = lambda d: _save(F_EXTRA, d)

def get_mapping(cid, ano, name=""):
    for m in load_mapping():
        if str(m.get("customer_id","")) == str(cid) and str(m.get("ad_account_no","")) == str(ano):
            return m
    if name:
        for m in load_mapping():
            if m.get("account_name","") == name:
                return m
    return None

def upsert_mapping(cid, ano, name, fl, fr, rr, is_own):
    data = load_mapping()
    for m in data:
        if str(m.get("customer_id","")) == str(cid) and str(m.get("ad_account_no","")) == str(ano):
            m.update({"account_name": name, "freelancer": fl,
                      "freelancer_rate": fr, "rebate_rate": rr, "is_owner_managed": is_own})
            save_mapping(data)
            return
    data.append({"customer_id": str(cid), "ad_account_no": str(ano), "account_name": name,
                 "freelancer": fl, "freelancer_rate": fr, "rebate_rate": rr, "is_owner_managed": is_own})
    save_mapping(data)

def get_expenses_for_month(ym):
    return [e for e in load_expenses() if e["year_month"] == ym]

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
            save_extra(data); return
    data.append({"year_month": ym, "place_revenue": place, "blog_revenue": blog, "memo": memo})
    save_extra(data)

# ── 엑셀 파싱 ─────────────────────────────────────────────────────────────────
ALIAS = {
    "매체사":         ["매체사","매체","Media"],
    "계정명":         ["계정명","광고주명","Account Name"],
    "customer_id":   ["CustomerID","Customer ID","계정번호 CustomerID","고객ID","customer_id"],
    "ad_account_no": ["AdAccountNo","Ad Account No","계정번호 AdAccountNo","광고계정번호"],
    "ad_supply":     ["광고비 공급가","광고비공급가","공급가액"],
    "ad_vat":        ["광고비 세액","광고비세액"],
    "ad_total":      ["광고비 합계금액","광고비합계금액","광고비합계"],
    "comm_rate":     ["수수료율","수수료율(%)"],
    "comm_supply":   ["수수료 공급가","수수료공급가"],
    "comm_vat":      ["수수료 세액","수수료세액"],
    "comm_total":    ["수수료 합계금액","수수료합계금액","수수료합계"],
}

def _find_col(df_cols, aliases):
    norm = lambda s: str(s).strip().replace(" ","").lower()
    for a in aliases:
        for c in df_cols:
            if norm(c) == norm(a): return c
    for a in aliases:
        for c in df_cols:
            if norm(a) in norm(c): return c
    return None

def parse_excel(f):
    try:
        df_raw = pd.read_excel(f, header=2, engine="openpyxl")
    except Exception:
        try:
            df_raw = pd.read_csv(f, header=2, encoding="utf-8-sig")
        except Exception as e:
            return None, str(e), None

    col_map = {k: _find_col(df_raw.columns.tolist(), v) for k, v in ALIAS.items()}
    name_col = col_map.get("계정명")
    if not name_col:
        return None, "계정명 컬럼을 찾을 수 없습니다.", df_raw

    df = df_raw[df_raw[name_col].notna()].copy()
    df = df[~df[name_col].astype(str).str.contains("합계|소계|TOTAL|합 계", regex=True, na=False)]
    df = df[df[name_col].astype(str).str.strip() != ""]

    df = df.rename(columns={v: k for k, v in col_map.items() if v})

    for nc in ["ad_supply","ad_vat","ad_total","comm_supply","comm_vat","comm_total"]:
        if nc in df.columns:
            df[nc] = pd.to_numeric(
                df[nc].astype(str).str.replace(",","").str.replace("원","").str.strip(),
                errors="coerce").fillna(0)
    for ic in ["customer_id","ad_account_no"]:
        if ic in df.columns:
            df[ic] = df[ic].astype(str).str.strip().str.replace(r"\.0$","",regex=True)

    num_cols  = [c for c in ["ad_supply","ad_vat","ad_total","comm_supply","comm_vat","comm_total"] if c in df.columns]
    first_cols = [c for c in ["comm_rate","계정명","매체사"] if c in df.columns]

    if "customer_id" in df.columns and "ad_account_no" in df.columns:
        agg = {c: "sum" for c in num_cols}
        agg.update({c: "first" for c in first_cols if c not in ["customer_id","ad_account_no"]})
        df_g = df.groupby(["customer_id","ad_account_no"], as_index=False).agg(agg)
    else:
        agg = {c: "sum" for c in num_cols}
        agg.update({c: "first" for c in first_cols if c != "계정명"})
        df_g = df.groupby(["계정명"], as_index=False).agg(agg)

    return df_g, None, df_raw

# ── 정산 계산 ─────────────────────────────────────────────────────────────────
def calc_from_ad(ad_supply, comm_supply, freelancer_rate, rebate_rate, is_owner):
    fr = freelancer_rate / 100
    rr = rebate_rate / 100
    rebate_payout = round(ad_supply * rr)
    if is_owner:
        return {"effective_rate": 0.0, "fl_payout": 0,
                "rebate_payout": rebate_payout,
                "rep_revenue": round(comm_supply - rebate_payout),
                "warning": False}
    effective = fr - rr
    fl_payout = round(ad_supply * max(effective, 0))
    return {"effective_rate": round(effective * 100, 2),
            "fl_payout": fl_payout, "rebate_payout": rebate_payout,
            "rep_revenue": round(comm_supply - fl_payout - rebate_payout),
            "warning": effective < 0}

# ── 헤더 ──────────────────────────────────────────────────────────────────────
hc1, hc2 = st.columns([5, 1])
with hc1:
    st.title("📊 정산 관리")
with hc2:
    st.write("")
    if st.button("로그아웃"):
        for k in ["settlement_auth","uploaded_df","upload_ym"]:
            st.session_state.pop(k, None)
        st.rerun()

YM_LIST = [f"{y}-{m:02d}" for y in range(2025, 2028) for m in range(1, 13)]
sel_ym = st.selectbox("📅 정산 월", YM_LIST, index=None,
                       placeholder="YYYY-MM 선택...", key="main_ym")
st.divider()

t_up, t_cl, t_un, t_fl, t_ex, t_pnl = st.tabs([
    "📤 엑셀 업로드", "🏢 업체 분류", "❓ 미분류",
    "👤 프리랜서 정산", "💰 기타비용", "📈 월 손익",
])

# ═══════════════════════════════════════════════════════════════
# 탭: 엑셀 업로드
# ═══════════════════════════════════════════════════════════════
with t_up:
    st.subheader("상위대행사 정산 엑셀 업로드")
    st.caption("3행이 헤더인 xlsx/csv 파일을 업로드하세요.")
    f = st.file_uploader("파일 선택", type=["xlsx","xls","csv"])
    if f:
        df_g, err, df_raw = parse_excel(f)
        if err:
            st.error(f"파싱 오류: {err}")
        else:
            st.success(f"✅ 파싱 완료 — {len(df_g)}개 계정 추출")

            with st.expander("원본 미리보기 (상위 20행)"):
                st.dataframe(df_raw.head(20), use_container_width=True)

            # 검증
            VALID = [("광고비 공급가","ad_supply"),("광고비 합계금액","ad_total"),
                     ("수수료 공급가","comm_supply"),("수수료 합계금액","comm_total")]
            vcols = st.columns(4)
            for idx, (label, col) in enumerate(VALID):
                if col in df_g.columns:
                    ext = df_g[col].sum()
                    raw_col = _find_col(df_raw.columns.tolist(), ALIAS.get(col,[col]))
                    if raw_col:
                        raw = pd.to_numeric(df_raw[raw_col].astype(str).str.replace(",",""), errors="coerce").fillna(0).sum()
                        diff = abs(ext - raw)
                        vcols[idx].metric(label, f"{ext:,.0f}원",
                                          delta="✅ 일치" if diff < 1 else f"⚠️ 차이 {diff:,.0f}")
                    else:
                        vcols[idx].metric(label, f"{ext:,.0f}원")

            st.session_state["uploaded_df"] = df_g
            st.session_state["upload_ym"]   = sel_ym
            st.markdown("**추출된 계정 목록**")
            st.dataframe(df_g, use_container_width=True, hide_index=True)

# ═══════════════════════════════════════════════════════════════
# 탭: 업체 분류
# ═══════════════════════════════════════════════════════════════
with t_cl:
    st.subheader("업체별 프리랜서 분류")
    df = st.session_state.get("uploaded_df")
    if df is None:
        st.info("엑셀 업로드 탭에서 파일을 먼저 업로드해주세요.")
    else:
        st.caption("설정을 변경한 후 행별 **저장** 또는 하단 **일괄 저장**을 클릭하세요.")
        for ri, (_, row) in enumerate(df.iterrows()):
            cid  = str(row.get("customer_id","")).strip()
            ano  = str(row.get("ad_account_no","")).strip()
            name = str(row.get("계정명","")).strip()
            ex   = get_mapping(cid, ano, name) or {}
            ad_s = int(row.get("ad_supply", 0))
            cm_s = int(row.get("comm_supply", 0))
            _k   = f"{ri}_{cid}_{ano}"          # 행 인덱스 포함 → 중복 방지

            with st.expander(f"**{name}** │ CID:{cid} │ 광고비:{ad_s:,}원 │ 수수료:{cm_s:,}원"):
                r1c1, r1c2, r1c3 = st.columns([2, 2, 2])
                with r1c1:
                    fl = st.selectbox("담당 프리랜서", FREELANCERS,
                        index=FREELANCERS.index(ex["freelancer"]) if ex.get("freelancer") in FREELANCERS else 0,
                        key=f"fl_{_k}")
                    is_own = st.checkbox("대표 직접 운영", ex.get("is_owner_managed", False),
                                         key=f"own_{_k}")
                with r1c2:
                    fr = st.number_input("프리랜서 기본 정산율(%)", 0.0, 100.0,
                        float(ex.get("freelancer_rate", 0)), step=0.5, key=f"fr_{_k}")
                    rr = st.number_input("리베이트율(%)", 0.0, 100.0,
                        float(ex.get("rebate_rate", 0)), step=0.5, key=f"rr_{_k}")
                with r1c3:
                    eff = fr - rr
                    if not is_own:
                        if eff < 0:
                            st.error(f"⚠️ 실지급률 음수: {eff:.1f}%")
                        else:
                            st.info(f"실지급률: **{eff:.1f}%**")
                    r = calc_from_ad(ad_s, cm_s, fr, rr, is_own)
                    st.caption(f"프리랜서 지급액: {r['fl_payout']:,}원")
                    st.caption(f"리베이트 지급액: {r['rebate_payout']:,}원")
                    st.caption(f"대표 수익: {r['rep_revenue']:,}원")
                    if st.button("💾 저장", key=f"sv_{_k}"):
                        upsert_mapping(cid, ano, name, fl, fr, rr, is_own)
                        st.toast(f"✅ {name} 저장됨")
                        st.rerun()

        st.divider()
        if st.button("💾 전체 일괄 저장", type="primary", use_container_width=True):
            for ri, (_, row) in enumerate(df.iterrows()):
                cid  = str(row.get("customer_id","")).strip()
                ano  = str(row.get("ad_account_no","")).strip()
                name = str(row.get("계정명","")).strip()
                _k   = f"{ri}_{cid}_{ano}"
                upsert_mapping(
                    cid, ano, name,
                    st.session_state.get(f"fl_{_k}", "미분류"),
                    float(st.session_state.get(f"fr_{_k}", 0)),
                    float(st.session_state.get(f"rr_{_k}", 0)),
                    bool(st.session_state.get(f"own_{_k}", False)),
                )
            st.success("✅ 전체 저장 완료")
            st.rerun()

# ═══════════════════════════════════════════════════════════════
# 탭: 미분류
# ═══════════════════════════════════════════════════════════════
with t_un:
    st.subheader("미분류 업체")
    df = st.session_state.get("uploaded_df")
    if df is None:
        st.info("엑셀 업로드 탭에서 파일을 먼저 업로드해주세요.")
    else:
        unclassified = []
        for _, row in df.iterrows():
            cid  = str(row.get("customer_id","")).strip()
            ano  = str(row.get("ad_account_no","")).strip()
            name = str(row.get("계정명","")).strip()
            m = get_mapping(cid, ano, name)
            if not m or m.get("freelancer","") in ["미분류",""]:
                unclassified.append({"계정명": name, "CustomerID": cid, "AdAccountNo": ano,
                                     "광고비 공급가": int(row.get("ad_supply",0)),
                                     "수수료 공급가": int(row.get("comm_supply",0))})

        total, remain = len(df), len(unclassified)
        m1, m2 = st.columns(2)
        m1.metric("미분류 업체", f"{remain}개", delta=f"전체 {total}개 중")
        m2.metric("분류 완료", f"{total - remain}개")

        if remain == 0:
            st.success("✅ 모든 업체 분류 완료. 정산 확정 가능합니다.")
        else:
            st.warning(f"⚠️ {remain}개 미분류. 업체 분류 탭에서 프리랜서를 지정해주세요.")
            st.dataframe(pd.DataFrame(unclassified), use_container_width=True, hide_index=True)

        # 정산 확정 버튼
        st.divider()
        if st.button("✅ 정산 확정", type="primary", disabled=(remain > 0),
                      use_container_width=True):
            st.success("정산이 확정되었습니다.")

# ═══════════════════════════════════════════════════════════════
# 탭: 프리랜서 정산
# ═══════════════════════════════════════════════════════════════
with t_fl:
    st.subheader("프리랜서별 정산 집계")
    df = st.session_state.get("uploaded_df")
    if df is None:
        st.info("엑셀 업로드 탭에서 파일을 먼저 업로드해주세요.")
    else:
        fl_sum  = {}
        details = []
        for _, row in df.iterrows():
            cid  = str(row.get("customer_id","")).strip()
            ano  = str(row.get("ad_account_no","")).strip()
            name = str(row.get("계정명","")).strip()
            m    = get_mapping(cid, ano, name) or {}
            fl   = m.get("freelancer","미분류")
            fr   = float(m.get("freelancer_rate", 0))
            rr   = float(m.get("rebate_rate", 0))
            is_o = m.get("is_owner_managed", False)
            ad_s = float(row.get("ad_supply", 0))
            ad_t = float(row.get("ad_total",  0))
            cm_s = float(row.get("comm_supply",0))
            r    = calc_from_ad(ad_s, cm_s, fr, rr, is_o)

            details.append({
                "프리랜서": fl, "업체명": name,
                "광고비 공급가": int(ad_s), "광고비 합계": int(ad_t),
                "수수료 공급가": int(cm_s),
                "기본 정산율(%)": fr, "리베이트율(%)": rr,
                "실지급률(%)": r["effective_rate"],
                "프리랜서 지급액": r["fl_payout"],
                "리베이트 지급액": r["rebate_payout"],
                "대표 수익": r["rep_revenue"],
                "⚠️": "⚠️" if r["warning"] else "",
            })
            g = fl_sum.setdefault(fl, {"업체수":0,"광고비 공급가":0,"광고비 합계":0,
                                        "수수료 공급가":0,"프리랜서 지급액":0,
                                        "리베이트 지급액":0,"대표 수익":0})
            g["업체수"]        += 1
            g["광고비 공급가"]  += int(ad_s)
            g["광고비 합계"]    += int(ad_t)
            g["수수료 공급가"]  += int(cm_s)
            g["프리랜서 지급액"] += r["fl_payout"]
            g["리베이트 지급액"] += r["rebate_payout"]
            g["대표 수익"]      += r["rep_revenue"]

        warns = [d for d in details if d["⚠️"]]
        for w in warns:
            st.warning(f"⚠️ **{w['업체명']}**: 실지급률 음수 ({w['실지급률(%)']:.1f}%)")

        st.markdown("**프리랜서별 요약**")
        if fl_sum:
            s_df = pd.DataFrame([{"프리랜서":k,**v} for k,v in fl_sum.items()])
            tot  = {"프리랜서":"합계", **{c: s_df[c].sum() for c in s_df.columns if c!="프리랜서"}}
            s_df = pd.concat([s_df, pd.DataFrame([tot])], ignore_index=True)
            st.dataframe(s_df, use_container_width=True, hide_index=True)

        st.markdown("**업체별 상세**")
        d_df = pd.DataFrame(details).sort_values("프리랜서")
        st.dataframe(d_df, use_container_width=True, hide_index=True)

        st.download_button("📥 CSV 다운로드",
            d_df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig"),
            file_name=f"프리랜서정산_{sel_ym or 'all'}.csv", mime="text/csv")

# ═══════════════════════════════════════════════════════════════
# 탭: 기타비용
# ═══════════════════════════════════════════════════════════════
with t_ex:
    st.subheader("기타비용 관리")
    if not sel_ym:
        st.info("상단에서 정산 월을 선택해주세요.")
    else:
        with st.form("add_expense", clear_on_submit=True):
            ec1, ec2, ec3 = st.columns([2, 2, 3])
            with ec1: exp_name = st.text_input("비용명 *")
            with ec2: exp_amt  = st.number_input("금액 (원)", 0, step=1000)
            with ec3: exp_memo = st.text_input("메모")
            if st.form_submit_button("➕ 추가"):
                if not exp_name:
                    st.error("비용명 필수")
                else:
                    exps = load_expenses()
                    exps.append({"id": str(uuid.uuid4()), "year_month": sel_ym,
                                 "name": exp_name.strip(), "amount": int(exp_amt),
                                 "memo": exp_memo.strip(), "created_at": date.today().isoformat()})
                    save_expenses(exps); st.rerun()

        month_exps = get_expenses_for_month(sel_ym)
        if month_exps:
            all_exps = load_expenses()
            for e in month_exps:
                c1, c2, c3, c4, c5 = st.columns([2, 2, 3, 1, 1])
                c1.markdown(f"**{e['name']}**")
                na = c2.number_input("금액", e["amount"], step=1000, key=f"ea_{e['id']}", label_visibility="collapsed")
                nm = c3.text_input("메모", e.get("memo",""), key=f"em_{e['id']}", label_visibility="collapsed")
                if c4.button("저장", key=f"es_{e['id']}"):
                    for x in all_exps:
                        if x["id"] == e["id"]:
                            x["amount"] = int(na); x["memo"] = nm
                    save_expenses(all_exps); st.rerun()
                if c5.button("🗑️", key=f"ed_{e['id']}"):
                    save_expenses([x for x in all_exps if x["id"] != e["id"]]); st.rerun()
            st.divider()
            st.metric("합계", f"{sum(e['amount'] for e in month_exps):,}원")
        else:
            st.info("이 달의 기타비용이 없습니다.")

# ═══════════════════════════════════════════════════════════════
# 탭: 월 손익
# ═══════════════════════════════════════════════════════════════
with t_pnl:
    st.subheader("월별 손익")
    if not sel_ym:
        st.info("상단에서 정산 월을 선택해주세요.")
    else:
        df        = st.session_state.get("uploaded_df")
        exps      = get_expenses_for_month(sel_ym)
        extra     = get_extra_for_month(sel_ym)
        total_exp = sum(e["amount"] for e in exps)

        search_rep = 0
        if df is not None:
            for _, row in df.iterrows():
                cid  = str(row.get("customer_id","")).strip()
                ano  = str(row.get("ad_account_no","")).strip()
                name = str(row.get("계정명","")).strip()
                m    = get_mapping(cid, ano, name) or {}
                r    = calc_from_ad(float(row.get("ad_supply",0)),
                                    float(row.get("comm_supply",0)),
                                    float(m.get("freelancer_rate",0)),
                                    float(m.get("rebate_rate",0)),
                                    m.get("is_owner_managed",False))
                search_rep += r["rep_revenue"]

        with st.form("extra_rev"):
            xc1, xc2, xc3 = st.columns(3)
            with xc1: place = st.number_input("플레이스 수익(원)", value=float(extra["place_revenue"]), step=10000.0)
            with xc2: blog  = st.number_input("블로그 수익(원)",   value=float(extra["blog_revenue"]),  step=10000.0)
            with xc3: xmemo = st.text_input("메모", extra.get("memo",""))
            if st.form_submit_button("💾 저장"):
                set_extra(sel_ym, int(place), int(blog), xmemo); st.rerun()

        place_rev = int(extra["place_revenue"])
        blog_rev  = int(extra["blog_revenue"])
        net = search_rep + place_rev + blog_rev - total_exp

        st.divider()
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("검색광고 대표 수익", f"{search_rep:,}원")
        c2.metric("플레이스 수익",      f"{place_rev:,}원")
        c3.metric("블로그 수익",        f"{blog_rev:,}원")
        c4.metric("기타비용 합계",      f"{total_exp:,}원", delta=f"-{total_exp:,}")
        c5.metric("월 최종 순수익",     f"{net:,}원",
                  delta=f"{'▲' if net>=0 else '▼'} {abs(net):,}")

        if df is None:
            st.warning("엑셀 데이터 없음 — 검색광고 수익 0원으로 계산됩니다.")
