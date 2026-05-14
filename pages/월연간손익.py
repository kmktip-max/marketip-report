"""
월/연간 손익 대시보드 — 관리자 전용
정산관리 → 월 손익 → '이 달 손익 확정 저장' 버튼으로 데이터가 쌓입니다.
"""
import streamlit as st
import json, os, sys
import pandas as pd
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# ── 관리자 인증 ───────────────────────────────────────────────────────────────
def _admin_pw():
    try:
        if hasattr(st, "secrets") and "SETTLEMENT_ADMIN_PW" in st.secrets:
            return str(st.secrets["SETTLEMENT_ADMIN_PW"])
    except Exception:
        pass
    return os.getenv("SETTLEMENT_ADMIN_PW", "1471028690")

if not st.session_state.get("settlement_auth"):
    st.title("🔐 월/연간 손익 — 관리자 전용")
    pw = st.text_input("비밀번호", type="password")
    if st.button("로그인", type="primary"):
        if pw == _admin_pw():
            st.session_state.settlement_auth = True
            st.rerun()
        else:
            st.error("비밀번호가 틀렸습니다.")
    st.stop()

# ── 경로 ─────────────────────────────────────────────────────────────────────
F_PNL      = os.path.join(ROOT, "monthly_pnl_data.json")
F_EXPENSES = os.path.join(ROOT, "other_expenses.json")
F_EXTRA    = os.path.join(ROOT, "monthly_extra_revenue.json")

START_YEAR, START_MONTH = 2026, 5   # 기록 시작 월

# ── 데이터 로더 ───────────────────────────────────────────────────────────────
def _load(p):
    try:
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f: return json.load(f)
    except Exception: pass
    return []

def get_pnl(ym):
    for r in _load(F_PNL):
        if r.get("year_month") == ym: return r
    return None

def get_extra(ym):
    for r in _load(F_EXTRA):
        if r.get("year_month") == ym: return r
    return {"place_revenue": 0, "blog_revenue": 0}

def get_expenses_total(ym):
    return sum(e.get("amount", 0) for e in _load(F_EXPENSES) if e.get("year_month") == ym)

# ── 포맷 ─────────────────────────────────────────────────────────────────────
def w(n): return f"{int(round(n)):,} 원"

# ── KPI 카드 ─────────────────────────────────────────────────────────────────
_KPI = {
    "neutral":  {"bg":"#FFFFFF","border":"#E5E8ED","lc":"#6B7280","vc":"#111827","vs":"22px","fw":"600"},
    "negative": {"bg":"#FFF5F5","border":"#FCA5A5","lc":"#DC2626","vc":"#DC2626","vs":"22px","fw":"700"},
    "primary":  {"bg":"#EFF6FF","border":"#93C5FD","lc":"#1D4ED8","vc":"#1D4ED8","vs":"28px","fw":"800"},
    "secondary":{"bg":"#F0F9FF","border":"#BAE6FD","lc":"#0369A1","vc":"#0369A1","vs":"22px","fw":"700"},
}

def _kpi(label, value, variant="neutral", badge=None):
    c = _KPI.get(variant, _KPI["neutral"])
    bdg = (f'<span style="background:#DBEAFE;color:#1D4ED8;font-size:10px;font-weight:700;'
           f'padding:1px 7px;border-radius:100px;margin-left:6px;">{badge}</span>') if badge else ""
    return (f'<div style="background:{c["bg"]};border:1.5px solid {c["border"]};border-radius:14px;'
            f'padding:22px 24px;height:100%;">'
            f'<div style="font-size:12px;color:{c["lc"]};font-weight:600;margin-bottom:10px;letter-spacing:.3px;">'
            f'{label}{bdg}</div>'
            f'<div style="font-size:{c["vs"]};color:{c["vc"]};font-weight:{c["fw"]};line-height:1.2;">'
            f'{value}</div></div>')

# ═════════════════════════════════════════════════════════════════════════════
# UI
# ═════════════════════════════════════════════════════════════════════════════
hc1, hc2 = st.columns([5, 1])
with hc1:
    st.title("📊 월/연간 손익")
    st.caption("정산관리 → 월 손익 탭에서 '이 달 손익 확정 저장'을 눌러야 이 대시보드에 반영됩니다.")
with hc2:
    st.write("")
    if st.button("로그아웃"):
        st.session_state.pop("settlement_auth", None)
        st.rerun()

# ── 연도 선택 ─────────────────────────────────────────────────────────────────
today = date.today()
year_options = list(range(START_YEAR, today.year + 2))
default_year = today.year if today.year >= START_YEAR else START_YEAR
sel_year = st.selectbox(
    "연도 선택",
    year_options,
    index=year_options.index(default_year),
    key="pnl_year",
)
st.divider()

# ── 월별 데이터 집계 ──────────────────────────────────────────────────────────
rows = []
for m in range(1, 13):
    ym = f"{sel_year}-{m:02d}"
    # 기록 시작 월 이전이면 비활성
    is_active = (sel_year, m) >= (START_YEAR, START_MONTH)

    pnl     = get_pnl(ym)
    extra   = get_extra(ym)
    expenses = get_expenses_total(ym)

    if pnl:
        search_total = pnl.get("gross_total_profit", 0)
        gross        = pnl.get("gross_total_profit", 0)
        after_tax    = pnl.get("gross_after_tax",    0)
        net          = pnl.get("final_net_profit",   0)
        net_at       = pnl.get("final_net_after_tax",0)
        has_data     = True
    else:
        place    = int(extra.get("place_revenue", 0))
        blog     = int(extra.get("blog_revenue",  0))
        gross    = place + blog
        after_tax = round(gross * 0.8)
        net       = gross - expenses
        net_at    = after_tax - expenses
        has_data  = (gross > 0 or expenses > 0)

    rows.append({
        "month":    m,
        "월":       f"{m}월",
        "ym":       ym,
        "is_active": is_active,
        "has_data":  has_data,
        "세전 수익":   gross,
        "세후 추정":   after_tax,
        "기타비용":    expenses,
        "최종 순수익": net,
        "최종 세후":   net_at,
        "confirmed":   pnl is not None,
    })

df_all    = pd.DataFrame(rows)
df_active = df_all[df_all["has_data"]]

# ── 누적 KPI ─────────────────────────────────────────────────────────────────
cum_gross    = df_active["세전 수익"].sum()
cum_after    = df_active["세후 추정"].sum()
cum_exp      = df_active["기타비용"].sum()
cum_net      = df_active["최종 순수익"].sum()

kc = st.columns(4)
kc[0].markdown(_kpi(f"{sel_year}년 누적 세전 수익",   w(cum_gross)),  unsafe_allow_html=True)
kc[1].markdown(_kpi(f"{sel_year}년 누적 세후 추정",   w(cum_after),  "secondary", badge="×0.8"), unsafe_allow_html=True)
kc[2].markdown(_kpi(f"{sel_year}년 누적 기타비용",
                    f"🔻 -{int(round(cum_exp)):,} 원" if cum_exp else "0 원", "negative"), unsafe_allow_html=True)
kc[3].markdown(_kpi(f"{sel_year}년 누적 최종 순수익", w(cum_net), "primary"), unsafe_allow_html=True)

st.markdown("<div style='margin-top:28px;'></div>", unsafe_allow_html=True)

# ── 월별 수익 흐름 차트 ───────────────────────────────────────────────────────
chart_df = df_all[df_all["is_active"]].copy()

if chart_df["세전 수익"].sum() == 0 and chart_df["최종 순수익"].sum() == 0:
    st.info("아직 확정된 손익 데이터가 없습니다. 정산관리 → 월 손익 탭에서 월별로 확정 저장하세요.")
else:
    st.subheader("월별 수익 흐름")
    try:
        import plotly.graph_objects as go

        fig = go.Figure()
        series = [
            ("세전 수익",   "#9CA3AF", False),
            ("세후 추정",   "#60A5FA", False),
            ("최종 순수익", "#1D4ED8", True),
        ]
        for col, color, bold in series:
            fig.add_trace(go.Scatter(
                x=chart_df["월"],
                y=chart_df[col],
                name=col,
                mode="lines+markers",
                line=dict(color=color, width=3 if bold else 2,
                          dash="solid" if bold else "dot" if col == "세후 추정" else "solid"),
                marker=dict(size=9 if bold else 6, color=color),
                fill="tozeroy" if bold else None,
                fillcolor="rgba(29,78,216,0.06)" if bold else None,
                hovertemplate="%{x}: %{y:,.0f}원<extra>" + col + "</extra>",
            ))
        fig.update_layout(
            plot_bgcolor="white", paper_bgcolor="white",
            font=dict(family="Pretendard, Apple SD Gothic Neo, sans-serif", size=13),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            yaxis=dict(tickformat=",.0f", title="원", gridcolor="#F3F4F6"),
            xaxis=dict(title="", gridcolor="#F3F4F6"),
            margin=dict(l=10, r=10, t=20, b=10),
            height=360,
            hovermode="x unified",
        )
        st.plotly_chart(fig, use_container_width=True)
    except ImportError:
        chart_data = chart_df.set_index("월")[["세전 수익","세후 추정","최종 순수익"]]
        st.line_chart(chart_data)

st.markdown("<div style='margin-top:8px;'></div>", unsafe_allow_html=True)

# ── 월별 요약 테이블 ──────────────────────────────────────────────────────────
st.subheader("월별 요약")

table_rows = []
for _, r in df_all.iterrows():
    if not r["is_active"]:
        table_rows.append({
            "월": r["월"], "확정": "",
            "세전 수익": "—", "세후 추정": "—",
            "기타비용": "—", "최종 순수익": "—",
        })
    else:
        confirmed_badge = "✅" if r["confirmed"] else "⏳"
        table_rows.append({
            "월":       r["월"],
            "확정":     confirmed_badge,
            "세전 수익":   w(r["세전 수익"])   if r["has_data"] else "—",
            "세후 추정":   w(r["세후 추정"])   if r["has_data"] else "—",
            "기타비용":    w(r["기타비용"])    if r["has_data"] else "—",
            "최종 순수익": w(r["최종 순수익"]) if r["has_data"] else "—",
        })

# 합계 행
table_rows.append({
    "월": "합계", "확정": "",
    "세전 수익":   w(cum_gross),
    "세후 추정":   w(cum_after),
    "기타비용":    w(cum_exp),
    "최종 순수익": w(cum_net),
})

table_df = pd.DataFrame(table_rows)

def _style_table(df):
    styles = pd.DataFrame("", index=df.index, columns=df.columns)
    styles["기타비용"]    = "color: #DC2626;"
    styles["최종 순수익"] = "color: #1D4ED8; font-weight: 700;"
    # 합계 행
    last = len(df) - 1
    for col in df.columns:
        styles.iloc[last][col] = "font-weight: 800; border-top: 2px solid #E5E8ED;"
    styles.iloc[last]["기타비용"]    = "font-weight: 800; color: #DC2626; border-top: 2px solid #E5E8ED;"
    styles.iloc[last]["최종 순수익"] = "font-weight: 800; color: #1D4ED8; border-top: 2px solid #E5E8ED;"
    return styles

st.dataframe(
    table_df.style.apply(_style_table, axis=None),
    use_container_width=True, hide_index=True,
)

st.caption("✅ 확정: 정산관리에서 손익 저장 완료 &nbsp;|&nbsp; ⏳ 미확정: 기타비용/플레이스/블로그 데이터만 있는 상태")
