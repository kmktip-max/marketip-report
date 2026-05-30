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
from db import sb_load, sb_save

# ── 상수 ─────────────────────────────────────────────────────────────────────
FREELANCERS = [
    "미분류", "권혁우", "최은성", "조성지", "임예슬", "홍선기",
    "안주희", "이승준", "문성빈", "김하린", "김주훈", "대표 직접",
]
OWNER_FL   = "권혁우"   # 대표가 직접 담당하는 프리랜서명
F_MAPPING  = os.path.join(ROOT, "freelancer_mapping.json")
F_EXPENSES = os.path.join(ROOT, "other_expenses.json")
F_EXTRA    = os.path.join(ROOT, "monthly_extra_revenue.json")
F_PNL      = os.path.join(ROOT, "monthly_pnl_data.json")
F_ANNUAL   = os.path.join(ROOT, "annual_pnl.json")

# ── 관리자 전용 ───────────────────────────────────────────────────────────────
if st.session_state.get("auth_type") != "admin":
    st.error("🔒 관리자만 접근 가능합니다.")
    st.stop()


# ── 스토리지 헬퍼 (세션 캐시 → Supabase → JSON 폴백) ────────────────────────
def _sc_load(key, sb_key, path):
    """세션 내 캐시 우선 로드. 없으면 Supabase에서 로드 후 캐시."""
    if key not in st.session_state:
        st.session_state[key] = sb_load(sb_key, path) or []
    return st.session_state[key]

def _sc_save(key, sb_key, path, data):
    """저장 후 세션 캐시도 갱신."""
    st.session_state[key] = data
    sb_save(sb_key, data, path)

load_mapping  = lambda: _sc_load("_c_mapping",  "freelancer_mapping",    F_MAPPING)
save_mapping  = lambda d: _sc_save("_c_mapping", "freelancer_mapping",   F_MAPPING, d)
load_expenses = lambda: _sc_load("_c_expenses", "other_expenses",        F_EXPENSES)
save_expenses = lambda d: _sc_save("_c_expenses","other_expenses",       F_EXPENSES, d)
load_extra    = lambda: _sc_load("_c_extra",    "monthly_extra_revenue", F_EXTRA)
save_extra    = lambda d: _sc_save("_c_extra",   "monthly_extra_revenue",F_EXTRA, d)
load_pnl      = lambda: _sc_load("_c_pnl",      "monthly_pnl",          F_PNL)
save_pnl      = lambda d: _sc_save("_c_pnl",    "monthly_pnl",          F_PNL, d)
load_annual   = lambda: _sc_load("_c_annual",   "annual_pnl",           F_ANNUAL)
save_annual   = lambda d: _sc_save("_c_annual", "annual_pnl",           F_ANNUAL, d)

# ── 프리랜서명 오타 마이그레이션 (임예솔 → 임예슬) — 세션당 1회 ─────────────
if "_migrated" not in st.session_state:
    _RENAME = {"임예솔": "임예슬"}
    _mdata  = load_mapping()
    _changed = False
    for _m in _mdata:
        if _m.get("freelancer") in _RENAME:
            _m["freelancer"] = _RENAME[_m["freelancer"]]
            _changed = True
    if _changed:
        save_mapping(_mdata)
    st.session_state["_migrated"] = True

def upsert_pnl(ym, search_owner, search_fl,
               place_revenue, place_cost, blog_revenue, blog_cost,
               expenses, gross, after_tax, net, net_after_tax):
    data = load_pnl()
    entry = {
        "year_month": ym,
        "search_owner_profit":      int(round(search_owner)),
        "search_freelancer_profit": int(round(search_fl)),
        "place_revenue":            int(place_revenue),
        "place_cost":               int(place_cost),
        "place_profit":             int(place_revenue - place_cost),
        "blog_revenue":             int(blog_revenue),
        "blog_cost":                int(blog_cost),
        "blog_profit":              int(blog_revenue - blog_cost),
        "other_expenses":           int(expenses),
        "gross_total_profit":       int(round(gross)),
        "gross_after_tax":          int(round(after_tax)),
        "final_net_profit":         int(round(net)),
        "final_net_after_tax":      int(round(net_after_tax)),
        "confirmed_at":             date.today().isoformat(),
    }
    for r in data:
        if r.get("year_month") == ym:
            r.update(entry); save_pnl(data); break
    else:
        data.append(entry); save_pnl(data)
    # 연간 손익 탭에도 자동 반영
    try:
        yr, mo = int(ym[:4]), int(ym[5:7])
        upsert_annual(yr, mo,
                      int(round(net_after_tax)),  # 세후순수익
                      int(expenses))              # 기타비용
    except Exception:
        pass

def upsert_annual(year, month, after_tax_profit, other_expenses):
    """
    after_tax_profit : 세후순수익 (입력값)
    other_expenses   : 기타비용 (입력값)
    net_amount       : 기타비용 제외 금액 = after_tax_profit - other_expenses (자동)
    """
    data = load_annual()
    net  = max(0, int(after_tax_profit) - int(other_expenses))
    entry = {
        "year": int(year), "month": int(month),
        "after_tax_profit": int(after_tax_profit),
        "other_expenses":   int(other_expenses),
        "net_amount":       net,
    }
    for r in data:
        if r.get("year") == int(year) and r.get("month") == int(month):
            r.update(entry); save_annual(data); return
    data.append(entry); save_annual(data)

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
    return {"year_month": ym,
            "place_revenue": 0, "place_cost": 0,
            "blog_revenue": 0,  "blog_cost": 0,
            "memo": ""}

def set_extra(ym, place_revenue, place_cost, blog_revenue, blog_cost, memo=""):
    data = load_extra()
    upd  = {"place_revenue": place_revenue, "place_cost": place_cost,
            "blog_revenue":  blog_revenue,  "blog_cost":  blog_cost, "memo": memo}
    for r in data:
        if r["year_month"] == ym:
            r.update(upd); save_extra(data); return
    data.append({"year_month": ym, **upd})
    save_extra(data)

# ── 숫자 포맷 ─────────────────────────────────────────────────────────────────
def w(n):   return f"{int(round(n)):,} 원"
def pct(p): return f"{p:.1f}%"

# ── 엑셀 파싱 ─────────────────────────────────────────────────────────────────
def _norm(s): return re.sub(r'[\s\(\)\[\]\{\}%]', '', str(s)).lower()

def _find_sections(df_raw):
    for i in range(min(10, len(df_raw))):
        vals = list(df_raw.iloc[i].values)
        ad_p = comm_p = None
        for j, v in enumerate(vals):
            sv = str(v).strip()
            # 광고비 섹션: "광고비" 정확 일치 또는 "광고매출" 포함
            if (sv == "광고비" or "광고매출" in sv) and ad_p is None: ad_p = j
            # 수수료 섹션: "지급수수료" 또는 "수수료" 포함 (단, 지급수수료율 단독 컬럼은 제외)
            if "수수료" in sv and "율" not in sv and comm_p is None: comm_p = j
        if ad_p is not None and comm_p is not None:
            return i, ad_p, comm_p
    return None, None, None

# 헤더 행 앵커 컬럼명 (어떤 것이 있으면 헤더 행으로 인식)
_HEADER_ANCHORS = {
    "계정명", "광고주명", "광고주 명", "광고주이름", "업체명",
    "광고주ID", "광고주 ID", "광고주id", "광고주 id",
}

def _find_header(df_raw, merged_row):
    """헤더 앵커 컬럼 중 하나라도 있는 행 반환 (다양한 포맷 지원)"""
    start = (merged_row + 1) if merged_row is not None else 0
    for i in range(start, min(start + 8, len(df_raw))):
        vals = {str(v).strip() for v in df_raw.iloc[i].values}
        if _HEADER_ANCHORS & vals: return i
    for i in range(min(15, len(df_raw))):
        vals = {str(v).strip() for v in df_raw.iloc[i].values}
        if _HEADER_ANCHORS & vals: return i
    return (merged_row + 1) if merged_row is not None else 0

# 계정명 동의어 (순서대로 시도)
_ACCOUNT_NAME_SYNONYMS = ["계정명", "광고주명", "광고주 명", "업체명", "광고주이름"]

_FIXED_MAP = {
    # 매체사
    "매체사":"매체사", "매체":"매체사",
    "담당자":"담당자",
    # 계정 ID
    "계정id":"account_id",
    # customer_id 동의어
    "계정번호customerid":"customer_id", "customerid":"customer_id",
    "광고주id":"customer_id",           # 신규 포맷: 광고주 ID
    # ad_account_no 동의어
    "계정번호adaccountno":"ad_account_no", "adaccountno":"ad_account_no",
    # 계정명 동의어 (정규화 후)
    "계정명":"계정명", "광고주명":"계정명", "업체명":"계정명", "광고주이름":"계정명",
}

def parse_excel(f):
    try:
        df_raw = pd.read_excel(f, header=None, engine="openpyxl")
    except Exception as e:
        return None, str(e), None, {}

    merged_row, ad_p, comm_p = _find_sections(df_raw)
    hr = _find_header(df_raw, merged_row)
    df = pd.read_excel(f, header=hr, engine="openpyxl")

    # ── Unnamed 컬럼 복원: 병합셀로 인해 헤더 행에 이름이 없는 컬럼은
    #    위 행(df_raw)에서 의미 있는 텍스트를 역방향으로 탐색해 채움
    _cols = list(df.columns)
    for _ci, _col in enumerate(_cols):
        if "Unnamed" in str(_col) or str(_col).strip() in ("", "nan", "None"):
            for _ri in range(hr - 1, -1, -1):
                if _ci < df_raw.shape[1]:
                    _v = str(df_raw.iloc[_ri, _ci]).strip()
                    if _v and _v.lower() not in ("nan","none") and "Unnamed" not in _v:
                        _cols[_ci] = _v; break
    df.columns = _cols
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
        # 이름 기반 폴백 — 다양한 대행사 포맷 지원
        _NAME = {
            **_FIXED_MAP,
            # 광고비 공급가 동의어
            "광고비공급가":"ad_supply", "공급가":"ad_supply", "공급가액":"ad_supply",
            # 광고비 VAT 동의어
            "광고비세액":"ad_vat", "세액":"ad_vat", "vat":"ad_vat",
            # 광고비 합계 동의어
            "광고비합계금액":"ad_total", "합계금액":"ad_total", "total":"ad_total",
            # 수수료율 동의어 (괄호·% 등은 _norm()에서 제거 후 비교)
            "수수료율":"comm_rate", "지급수수료율":"comm_rate",
            "지급수수료율":"comm_rate", "상위수수료율":"comm_rate",
            "commissionrate":"comm_rate", "feerate":"comm_rate",
            # 수수료 공급가 동의어
            "수수료공급가":"comm_supply", "공급가.1":"comm_supply",
            # 수수료 VAT 동의어
            "수수료세액":"comm_vat", "세액.1":"comm_vat", "수수료부가세":"comm_vat",
            # 수수료 합계 동의어
            "수수료합계금액":"comm_total", "합계금액.1":"comm_total",
            "수수료합계":"comm_total",     "합계.1":"comm_total",
        }
        for c in orig:
            nc = _norm(c)
            std = _NAME.get(nc)
            if std and std not in rename.values():
                rename[c] = std

    debug["rename_map"] = {str(k): v for k, v in rename.items()}
    df = df.rename(columns=rename)

    # 계정명 컬럼 확보 — 다양한 동의어 순서대로 시도
    if "계정명" not in df.columns:
        for _syn in _ACCOUNT_NAME_SYNONYMS:
            if _syn in df.columns:
                df = df.rename(columns={_syn: "계정명"}); break
        else:
            for c in df.columns:
                nc2 = _norm(c)
                if any(nc2 == _norm(s) for s in _ACCOUNT_NAME_SYNONYMS):
                    df = df.rename(columns={c: "계정명"}); break
    # 여전히 없으면 customer_id 또는 account_id로 대체
    if "계정명" not in df.columns:
        for _fb in ["customer_id", "account_id"]:
            if _fb in df.columns:
                df["계정명"] = df[_fb].astype(str)
                break
        else:
            return None, f"계정명 컬럼 없음. 원본: {orig}", df, debug

    df = df[df["계정명"].notna()].copy()
    df = df[~df["계정명"].astype(str).str.strip().str.match(
        r"^(합계|소계|TOTAL|합\s*계|nan)$", na=False)]
    df = df[df["계정명"].astype(str).str.strip().replace("nan","") != ""]

    NUM = ["ad_supply","ad_vat","ad_total","comm_supply","comm_vat","comm_total","comm_rate"]
    for col in NUM:
        if col in df.columns:
            df[col] = pd.to_numeric(
                df[col].astype(str)
                       .str.replace(",", "")
                       .str.replace("원", "")
                       .str.replace("%", "")   # "14.0%" → "14.0" 처리
                       .str.strip(),
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

    # ── 수수료율 역산 fallback ──────────────────────────────────────────────
    # comm_rate == 0인데 comm_supply / ad_supply 가 있으면 역산
    if all(c in df.columns for c in ["comm_rate","comm_supply","ad_supply"]):
        _mask = (df["comm_rate"] == 0) & (df["comm_supply"] > 0) & (df["ad_supply"] > 0)
        if _mask.any():
            df.loc[_mask, "comm_rate"] = (
                df.loc[_mask, "comm_supply"] / df.loc[_mask, "ad_supply"] * 100
            ).round(1)
            debug["comm_rate_fallback"] = (
                f"{_mask.sum()}개 계정에서 수수료율 역산 적용 "
                f"(comm_supply / ad_supply × 100)"
            )
        # 역산 후에도 0이면 경고
        _warn = (df["comm_rate"] == 0) & (df["comm_supply"] > 0)
        if _warn.any():
            debug["comm_rate_warn"] = (
                "⚠️ 수수료 공급가는 있으나 수수료율 인식 실패: "
                + ", ".join(df.loc[_warn, "display_name"].astype(str).head(5).tolist())
            )
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

# ── 대표 정산공유용 매체별 기본 정산율 ───────────────────────────────────────
def _owner_calc(ad_supply, ad_total, fr_pct, rr_pct):
    """권혁우(대표) 전용: 3.3% 공제 없이 공급가×정산율 - 리베이트."""
    rebate   = round(ad_total * rr_pct / 100)
    fl_gross = round(ad_supply * fr_pct / 100)
    fl_net   = fl_gross - rebate
    return {"eff_pct": fr_pct - rr_pct, "fl_gross": fl_gross, "fl_tax": 0,
            "fl_net": fl_net, "rebate": rebate, "owner": 0,
            "direct_comm": 0, "warn": fl_net < 0, "direct": False}

def _owner_share_rate(media: str, display_name: str = "") -> float:
    """권혁우(대표) 정산공유 카드 전용: 매체명 기준 기본 정산율(%) 반환."""
    t = f"{media} {display_name}".lower()
    if "구글" in t or "google" in t:
        return 0.0
    if "애드부스트" in t or "adboost" in t or "ad boost" in t:
        return 9.5
    if "당근" in t:
        return 12.0
    if ("카카오" in t or "kakao" in t or "모먼트" in t
            or "키워드광고" in t and "카카오" in t):
        return 14.5
    if "gfa" in t or "성과형" in t or "da" in t:
        return 14.5
    if ("브랜드검색" in t or "브랜드라이트" in t or "브검" in t
            or "brand" in t):
        return 14.5
    # 네이버 CPC / 쇼핑 / 파워링크 / 기타 네이버
    if "네이버" in t or "cpc" in t or "쇼핑" in t or "파워링크" in t:
        return 14.5
    return 14.5  # 미분류도 기본 14.5%


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

# ── 정산 공유 PNG 생성 (Pillow 기반 — 한글 안정 렌더링) ──────────────────────
def _gen_share_png(fl_name, ym, rows, total_gross, total_tax, total_net):
    from PIL import Image, ImageDraw, ImageFont
    from io import BytesIO
    import os

    # 한글 TTF 폰트 탐색 (Bold / Regular)
    _FONT_CANDS = {
        "bold": [
            "C:/Windows/Fonts/malgunbd.ttf",          # Windows Malgun Gothic Bold
            "C:/Windows/Fonts/malgun.ttf",
            "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
            "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
            "/System/Library/Fonts/AppleSDGothicNeo.ttc",
        ],
        "regular": [
            "C:/Windows/Fonts/malgun.ttf",
            "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/System/Library/Fonts/AppleSDGothicNeo.ttc",
        ],
    }

    def _font(size, bold=False):
        for p in _FONT_CANDS["bold" if bold else "regular"]:
            if os.path.exists(p):
                try: return ImageFont.truetype(p, size)
                except: pass
        try: return ImageFont.truetype(size)
        except: return ImageFont.load_default()

    def _rr(draw, xy, r, fill=None, outline=None, lw=1):
        """rounded_rectangle 호환 래퍼 (Pillow < 8.2 fallback)"""
        try:
            draw.rounded_rectangle(xy, radius=r, fill=fill, outline=outline, width=lw)
        except AttributeError:
            draw.rectangle(xy, fill=fill, outline=outline, width=lw)

    def _tw(draw, text, font):
        try:
            bb = draw.textbbox((0,0), text, font=font)
            return bb[2] - bb[0]
        except AttributeError:
            return draw.textsize(text, font=font)[0]

    yr = ym[:4]; mo = ym[5:7].lstrip("0") if len(ym) >= 7 else ""
    W = 620; PAD = 28; ROW_H = 92

    f_hdr  = _font(19, bold=True)
    f_name = _font(16, bold=True)
    f_co   = _font(14, bold=True)
    f_med  = _font(11)
    f_sub  = _font(12)
    f_amt  = _font(15, bold=True)
    f_lbl  = _font(13)
    f_nlbl = _font(14, bold=True)
    f_nval = _font(22, bold=True)
    f_foot = _font(12)

    HDR_H  = 62
    NAME_H = 50
    SEP_H  = 26
    SUM_H  = 40 + 40 + 76   # 공제전 + 공제액 + 실수령박스
    FOOT_H = 44
    IMG_H  = HDR_H + NAME_H + len(rows) * ROW_H + SEP_H + SUM_H + FOOT_H + 30

    img  = Image.new("RGB", (W, IMG_H), "#FFFFFF")
    draw = ImageDraw.Draw(img)

    y = 10

    # ── 빨간 헤더 ────────────────────────────────────────────────────────────
    _rr(draw, (PAD, y, W-PAD, y+HDR_H-10), r=10, fill="#CC0000")
    title = f"마케팁 정산 안내  |  {yr}년 {mo}월"
    draw.text(((W - _tw(draw, title, f_hdr))//2, y+18), title, font=f_hdr, fill="white")
    y += HDR_H + 6

    # ── 프리랜서명 ────────────────────────────────────────────────────────────
    draw.text((PAD, y), f"{fl_name} 프리랜서님", font=f_name, fill="#111827")
    y += NAME_H

    # ── 업체별 카드 ───────────────────────────────────────────────────────────
    for r in rows:
        _rr(draw, (PAD, y, W-PAD, y+ROW_H-6), r=10, fill="#FFFBEB", outline="#FDE68A", lw=1)
        draw.text((PAD+14, y+12), r["업체명"], font=f_co, fill="#111827")

        # 매체사 뱃지 (업체명 오른쪽)
        _med = r["매체사"] if r["매체사"] and r["매체사"] != "—" else ""
        if _med:
            _co_w = _tw(draw, r["업체명"], f_co)
            _mb_x = PAD + 14 + _co_w + 10
            _mb_w = _tw(draw, _med, f_med) + 16
            _rr(draw, (_mb_x, y+13, _mb_x+_mb_w, y+30), r=8, fill="#E0E7FF")
            draw.text((_mb_x+8, y+14), _med, font=f_med, fill="#3730A3")

        _sub = f"광고비 {r['광고비 공급가']:,}원   정산율 {r['정산율(%)']:g}%"
        draw.text((PAD+14, y+42), _sub, font=f_sub, fill="#6B7280")

        _as = f"{r['공제후 실수령액']:,}원"
        draw.text((W-PAD-14-_tw(draw, _as, f_amt), y+28), _as, font=f_amt, fill="#1D4ED8")
        y += ROW_H

    # ── 구분선 ────────────────────────────────────────────────────────────────
    y += 8
    draw.line((PAD, y, W-PAD, y), fill="#E5E7EB", width=1)
    y += 18

    # ── 소계 ─────────────────────────────────────────────────────────────────
    draw.text((PAD, y), "공제전 정산액", font=f_lbl, fill="#374151")
    _gs = f"{total_gross:,}원"
    draw.text((W-PAD-_tw(draw, _gs, f_lbl), y), _gs, font=f_lbl, fill="#374151")
    y += 40

    draw.text((PAD, y), "3.3% 공제액", font=f_lbl, fill="#DC2626")
    _tx = f"-{total_tax:,}원"
    draw.text((W-PAD-_tw(draw, _tx, f_lbl), y), _tx, font=f_lbl, fill="#DC2626")
    y += 46

    # ── 파란 실수령액 박스 ────────────────────────────────────────────────────
    _rr(draw, (PAD, y, W-PAD, y+70), r=10, fill="#EFF6FF", outline="#93C5FD", lw=2)
    draw.text((PAD+16, y+18), "공제후 실수령액", font=f_nlbl, fill="#1D4ED8")
    _nv = f"{total_net:,}원"
    draw.text((W-PAD-16-_tw(draw, _nv, f_nval), y+16), _nv, font=f_nval, fill="#1D4ED8")
    y += 84

    # ── 푸터 ─────────────────────────────────────────────────────────────────
    _ft = "입금 예정입니다"
    draw.text(((W-_tw(draw, _ft, f_foot))//2, y), _ft, font=f_foot, fill="#9CA3AF")

    buf = BytesIO()
    img.crop((0, 0, W, y + FOOT_H)).save(buf, format="PNG")
    return buf.getvalue()

# ── 리베이트 HTML 섹션 생성 헬퍼 ─────────────────────────────────────────────
def _rb_html_section(rb_list):
    if not rb_list:
        return ""
    cards = ""
    for biz_nm, d in rb_list:
        cards += f"""
<div class="rb-card">
  <div class="rb-title">🔴 {biz_nm} — 리베이트/세금계산서 안내</div>
  <div class="rb-meta">
    <span>광고비 합계: <b>{d['vat']:,}원</b></span>
    <span>리베이트율: <b>{d['rate']:.1f}%</b></span>
  </div>
  <div class="rb-amt-box">
    <div class="rb-amt-lbl">세금계산서 발행금액</div>
    <div class="rb-amt-val">{d['amt']:,}원</div>
  </div>
  <div class="rb-email">
    <span style="font-size:14px;">📧</span>
    <span class="rb-email-lbl">발행 이메일:</span>
    <span class="rb-email-val">mktip@naver.com</span>
  </div>
</div>"""
    return f'<hr class="rb-sep">{cards}'

# ── 정산 공유 HTML 생성 (Playwright PNG 소스 겸 다운로드용) ───────────────────
def _gen_share_html(fl_name, ym, rows, total_gross, total_rebate, total_tax, total_net, rb_list=None):
    yr = ym[:4]; mo = ym[5:7].lstrip("0") if len(ym) >= 7 else ""

    rows_html = ""
    for r in rows:
        media = r["매체사"] if r["매체사"] and r["매체사"] != "—" else ""
        mbadge = (f'<span class="mbadge">{media}</span>') if media else ""
        rows_html += f"""
<div class="acc-row">
  <div class="acc-info">
    <div class="acc-name">{r['업체명']}{mbadge}</div>
    <div class="acc-sub">광고비 {r['광고비 공급가']:,}원 &nbsp;|&nbsp; 정산율 {r['정산율(%)']:g}%</div>
  </div>
  <div class="acc-amt">{r['공제후 실수령액']:,}원</div>
</div>"""

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;600;700;800&display=swap" rel="stylesheet">
<style>
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{background:#F3F4F6;display:flex;justify-content:center;padding:28px 16px;
     font-family:"Malgun Gothic","Apple SD Gothic Neo","Noto Sans KR",sans-serif;}}
#settlement-card{{width:100%;max-width:680px;border:1.5px solid #E5E8ED;
                  border-radius:16px;overflow:hidden;background:#fff;}}
.hdr{{background:#CC0000;color:#fff;padding:18px 28px;font-size:18px;
      font-weight:800;text-align:center;letter-spacing:-0.3px;line-height:1.4;}}
.body{{padding:24px 26px;}}
.fl-name{{font-size:15px;font-weight:700;color:#111827;margin-bottom:16px;line-height:1.5;}}
.acc-row{{background:#FFFBEB;border:1px solid #FDE68A;border-radius:10px;
          padding:14px 16px;margin-bottom:10px;
          display:flex;justify-content:space-between;align-items:center;gap:10px;}}
.acc-name{{font-size:14px;font-weight:700;color:#111;margin-bottom:4px;line-height:1.4;}}
.acc-sub{{font-size:12px;color:#6B7280;line-height:1.5;}}
.acc-amt{{font-size:15px;font-weight:800;color:#1D4ED8;white-space:nowrap;flex-shrink:0;}}
.mbadge{{display:inline-block;background:#E0E7FF;color:#3730A3;
         font-size:10px;font-weight:600;padding:2px 7px;border-radius:100px;margin-left:7px;
         vertical-align:middle;}}
.sep{{border:none;border-top:1px solid #E5E7EB;margin:16px 0;}}
.srow{{display:flex;justify-content:space-between;align-items:center;
       margin-bottom:12px;font-size:13px;line-height:1.7;}}
.net-box{{background:#EFF6FF;border:1.5px solid #93C5FD;border-radius:10px;
          padding:16px 18px;display:flex;justify-content:space-between;
          align-items:center;gap:8px;margin:4px 0 16px;}}
.net-lbl{{font-size:14px;font-weight:700;color:#1D4ED8;line-height:1.4;}}
.net-val{{font-size:22px;font-weight:900;color:#1D4ED8;white-space:nowrap;}}
.rb-sep{{border:none;border-top:1px solid #FECACA;margin:16px 0;}}
.rb-card{{background:#FEF2F2;border:2px solid #DC2626;border-radius:12px;
          padding:14px 16px;margin-bottom:10px;}}
.rb-title{{font-size:13px;font-weight:800;color:#DC2626;
           margin-bottom:10px;letter-spacing:-0.2px;line-height:1.5;}}
.rb-meta{{display:flex;gap:16px;flex-wrap:wrap;margin-bottom:10px;line-height:1.7;}}
.rb-meta span{{font-size:12px;color:#B91C1C;}}
.rb-meta b{{font-size:13px;color:#7F1D1D;}}
.rb-amt-box{{background:#fff;border:1px solid #FECACA;border-radius:8px;
             padding:10px 14px;margin-bottom:10px;}}
.rb-amt-lbl{{font-size:11px;color:#9CA3AF;margin-bottom:4px;letter-spacing:0.2px;}}
.rb-amt-val{{font-size:18px;font-weight:900;color:#DC2626;line-height:1.2;}}
.rb-email{{display:flex;align-items:center;gap:8px;flex-wrap:wrap;
           padding:9px 13px;background:#FFE4E4;border-radius:8px;line-height:1.6;}}
.rb-email-lbl{{font-size:12px;font-weight:700;color:#B91C1C;}}
.rb-email-val{{font-size:13px;font-weight:800;color:#991B1B;letter-spacing:0.1px;}}
.foot{{text-align:center;font-size:13px;color:#9CA3AF;padding-bottom:4px;line-height:1.6;}}
@media(max-width:480px){{
  body{{padding:16px 10px;}}
  .hdr{{font-size:15px;padding:14px 16px;}}
  .body{{padding:16px 14px;}}
  .acc-row{{padding:12px 13px;}}
  .acc-name{{font-size:13px;}}
  .acc-amt{{font-size:14px;}}
  .net-val{{font-size:19px;}}
  .rb-title{{font-size:12px;}}
  .rb-amt-val{{font-size:16px;}}
  .rb-email-val{{font-size:12px;}}
}}
</style>
</head>
<body>
<div id="settlement-card">
  <div class="hdr">마케팁 정산 안내 | {yr}년 {mo}월</div>
  <div class="body">
    <div class="fl-name">{fl_name} 프리랜서님</div>
    {rows_html}
    <hr class="sep">
    <div class="srow"><span style="color:#374151;">공제전 정산액</span>
                      <span style="color:#374151;">{total_gross:,}원</span></div>
    <div class="srow"><span style="color:#DC2626;">3.3% 공제액</span>
                      <span style="color:#DC2626;">-{total_tax:,}원</span></div>
    <div class="net-box">
      <span class="net-lbl">공제후 실수령액</span>
      <span class="net-val">{total_net:,}원</span>
    </div>
    {_rb_html_section(rb_list)}
    <div class="foot">입금 예정입니다</div>
  </div>
</div>
</body></html>"""

# ── Playwright 기반 PNG 생성 ──────────────────────────────────────────────────
def _gen_png_playwright(html_str):
    import tempfile, os
    from playwright.sync_api import sync_playwright

    with tempfile.NamedTemporaryFile(
        suffix=".html", mode="w", encoding="utf-8", delete=False
    ) as f:
        f.write(html_str); tmp = f.name

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(
                viewport={"width": 760, "height": 1400},
                device_scale_factor=2,
            )
            # file:// URL (Windows/Unix 모두 호환)
            file_url = "file:///" + tmp.replace("\\", "/").lstrip("/")
            page.goto(file_url)
            page.wait_for_load_state("networkidle", timeout=8000)
            png = page.locator("#settlement-card").screenshot()
            browser.close()
        return png
    finally:
        try: os.unlink(tmp)
        except: pass

# ── Styler 헬퍼 ───────────────────────────────────────────────────────────────
import importlib.util as _ilu
_JINJA2_OK = _ilu.find_spec("jinja2") is not None


def _safe_dataframe(df, style_fn, axis=0, **kwargs):
    """Styler.apply() with jinja2 fallback — jinja2 없으면 plain dataframe 표시."""
    if _JINJA2_OK:
        try:
            return st.dataframe(df.style.apply(style_fn, axis=axis), **kwargs)
        except Exception:
            pass
    return st.dataframe(df, **kwargs)


def _style_fl(col):
    if col.name == "프리랜서 지급액":
        return ["color: #dc2626; font-weight: 700"] * len(col)
    return [""] * len(col)

# ── KPI 카드 HTML 헬퍼 ────────────────────────────────────────────────────────
_KPI_CONFIGS = {
    "neutral":  {"bg":"#FFFFFF","border":"#E5E8ED","lc":"#6B7280","vc":"#111827","vs":"19px","fw":"600"},
    "negative": {"bg":"#FFF5F5","border":"#FCA5A5","lc":"#DC2626","vc":"#DC2626","vs":"19px","fw":"700"},
    "primary":  {"bg":"#EFF6FF","border":"#93C5FD","lc":"#1D4ED8","vc":"#1D4ED8","vs":"26px","fw":"800"},
    "secondary":{"bg":"#F0F9FF","border":"#BAE6FD","lc":"#0369A1","vc":"#0369A1","vs":"21px","fw":"700"},
    "amber":    {"bg":"#FFFBEB","border":"#FDE68A","lc":"#92400E","vc":"#1E3A5F","vs":"22px","fw":"700"},
    "green":    {"bg":"#F0FDF4","border":"#86EFAC","lc":"#166534","vc":"#059669","vs":"22px","fw":"700"},
}

def _kpi_card(label, value, variant="neutral", badge=None):
    c = _KPI_CONFIGS.get(variant, _KPI_CONFIGS["neutral"])
    bdg = (f'<span style="background:#DBEAFE;color:#1D4ED8;font-size:10px;font-weight:700;'
           f'padding:1px 7px;border-radius:100px;margin-left:6px;">{badge}</span>') if badge else ""
    return (f'<div style="background:{c["bg"]};border:1.5px solid {c["border"]};border-radius:12px;'
            f'padding:16px 18px;height:100%;">'
            f'<div style="font-size:12px;color:{c["lc"]};font-weight:600;margin-bottom:8px;">'
            f'{label}{bdg}</div>'
            f'<div style="font-size:{c["vs"]};color:{c["vc"]};font-weight:{c["fw"]};line-height:1.2;">'
            f'{value}</div></div>')

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
        st.query_params.clear()
        st.rerun()

_today      = date.today()
_ym_years   = list(range(2026, _today.year + 2))
_def_y_idx  = _ym_years.index(max(2026, _today.year)) if max(2026, _today.year) in _ym_years else 0
_def_m_idx  = _today.month - 1   # 0-based

_yc, _mc, _ = st.columns([1, 1, 5])
with _yc:
    _sel_year  = st.selectbox("연도", _ym_years, index=_def_y_idx,
                              format_func=lambda y: f"{y}년", key="main_year")
with _mc:
    _sel_month = st.selectbox("월", list(range(1, 13)), index=_def_m_idx,
                              format_func=lambda m: f"{m}월", key="main_month")

sel_ym = f"{_sel_year}-{_sel_month:02d}"
st.divider()

t_up, t_cl, t_un, t_fl, t_share, t_ex, t_pnl, t_annual = st.tabs([
    "📤 엑셀 업로드", "🏢 업체 분류", "❓ 미분류",
    "👤 프리랜서 정산", "📨 정산 공유", "💰 기타비용", "📈 월 손익", "📊 월/연간 손익",
])

# ─── 업로드 탭 ────────────────────────────────────────────────────────────────
def _merge_uploads(existing: pd.DataFrame, new_df: pd.DataFrame) -> pd.DataFrame:
    """두 DataFrame을 groupby 키 기준으로 합산 병합 (중복 방지)"""
    combined = pd.concat([existing, new_df], ignore_index=True)
    for col in ["customer_id","ad_account_no"]:
        combined[col] = combined.get(col, pd.Series(dtype=str)).fillna("").astype(str).str.strip()
    if "매체사" not in combined.columns:
        combined["매체사"] = ""
    else:
        combined["매체사"] = combined["매체사"].fillna("").astype(str).str.strip()
    if "comm_rate" not in combined.columns:
        combined["comm_rate"] = 0.0
    SUM_C   = [c for c in ["ad_supply","ad_vat","ad_total","comm_supply","comm_vat","comm_total"]
               if c in combined.columns]
    FIRST_C = [c for c in ["계정명","display_name","account_id"] if c in combined.columns]
    agg = {c:"sum" for c in SUM_C}; agg.update({c:"first" for c in FIRST_C})
    return combined.groupby(["customer_id","ad_account_no","매체사","comm_rate"],
                            as_index=False).agg(agg)

with t_up:
    st.subheader("상위대행사 정산 엑셀 업로드")
    st.caption("여러 대행사 엑셀을 동시에 선택하거나 '+' 버튼으로 추가 — 자동 합산 처리됩니다.")

    ufs = st.file_uploader(
        "파일 선택 (여러 파일 동시 업로드 가능)",
        type=["xlsx","xls","csv"],
        accept_multiple_files=True,
        label_visibility="collapsed",
    )

    if ufs:
        # ── 파일이 바뀐 경우에만 재파싱 ─────────────────────────────────────
        _cur_keys = [(f.name, f.size) for f in ufs]
        _cached_keys = st.session_state.get("_upload_keys", [])

        if _cur_keys != _cached_keys:
            _results, merged_df = [], None
            for _uf in ufs:
                _dg, _err, _, _dbg = parse_excel(_uf)
                _results.append({
                    "name": _uf.name,
                    "ok":   _err is None,
                    "cnt":  len(_dg) if _err is None else 0,
                    "err":  _err,
                    "dbg":  _dbg,
                    "df":   _dg if _err is None else None,
                })
                if _err is None:
                    merged_df = _dg if merged_df is None else _merge_uploads(merged_df, _dg)
            st.session_state["_upload_keys"]    = _cur_keys
            st.session_state["_upload_results"] = _results
            if merged_df is not None:
                st.session_state["uploaded_df"] = merged_df
        else:
            _results  = st.session_state.get("_upload_results", [])
            merged_df = st.session_state.get("uploaded_df")

        # ── 파일별 상태 카드 ──────────────────────────────────────────────────
        for _r in _results:
            _ico   = "✅" if _r["ok"] else "❌"
            _color = "#059669" if _r["ok"] else "#DC2626"
            _detail = f"{_r['cnt']}개 계정 추출" if _r["ok"] else f"오류: {_r['err']}"
            st.markdown(
                f'<div style="display:flex;align-items:center;gap:10px;'
                f'padding:8px 14px;margin-bottom:4px;'
                f'border:1px solid #E5E8ED;border-radius:10px;background:#FAFAFA;">'
                f'<span style="font-size:16px;">{_ico}</span>'
                f'<span style="font-weight:600;color:#111;flex:1;">{_r["name"]}</span>'
                f'<span style="font-size:12px;color:{_color};">{_detail}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )
            if not _r["ok"]:
                with st.expander(f"🐛 {_r['name']} 디버그"):
                    st.write(_r["dbg"])

        if merged_df is not None:
            n_ok  = sum(1 for r in _results if r["ok"])
            n_acc = len(merged_df)
            _ts   = merged_df["ad_supply"].sum()  if "ad_supply"  in merged_df.columns else 0
            _tt   = merged_df["ad_total"].sum()   if "ad_total"   in merged_df.columns else 0
            _cs   = merged_df["comm_supply"].sum() if "comm_supply" in merged_df.columns else 0
            _ct   = merged_df["comm_total"].sum()  if "comm_total"  in merged_df.columns else 0

            # ── 합산 요약 카드 ────────────────────────────────────────────────
            st.markdown("<div style='margin-top:12px;'></div>", unsafe_allow_html=True)
            st.markdown(
                f'<div style="background:#EFF6FF;border:1.5px solid #93C5FD;border-radius:12px;'
                f'padding:16px 20px;margin-bottom:12px;">'
                f'<div style="font-size:13px;font-weight:700;color:#1D4ED8;margin-bottom:10px;">'
                f'📊 합산 완료 — 업로드 {n_ok}개 파일 / 총 {n_acc}개 계정</div>'
                f'<div style="display:flex;gap:32px;flex-wrap:wrap;">'
                f'<span style="font-size:12px;color:#374151;">광고비 공급가 합계 '
                f'<b>{_ts:,.0f}원</b></span>'
                f'<span style="font-size:12px;color:#374151;">광고비 합계금액 '
                f'<b>{_tt:,.0f}원</b></span>'
                f'<span style="font-size:12px;color:#374151;">수수료 공급가 합계 '
                f'<b>{_cs:,.0f}원</b></span>'
                f'<span style="font-size:12px;color:#374151;">수수료 합계금액 '
                f'<b>{_ct:,.0f}원</b></span>'
                f'</div></div>',
                unsafe_allow_html=True,
            )
            st.caption("※ 같은 업체라도 매체사·수수료율이 다르면 별개 계정으로 분리됩니다.")

            # 디버그 (마지막 성공 파일 기준)
            _last_dbg = next((r["dbg"] for r in reversed(_results) if r["ok"]), {})
            with st.expander("🐛 디버그 정보 (마지막 파일 기준)"):
                st.markdown(f"**병합헤더 행**: {_last_dbg.get('merged_row')}  "
                            f"|  **실헤더 행**: {_last_dbg.get('header_row')}")
                st.markdown("**원본 컬럼명**"); st.write(_last_dbg.get("orig_cols"))
                st.markdown("**컬럼 매핑 결과**"); st.json(_last_dbg.get("rename_map",{}))
                if _last_dbg.get("comm_rate_fallback"):
                    st.info(f"🔄 {_last_dbg['comm_rate_fallback']}")
                if _last_dbg.get("comm_rate_warn"):
                    st.warning(_last_dbg["comm_rate_warn"])
                st.markdown("**상위 20행**")
                st.dataframe(pd.DataFrame(_last_dbg.get("raw_sample",[])), use_container_width=True)
                st.markdown("**그룹핑 결과 상위 10행**")
                st.dataframe(pd.DataFrame(_last_dbg.get("group_sample",[])), use_container_width=True)

            show = [c for c in ["display_name","customer_id","ad_account_no","매체사",
                                 "ad_supply","ad_total","comm_rate","comm_supply","comm_total"]
                    if c in merged_df.columns]
            st.markdown("**통합 계정 목록**")
            st.dataframe(merged_df[show], use_container_width=True, hide_index=True)
        else:
            st.error("모든 파일 파싱에 실패했습니다. 디버그 정보를 확인하세요.")

# ─── 업체 분류 탭 ─────────────────────────────────────────────────────────────
with t_cl:
    st.subheader("업체별 프리랜서 분류 및 정산율 설정")
    df = st.session_state.get("uploaded_df")
    if df is None:
        st.info("엑셀 업로드 탭에서 파일을 먼저 업로드해주세요.")
    else:
        view_mode = st.radio("보기 방식", ["업체별 보기", "프리랜서별 보기"],
                              horizontal=True, key="cl_view_mode")
        st.divider()

        if view_mode == "업체별 보기":
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

        else:  # ── 프리랜서별 보기 ───────────────────────────────────────────
            # 데이터 집계: 프리랜서별 업체 리스트 구성
            _cl_groups = {}
            _cl_total_ad  = 0.0
            _cl_total_pay = 0.0

            for _, row in df.iterrows():
                cid   = str(row.get("customer_id","")).strip()
                ano   = str(row.get("ad_account_no","")).strip()
                name  = str(row.get("계정명","")).strip()
                disp  = str(row.get("display_name", name)).strip()
                media = _norm_media(row.get("매체사",""))
                cr    = float(row.get("comm_rate", 0))
                cr_pct= cr * 100 if cr < 1 else cr
                ad_s  = float(row.get("ad_supply",  0))
                ad_t  = float(row.get("ad_total",   0))
                cm_s  = float(row.get("comm_supply", 0))
                ex    = get_mapping(cid, ano, media, cr_pct) or {}
                fl_k  = ex.get("freelancer", "미분류") or "미분류"
                fr    = float(ex.get("freelancer_rate", 0))
                rr    = float(ex.get("rebate_rate", 0))
                is_o  = ex.get("is_owner_managed", False)
                dm    = ex.get("direct_commission_mode", False)
                dr    = float(ex.get("direct_commission_rate", 0))

                # 권혁우(대표): 매체별 기본율, 3.3% 공제 없음
                if fl_k == OWNER_FL:
                    _fr_disp = _owner_share_rate(media, disp)
                    r = _owner_calc(ad_s, ad_t, _fr_disp, rr)
                else:
                    _fr_disp = fr
                    r = calc(ad_s, ad_t, cm_s, fr, rr, is_o, dm, dr)

                _cl_groups.setdefault(fl_k, []).append({
                    "disp": disp, "cid": cid, "media": media, "cr_pct": cr_pct,
                    "ad_s": ad_s, "fr": _fr_disp, "rr": rr,
                    "rebate": r["rebate"], "fl_net": r["fl_net"],
                })
                _cl_total_ad  += ad_s
                _cl_total_pay += r["fl_net"]

            # ── 전체 요약 KPI ────────────────────────────────────────────────
            _cl_fl_names = [k for k in _cl_groups if k not in ("미분류", "", "대표 직접")]
            _cl_uncls    = len(_cl_groups.get("미분류", [])) + len(_cl_groups.get("", []))
            _cl_total_cl = sum(len(v) for v in _cl_groups.values())

            km1, km2, km3, km4, km5 = st.columns(5)
            km1.metric("프리랜서 수",    f"{len(_cl_fl_names)}명")
            km2.metric("전체 업체 수",   f"{_cl_total_cl}개")
            km3.metric("미분류",         f"{_cl_uncls}개")
            km4.metric("총 광고비",      w(_cl_total_ad))
            km5.metric("총 예상 정산액", w(_cl_total_pay))
            st.divider()

            # ── 프리랜서 필터 + 검색 ─────────────────────────────────────────
            _cl_opts = [k for k in FREELANCERS[1:] if k in _cl_groups and k != "대표 직접"]
            _cl_opts += [k for k in _cl_groups if k not in FREELANCERS and k not in ("", "미분류")]
            if "미분류" in _cl_groups:
                _cl_opts.append("미분류")

            fc1, fc2 = st.columns([2, 3])
            with fc1:
                _cl_sel = st.multiselect(
                    "프리랜서 필터",
                    options=_cl_opts,
                    default=[],
                    placeholder="전체 (비워두면 전체 표시)",
                    key="cl_fl_filter",
                )
            with fc2:
                _cl_q = st.text_input(
                    "🔍 업체명 · CID · 매체명 검색", key="cl_search"
                ).strip().lower()

            _cl_show = _cl_sel if _cl_sel else _cl_opts

            # ── 프리랜서별 expander ──────────────────────────────────────────
            for _fl_name in _cl_show:
                _items = list(_cl_groups.get(_fl_name, []))
                if _cl_q:
                    _items = [it for it in _items if (
                        _cl_q in it["disp"].lower()
                        or _cl_q in it["cid"].lower()
                        or _cl_q in it["media"].lower()
                        or _cl_q in _fl_name.lower()
                    )]
                if not _items:
                    continue

                _fl_ad  = sum(it["ad_s"]   for it in _items)
                _fl_pay = sum(it["fl_net"] for it in _items)
                _icon   = "🔴" if _fl_name == "미분류" else "👤"
                _exp_lbl = (
                    f"{_icon} **{_fl_name}** │ 업체 {len(_items)}개 │ "
                    f"광고비 {_fl_ad:,.0f}원 │ 정산액 {_fl_pay:,.0f}원"
                )

                with st.expander(_exp_lbl, expanded=(_fl_name == "미분류")):
                    _tbl = []
                    for it in _items:
                        _tbl.append({
                            "업체명":         it["disp"],
                            "CID":            it["cid"],
                            "매체/상품":      it["media"] or "—",
                            "광고비(원)":     f"{it['ad_s']:,.0f}",
                            "정산율(%)":      f"{it['fr']:.1f}",
                            "예상 정산액(원)": f"{it['fl_net']:,.0f}",
                            "리베이트":       "O" if it["rebate"] > 0 else "",
                        })
                    st.dataframe(pd.DataFrame(_tbl), use_container_width=True, hide_index=True)

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
            # 권혁우 최상단, 나머지 이름순, 합계 최하단
            _fl_top   = {k: g for k, g in fl_sum.items() if k == "권혁우"}
            _fl_rest  = {k: g for k, g in fl_sum.items() if k != "권혁우"}
            for k, g in {**_fl_top, **dict(sorted(_fl_rest.items()))}.items():
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
            st.table(pd.DataFrame(s_rows))

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
        _safe_dataframe(
            pd.DataFrame(fmt_details), _style_fl, axis=0,
            use_container_width=True, hide_index=True,
        )

        d_df = pd.DataFrame(details).sort_values("프리랜서")
        st.download_button("📥 CSV 다운로드",
            d_df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig"),
            file_name=f"정산_{sel_ym or 'all'}.csv", mime="text/csv")

# ─── 정산 공유 탭 ─────────────────────────────────────────────────────────────
with t_share:
    st.subheader("프리랜서 정산 공유")
    st.caption("대표 수익·리베이트 등 내부 정보는 제외된 프리랜서 공유용 정산서입니다.")
    _sdf = st.session_state.get("uploaded_df")
    if _sdf is None:
        st.info("엑셀을 먼저 업로드해주세요.")
    else:
        # 프리랜서 목록 (미분류·대표 직접 제외 / 권혁우 포함)
        _all_fls = sorted({
            m.get("freelancer","")
            for m in load_mapping()
            if m.get("freelancer","") not in ["","미분류","대표 직접"]
        })
        if not _all_fls:
            st.info("업체 분류 탭에서 프리랜서를 먼저 지정해주세요.")
        else:
            _sc1, _sc2 = st.columns([2, 5])
            with _sc1:
                _sel_fl = st.selectbox("프리랜서 선택", _all_fls, key="share_fl")

            # 해당 프리랜서 업체 집계
            _fl_rows = []
            for _, _row in _sdf.iterrows():
                _cid   = str(_row.get("customer_id","")).strip()
                _ano   = str(_row.get("ad_account_no","")).strip()
                _media = _norm_media(_row.get("매체사",""))
                _cr    = float(_row.get("comm_rate", 0))
                _crp   = _cr * 100 if _cr < 1 else _cr
                _m     = get_mapping(_cid, _ano, _media, _crp) or {}
                if _m.get("freelancer") != _sel_fl: continue
                _fr    = float(_m.get("freelancer_rate", 0))
                _rr    = float(_m.get("rebate_rate", 0))
                _is_o  = _m.get("is_owner_managed", False)
                _dm    = _m.get("direct_commission_mode", False)
                _dr    = float(_m.get("direct_commission_rate", 0))
                _ad_s  = float(_row.get("ad_supply", 0))
                _ad_t  = float(_row.get("ad_total", 0))
                _cm_s  = float(_row.get("comm_supply", 0))
                # 대표(권혁우): 매체별 기본율 적용, 3.3% 공제 없음
                if _sel_fl == OWNER_FL:
                    _fr = _owner_share_rate(_media, str(_row.get("display_name", "")))
                    _r  = _owner_calc(_ad_s, _ad_t, _fr, _rr)
                else:
                    _r  = calc(_ad_s, _ad_t, _cm_s, _fr, _rr, _is_o, _dm, _dr)
                _fl_rows.append({
                    "업체명":       str(_row.get("display_name","")).strip(),
                    "매체사":       _media or "—",
                    "광고비 공급가": int(_ad_s),
                    "광고비합계VAT": int(_ad_t),
                    "리베이트율":   _rr,
                    "정산율(%)":    _fr,
                    "공제전 지급액": _r["fl_gross"],
                    "리베이트 지급액": _r["rebate"],
                    "3.3% 공제액":  _r["fl_tax"],
                    "공제후 실수령액": _r["fl_net"],
                })

            _col_left, _col_right = st.columns(2)

            with _col_left:
                if not _fl_rows:
                    st.info(f"{_sel_fl} 프리랜서에게 배정된 업체가 없습니다.")
                else:
                    _t_gross   = sum(r["공제전 지급액"]    for r in _fl_rows)
                    _t_rebate  = sum(r["리베이트 지급액"]  for r in _fl_rows)
                    _t_tax     = sum(r["3.3% 공제액"]      for r in _fl_rows)
                    _t_net     = sum(r["공제후 실수령액"]   for r in _fl_rows)

                    # 업체별 리베이트 집계 (리베이트 > 0인 업체만)
                    _rb_by_biz: dict = {}
                    for _r in _fl_rows:
                        _biz = _r["업체명"]
                        if _biz not in _rb_by_biz:
                            _rb_by_biz[_biz] = {"vat": 0, "amt": 0, "rate": _r["리베이트율"]}
                        _rb_by_biz[_biz]["vat"] += _r["광고비합계VAT"]
                        _rb_by_biz[_biz]["amt"] += _r["리베이트 지급액"]
                        if _r["리베이트율"] > 0:
                            _rb_by_biz[_biz]["rate"] = _r["리베이트율"]
                    _rb_list = [(biz, d) for biz, d in _rb_by_biz.items() if d["amt"] > 0]

                    # 업체명 기준 그룹핑 (순서 보존)
                    _biz_order_share = []
                    _biz_rows_map_share: dict = {}
                    for _r in _fl_rows:
                        _biz = _r["업체명"]
                        if _biz not in _biz_rows_map_share:
                            _biz_order_share.append(_biz)
                            _biz_rows_map_share[_biz] = []
                        _biz_rows_map_share[_biz].append(_r)

                    _ym_lbl  = sel_ym or "YYYY-MM"
                    _yr      = _ym_lbl[:4]
                    _mo      = _ym_lbl[5:7].lstrip("0") if len(_ym_lbl) >= 7 else ""

                    # ── HTML 프리뷰 카드 ──────────────────────────────────────────
                    _rows_html = ""
                    for _biz_nm in _biz_order_share:
                        for _r in _biz_rows_map_share[_biz_nm]:
                            _media_badge = (
                                f'<span style="display:inline-block;background:#E0E7FF;color:#3730A3;'
                                f'font-size:11px;font-weight:600;padding:2px 8px;'
                                f'border-radius:100px;margin-left:8px;vertical-align:middle;">'
                                f'{_r["매체사"]}</span>'
                            ) if _r["매체사"] and _r["매체사"] != "—" else ""
                            _rows_html += f"""
<div style="background:#FFFBEB;border:1px solid #FDE68A;border-radius:10px;
            padding:12px 16px;margin-bottom:8px;
            display:flex;justify-content:space-between;align-items:center;">
  <div>
    <div style="font-size:14px;font-weight:700;color:#111;margin-bottom:4px;">
      {_r['업체명']}{_media_badge}
    </div>
    <div style="font-size:12px;color:#6B7280;">
      광고비 {_r['광고비 공급가']:,}원 &nbsp;|&nbsp; 정산율 {_r['정산율(%)']:g}%
    </div>
  </div>
  <div style="font-size:15px;font-weight:800;color:#1D4ED8;">
    {_r['공제후 실수령액']:,}원
  </div>
</div>"""

                    # 리베이트 안내 섹션 (카드 맨 아래)
                    _rb_section_html = ""
                    for _biz_nm in _biz_order_share:
                        _rb = _rb_by_biz.get(_biz_nm, {})
                        if _rb.get("amt", 0) > 0:
                            _rb_section_html += f"""
<div style="background:#FEF2F2;border:2px solid #DC2626;border-radius:12px;
            padding:14px 16px;margin-bottom:10px;">
  <div style="font-size:13px;font-weight:800;color:#DC2626;
              margin-bottom:10px;letter-spacing:-0.2px;line-height:1.4;">
    🔴 {_biz_nm} — 리베이트/세금계산서 안내
  </div>
  <div style="display:flex;gap:16px;flex-wrap:wrap;margin-bottom:10px;line-height:1.6;">
    <span style="font-size:12px;color:#B91C1C;">
      광고비 합계: <b style="font-size:13px;color:#7F1D1D;">{_rb['vat']:,}원</b>
    </span>
    <span style="font-size:12px;color:#B91C1C;">
      리베이트율: <b style="font-size:13px;color:#7F1D1D;">{_rb['rate']:.1f}%</b>
    </span>
  </div>
  <div style="background:#fff;border:1px solid #FECACA;border-radius:8px;
              padding:10px 14px;margin-bottom:10px;">
    <div style="font-size:11px;color:#9CA3AF;margin-bottom:3px;">세금계산서 발행금액</div>
    <div style="font-size:17px;font-weight:900;color:#DC2626;line-height:1.2;">
      {_rb['amt']:,}원
    </div>
  </div>
  <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;
              padding:9px 13px;background:#FFE4E4;border-radius:8px;line-height:1.6;">
    <span style="font-size:14px;">📧</span>
    <span style="font-size:12px;font-weight:700;color:#B91C1C;">발행 이메일:</span>
    <span style="font-size:13px;font-weight:800;color:#991B1B;letter-spacing:0.1px;">mktip@naver.com</span>
  </div>
</div>"""

                    # 중첩 f-string 제거: 변수로 조립 후 단순 치환만 사용
                    _rb_insert = (
                        '<hr style="border:none;border-top:1px solid #FECACA;margin:16px 0;">'
                        + _rb_section_html
                    ) if _rb_section_html else ""
                    # 3.3% 공제 행: 권혁우(대표)는 표시 안 함
                    _net_label = "정산액" if _sel_fl == OWNER_FL else "공제후 실수령액"
                    # 요약 섹션을 하나의 변수로 미리 조립 (빈 줄로 HTML 블록이 끊기는 현상 방지)
                    _summary_html = (
                        f'<div style="display:flex;justify-content:space-between;align-items:center;'
                        f'margin-bottom:10px;line-height:1.7;">'
                        f'<span style="font-size:13px;color:#374151;">공제전 정산액</span>'
                        f'<span style="font-size:13px;color:#374151;">{_t_gross:,}원</span>'
                        f'</div>'
                    )
                    if _t_tax > 0:
                        _summary_html += (
                            f'<div style="display:flex;justify-content:space-between;align-items:center;'
                            f'margin-bottom:12px;line-height:1.7;">'
                            f'<span style="font-size:13px;color:#DC2626;">3.3% 공제액</span>'
                            f'<span style="font-size:13px;color:#DC2626;">-{_t_tax:,}원</span>'
                            f'</div>'
                        )
                    _summary_html += (
                        f'<div style="background:#EFF6FF;border:1.5px solid #93C5FD;border-radius:10px;'
                        f'padding:14px 18px;display:flex;justify-content:space-between;'
                        f'align-items:center;gap:8px;margin-bottom:4px;">'
                        f'<span style="font-size:14px;font-weight:700;color:#1D4ED8;line-height:1.4;">{_net_label}</span>'
                        f'<span style="font-size:22px;font-weight:900;color:#1D4ED8;white-space:nowrap;">{_t_net:,}원</span>'
                        f'</div>'
                    )
                    st.markdown(f"""
<div style="background:#fff;border:1.5px solid #E5E8ED;border-radius:16px;
            overflow:hidden;max-width:560px;box-sizing:border-box;">
  <div style="background:#CC0000;color:white;padding:13px 20px;
              font-size:15px;font-weight:800;
              text-align:center;line-height:1.5;letter-spacing:-0.2px;">
    마케팁 정산 안내 &nbsp;|&nbsp; {_yr}년 {_mo}월
  </div>
  <div style="padding:18px 20px;">
    <div style="font-size:15px;font-weight:700;margin-bottom:14px;
                color:#111827;line-height:1.5;">{_sel_fl} 프리랜서님</div>
    {_rows_html}
    <hr style="border:none;border-top:1px solid #E5E8ED;margin:14px 0;">
    {_summary_html}
    {_rb_insert}
  </div>
</div>
""", unsafe_allow_html=True)

                    st.markdown("<div style='margin-top:20px;'></div>", unsafe_allow_html=True)

                    # ── 카톡 복사용 텍스트 ───────────────────────────────────────
                    st.markdown("**📋 카톡 복사용 텍스트**")
                    _lines = [
                        f"📌 {_yr}년 {_mo}월 정산 안내",
                        "",
                        f"{_sel_fl} 프리랜서님",
                        "",
                        "■ 업체별 정산",
                    ]
                    for _biz_nm in _biz_order_share:
                        for _r in _biz_rows_map_share[_biz_nm]:
                            _lines.append(f"\n- {_r['업체명']} [{_r['매체사']}]")
                            _lines.append(f"  광고비: {_r['광고비 공급가']:,}원")
                            _lines.append(f"  정산율: {_r['정산율(%)']:g}%")
                            _lines.append(f"  공제후 실수령액: {_r['공제후 실수령액']:,}원")
                    _lines += [
                        "",
                        "━━━━━━━━━━━━━━━━",
                        "",
                        f"공제전 정산액: {_t_gross:,}원",
                        *([] if _t_tax == 0 else [f"3.3% 공제액: -{_t_tax:,}원"]),
                        f"{_net_label}: {_t_net:,}원",
                        "",
                        "입금 예정입니다 🙏",
                    ]
                    # 리베이트 안내 (맨 아래)
                    for _biz_nm in _biz_order_share:
                        _rb = _rb_by_biz.get(_biz_nm, {})
                        if _rb.get("amt", 0) > 0:
                            _lines += [
                                "",
                                f"━━━━━━━━━━━━━━━━",
                                f"※ {_biz_nm} 리베이트/세금계산서 안내",
                                f"광고비 합계: {_rb['vat']:,}원",
                                f"리베이트율: {_rb['rate']:.1f}%",
                                f"세금계산서 발행금액: {_rb['amt']:,}원",
                                f"발행이메일: mktip@naver.com",
                            ]
                    _kakao_text = "\n".join(_lines)
                    st.code(_kakao_text, language=None)

                    # ── HTML 저장 ────────────────────────────────────────────────
                    st.markdown("<div style='margin-top:10px;'></div>", unsafe_allow_html=True)
                    _html_str = _gen_share_html(
                        _sel_fl, _ym_lbl, _fl_rows, _t_gross, _t_rebate, _t_tax, _t_net,
                        rb_list=_rb_list,
                    )
                    st.download_button(
                        "📄 HTML 저장 (브라우저에서 열면 정상 표시)",
                        _html_str.encode("utf-8"),
                        file_name=f"{_sel_fl}_{_ym_lbl}_정산.html",
                        mime="text/html",
                    )

            with _col_right:
                st.markdown("### 🧾 세무사 보고용")
                st.caption("전체 프리랜서 입금 내역을 세무사 전달용 텍스트로 자동 생성합니다.")

                if _sdf is None:
                    st.info("엑셀을 먼저 업로드해주세요.")
                else:
                    # 프리랜서별 fl_net 합산 (권혁우·미분류·대표 직접 제외)
                    _tax_sum = {}  # {fl_name: fl_net_total}
                    for _, _row in _sdf.iterrows():
                        _cid2   = str(_row.get("customer_id","")).strip()
                        _ano2   = str(_row.get("ad_account_no","")).strip()
                        _media2 = _norm_media(_row.get("매체사",""))
                        _cr2    = float(_row.get("comm_rate", 0))
                        _crp2   = _cr2 * 100 if _cr2 < 1 else _cr2
                        _m2     = get_mapping(_cid2, _ano2, _media2, _crp2) or {}
                        _fl2    = _m2.get("freelancer","미분류")
                        if _fl2 in ["", "미분류", "대표 직접", OWNER_FL]: continue
                        _r2 = calc(
                            float(_row.get("ad_supply",0)), float(_row.get("ad_total",0)),
                            float(_row.get("comm_supply",0)),
                            float(_m2.get("freelancer_rate",0)), float(_m2.get("rebate_rate",0)),
                            _m2.get("is_owner_managed",False),
                            _m2.get("direct_commission_mode",False),
                            float(_m2.get("direct_commission_rate",0)),
                        )
                        _tax_sum[_fl2] = _tax_sum.get(_fl2, 0) + _r2["fl_net"]

                    if not _tax_sum:
                        st.info("분류된 프리랜서 데이터가 없습니다.")
                    else:
                        _ym_lbl2 = sel_ym or "YYYY-MM"
                        _yr2 = _ym_lbl2[:4]; _mo2 = _ym_lbl2[5:7].lstrip("0") if len(_ym_lbl2) >= 7 else ""
                        _today_day = date.today().day

                        # 입금완료 체크박스
                        st.markdown("**입금 완료 여부 선택**")
                        _paid = {}
                        _chk_cols = st.columns(min(len(_tax_sum), 4))
                        for _ci2, (_fn, _famt) in enumerate(sorted(_tax_sum.items())):
                            with _chk_cols[_ci2 % len(_chk_cols)]:
                                _paid[_fn] = st.checkbox(
                                    f"{_fn}  {int(round(_famt)):,}원",
                                    value=True,
                                    key=f"tax_paid_{_ym_lbl2}_{_fn}",
                                )

                        # 포함 대상만 필터
                        _included = {fn: amt for fn, amt in sorted(_tax_sum.items()) if _paid.get(fn)}
                        _total_net = sum(_included.values())

                        # 텍스트 생성
                        _tax_lines = [
                            "안녕하세요 세무사님~",
                            "좋은 아침입니다.",
                            "",
                            f"{_yr2}년 {_mo2}월 프리랜서 비용 전달드립니다.",
                            "",
                        ]
                        for _fn, _famt in _included.items():
                            _tax_lines.append(_fn)
                            _tax_lines.append(f"{int(round(_famt)):,}원")
                            _tax_lines.append("")
                        _tax_lines += [
                            "━━━━━━━━━━━━━━━━",
                            "",
                            f"{_mo2}월 프리랜서 총 입금액:",
                            f"{int(round(_total_net)):,}원",
                            "",
                            f"{_yr2}년 {_mo2}월 {_today_day}일 프리랜서 비용 입금 완료입니다.",
                            "감사합니다.",
                        ]
                        _tax_text = "\n".join(_tax_lines)

                        st.markdown("**📋 세무사 전달 텍스트**")
                        st.code(_tax_text, language=None)

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
    st.warning("🔄 월 손익 v2 적용됨: 플레이스/블로그 매출·매입·순수익 구조")
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

        # ── 플레이스 / 블로그 입력 (실시간 순수익 자동 계산) ────────────────────
        def _profit_display(label, profit):
            color = "#059669" if profit >= 0 else "#DC2626"
            return (
                f'<div style="background:#F9FAFB;border:1.5px solid #E5E7EB;border-radius:10px;'
                f'padding:10px 14px;height:100%;">'
                f'<div style="font-size:12px;color:#6B7280;font-weight:600;margin-bottom:6px;">'
                f'{label}</div>'
                f'<div style="font-size:20px;font-weight:800;color:{color};line-height:1.2;">'
                f'{profit:,} 원</div>'
                f'<div style="font-size:10px;color:#9CA3AF;margin-top:4px;">매출 − 매입비용</div>'
                f'</div>'
            )

        _inp_col, _memo_col = st.columns([3, 1])
        with _inp_col:
            # ── 플레이스 ──────────────────────────────────────────────────────
            st.markdown('<div style="font-size:14px;font-weight:700;color:#374151;'
                        'margin-bottom:6px;">🏪 플레이스</div>', unsafe_allow_html=True)
            pc1, pc2, pc3 = st.columns(3)
            with pc1:
                place_rev = st.number_input(
                    "플레이스 매출(원)", value=int(extra.get("place_revenue") or 0),
                    min_value=0, step=1000, format="%d", key=f"pnl_pr_{sel_ym}",
                )
            with pc2:
                place_cost = st.number_input(
                    "플레이스 매입비용(원)", value=int(extra.get("place_cost") or 0),
                    min_value=0, step=1000, format="%d", key=f"pnl_pc_{sel_ym}",
                )
            with pc3:
                place_profit = place_rev - place_cost
                st.markdown(_profit_display("플레이스 순수익 (자동)", place_profit),
                            unsafe_allow_html=True)

            st.markdown("<div style='margin-top:10px;'></div>", unsafe_allow_html=True)

            # ── 블로그 ────────────────────────────────────────────────────────
            st.markdown('<div style="font-size:14px;font-weight:700;color:#374151;'
                        'margin-bottom:6px;">📝 블로그</div>', unsafe_allow_html=True)
            bc1, bc2, bc3 = st.columns(3)
            with bc1:
                blog_rev = st.number_input(
                    "블로그 매출(원)", value=int(extra.get("blog_revenue") or 0),
                    min_value=0, step=1000, format="%d", key=f"pnl_br_{sel_ym}",
                )
            with bc2:
                blog_cost = st.number_input(
                    "블로그 매입비용(원)", value=int(extra.get("blog_cost") or 0),
                    min_value=0, step=1000, format="%d", key=f"pnl_bc_{sel_ym}",
                )
            with bc3:
                blog_profit = blog_rev - blog_cost
                st.markdown(_profit_display("블로그 순수익 (자동)", blog_profit),
                            unsafe_allow_html=True)

            st.markdown("<div style='margin-top:12px;'></div>", unsafe_allow_html=True)

            # ── 합계 카드 ─────────────────────────────────────────────────────
            combined_rev       = place_rev  + blog_rev
            combined_cost      = place_cost + blog_cost
            combined_profit    = place_profit + blog_profit
            combined_after_tax = round(combined_profit * 0.8)

            st.markdown('<div style="font-size:13px;font-weight:700;color:#6B7280;'
                        'margin-bottom:6px;">합계</div>', unsafe_allow_html=True)
            sc1, sc2, sc3, sc4 = st.columns(4)
            sc1.markdown(_kpi_card("합산 매출",            w(combined_rev)),
                         unsafe_allow_html=True)
            sc2.markdown(_kpi_card("합산 매입비용",        w(combined_cost), "negative"),
                         unsafe_allow_html=True)
            _sv = "green" if combined_profit >= 0 else "negative"
            sc3.markdown(_kpi_card("합산 순수익",          w(combined_profit), _sv),
                         unsafe_allow_html=True)
            sc4.markdown(_kpi_card("세후 추정 순수익", w(combined_after_tax),
                                   "secondary", badge="×0.8"),
                         unsafe_allow_html=True)
            st.caption("※ 세후 추정(×0.8)은 종소세·건보료·국민연금 등을 감안한 보수적 추정치입니다.")

        with _memo_col:
            st.markdown('<div style="font-size:14px;font-weight:700;color:#374151;'
                        'margin-bottom:6px;">📋 메모</div>', unsafe_allow_html=True)
            xm = st.text_area("메모", extra.get("memo", ""), height=200,
                              key=f"pnl_memo_{sel_ym}", label_visibility="collapsed")
            if st.button("💾 저장", key=f"pnl_save_{sel_ym}", type="primary",
                         use_container_width=True):
                set_extra(sel_ym,
                          int(place_rev), int(place_cost),
                          int(blog_rev),  int(blog_cost), xm)
                st.rerun()

        # ── 월 손익 계산 (플레이스/블로그는 순수익 기준) ────────────────────
        search_total_profit          = search_owner_profit + search_freelancer_profit
        gross_total_profit           = search_total_profit + combined_profit   # 순수익 기준
        gross_total_profit_after_tax = round(gross_total_profit * 0.8)
        final_net_profit             = gross_total_profit - tot_exp
        final_net_profit_after_tax   = gross_total_profit_after_tax - tot_exp

        st.divider()

        exp_val = f"🔻 -{int(round(tot_exp)):,} 원" if tot_exp else "0 원"

        c1 = st.columns(4)
        c1[0].markdown(_kpi_card("검색광고 대표 직접수익",    w(search_owner_profit)),      unsafe_allow_html=True)
        c1[1].markdown(_kpi_card("검색광고 프리랜서 계정수익", w(search_freelancer_profit)), unsafe_allow_html=True)
        c1[2].markdown(_kpi_card("플레이스 순수익",            w(place_profit)),             unsafe_allow_html=True)
        c1[3].markdown(_kpi_card("블로그 순수익",              w(blog_profit)),              unsafe_allow_html=True)

        st.markdown("<div style='margin-top:12px;'></div>", unsafe_allow_html=True)

        c2 = st.columns(4)
        c2[0].markdown(_kpi_card("총 수익",            w(gross_total_profit)),            unsafe_allow_html=True)
        c2[1].markdown(_kpi_card("총 수익 세후 추정 (종소세80%)",  w(gross_total_profit_after_tax)),  unsafe_allow_html=True)
        c2[2].markdown(_kpi_card("기타비용 합계",       exp_val, "negative"),              unsafe_allow_html=True)
        c2[3].markdown(_kpi_card("기타비용 제외 금액",  w(final_net_profit_after_tax),
                                 "primary", badge="세후 추정"),                            unsafe_allow_html=True)

        if df is None:
            st.warning("엑셀 없음 — 검색광고 수익 0원으로 계산됩니다.")

        st.divider()
        btn_disabled = (not sel_ym) or (df is None)
        if st.button("💾 이 달 손익 확정 저장 → 월/연간 손익 탭에 반영",
                     type="primary", use_container_width=True, disabled=btn_disabled):
            upsert_pnl(sel_ym,
                       search_owner_profit, search_freelancer_profit,
                       int(place_rev), int(place_cost),
                       int(blog_rev),  int(blog_cost),
                       tot_exp,
                       gross_total_profit, gross_total_profit_after_tax,
                       final_net_profit, final_net_profit_after_tax)
            st.success(f"✅ {sel_ym} 손익 저장 완료 — 월/연간 손익 탭에서 확인하세요.")

# ─── 월/연간 손익 탭 ──────────────────────────────────────────────────────────
with t_annual:
    st.subheader("월/연간 손익 현황")
    st.caption("월 손익 탭 '이 달 손익 확정 저장' 또는 아래 수동 입력으로 데이터를 추가하세요.")

    # 연도 선택
    _today = date.today()
    _years = list(range(2026, _today.year + 2))
    _def_y = _today.year if _today.year >= 2026 else 2026
    ann_year = st.selectbox("연도 선택", _years,
                            index=_years.index(_def_y), key="ann_year_sel")
    ann_months = list(range(1, 13))

    # 데이터 로드
    _ann_raw = {r["month"]: r for r in load_annual() if r.get("year") == ann_year}

    # 월별 집계 — 기타비용 제외 금액 = 세후순수익 - 기타비용 (자동)
    _ann_rows = []
    for _m in ann_months:
        _r   = _ann_raw.get(_m, {})
        _has = bool(_r)
        _atp = int(_r.get("after_tax_profit", 0)) if _has else 0
        _oth = int(_r.get("other_expenses",   0)) if _has else 0
        _net = int(_r.get("net_amount", max(0, _atp - _oth))) if _has else 0
        _ann_rows.append({
            "month": _m, "월": f"{_m}월",
            "세후순수익": _atp, "기타비용": _oth, "기타비용 제외 금액": _net,
            "has_data": _has,
        })
    _ann_df = pd.DataFrame(_ann_rows)

    # 누적 (데이터 있는 월만)
    _hd   = _ann_df[_ann_df["has_data"]]
    c_atp = _hd["세후순수익"].sum()
    c_oth = _hd["기타비용"].sum()
    c_net = _hd["기타비용 제외 금액"].sum()

    # ── KPI 카드 3개 ─────────────────────────────────────────────────────────
    _kc = st.columns(3)
    _kc[0].markdown(_kpi_card(f"{ann_year}년 누적 세후순수익",
                              w(c_atp), "amber"), unsafe_allow_html=True)
    _kc[1].markdown(_kpi_card(f"{ann_year}년 누적 기타비용",
                              f"🔻 -{int(c_oth):,} 원" if c_oth else "0 원", "negative"),
                    unsafe_allow_html=True)
    _kc[2].markdown(_kpi_card(f"{ann_year}년 누적 기타비용 제외 금액",
                              w(c_net), "green"), unsafe_allow_html=True)

    st.markdown("<div style='margin-top:20px;'></div>", unsafe_allow_html=True)

    # ── 차트: 세후순수익 / 기타비용 제외 금액 ───────────────────────────────
    def _cy(col):
        return [float(r[col]) if r["has_data"] else None for _, r in _ann_df.iterrows()]

    def _ct(col):
        return [f"{int(r[col]):,}원" if r["has_data"] else "" for _, r in _ann_df.iterrows()]

    try:
        import plotly.graph_objects as go
        _chart_cfg = [
            ("세후순수익",        "#F59E0B", 2.0, "dot",   False),
            ("기타비용 제외 금액", "#059669", 2.5, "solid", True),
        ]
        _fig = go.Figure()
        for _col, _clr, _lw, _dash, _fill in _chart_cfg:
            _fig.add_trace(go.Scatter(
                x=_ann_df["월"], y=_cy(_col), text=_ct(_col), name=_col,
                mode="lines+markers", connectgaps=False,
                line=dict(color=_clr, width=_lw, dash=_dash, shape="spline", smoothing=0.3),
                marker=dict(size=7, color=_clr),
                fill="tozeroy" if _fill else None,
                fillcolor="rgba(5,150,105,0.06)" if _fill else None,
                hovertemplate="<b>%{text}</b><extra>%{fullData.name}</extra>",
                hoverlabel=dict(bgcolor="white", font_size=13),
            ))
        _fig.update_layout(
            plot_bgcolor="white", paper_bgcolor="white",
            margin=dict(l=8, r=8, t=36, b=8), height=260,
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.04, xanchor="right", x=1,
                        font=dict(size=13), bgcolor="rgba(0,0,0,0)"),
            xaxis=dict(showgrid=False, zeroline=False, tickfont=dict(size=12, color="#6B7280")),
            yaxis=dict(showgrid=True, gridcolor="#F3F4F6", zeroline=False,
                       tickformat=",.0f", tickfont=dict(size=11, color="#9CA3AF"), title=None),
        )
        st.markdown('<div style="border:1.5px solid #E5E8ED;border-radius:14px;'
                    'padding:4px 8px 0;background:#fff;">', unsafe_allow_html=True)
        st.plotly_chart(_fig, use_container_width=True, config={"displayModeBar": False})
        st.markdown("</div>", unsafe_allow_html=True)
    except ImportError:
        st.line_chart(_ann_df.set_index("월")[["세후순수익","기타비용 제외 금액"]])

    st.markdown("<div style='margin-top:16px;'></div>", unsafe_allow_html=True)

    # ── 월별 요약 테이블 ─────────────────────────────────────────────────────
    st.markdown("**월별 요약**")
    _tbl = []
    for _, _r in _ann_df.iterrows():
        _d = _r["has_data"]
        _tbl.append({
            "월":              _r["월"],
            "세후순수익":      w(_r["세후순수익"])         if _d else "—",
            "기타비용":        w(_r["기타비용"])            if _d else "—",
            "기타비용 제외 금액": w(_r["기타비용 제외 금액"]) if _d else "—",
        })
    _tbl.append({"월":"합계",
                 "세후순수익": w(c_atp), "기타비용": w(c_oth), "기타비용 제외 금액": w(c_net)})

    def _ann_style(sdf):
        out = pd.DataFrame("", index=sdf.index, columns=sdf.columns)
        out["세후순수익"]        = "color:#92400E;font-weight:600;"
        out["기타비용"]          = "color:#DC2626;font-weight:600;"
        out["기타비용 제외 금액"] = "color:#059669;font-weight:700;"
        last = len(sdf) - 1
        for _c in sdf.columns:
            out.iloc[last, sdf.columns.get_loc(_c)] = "font-weight:800;"
        out.iloc[last, sdf.columns.get_loc("세후순수익")]        = "font-weight:800;color:#92400E;"
        out.iloc[last, sdf.columns.get_loc("기타비용")]          = "font-weight:800;color:#DC2626;"
        out.iloc[last, sdf.columns.get_loc("기타비용 제외 금액")] = "font-weight:800;color:#059669;"
        return out

    _safe_dataframe(
        pd.DataFrame(_tbl), _ann_style, axis=None,
        use_container_width=True, hide_index=True,
    )

    # ── 수동 입력 폼 ─────────────────────────────────────────────────────────
    st.divider()
    st.markdown("**월별 수동 입력** (수정 또는 확정 저장이 없는 달 직접 입력)")
    _fi1, _fi2, _fi3, _fi4 = st.columns([1, 2, 2, 2])
    with _fi1:
        _man_m = st.selectbox("월 선택", ann_months,
                              format_func=lambda x: f"{x}월", key="ann_man_month")
    _mex = _ann_raw.get(_man_m, {})
    with _fi2:
        _man_atp = st.number_input("세후순수익(원)",
                                   value=int(_mex.get("after_tax_profit", 0)),
                                   min_value=0, step=100000, format="%d",
                                   key=f"ann_atp_{ann_year}_{_man_m}")
    with _fi3:
        _man_oth = st.number_input("기타비용(원)",
                                   value=int(_mex.get("other_expenses", 0)),
                                   min_value=0, step=10000, format="%d",
                                   key=f"ann_oth_{ann_year}_{_man_m}")
    with _fi4:
        _preview = max(0, _man_atp - _man_oth)
        st.markdown("**기타비용 제외 금액 (자동)**")
        st.markdown(f"<span style='font-size:20px;font-weight:800;color:#059669;'>"
                    f"{_preview:,} 원</span>", unsafe_allow_html=True)
        st.caption("= 세후순수익 − 기타비용")

    if st.button("💾 저장", key=f"ann_sv_{ann_year}_{_man_m}",
                 type="primary", use_container_width=True):
        upsert_annual(ann_year, _man_m, _man_atp, _man_oth)
        st.success(f"✅ {ann_year}년 {_man_m}월 저장 완료")
        st.rerun()
