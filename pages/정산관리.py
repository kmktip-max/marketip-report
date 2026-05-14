import streamlit as st
import json, os, sys, uuid, re
import pandas as pd
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# ── 상수 ─────────────────────────────────────────────────────────────────────
FREELANCERS = [
    "미분류", "권혁우", "최은성", "조성지", "임예솔", "홍선기",
    "안주희", "이승준", "문성빈", "김하린", "김주훈", "대표 직접",
]
F_MAPPING  = os.path.join(ROOT, "freelancer_mapping.json")
F_EXPENSES = os.path.join(ROOT, "other_expenses.json")
F_EXTRA    = os.path.join(ROOT, "monthly_extra_revenue.json")

# ── 인증 ─────────────────────────────────────────────────────────────────────
def _pw():
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
        if pw == _pw():
            st.session_state.settlement_auth = True
            st.rerun()
        else:
            st.error("비밀번호가 틀렸습니다.")
    st.stop()

# ── 스토리지 ──────────────────────────────────────────────────────────────────
def _load(p):
    try:
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f: return json.load(f)
    except Exception: pass
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

def map_key(cid, ano):
    return f"{str(cid).strip()}_{str(ano).strip()}"

def get_mapping(cid, ano):
    k = map_key(cid, ano)
    for m in load_mapping():
        if map_key(m.get("customer_id",""), m.get("ad_account_no","")) == k:
            return m
    return None

def upsert_mapping(cid, ano, account_id, account_name, display_name,
                   fl, fr, rr, is_own):
    data = load_mapping()
    k = map_key(cid, ano)
    for m in data:
        if map_key(m.get("customer_id",""), m.get("ad_account_no","")) == k:
            m.update({"account_id": account_id, "account_name": account_name,
                      "display_name": display_name, "freelancer": fl,
                      "freelancer_rate": fr, "rebate_rate": rr,
                      "is_owner_managed": is_own})
            save_mapping(data)
            return
    data.append({"customer_id": str(cid), "ad_account_no": str(ano),
                 "account_id": account_id, "account_name": account_name,
                 "display_name": display_name, "freelancer": fl,
                 "freelancer_rate": fr, "rebate_rate": rr,
                 "is_owner_managed": is_own})
    save_mapping(data)

# ── 엑셀 파싱 ─────────────────────────────────────────────────────────────────
def norm(s):
    """컬럼명 정규화: 공백·줄바꿈 제거, 소문자"""
    return re.sub(r'\s+', '', str(s)).lower()

# 표준명 → 원본 컬럼명 매핑을 위한 alias 딕셔너리 (정규화 키)
ALIASES = {
    "매체사":        ["매체사","매체","media"],
    "account_id":   ["계정id","accountid","계정id"],
    "customer_id":  ["계정번호customerId","customerId","customerId","고객id"],
    "ad_account_no":["계정번호adaccountno","adaccountno","광고계정번호"],
    "계정명":        ["계정명","광고주명","accountname"],
    "ad_supply":    ["광고비공급가","공급가액","adspend"],
    "ad_vat":       ["광고비세액"],
    "ad_total":     ["광고비합계금액","광고비합계"],
    "comm_rate":    ["수수료율","수수료율(%)"],
    "comm_supply":  ["수수료공급가"],
    "comm_vat":     ["수수료세액"],
    "comm_total":   ["수수료합계금액","수수료합계"],
}
# norm된 alias → 표준명 역방향 맵
_ALIAS_MAP = {norm(a): std for std, aliases in ALIASES.items() for a in aliases}

def find_header_row(df_raw):
    """헤더가 있는 행 자동 탐지"""
    keywords = ["계정명","매체사","광고비"]
    for i in range(min(10, len(df_raw))):
        row_str = " ".join(str(v) for v in df_raw.iloc[i].values if pd.notna(v))
        if any(k in row_str for k in keywords):
            return i
    return 2

def parse_excel(f):
    try:
        df_raw = pd.read_excel(f, header=None, engine="openpyxl")
    except Exception as e:
        return None, str(e), None, {}

    # 헤더 행 탐지
    hr = find_header_row(df_raw)
    df = pd.read_excel(f, header=hr, engine="openpyxl")

    orig_cols = df.columns.tolist()
    col_map = {}   # 표준명 → 원본 컬럼명
    for c in orig_cols:
        nc = norm(c)
        std = _ALIAS_MAP.get(nc)
        if std and std not in col_map:
            col_map[std] = c

    debug = {
        "header_row":  hr,
        "orig_cols":   orig_cols,
        "norm_cols":   [norm(c) for c in orig_cols],
        "col_map":     col_map,
    }

    # 계정명 컬럼 확인
    name_col = col_map.get("계정명")
    if not name_col:
        # Fallback: 컬럼에서 직접 탐색
        for c in orig_cols:
            if "계정명" in str(c):
                name_col = c; col_map["계정명"] = c; break

    if not name_col:
        return None, f"'계정명' 컬럼을 찾을 수 없습니다.\n원본 컬럼: {orig_cols}", df, debug

    # 빈 행 / 합계 행 제거
    df = df[df[name_col].notna()].copy()
    df = df[~df[name_col].astype(str).str.contains(
        r"^(합계|소계|TOTAL|합\s*계|nan)$", regex=True, na=False)]
    df = df[df[name_col].astype(str).str.strip() != ""]

    # 표준 컬럼으로 rename
    df = df.rename(columns={v: k for k, v in col_map.items() if v in df.columns})

    # 숫자형 변환
    for nc in ["ad_supply","ad_vat","ad_total","comm_supply","comm_vat","comm_total","comm_rate"]:
        if nc in df.columns:
            df[nc] = pd.to_numeric(
                df[nc].astype(str).str.replace(",","").str.replace("원","").str.strip(),
                errors="coerce").fillna(0)

    # ID 컬럼 문자열화
    for ic in ["customer_id","ad_account_no","account_id"]:
        if ic in df.columns:
            df[ic] = df[ic].astype(str).str.strip().str.replace(r"\.0$","",regex=True)
        else:
            df[ic] = ""

    # 계정명 정제 및 display_name 생성
    def make_display(row):
        name = str(row.get("계정명","")).strip()
        if name in ["-","","nan","None"] or not name:
            aid = str(row.get("account_id","")).strip()
            return aid if aid and aid not in ["","nan"] else f"CID:{row.get('customer_id','')}"
        return name

    # 계정명 컬럼 표준화
    if "계정명" not in df.columns and name_col in df.columns:
        df["계정명"] = df[name_col]

    df["display_name"] = df.apply(make_display, axis=1)

    debug["raw_sample"] = df.head(10).to_dict("records")
    debug["display_names"] = df["display_name"].head(20).tolist()

    # CustomerID + AdAccountNo 기준 그룹핑
    num_cols   = [c for c in ["ad_supply","ad_vat","ad_total","comm_supply","comm_vat","comm_total"] if c in df.columns]
    first_cols = [c for c in ["comm_rate","계정명","display_name","매체사","account_id"] if c in df.columns]

    agg = {c: "sum" for c in num_cols}
    agg.update({c: "first" for c in first_cols})

    if "customer_id" in df.columns and "ad_account_no" in df.columns:
        df_g = df.groupby(["customer_id","ad_account_no"], as_index=False).agg(agg)
    else:
        df_g = df.groupby(["계정명"], as_index=False).agg(agg)
        df_g["customer_id"]   = ""
        df_g["ad_account_no"] = ""

    debug["group_count"] = len(df_g)
    debug["ad_supply_total"]   = float(df_g["ad_supply"].sum())   if "ad_supply"   in df_g.columns else 0
    debug["comm_supply_total"] = float(df_g["comm_supply"].sum()) if "comm_supply" in df_g.columns else 0

    return df_g, None, df, debug

# ── 정산 계산 ─────────────────────────────────────────────────────────────────
def calc(ad_supply, comm_supply, fr_pct, rr_pct, is_own):
    fr = fr_pct / 100
    rr = rr_pct / 100
    rebate_payout = round(ad_supply * rr)
    if is_own:
        return {"eff_pct": 0.0, "fl_payout": 0, "rebate_payout": rebate_payout,
                "rep_revenue": round(comm_supply - rebate_payout), "warning": False}
    eff = fr - rr
    fl_payout = round(ad_supply * max(eff, 0))
    return {"eff_pct": round(eff * 100, 2), "fl_payout": fl_payout,
            "rebate_payout": rebate_payout,
            "rep_revenue": round(comm_supply - fl_payout - rebate_payout),
            "warning": eff < 0}

# ── 기타비용/수익 헬퍼 ────────────────────────────────────────────────────────
def get_expenses_for_month(ym): return [e for e in load_expenses() if e["year_month"] == ym]
def get_extra_for_month(ym):
    for r in load_extra():
        if r["year_month"] == ym: return r
    return {"year_month": ym, "place_revenue": 0, "blog_revenue": 0, "memo": ""}
def set_extra(ym, place, blog, memo=""):
    data = load_extra()
    for r in data:
        if r["year_month"] == ym:
            r.update({"place_revenue": place, "blog_revenue": blog, "memo": memo})
            save_extra(data); return
    data.append({"year_month": ym, "place_revenue": place, "blog_revenue": blog, "memo": memo})
    save_extra(data)

# ── 헤더 ──────────────────────────────────────────────────────────────────────
hc1, hc2 = st.columns([5, 1])
with hc1: st.title("📊 정산 관리")
with hc2:
    st.write("")
    if st.button("로그아웃"):
        for k in ["settlement_auth","uploaded_df","upload_debug"]: st.session_state.pop(k, None)
        st.rerun()

YM_LIST = [f"{y}-{m:02d}" for y in range(2025, 2028) for m in range(1, 13)]
sel_ym = st.selectbox("📅 정산 월", YM_LIST, index=None, placeholder="YYYY-MM...", key="main_ym")
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
    st.caption("헤더가 3행에 있는 xlsx 파일을 업로드합니다.")
    f = st.file_uploader("파일 선택", type=["xlsx","xls","csv"])

    if f:
        df_g, err, df_raw_proc, debug = parse_excel(f)
        if err:
            st.error(f"파싱 오류: {err}")
            if debug:
                with st.expander("🐛 디버그"):
                    st.write("원본 컬럼:", debug.get("orig_cols"))
        else:
            st.success(f"✅ {len(df_g)}개 계정 추출 (헤더 {debug['header_row']+1}행)")

            # 디버그 패널
            with st.expander("🐛 디버그 정보", expanded=False):
                st.markdown("**원본 컬럼명**")
                st.write(debug["orig_cols"])
                st.markdown("**정규화 컬럼명**")
                st.write(debug["norm_cols"])
                st.markdown("**컬럼 매핑 결과**")
                st.json(debug["col_map"])
                st.markdown(f"**업체 수**: {debug['group_count']}개")
                st.markdown(f"**광고비 공급가 합계**: {debug.get('ad_supply_total',0):,.0f}원")
                st.markdown(f"**수수료 공급가 합계**: {debug.get('comm_supply_total',0):,.0f}원")
                st.markdown("**display_name 생성 결과 (상위 20)**")
                st.write(debug.get("display_names"))
                st.markdown("**정제 후 상위 10행**")
                st.dataframe(pd.DataFrame(debug.get("raw_sample",[])), use_container_width=True)

            # 검증 합계
            VALID = [("광고비 공급가","ad_supply"),("광고비 합계금액","ad_total"),
                     ("수수료 공급가","comm_supply"),("수수료 합계금액","comm_total")]
            vcols = st.columns(4)
            for idx, (label, col) in enumerate(VALID):
                if col in df_g.columns:
                    vcols[idx].metric(label, f"{df_g[col].sum():,.0f}원")

            st.session_state["uploaded_df"]    = df_g
            st.session_state["upload_debug"]   = debug

            st.markdown("**추출된 계정 목록**")
            show_cols = [c for c in ["display_name","customer_id","ad_account_no",
                                      "ad_supply","comm_supply","comm_rate","매체사"] if c in df_g.columns]
            st.dataframe(df_g[show_cols], use_container_width=True, hide_index=True)

# ═══════════════════════════════════════════════════════════════
# 탭: 업체 분류
# ═══════════════════════════════════════════════════════════════
with t_cl:
    st.subheader("업체별 프리랜서 분류")
    df = st.session_state.get("uploaded_df")
    if df is None:
        st.info("엑셀 업로드 탭에서 파일을 먼저 업로드해주세요.")
    else:
        st.caption("설정 후 행별 **저장** 또는 하단 **전체 저장**을 클릭하세요.")
        all_saved = True

        for _, row in df.iterrows():
            cid  = str(row.get("customer_id","")).strip()
            ano  = str(row.get("ad_account_no","")).strip()
            aid  = str(row.get("account_id","")).strip()
            name = str(row.get("계정명","")).strip()
            disp = str(row.get("display_name", name)).strip()
            ad_s = float(row.get("ad_supply",  0))
            cm_s = float(row.get("comm_supply", 0))

            # 저장된 매핑 불러오기
            ex = get_mapping(cid, ano) or {}

            # 위젯 key: customer_id + ad_account_no 기준
            wk = f"{cid}_{ano}".replace(" ","_")

            with st.expander(
                f"**{disp}** │ CID:{cid} │ 광고비:{ad_s:,.0f}원 │ 수수료:{cm_s:,.0f}원",
                expanded=(ex.get("freelancer","미분류") == "미분류")
            ):
                c1, c2, c3 = st.columns([2, 2, 2])
                with c1:
                    fl_idx = FREELANCERS.index(ex["freelancer"]) if ex.get("freelancer") in FREELANCERS else 0
                    fl = st.selectbox("담당 프리랜서", FREELANCERS, index=fl_idx,
                                      key=f"fl_{wk}")
                    is_own = st.checkbox("대표 직접 운영",
                                         value=ex.get("is_owner_managed", False),
                                         key=f"own_{wk}")
                with c2:
                    fr = st.number_input("프리랜서 기본 정산율(%)", 0.0, 100.0,
                                         float(ex.get("freelancer_rate", 0)),
                                         step=0.5, key=f"fr_{wk}")
                    rr = st.number_input("리베이트율(%)", 0.0, 100.0,
                                         float(ex.get("rebate_rate", 0)),
                                         step=0.5, key=f"rr_{wk}")
                with c3:
                    r = calc(ad_s, cm_s, fr, rr, is_own)
                    eff = fr - rr
                    if not is_own:
                        if r["warning"]: st.error(f"⚠️ 실지급률 음수: {eff:.1f}%")
                        else:            st.success(f"실지급률: **{eff:.1f}%**")
                    st.metric("프리랜서 지급액",  f"{r['fl_payout']:,}원")
                    st.metric("리베이트 지급액",   f"{r['rebate_payout']:,}원")
                    st.metric("대표 수익",          f"{r['rep_revenue']:,}원")

                    if st.button("💾 저장", key=f"sv_{wk}", type="primary"):
                        upsert_mapping(cid, ano, aid, name, disp, fl, fr, rr, is_own)
                        st.success(f"✅ '{disp}' 저장됨")
                        st.rerun()

                if ex.get("freelancer","미분류") == "미분류":
                    all_saved = False

        st.divider()
        if st.button("💾 전체 일괄 저장", type="primary", use_container_width=True):
            for _, row in df.iterrows():
                cid  = str(row.get("customer_id","")).strip()
                ano  = str(row.get("ad_account_no","")).strip()
                aid  = str(row.get("account_id","")).strip()
                name = str(row.get("계정명","")).strip()
                disp = str(row.get("display_name", name)).strip()
                wk   = f"{cid}_{ano}".replace(" ","_")
                upsert_mapping(
                    cid, ano, aid, name, disp,
                    st.session_state.get(f"fl_{wk}", "미분류"),
                    float(st.session_state.get(f"fr_{wk}", 0)),
                    float(st.session_state.get(f"rr_{wk}", 0)),
                    bool(st.session_state.get(f"own_{wk}", False)),
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
        unc = []
        for _, row in df.iterrows():
            cid  = str(row.get("customer_id","")).strip()
            ano  = str(row.get("ad_account_no","")).strip()
            disp = str(row.get("display_name","")).strip()
            m = get_mapping(cid, ano)
            if not m or m.get("freelancer","미분류") in ["미분류",""]:
                unc.append({"display_name": disp, "customer_id": cid,
                             "ad_account_no": ano,
                             "광고비 공급가": int(row.get("ad_supply",0)),
                             "수수료 공급가": int(row.get("comm_supply",0))})

        total, remain = len(df), len(unc)
        m1, m2 = st.columns(2)
        m1.metric("미분류", f"{remain}개", delta=f"전체 {total}개")
        m2.metric("분류 완료", f"{total - remain}개")

        if remain == 0:
            st.success("✅ 모든 업체 분류 완료")
        else:
            st.warning(f"⚠️ {remain}개 미분류")
            st.dataframe(pd.DataFrame(unc), use_container_width=True, hide_index=True)

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
        fl_sum, details = {}, []
        for _, row in df.iterrows():
            cid  = str(row.get("customer_id","")).strip()
            ano  = str(row.get("ad_account_no","")).strip()
            disp = str(row.get("display_name","")).strip()
            m    = get_mapping(cid, ano) or {}
            fl   = m.get("freelancer","미분류")
            fr   = float(m.get("freelancer_rate", 0))
            rr   = float(m.get("rebate_rate", 0))
            is_o = m.get("is_owner_managed", False)
            ad_s = float(row.get("ad_supply",  0))
            ad_t = float(row.get("ad_total",   0))
            cm_s = float(row.get("comm_supply",0))
            r    = calc(ad_s, cm_s, fr, rr, is_o)

            details.append({"프리랜서": fl, "업체명": disp,
                            "광고비 공급가": int(ad_s), "광고비 합계": int(ad_t),
                            "수수료 공급가": int(cm_s),
                            "기본 정산율(%)": fr, "리베이트율(%)": rr,
                            "실지급률(%)": r["eff_pct"],
                            "프리랜서 지급액": r["fl_payout"],
                            "리베이트 지급액": r["rebate_payout"],
                            "대표 수익": r["rep_revenue"],
                            "⚠️": "⚠️" if r["warning"] else ""})
            g = fl_sum.setdefault(fl, {k: 0 for k in
                ["업체수","광고비 공급가","광고비 합계","수수료 공급가",
                 "프리랜서 지급액","리베이트 지급액","대표 수익"]})
            g["업체수"]        += 1
            g["광고비 공급가"]  += int(ad_s)
            g["광고비 합계"]    += int(ad_t)
            g["수수료 공급가"]  += int(cm_s)
            g["프리랜서 지급액"] += r["fl_payout"]
            g["리베이트 지급액"] += r["rebate_payout"]
            g["대표 수익"]      += r["rep_revenue"]

        for w in [d for d in details if d["⚠️"]]:
            st.warning(f"⚠️ **{w['업체명']}**: 실지급률 음수 ({w['실지급률(%)']:.1f}%)")

        if fl_sum:
            st.markdown("**프리랜서별 요약**")
            s_df = pd.DataFrame([{"프리랜서":k,**v} for k,v in fl_sum.items()])
            tot  = {"프리랜서":"합계",**{c:s_df[c].sum() for c in s_df.columns if c!="프리랜서"}}
            s_df = pd.concat([s_df, pd.DataFrame([tot])], ignore_index=True)
            st.dataframe(s_df, use_container_width=True, hide_index=True)

        st.markdown("**업체별 상세**")
        d_df = pd.DataFrame(details).sort_values("프리랜서")
        st.dataframe(d_df, use_container_width=True, hide_index=True)
        st.download_button("📥 CSV",
            d_df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig"),
            file_name=f"정산_{sel_ym or 'all'}.csv", mime="text/csv")

# ═══════════════════════════════════════════════════════════════
# 탭: 기타비용
# ═══════════════════════════════════════════════════════════════
with t_ex:
    st.subheader("기타비용 관리")
    if not sel_ym:
        st.info("상단에서 정산 월을 선택해주세요.")
    else:
        with st.form("add_exp", clear_on_submit=True):
            ec1, ec2, ec3 = st.columns([2,2,3])
            with ec1: en = st.text_input("비용명 *")
            with ec2: ea = st.number_input("금액(원)", 0, step=1000)
            with ec3: em = st.text_input("메모")
            if st.form_submit_button("➕ 추가"):
                if not en: st.error("비용명 필수")
                else:
                    exps = load_expenses()
                    exps.append({"id": str(uuid.uuid4()), "year_month": sel_ym,
                                 "name": en.strip(), "amount": int(ea),
                                 "memo": em.strip(), "created_at": date.today().isoformat()})
                    save_expenses(exps); st.rerun()

        month_exps = get_expenses_for_month(sel_ym)
        if month_exps:
            all_exps = load_expenses()
            for e in month_exps:
                c1,c2,c3,c4,c5 = st.columns([2,2,3,1,1])
                c1.markdown(f"**{e['name']}**")
                na = c2.number_input("금액", e["amount"], step=1000, key=f"ea_{e['id']}", label_visibility="collapsed")
                nm = c3.text_input("메모", e.get("memo",""), key=f"em_{e['id']}", label_visibility="collapsed")
                if c4.button("저장", key=f"es_{e['id']}"):
                    for x in all_exps:
                        if x["id"]==e["id"]: x["amount"]=int(na); x["memo"]=nm
                    save_expenses(all_exps); st.rerun()
                if c5.button("🗑️", key=f"ed_{e['id']}"):
                    save_expenses([x for x in all_exps if x["id"]!=e["id"]]); st.rerun()
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
        df    = st.session_state.get("uploaded_df")
        exps  = get_expenses_for_month(sel_ym)
        extra = get_extra_for_month(sel_ym)
        total_exp = sum(e["amount"] for e in exps)

        search_rep = 0
        if df is not None:
            for _, row in df.iterrows():
                cid = str(row.get("customer_id","")).strip()
                ano = str(row.get("ad_account_no","")).strip()
                m   = get_mapping(cid, ano) or {}
                r   = calc(float(row.get("ad_supply",0)), float(row.get("comm_supply",0)),
                           float(m.get("freelancer_rate",0)), float(m.get("rebate_rate",0)),
                           m.get("is_owner_managed",False))
                search_rep += r["rep_revenue"]

        with st.form("extra_rev"):
            xc1,xc2,xc3 = st.columns(3)
            with xc1: place = st.number_input("플레이스(원)", float(extra["place_revenue"]), step=10000.0)
            with xc2: blog  = st.number_input("블로그(원)",   float(extra["blog_revenue"]),  step=10000.0)
            with xc3: xm    = st.text_input("메모", extra.get("memo",""))
            if st.form_submit_button("💾 저장"):
                set_extra(sel_ym, int(place), int(blog), xm); st.rerun()

        net = search_rep + int(extra["place_revenue"]) + int(extra["blog_revenue"]) - total_exp
        c1,c2,c3,c4,c5 = st.columns(5)
        c1.metric("검색광고 대표 수익", f"{search_rep:,}원")
        c2.metric("플레이스",           f"{int(extra['place_revenue']):,}원")
        c3.metric("블로그",             f"{int(extra['blog_revenue']):,}원")
        c4.metric("기타비용",           f"{total_exp:,}원", delta=f"-{total_exp:,}")
        c5.metric("월 최종 순수익",     f"{net:,}원")
        if df is None:
            st.warning("엑셀 없음 — 검색광고 수익 0원으로 계산됩니다.")
