"""
정산관리 — 관리자 전용
엑셀 업로드 → 업체 분류 → 프리랜서 정산 → 기타비용 → 월 손익
"""
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
OWNER_FL   = "권혁우"   # 대표가 직접 담당하는 프리랜서명
F_MAPPING  = os.path.join(ROOT, "freelancer_mapping.json")
F_EXPENSES = os.path.join(ROOT, "other_expenses.json")
F_EXTRA    = os.path.join(ROOT, "monthly_extra_revenue.json")

# ── 관리자 인증 ───────────────────────────────────────────────────────────────
def _admin_pw():
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
        if pw == _admin_pw():
            st.session_state.settlement_auth = True
            st.rerun()
        else:
            st.error("비밀번호가 틀렸습니다.")
    st.stop()

# ── 스토리지 헬퍼 ─────────────────────────────────────────────────────────────
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

# ── 복합 키: CID + AdAccountNo + 매체사 + 상위수수료율 ───────────────────────
def _norm_media(m):
    s = str(m).strip()
    return "" if s in ("", "nan", "None", "NaT") else s

def _mk(cid, ano, media="", upper_rate=0.0):
    r = round(float(upper_rate) if upper_rate else 0.0, 1)
    return f"{str(cid).strip()}|{str(ano).strip()}|{_norm_media(media)}|{r}"

def get_mapping(cid, ano, media="", upper_rate=0.0):
    k = _mk(cid, ano, media, upper_rate)
    for m in load_mapping():
        mk = _mk(m.get("customer_id",""), m.get("ad_account_no",""),
                 m.get("media",""), m.get("upper_comm_rate", 0))
        if mk == k:
            return m
    return None

def upsert_mapping(cid, ano, aid, name, disp, media, upper_rate,
                   fl, fr, rr, is_own,
                   direct_mode=False, direct_rate=0.0, locked=True):
    data = load_mapping()
    k = _mk(cid, ano, media, upper_rate)
    entry = {
        "customer_id": str(cid), "ad_account_no": str(ano),
        "account_id": aid, "account_name": name, "display_name": disp,
        "media": _norm_media(media),
        "upper_comm_rate": round(float(upper_rate) if upper_rate else 0.0, 1),
        "freelancer": fl, "freelancer_rate": fr, "rebate_rate": rr,
        "is_owner_managed": is_own,
        "direct_commission_mode": direct_mode,
        "direct_commission_rate": direct_rate,
        "locked": locked,
        "updated_at": date.today().isoformat(),
    }
    for m in data:
        mk = _mk(m.get("customer_id",""), m.get("ad_account_no",""),
                 m.get("media",""), m.get("upper_comm_rate", 0))
        if mk == k:
            m.update(entry)
            save_mapping(data)
            return
    data.append(entry)
    save_mapping(data)

def get_expenses_for_month(ym): return [e for e in load_expenses() if e["year_month"] == ym]

def get_extra(ym):
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

# ── 숫자 포맷 ─────────────────────────────────────────────────────────────────
def w(n):   return f"{int(round(n)):,} 원"
def pct(p): return f"{p:.1f}%"

# ── 엑셀 파싱 ─────────────────────────────────────────────────────────────────
def _norm(s): return re.sub(r'\s+', '', str(s)).lower()

def _find_sections(df_raw):
    for i in range(min(10, len(df_raw))):
        vals = list(df_raw.iloc[i].values)
        ad_p = comm_p = None
        for j, v in enumerate(vals):
            sv = str(v).strip()
            if sv == "광고비" and ad_p is None: ad_p = j
            if "수수료" in sv and comm_p is None: comm_p = j
        if ad_p is not None and comm_p is not None:
            return i, ad_p, comm_p
    return None, None, None

def _find_header(df_raw, merged_row):
    start = (merged_row + 1) if merged_row is not None else 0
    for i in range(start, min(start + 6, len(df_raw))):
        vals = [str(v).strip() for v in df_raw.iloc[i].values]
        if "계정명" in vals: return i
    for i in range(min(12, len(df_raw))):
        vals = [str(v).strip() for v in df_raw.iloc[i].values]
        if "계정명" in vals: return i
    return (merged_row + 1) if merged_row is not None else 3

_FIXED_MAP = {
    "매체사":"매체사", "매체":"매체사",
    "담당자":"담당자",
    "계정id":"account_id",
    "계정번호customerid":"customer_id","customerid":"customer_id",
    "계정번호adaccountno":"ad_account_no","adaccountno":"ad_account_no",
    "계정명":"계정명",
}

def parse_excel(f):
    try:
        df_raw = pd.read_excel(f, header=None, engine="openpyxl")
    except Exception as e:
        return None, str(e), None, {}

    merged_row, ad_p, comm_p = _find_sections(df_raw)
    hr = _find_header(df_raw, merged_row)
    df = pd.read_excel(f, header=hr, engine="openpyxl")
    orig = df.columns.tolist()

    debug = {
        "merged_row": merged_row, "header_row": hr,
        "ad_pos": ad_p, "comm_pos": comm_p,
        "orig_cols": [str(c) for c in orig],
    }

    rename = {}

    if ad_p is not None and comm_p is not None:
        for i, c in enumerate(orig[:ad_p]):
            nc = _norm(c)
            for k, std in _FIXED_MAP.items():
                if k in nc and std not in rename.values():
                    rename[c] = std; break

        def _set(pos, std):
            if pos < len(orig): rename[orig[pos]] = std

        _set(ad_p,   "ad_supply")
        _set(ad_p+1, "ad_vat")
        _set(ad_p+2, "ad_total")

        for i in range(ad_p+3, comm_p):
            if i < len(orig) and "comm_rate" not in rename.values():
                rename[orig[i]] = "comm_rate"

        nc0 = _norm(orig[comm_p]) if comm_p < len(orig) else ""
        if "율" in nc0:
            _set(comm_p,   "comm_rate")
            _set(comm_p+1, "comm_supply")
            _set(comm_p+2, "comm_vat")
            _set(comm_p+3, "comm_total")
        else:
            _set(comm_p,   "comm_supply")
            _set(comm_p+1, "comm_vat")
            _set(comm_p+2, "comm_total")
    else:
        _NAME = {
            **_FIXED_MAP,
            "광고비공급가":"ad_supply","공급가":"ad_supply",
            "광고비세액":"ad_vat","세액":"ad_vat",
            "광고비합계금액":"ad_total","합계금액":"ad_total",
            "수수료율":"comm_rate",
            "수수료공급가":"comm_supply","공급가.1":"comm_supply",
            "수수료세액":"comm_vat","세액.1":"comm_vat",
            "수수료합계금액":"comm_total","합계금액.1":"comm_total",
        }
        for c in orig:
            nc = _norm(c)
            std = _NAME.get(nc)
            if std and std not in rename.values():
                rename[c] = std

    debug["rename_map"] = {str(k): v for k, v in rename.items()}
    df = df.rename(columns=rename)

    if "계정명" not in df.columns:
        for c in df.columns:
            if "계정명" in str(c): df = df.rename(columns={c:"계정명"}); break
    if "계정명" not in df.columns:
        return None, f"계정명 컬럼 없음. 원본: {orig}", df, debug

    df = df[df["계정명"].notna()].copy()
    df = df[~df["계정명"].astype(str).str.strip().str.match(
        r"^(합계|소계|TOTAL|합\s*계|nan)$", na=False)]
    df = df[df["계정명"].astype(str).str.strip().replace("nan","") != ""]

    NUM = ["ad_supply","ad_vat","ad_total","comm_supply","comm_vat","comm_total","comm_rate"]
    for col in NUM:
        if col in df.columns:
            df[col] = pd.to_numeric(
                df[col].astype(str).str.replace(",","").str.replace("원","").str.strip(),
                errors="coerce").fillna(0)
        else:
            df[col] = 0.0

    for ic in ["customer_id","ad_account_no","account_id"]:
        if ic in df.columns:
            df[ic] = df[ic].astype(str).str.strip().str.replace(r"\.0$","",regex=True)
        else:
            df[ic] = ""

    def _disp(row):
        nm = str(row.get("계정명","")).strip()
        if not nm or nm in ["-","nan","None","NaN",""]:
            aid = str(row.get("account_id","")).strip()
            return aid if aid not in ["","nan","None"] else f"CID:{row.get('customer_id','')}"
        return nm
    df["display_name"] = df.apply(_disp, axis=1)

    debug["ad_supply_sum"]   = float(df["ad_supply"].sum())
    debug["ad_total_sum"]    = float(df["ad_total"].sum())
    debug["comm_supply_sum"] = float(df["comm_supply"].sum())
    debug["comm_total_sum"]  = float(df["comm_total"].sum())
    debug["raw_cols"] = list(df.columns)
    debug["raw_sample"] = df[[
        c for c in ["display_name","customer_id","ad_account_no","매체사",
                     "ad_supply","ad_total","comm_rate","comm_supply","comm_total"]
        if c in df.columns
    ]].head(20).to_dict("records")

    # ── 그룹핑: CID + AdAccountNo + 매체사 + 수수료율 ──────────────────────
    # 수수료율을 항상 % 단위로 정규화 (Excel에 0.095로 저장된 경우 → 9.5%)
    if "comm_rate" in df.columns:
        non_zero = df["comm_rate"][df["comm_rate"] != 0]
        if len(non_zero) > 0 and non_zero.abs().max() < 2:
            df["comm_rate"] = df["comm_rate"] * 100   # 소수 → %
        df["comm_rate"] = df["comm_rate"].round(1)
    # 매체사가 없으면 빈 문자열
    if "매체사" not in df.columns:
        df["매체사"] = ""
    else:
        df["매체사"] = df["매체사"].fillna("").astype(str).str.strip()

    SUM_COLS   = [c for c in ["ad_supply","ad_vat","ad_total","comm_supply","comm_vat","comm_total"]
                  if c in df.columns]
    FIRST_COLS = [c for c in ["계정명","display_name","account_id"] if c in df.columns]
    agg = {c: "sum" for c in SUM_COLS}
    agg.update({c: "first" for c in FIRST_COLS})

    if "customer_id" in df.columns and "ad_account_no" in df.columns:
        df_g = df.groupby(
            ["customer_id","ad_account_no","매체사","comm_rate"],
            as_index=False
        ).agg(agg)
    else:
        df_g = df.groupby(["계정명"], as_index=False).agg(agg)
        df_g["customer_id"] = df_g["ad_account_no"] = ""
        df_g["매체사"]  = ""
        df_g["comm_rate"] = 0.0

    debug["group_count"]  = len(df_g)
    debug["group_sample"] = df_g.head(10).to_dict("records")

    return df_g, None, df, debug

# ── 정산 계산 ─────────────────────────────────────────────────────────────────
def calc(ad_supply, ad_total, comm_supply, fr_pct, rr_pct, is_own,
         direct_mode=False, direct_rate_pct=0.0):
    fr  = fr_pct / 100
    rr  = rr_pct / 100
    eff = max(fr - rr, 0)
    rebate = round(ad_total * rr)

    if direct_mode:
        dr = direct_rate_pct / 100
        direct_comm = round(ad_supply * dr)
        if is_own:
            return {"eff_pct": 0.0, "fl_gross": 0, "fl_tax": 0, "fl_net": 0,
                    "rebate": rebate, "owner": direct_comm - rebate,
                    "direct_comm": direct_comm, "warn": False, "direct": True}
        fl_gross = round(ad_supply * eff)
        fl_tax   = round(fl_gross * 0.033)
        fl_net   = round(fl_gross * 0.967)
        return {"eff_pct": round(eff * 100, 2),
                "fl_gross": fl_gross, "fl_tax": fl_tax, "fl_net": fl_net,
                "rebate": rebate,
                "owner": direct_comm - fl_gross - rebate,
                "direct_comm": direct_comm, "warn": (fr - rr) < 0, "direct": True}
    else:
        if is_own:
            return {"eff_pct": 0.0, "fl_gross": 0, "fl_tax": 0, "fl_net": 0,
                    "rebate": rebate, "owner": round(comm_supply - rebate),
                    "direct_comm": 0, "warn": False, "direct": False}
        fl_gross = round(ad_supply * eff)
        fl_tax   = round(fl_gross * 0.033)
        fl_net   = round(fl_gross * 0.967)
        return {"eff_pct": round(eff * 100, 2),
                "fl_gross": fl_gross, "fl_tax": fl_tax, "fl_net": fl_net,
                "rebate": rebate,
                "owner": round(comm_supply - fl_gross - rebate),
                "direct_comm": 0, "warn": (fr - rr) < 0, "direct": False}

# ── Styler 헬퍼 ───────────────────────────────────────────────────────────────
def _style_fl(col):
    if col.name == "프리랜서 지급액":
        return ["color: #dc2626; font-weight: 700"] * len(col)
    return [""] * len(col)

# ── 위젯 키 생성 (CID + AdNo + 매체 + 수수료율) ──────────────────────────────
def _wk(cid, ano, media, rate):
    m = re.sub(r'\W+', '', str(media))
    r = f"{float(rate):.1f}".replace(".", "p")
    return re.sub(r'\W+', '_', f"{cid}_{ano}_{m}_{r}")

# ═════════════════════════════════════════════════════════════════════════════
# UI
# ═════════════════════════════════════════════════════════════════════════════
hc1, hc2 = st.columns([5, 1])
with hc1: st.title("📊 정산 관리")
with hc2:
    st.write("")
    if st.button("로그아웃"):
        for k in ["settlement_auth","uploaded_df","upload_dbg"]: st.session_state.pop(k, None)
        st.rerun()

YM = [f"{y}-{m:02d}" for y in range(2025, 2028) for m in range(1, 13)]
sel_ym = st.selectbox("📅 정산 월", YM, index=None, placeholder="YYYY-MM...", key="main_ym")
st.divider()

t_up, t_cl, t_un, t_fl, t_ex, t_pnl = st.tabs([
    "📤 엑셀 업로드", "🏢 업체 분류", "❓ 미분류",
    "👤 프리랜서 정산", "💰 기타비용", "📈 월 손익",
])

# ─── 업로드 탭 ────────────────────────────────────────────────────────────────
with t_up:
    st.subheader("상위대행사 정산 엑셀 업로드")
    st.caption("헤더가 3~4행에 있는 병합셀 구조 xlsx 파일")
    uf = st.file_uploader("파일 선택", type=["xlsx","xls","csv"])

    if uf:
        df_g, err, df_detail, dbg = parse_excel(uf)

        if err:
            st.error(f"파싱 오류: {err}")
            with st.expander("🐛 디버그"):
                st.write(dbg)
        else:
            st.success(f"✅ {len(df_g)}개 계정 추출 (병합헤더:{dbg['merged_row']}행 → 실헤더:{dbg['header_row']}행)")
            st.caption("※ 같은 업체라도 매체사·수수료율이 다르면 별개 계정으로 분리됩니다.")

            vc1, vc2, vc3, vc4 = st.columns(4)
            vc1.metric("광고비 공급가 합계",  f"{dbg['ad_supply_sum']:,.0f}원")
            vc2.metric("광고비 합계금액 합계", f"{dbg['ad_total_sum']:,.0f}원")
            vc3.metric("수수료 공급가 합계",   f"{dbg['comm_supply_sum']:,.0f}원")
            vc4.metric("수수료 합계금액 합계", f"{dbg['comm_total_sum']:,.0f}원")

            with st.expander("🐛 디버그 정보"):
                st.markdown(f"**병합헤더 행**: {dbg['merged_row']}  |  **실헤더 행**: {dbg['header_row']}")
                st.markdown(f"**광고비 시작위치**: {dbg['ad_pos']}  |  **수수료 시작위치**: {dbg['comm_pos']}")
                st.markdown("**원본 컬럼명**"); st.write(dbg["orig_cols"])
                st.markdown("**컬럼 매핑 결과**"); st.json(dbg["rename_map"])
                st.markdown("**매핑 후 컬럼**"); st.write(dbg.get("raw_cols"))
                st.markdown("**상위 20행 (매핑 후)**")
                st.dataframe(pd.DataFrame(dbg["raw_sample"]), use_container_width=True)
                st.markdown("**그룹핑 결과 상위 10행**")
                st.dataframe(pd.DataFrame(dbg["group_sample"]), use_container_width=True)

            st.session_state["uploaded_df"]  = df_g
            st.session_state["upload_dbg"]   = dbg

            show = [c for c in ["display_name","customer_id","ad_account_no","매체사",
                                  "ad_supply","ad_total","comm_rate","comm_supply","comm_total"]
                    if c in df_g.columns]
            st.markdown("**추출된 계정 목록**")
            st.dataframe(df_g[show], use_container_width=True, hide_index=True)

# ─── 업체 분류 탭 ─────────────────────────────────────────────────────────────
with t_cl:
    st.subheader("업체별 프리랜서 분류 및 정산율 설정")
    df = st.session_state.get("uploaded_df")
    if df is None:
        st.info("엑셀 업로드 탭에서 파일을 먼저 업로드해주세요.")
    else:
        st.caption("같은 업체명이라도 매체사·수수료율이 다르면 별개 카드로 표시됩니다.")

        for _, row in df.iterrows():
            cid    = str(row.get("customer_id","")).strip()
            ano    = str(row.get("ad_account_no","")).strip()
            aid    = str(row.get("account_id","")).strip()
            name   = str(row.get("계정명","")).strip()
            disp   = str(row.get("display_name", name)).strip()
            media  = _norm_media(row.get("매체사",""))
            cr     = float(row.get("comm_rate", 0))   # 상위 수수료율
            cr_pct = cr * 100 if cr < 1 else cr       # 항상 % 단위

            ad_s  = float(row.get("ad_supply",  0))
            ad_v  = float(row.get("ad_vat",     0))
            ad_t  = float(row.get("ad_total",   0))
            cm_s  = float(row.get("comm_supply",0))
            cm_v  = float(row.get("comm_vat",   0))
            cm_t  = float(row.get("comm_total", 0))

            ex  = get_mapping(cid, ano, media, cr_pct) or {}
            wk  = _wk(cid, ano, media, cr_pct)

            is_locked = ex.get("locked", True) if ex else True
            lock_icon = "🔒" if is_locked else "🔓"
            media_lbl = media or "—"
            label = (f"{lock_icon} **{disp}** │ CID:{cid} │ "
                     f"{media_lbl} {cr_pct:.1f}% │ 광고비:{w(ad_s)}")

            with st.expander(label, expanded=(ex.get("freelancer","미분류")=="미분류")):
                # ── 계정 요약 정보 ──────────────────────────────────────
                st.markdown(
                    f"**{media_lbl}** &nbsp; `{cr_pct:.1f}%`  \n"
                    f"광고비 공급가: **{w(ad_s)}** &nbsp;│&nbsp; 수수료 공급가: **{w(cm_s)}**",
                    unsafe_allow_html=True,
                )
                st.markdown("")

                lc, rc = st.columns([2, 3])

                with lc:
                    fl_idx = FREELANCERS.index(ex["freelancer"]) if ex.get("freelancer") in FREELANCERS else 0
                    fl     = st.selectbox("담당 프리랜서", FREELANCERS, index=fl_idx, key=f"fl_{wk}")
                    is_own = st.checkbox("대표 직접 운영", ex.get("is_owner_managed", False), key=f"own_{wk}")
                    locked = st.checkbox("🔒 담당자 고정 (다음 업로드 시 유지)",
                                         ex.get("locked", True), key=f"lk_{wk}")
                    fr = st.number_input("프리랜서 기본 정산율(%)", 0.0, 100.0,
                                         float(ex.get("freelancer_rate", 0)), step=0.5, key=f"fr_{wk}")
                    rr = st.number_input("리베이트율(%)", 0.0, 100.0,
                                         float(ex.get("rebate_rate", 0)), step=0.5, key=f"rr_{wk}")
                    st.markdown("---")
                    direct_mode = st.checkbox("💡 광고주 직접 수수료 구조 (구글 등)",
                                              ex.get("direct_commission_mode", False),
                                              key=f"dm_{wk}")
                    direct_rate = 0.0
                    if direct_mode:
                        direct_rate = st.number_input("광고주 직접 수수료율(%)", 0.0, 100.0,
                                                      float(ex.get("direct_commission_rate", 0)),
                                                      step=0.5, key=f"dr_{wk}")

                with rc:
                    r = calc(ad_s, ad_t, cm_s, fr, rr, is_own, direct_mode, direct_rate)

                    data_rows = [("광고비 공급가", w(ad_s)),
                                 ("광고비 VAT",   w(ad_v)),
                                 ("광고비 합계",  w(ad_t))]

                    if direct_mode:
                        data_rows += [
                            ("───","───"),
                            ("광고주 직접 수수료율",    pct(direct_rate)),
                            ("광고주 직접 수수료 금액", w(r["direct_comm"])),
                        ]
                    else:
                        data_rows += [
                            ("상위 수수료율",  pct(cr_pct)),
                            ("수수료 공급가",  w(cm_s)),
                            ("수수료 VAT",     w(cm_v)),
                            ("수수료 합계",    w(cm_t)),
                        ]

                    data_rows += [
                        ("───","───"),
                        ("프리랜서 정산율",           pct(fr)),
                        ("리베이트율",                pct(rr)),
                        ("실지급률",                  pct(r["eff_pct"])),
                        ("───","───"),
                        ("리베이트 지급액",           w(r["rebate"])),
                        ("프리랜서 공제전 지급액",    w(r["fl_gross"])),
                        ("프리랜서 3.3% 공제액",      w(r["fl_tax"])),
                        ("프리랜서 공제후 실수령액",  w(r["fl_net"])),
                        ("───","───"),
                        ("대표 수익",                 w(r["owner"])),
                        ("대표 세후 추정 (×0.8)",     w(round(r["owner"] * 0.8))),
                    ]

                    tbl = "| 항목 | 금액 |\n|---|---:|\n"
                    for k, v in data_rows:
                        tbl += f"| {k} | {v} |\n"
                    st.markdown(tbl)
                    if r["warn"]: st.error("⚠️ 실지급률이 음수입니다!")

                if st.button("💾 저장", key=f"sv_{wk}", type="primary"):
                    upsert_mapping(cid, ano, aid, name, disp, media, cr_pct,
                                   fl, fr, rr, is_own, direct_mode, direct_rate, locked)
                    st.success(f"✅ {disp} ({media_lbl} {cr_pct:.1f}%) 저장 완료")
                    st.rerun()

        st.divider()
        if st.button("💾 전체 일괄 저장", type="primary", use_container_width=True):
            for _, row in df.iterrows():
                cid    = str(row.get("customer_id","")).strip()
                ano    = str(row.get("ad_account_no","")).strip()
                aid    = str(row.get("account_id","")).strip()
                name   = str(row.get("계정명","")).strip()
                disp   = str(row.get("display_name","")).strip()
                media  = _norm_media(row.get("매체사",""))
                cr     = float(row.get("comm_rate", 0))
                cr_pct = cr * 100 if cr < 1 else cr
                wk     = _wk(cid, ano, media, cr_pct)
                upsert_mapping(
                    cid, ano, aid, name, disp, media, cr_pct,
                    st.session_state.get(f"fl_{wk}","미분류"),
                    float(st.session_state.get(f"fr_{wk}",0)),
                    float(st.session_state.get(f"rr_{wk}",0)),
                    bool(st.session_state.get(f"own_{wk}",False)),
                    bool(st.session_state.get(f"dm_{wk}",False)),
                    float(st.session_state.get(f"dr_{wk}",0)),
                    bool(st.session_state.get(f"lk_{wk}",True)),
                )
            st.success("✅ 전체 저장 완료"); st.rerun()

# ─── 미분류 탭 ────────────────────────────────────────────────────────────────
with t_un:
    st.subheader("미분류 업체")
    df = st.session_state.get("uploaded_df")
    if df is None:
        st.info("엑셀을 먼저 업로드해주세요.")
    else:
        unc = []
        for _, row in df.iterrows():
            cid    = str(row.get("customer_id","")).strip()
            ano    = str(row.get("ad_account_no","")).strip()
            disp   = str(row.get("display_name","")).strip()
            media  = _norm_media(row.get("매체사",""))
            cr     = float(row.get("comm_rate", 0))
            cr_pct = cr * 100 if cr < 1 else cr
            m = get_mapping(cid, ano, media, cr_pct)
            if not m or m.get("freelancer","미분류") in ["미분류",""]:
                unc.append({
                    "업체명": disp, "매체사": media or "—",
                    "상위수수료율": pct(cr_pct),
                    "CustomerID": cid, "AdAccountNo": ano,
                    "광고비 공급가": w(float(row.get("ad_supply",0))),
                    "수수료 공급가": w(float(row.get("comm_supply",0))),
                })

        total, remain = len(df), len(unc)
        c1, c2 = st.columns(2)
        c1.metric("미분류", f"{remain}개", delta=f"전체 {total}개")
        c2.metric("분류 완료", f"{total-remain}개")
        if remain == 0: st.success("✅ 모든 계정 분류 완료")
        else:
            st.warning(f"⚠️ {remain}개 미분류")
            st.dataframe(pd.DataFrame(unc), use_container_width=True, hide_index=True)
        st.divider()
        if st.button("✅ 정산 확정", type="primary", disabled=(remain > 0), use_container_width=True):
            st.success("정산이 확정되었습니다.")

# ─── 프리랜서 정산 탭 ─────────────────────────────────────────────────────────
with t_fl:
    st.subheader("프리랜서별 정산 집계")
    df = st.session_state.get("uploaded_df")
    if df is None:
        st.info("엑셀을 먼저 업로드해주세요.")
    else:
        fl_sum, details = {}, []
        for _, row in df.iterrows():
            cid    = str(row.get("customer_id","")).strip()
            ano    = str(row.get("ad_account_no","")).strip()
            disp   = str(row.get("display_name","")).strip()
            media  = _norm_media(row.get("매체사",""))
            cr     = float(row.get("comm_rate", 0))
            cr_pct = cr * 100 if cr < 1 else cr
            m      = get_mapping(cid, ano, media, cr_pct) or {}
            fl     = m.get("freelancer","미분류")
            fr     = float(m.get("freelancer_rate",0))
            rr     = float(m.get("rebate_rate",0))
            is_o   = m.get("is_owner_managed",False)
            dm     = m.get("direct_commission_mode",False)
            dr     = float(m.get("direct_commission_rate",0))
            ad_s   = float(row.get("ad_supply",0))
            ad_t   = float(row.get("ad_total",0))
            cm_s   = float(row.get("comm_supply",0))
            r      = calc(ad_s, ad_t, cm_s, fr, rr, is_o, dm, dr)

            details.append({
                "프리랜서": fl, "업체명": disp,
                "매체사": media or "—", "상위수수료율": pct(cr_pct),
                "광고비 공급가": int(ad_s), "광고비 합계": int(ad_t),
                "수수료 공급가": int(cm_s),
                "기본 정산율(%)": fr, "리베이트율(%)": rr,
                "실지급률(%)": r["eff_pct"],
                "리베이트 지급액": r["rebate"],
                "프리랜서 지급액": r["fl_gross"],
                "대표 수익": r["owner"],
                "⚠️": "⚠️" if r["warn"] else "",
            })
            g = fl_sum.setdefault(fl, {k:0 for k in
                ["업체수","광고비 공급가","광고비 합계","수수료 공급가",
                 "리베이트 지급액","프리랜서 지급액","대표 수익"]})
            g["업체수"]         += 1
            g["광고비 공급가"]   += int(ad_s)
            g["광고비 합계"]     += int(ad_t)
            g["수수료 공급가"]   += int(cm_s)
            g["리베이트 지급액"] += r["rebate"]
            g["프리랜서 지급액"] += r["fl_gross"]
            g["대표 수익"]       += r["owner"]

        for wd in [d for d in details if d["⚠️"]]:
            st.warning(f"⚠️ **{wd['업체명']}** ({wd['매체사']}): 실지급률 음수 ({wd['실지급률(%)']:.1f}%)")

        # 프리랜서 요약
        if fl_sum:
            st.markdown("**프리랜서별 요약**")
            s_rows = []
            for k, g in fl_sum.items():
                s_rows.append({
                    "프리랜서": k, "계정수": g["업체수"],
                    "광고비 공급가":   w(g["광고비 공급가"]),
                    "광고비 합계":     w(g["광고비 합계"]),
                    "수수료 공급가":   w(g["수수료 공급가"]),
                    "리베이트 지급액": w(g["리베이트 지급액"]),
                    "프리랜서 지급액": w(g["프리랜서 지급액"]),
                    "대표 수익":       w(g["대표 수익"]),
                    "대표 세후 추정":  w(round(g["대표 수익"] * 0.8)),
                })
            s_rows.append({
                "프리랜서":"합계",
                "계정수": sum(g["업체수"] for g in fl_sum.values()),
                "광고비 공급가":   w(sum(g["광고비 공급가"]   for g in fl_sum.values())),
                "광고비 합계":     w(sum(g["광고비 합계"]     for g in fl_sum.values())),
                "수수료 공급가":   w(sum(g["수수료 공급가"]   for g in fl_sum.values())),
                "리베이트 지급액": w(sum(g["리베이트 지급액"] for g in fl_sum.values())),
                "프리랜서 지급액": w(sum(g["프리랜서 지급액"] for g in fl_sum.values())),
                "대표 수익":       w(sum(g["대표 수익"]       for g in fl_sum.values())),
                "대표 세후 추정":  w(round(sum(g["대표 수익"] for g in fl_sum.values()) * 0.8)),
            })
            st.dataframe(
                pd.DataFrame(s_rows).style.apply(_style_fl, axis=0),
                use_container_width=True, hide_index=True,
            )

        # 업체별 상세
        st.markdown("**계정별 상세**")
        fmt_details = []
        for d in sorted(details, key=lambda x: x["프리랜서"]):
            fmt_details.append({
                "프리랜서":    d["프리랜서"],
                "업체명":      d["업체명"],
                "매체사":      d["매체사"],
                "상위수수료율": d["상위수수료율"],
                "광고비 공급가": w(d["광고비 공급가"]),
                "광고비 합계":   w(d["광고비 합계"]),
                "수수료 공급가": w(d["수수료 공급가"]),
                "기본 정산율":   pct(d["기본 정산율(%)"]),
                "리베이트율":    pct(d["리베이트율(%)"]),
                "실지급률":      pct(d["실지급률(%)"]),
                "리베이트 지급액": w(d["리베이트 지급액"]),
                "프리랜서 지급액": w(d["프리랜서 지급액"]),
                "대표 수익":       w(d["대표 수익"]),
                "대표 세후 추정":  w(round(d["대표 수익"] * 0.8)),
                "⚠️": d["⚠️"],
            })
        st.dataframe(
            pd.DataFrame(fmt_details).style.apply(_style_fl, axis=0),
            use_container_width=True, hide_index=True,
        )

        d_df = pd.DataFrame(details).sort_values("프리랜서")
        st.download_button("📥 CSV 다운로드",
            d_df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig"),
            file_name=f"정산_{sel_ym or 'all'}.csv", mime="text/csv")

# ─── 기타비용 탭 ──────────────────────────────────────────────────────────────
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
                    exps.append({"id":str(uuid.uuid4()),"year_month":sel_ym,
                                 "name":en.strip(),"amount":int(ea),
                                 "memo":em.strip(),"created_at":date.today().isoformat()})
                    save_expenses(exps); st.rerun()

        month_exp = get_expenses_for_month(sel_ym)
        if month_exp:
            all_exp = load_expenses()
            for e in month_exp:
                c1,c2,c3,c4,c5 = st.columns([2,2,3,1,1])
                c1.markdown(f"**{e['name']}**")
                na = c2.number_input("금액", e["amount"], step=1000, key=f"ea_{e['id']}", label_visibility="collapsed")
                nm = c3.text_input("메모", e.get("memo",""), key=f"em_{e['id']}", label_visibility="collapsed")
                if c4.button("저장", key=f"es_{e['id']}"):
                    for x in all_exp:
                        if x["id"]==e["id"]: x["amount"]=int(na); x["memo"]=nm
                    save_expenses(all_exp); st.rerun()
                if c5.button("🗑️", key=f"ed_{e['id']}"):
                    save_expenses([x for x in all_exp if x["id"]!=e["id"]]); st.rerun()
            st.divider()
            st.metric("합계", w(sum(e["amount"] for e in month_exp)))
        else:
            st.info("이 달의 기타비용이 없습니다.")

# ─── 월 손익 탭 ───────────────────────────────────────────────────────────────
with t_pnl:
    st.subheader("월별 손익")
    if not sel_ym:
        st.info("상단에서 정산 월을 선택해주세요.")
    else:
        df      = st.session_state.get("uploaded_df")
        exps    = get_expenses_for_month(sel_ym)
        extra   = get_extra(sel_ym)
        tot_exp = sum(e["amount"] for e in exps)

        search_owner_profit      = 0   # 권혁우(대표) 담당 계정의 대표 수익 합계
        search_freelancer_profit = 0   # 나머지 프리랜서 계정의 대표 수익 합계

        if df is not None:
            for _, row in df.iterrows():
                cid    = str(row.get("customer_id","")).strip()
                ano    = str(row.get("ad_account_no","")).strip()
                media  = _norm_media(row.get("매체사",""))
                cr     = float(row.get("comm_rate", 0))
                cr_pct = cr * 100 if cr < 1 else cr
                m      = get_mapping(cid, ano, media, cr_pct) or {}
                fl     = m.get("freelancer", "미분류")
                r      = calc(float(row.get("ad_supply",0)),
                              float(row.get("ad_total",0)),
                              float(row.get("comm_supply",0)),
                              float(m.get("freelancer_rate",0)),
                              float(m.get("rebate_rate",0)),
                              m.get("is_owner_managed",False),
                              m.get("direct_commission_mode",False),
                              float(m.get("direct_commission_rate",0)))
                if fl == OWNER_FL:
                    search_owner_profit      += r["owner"]
                else:
                    search_freelancer_profit += r["owner"]

        with st.form("extra_rev"):
            xc1,xc2,xc3 = st.columns(3)
            with xc1: place = st.number_input("플레이스 수익(원)", float(extra["place_revenue"]), step=10000.0)
            with xc2: blog  = st.number_input("블로그 수익(원)",   float(extra["blog_revenue"]),  step=10000.0)
            with xc3: xm    = st.text_input("메모", extra.get("memo",""))
            if st.form_submit_button("💾 저장"):
                set_extra(sel_ym, int(place), int(blog), xm); st.rerun()

        place_rev  = int(extra["place_revenue"])
        blog_rev   = int(extra["blog_revenue"])

        search_total_profit          = search_owner_profit + search_freelancer_profit
        gross_total_profit           = search_total_profit + place_rev + blog_rev
        gross_total_profit_after_tax = round(gross_total_profit * 0.8)
        final_net_profit             = gross_total_profit - tot_exp
        final_net_profit_after_tax   = gross_total_profit_after_tax - tot_exp

        st.divider()

        r1 = st.columns(5)
        r1[0].metric("검색광고 대표 직접수익",    w(search_owner_profit))
        r1[1].metric("검색광고 프리랜서 계정수익", w(search_freelancer_profit))
        r1[2].metric("검색광고 총수익",            w(search_total_profit))
        r1[3].metric("플레이스",                   w(place_rev))
        r1[4].metric("블로그",                     w(blog_rev))

        r2 = st.columns(5)
        r2[0].metric("총 수익",                  w(gross_total_profit))
        r2[1].metric("총 수익 세후 추정",         w(gross_total_profit_after_tax))
        r2[2].metric("기타비용 합계",             w(tot_exp),
                     delta=f"-{tot_exp:,}" if tot_exp else None)
        r2[3].metric("월 최종 순수익",            w(final_net_profit))
        r2[4].metric("월 최종 세후 추정 순수익",  w(final_net_profit_after_tax))

        if df is None:
            st.warning("엑셀 없음 — 검색광고 수익 0원으로 계산됩니다.")
