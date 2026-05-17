"""영업툴 — 쇼핑광고 DB 조회 (관리자 전용)
수집은 로컬 collector.py 에서 실행 후 Supabase에 저장.
"""
import streamlit as st
import os, sys, io
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from db import sb_load, sb_save

if st.session_state.get("auth_type") != "admin":
    st.error("🔒 관리자만 접근 가능합니다.")
    st.stop()

FALLBACK_JSON = os.path.join(ROOT, "sales_leads_shopping.json")
SESSION_KEY   = "shopping_results"
COLS_DISPLAY  = ["keyword","store_name","is_ad","page","store_url","grade","email","phone","memo"]
COL_RENAME    = {
    "keyword":"수집키워드","store_name":"스토어명","is_ad":"광고여부",
    "page":"노출페이지","store_url":"스토어URL","grade":"등급",
    "email":"이메일","phone":"연락처","memo":"메모",
}

def _load():
    raw = sb_load("sales_leads_shopping", fallback_path=FALLBACK_JSON)
    return raw if isinstance(raw, list) else []

def _to_csv(rows):
    df = pd.DataFrame(rows)
    if "found_keywords" in df.columns:
        df["found_keywords"] = df["found_keywords"].apply(
            lambda v: ", ".join(v) if isinstance(v, list) else str(v))
    cols = COLS_DISPLAY + ["found_keywords"]
    for c in cols:
        if c not in df.columns: df[c] = ""
    return df[cols].to_csv(index=False).encode("utf-8-sig")

def _to_xlsx(rows):
    df = pd.DataFrame(rows)
    if "found_keywords" in df.columns:
        df["found_keywords"] = df["found_keywords"].apply(
            lambda v: ", ".join(v) if isinstance(v, list) else str(v))
    cols = COLS_DISPLAY + ["found_keywords"]
    for c in cols:
        if c not in df.columns: df[c] = ""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df[cols].to_excel(w, index=False, sheet_name="쇼핑광고DB")
    return buf.getvalue()

# ── UI ────────────────────────────────────────────────────────────────────────
st.title("🛍️ 쇼핑광고 DB")
st.caption("수집 데이터 조회 · 검색 · 다운로드 — 수집은 로컬 PC에서 collector.py로 실행")

# 수집 방법 안내
with st.expander("📋 수집 방법 (클릭해서 보기)", expanded=False):
    st.markdown("""
**로컬 PC에서 실행:**
```bash
python collector.py
```
1. `1` 선택 → 쇼핑광고 DB 추출
2. 키워드 입력 (쉼표 또는 줄바꿈)
3. 수집 페이지 수 입력
4. 실제 크롬 브라우저가 열리면서 자동 수집
5. 완료 후 Supabase 자동 저장 → 이 페이지에서 조회 가능

**필요 사항:**
- `playwright install chromium` 실행 (최초 1회)
- `.env` 파일에 `SUPABASE_URL`, `SUPABASE_KEY` 설정
""")

st.divider()

# 데이터 로드
if SESSION_KEY not in st.session_state:
    st.session_state[SESSION_KEY] = _load()

col_r, col_ref = st.columns([8, 2])
with col_ref:
    if st.button("🔄 새로고침", use_container_width=True):
        st.session_state[SESSION_KEY] = _load()
        st.rerun()

results = st.session_state.get(SESSION_KEY, [])

if not results:
    st.info("저장된 데이터가 없습니다. 로컬에서 `python collector.py`를 실행해 수집 후 Supabase에 저장해주세요.")
    st.stop()

# 검색 / 필터
with st.expander("🔍 검색 · 필터", expanded=True):
    f1, f2, f3 = st.columns(3)
    with f1:
        q_name = st.text_input("스토어명 검색", key="f_name")
    with f2:
        q_kw   = st.text_input("키워드 검색", key="f_kw")
    with f3:
        q_ad   = st.selectbox("광고여부", ["전체","광고","비광고"], key="f_ad")

filtered = results
if q_name:
    filtered = [r for r in filtered if q_name.lower() in (r.get("store_name","") or "").lower()]
if q_kw:
    filtered = [r for r in filtered
                if q_kw.lower() in (r.get("keyword","") or "").lower()
                or q_kw.lower() in str(r.get("found_keywords","")).lower()]
if q_ad != "전체":
    filtered = [r for r in filtered if r.get("is_ad","") == q_ad]

st.markdown(f"**총 {len(results)}건 중 {len(filtered)}건 표시**")

# 테이블
display_rows = []
for r in filtered:
    dr = dict(r)
    dr["found_keywords"] = ", ".join(dr.get("found_keywords",[]) or [])
    display_rows.append(dr)

df = pd.DataFrame(display_rows)
for c in COLS_DISPLAY:
    if c not in df.columns: df[c] = ""
df_disp = df[COLS_DISPLAY].rename(columns=COL_RENAME).copy()
df_disp.insert(0, "선택", False)

edited = st.data_editor(
    df_disp, use_container_width=True, hide_index=True,
    column_config={
        "선택":     st.column_config.CheckboxColumn("선택", width="small"),
        "수집키워드": st.column_config.TextColumn(disabled=True),
        "스토어명":  st.column_config.TextColumn(disabled=True),
        "광고여부":  st.column_config.TextColumn(disabled=True, width="small"),
        "노출페이지": st.column_config.TextColumn(disabled=True, width="small"),
        "스토어URL": st.column_config.LinkColumn(disabled=True),
        "등급":     st.column_config.TextColumn(disabled=True, width="small"),
        "이메일":   st.column_config.TextColumn(disabled=True),
        "연락처":   st.column_config.TextColumn(disabled=True),
        "메모":    st.column_config.TextColumn(disabled=False),
    },
    key="shop_editor",
)

# 메모 동기화
if edited is not None:
    orig_idx = {(r.get("store_id") or r.get("store_url","")): i for i, r in enumerate(results)}
    for df_idx, row in edited.iterrows():
        if df_idx < len(filtered):
            k = filtered[df_idx].get("store_id") or filtered[df_idx].get("store_url","")
            if k in orig_idx:
                results[orig_idx[k]]["memo"] = row.get("메모","")
    st.session_state[SESSION_KEY] = results

# 액션 버튼
a1, a2, a3, a4 = st.columns(4)
with a1:
    if st.button("🗑️ 선택 삭제", use_container_width=True, key="shop_del"):
        if edited is not None:
            del_keys = set()
            for df_idx, row in edited.iterrows():
                if row.get("선택", False) and df_idx < len(filtered):
                    k = filtered[df_idx].get("store_id") or filtered[df_idx].get("store_url","")
                    if k: del_keys.add(k)
            keep = [r for r in results
                    if (r.get("store_id") or r.get("store_url","")) not in del_keys]
            st.session_state[SESSION_KEY] = keep
            sb_save("sales_leads_shopping", keep, FALLBACK_JSON)
            st.rerun()
with a2:
    if st.button("💾 저장", use_container_width=True, key="shop_save"):
        sb_save("sales_leads_shopping", results, FALLBACK_JSON)
        st.success("저장 완료")
with a3:
    st.download_button("📥 CSV", _to_csv(filtered), "쇼핑광고DB.csv",
                       "text/csv", use_container_width=True, key="shop_csv")
with a4:
    st.download_button("📊 XLSX", _to_xlsx(filtered), "쇼핑광고DB.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       use_container_width=True, key="shop_xlsx")
