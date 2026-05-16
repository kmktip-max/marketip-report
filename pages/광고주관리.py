"""광고주 관리 — 관리자 전용"""
import streamlit as st
import json, os, sys, uuid
from datetime import date
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# ── 관리자 전용 ───────────────────────────────────────────────────────────────
if st.session_state.get("auth_type") != "admin":
    st.error("🔒 관리자만 접근 가능합니다.")
    st.stop()

# ── 경로 ─────────────────────────────────────────────────────────────────────
F_CLIENTS      = os.path.join(ROOT, "clients.json")
F_REPORTS      = os.path.join(ROOT, "client_reports.json")
F_ADSPEND      = os.path.join(ROOT, "client_ad_spend.json")
F_REBATES      = os.path.join(ROOT, "client_rebates.json")
F_IMPROVEMENTS = os.path.join(ROOT, "client_improvements.json")
F_REQUESTS     = os.path.join(ROOT, "client_requests.json")
REPORTS_DIR    = os.path.join(ROOT, "client_reports_files")
os.makedirs(REPORTS_DIR, exist_ok=True)

# ── 데이터 함수 ───────────────────────────────────────────────────────────────
def _load(p):
    try:
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return []

def _save(p, data):
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_clients():      return _load(F_CLIENTS)
def save_clients(d):     _save(F_CLIENTS, d)
def load_reports():      return _load(F_REPORTS)
def save_reports(d):     _save(F_REPORTS, d)
def load_adspend():      return _load(F_ADSPEND)
def save_adspend(d):     _save(F_ADSPEND, d)
def load_rebates():      return _load(F_REBATES)
def save_rebates(d):     _save(F_REBATES, d)
def load_improvements(): return _load(F_IMPROVEMENTS)
def save_improvements(d):_save(F_IMPROVEMENTS, d)
def load_requests():     return _load(F_REQUESTS)
def save_requests(d):    _save(F_REQUESTS, d)

# ── 상수 ─────────────────────────────────────────────────────────────────────
TRANSFER_STATUSES    = ["이관대기", "이관완료", "운영중", "보류", "종료"]
REBATE_STATUSES      = ["예정", "지급완료", "보류"]
IMPROVEMENT_STATUSES = ["제안", "진행중", "적용완료", "보류"]
REQUEST_STATUSES     = ["접수", "처리중", "완료", "보류"]

STATUS_COLORS = {
    "이관대기": ("#FEF3C7", "#92400E"),
    "이관완료": ("#DBEAFE", "#1D4ED8"),
    "운영중":   ("#DCFCE7", "#16A34A"),
    "보류":     ("#FEE2E2", "#DC2626"),
    "종료":     ("#F3F4F6", "#6B7280"),
    "예정":     ("#FEF3C7", "#92400E"),
    "지급완료": ("#DCFCE7", "#16A34A"),
    "제안":     ("#DBEAFE", "#1D4ED8"),
    "진행중":   ("#FEF3C7", "#92400E"),
    "적용완료": ("#DCFCE7", "#16A34A"),
    "접수":     ("#DBEAFE", "#1D4ED8"),
    "처리중":   ("#FEF3C7", "#92400E"),
    "완료":     ("#DCFCE7", "#16A34A"),
}

# ── UI 헬퍼 ──────────────────────────────────────────────────────────────────
def w(n):
    return f"{int(round(n)):,} 원"

_KPI = {
    "neutral":  ("#FFFFFF", "#E5E8ED", "#6B7280", "#111827", "22px", "600"),
    "negative": ("#FFF5F5", "#FCA5A5", "#DC2626", "#DC2626", "22px", "700"),
    "primary":  ("#EFF6FF", "#93C5FD", "#1D4ED8", "#1D4ED8", "28px", "800"),
    "green":    ("#F0FFF4", "#86EFAC", "#16A34A", "#16A34A", "22px", "700"),
    "blue":     ("#EFF6FF", "#93C5FD", "#1D4ED8", "#1D4ED8", "22px", "700"),
}

def _kpi(label, value, variant="neutral"):
    bg, border, lc, vc, vs, fw = _KPI.get(variant, _KPI["neutral"])
    return (f'<div style="background:{bg};border:1.5px solid {border};border-radius:14px;'
            f'padding:20px 22px;height:100%;">'
            f'<div style="font-size:12px;color:{lc};font-weight:600;margin-bottom:8px;">{label}</div>'
            f'<div style="font-size:{vs};color:{vc};font-weight:{fw};line-height:1.2;">{value}</div></div>')

def _badge(status):
    bg, tx = STATUS_COLORS.get(status, ("#E5E8ED", "#374151"))
    return (f'<span style="display:inline-block;background:{bg};color:{tx};font-size:11px;'
            f'font-weight:700;padding:3px 10px;border-radius:100px;">{status}</span>')

# ── 광고주 선택기 (다른 탭 공통) ──────────────────────────────────────────────
def _client_selector(tab_key):
    clients = load_clients()
    if not clients:
        st.info("등록된 광고주가 없습니다.")
        return None, None
    names = [c["name"] for c in clients]
    default_idx = 0
    sel_id = st.session_state.get("selected_client_id")
    if sel_id:
        ids = [c["client_id"] for c in clients]
        if sel_id in ids:
            default_idx = ids.index(sel_id)
    sel_name = st.selectbox("광고주 선택", names, index=default_idx, key=f"cl_sel_{tab_key}")
    sel_cl = next((c for c in clients if c["name"] == sel_name), None)
    if sel_cl:
        st.session_state["selected_client_id"] = sel_cl["client_id"]
    return sel_cl, sel_cl["client_id"] if sel_cl else None

# ── 헤더 ─────────────────────────────────────────────────────────────────────
hc1, hc2 = st.columns([5, 1])
with hc1:
    st.title("🏢 광고주 관리")
with hc2:
    st.write("")
    if st.button("로그아웃"):
        st.session_state.pop("settlement_auth", None)
        st.rerun()

# ── 탭 ───────────────────────────────────────────────────────────────────────
t_report, t_spend, t_rebate, t_improve, t_request = st.tabs([
    "📄 광고 리포트",
    "💰 광고비 흐름",
    "💸 리베이트",
    "🔧 개선 포인트",
    "📬 문의/요청",
])

# ═════════════════════════════════════════════════════════════════════════════
# 1. 광고 리포트
# ═════════════════════════════════════════════════════════════════════════════
with t_report:
    st.subheader("광고 리포트")
    sel_cl, cid = _client_selector("report")
    if cid:
        reports = [r for r in load_reports() if r.get("client_id") == cid]

        with st.expander("➕ 리포트 업로드", expanded=False):
            with st.form("add_report", clear_on_submit=True):
                rfc1, rfc2 = st.columns(2)
                with rfc1:
                    r_year  = st.number_input("연도", 2024, 2030, date.today().year, key="rfy")
                    r_month = st.number_input("월",   1,    12,   date.today().month, key="rfm")
                    r_title = st.text_input("리포트 제목")
                with rfc2:
                    r_status = st.selectbox("상태", ["작성중", "검토중", "발송완료"])
                    r_file   = st.file_uploader("파일 업로드 (HTML/PDF)", type=["html","pdf"])

                if st.form_submit_button("업로드", type="primary"):
                    file_path = ""
                    if r_file:
                        safe_name = f"{cid}_{r_year}_{r_month:02d}_{r_file.name}"
                        file_path = os.path.join(REPORTS_DIR, safe_name)
                        with open(file_path, "wb") as ff:
                            ff.write(r_file.getbuffer())
                    all_rpts = load_reports()
                    all_rpts.append({
                        "report_id":        str(uuid.uuid4()),
                        "client_id":        cid,
                        "year":             int(r_year),
                        "month":            int(r_month),
                        "report_title":     r_title.strip() or f"{r_year}년 {r_month}월 리포트",
                        "report_file_path": file_path,
                        "created_at":       str(date.today()),
                        "status":           r_status,
                    })
                    save_reports(all_rpts)
                    st.success("업로드 완료")
                    st.rerun()

        if not reports:
            st.info("업로드된 리포트가 없습니다.")
        else:
            for rp in sorted(reports, key=lambda x: (x.get("year",0), x.get("month",0)), reverse=True):
                rpc1, rpc2, rpc3 = st.columns([4, 2, 1])
                with rpc1:
                    st.markdown(f"**{rp.get('report_title','—')}**")
                    st.caption(f"{rp.get('year','')}년 {rp.get('month','')}월 | 등록: {rp.get('created_at','')}")
                with rpc2:
                    st.markdown(_badge(rp.get("status","—")), unsafe_allow_html=True)
                with rpc3:
                    fp = rp.get("report_file_path", "")
                    if fp and os.path.exists(fp):
                        with open(fp, "rb") as ff:
                            st.download_button(
                                "⬇️",
                                ff.read(),
                                file_name=os.path.basename(fp),
                                key=f"dl_{rp['report_id']}",
                            )
                    else:
                        st.caption("파일 없음")
                st.divider()

# ═════════════════════════════════════════════════════════════════════════════
# 3. 광고비 흐름
# ═════════════════════════════════════════════════════════════════════════════
with t_spend:
    st.subheader("광고비 흐름")
    sel_cl, cid = _client_selector("spend")
    if cid:
        spends = [s for s in load_adspend() if s.get("client_id") == cid]

        with st.expander("➕ 광고비 입력", expanded=False):
            with st.form("add_spend", clear_on_submit=True):
                spc1, spc2, spc3 = st.columns(3)
                with spc1:
                    sp_year  = st.number_input("연도", 2024, 2030, date.today().year, key="spy")
                    sp_month = st.number_input("월",   1,    12,   date.today().month, key="spm")
                    sp_media = st.text_input("매체")
                with spc2:
                    sp_supply = st.number_input("광고비 공급가(원)", 0, step=1000)
                    sp_vat    = st.number_input("광고비 VAT(원)",    0, step=100)
                    sp_total  = st.number_input("광고비 합계(원)",   0, step=1000)
                with spc3:
                    sp_inq  = st.number_input("문의수", 0, step=1)
                    sp_memo = st.text_area("메모", height=100)

                if st.form_submit_button("저장", type="primary"):
                    all_sp = load_adspend()
                    all_sp.append({
                        "spend_id":      str(uuid.uuid4()),
                        "client_id":     cid,
                        "year":          int(sp_year),
                        "month":         int(sp_month),
                        "media":         sp_media.strip(),
                        "ad_supply":     int(sp_supply),
                        "ad_vat":        int(sp_vat),
                        "ad_total":      int(sp_total),
                        "inquiry_count": int(sp_inq),
                        "memo":          sp_memo.strip(),
                        "created_at":    str(date.today()),
                    })
                    save_adspend(all_sp)
                    st.success("저장 완료")
                    st.rerun()

        if not spends:
            st.info("등록된 광고비 데이터가 없습니다.")
        else:
            df_sp = pd.DataFrame(spends).sort_values(["year","month"])
            df_sp["월"] = df_sp["year"].astype(str) + "-" + df_sp["month"].astype(str).str.zfill(2)

            total_spend = df_sp["ad_total"].sum()
            total_inq   = df_sp["inquiry_count"].sum()
            avg_cpi     = total_spend / total_inq if total_inq > 0 else 0

            kc = st.columns(3)
            kc[0].markdown(_kpi("총 광고비 합계", w(total_spend), "primary"), unsafe_allow_html=True)
            kc[1].markdown(_kpi("총 문의수",      f"{int(total_inq):,} 건"),   unsafe_allow_html=True)
            kc[2].markdown(_kpi("건당 광고비",    w(avg_cpi)),                 unsafe_allow_html=True)

            st.markdown("<div style='margin-top:20px;'></div>", unsafe_allow_html=True)

            try:
                import plotly.graph_objects as go
                from plotly.subplots import make_subplots

                monthly = df_sp.groupby("월").agg({"ad_total":"sum","inquiry_count":"sum"}).reset_index()

                fig = make_subplots(specs=[[{"secondary_y": True}]])
                fig.add_trace(go.Bar(
                    x=monthly["월"], y=monthly["ad_total"], name="광고비 합계",
                    marker_color="#93C5FD",
                ), secondary_y=False)
                fig.add_trace(go.Scatter(
                    x=monthly["월"], y=monthly["inquiry_count"], name="문의수",
                    mode="lines+markers",
                    line=dict(color="#1D4ED8", width=2), marker=dict(size=8),
                ), secondary_y=True)
                fig.update_layout(
                    plot_bgcolor="white", paper_bgcolor="white",
                    font=dict(family="Pretendard, Apple SD Gothic Neo, sans-serif", size=13),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                    yaxis=dict(tickformat=",.0f", title="광고비(원)", gridcolor="#F3F4F6"),
                    yaxis2=dict(title="문의수"),
                    margin=dict(l=10, r=10, t=20, b=10), height=320,
                )
                st.plotly_chart(fig, use_container_width=True)
            except ImportError:
                pass

            st.subheader("월별 상세")
            disp = df_sp[["월","media","ad_supply","ad_vat","ad_total","inquiry_count","memo"]].copy()
            disp.columns = ["월","매체","공급가(원)","VAT(원)","합계(원)","문의수","메모"]
            st.dataframe(disp, use_container_width=True, hide_index=True)

# ═════════════════════════════════════════════════════════════════════════════
# 4. 리베이트
# ═════════════════════════════════════════════════════════════════════════════
with t_rebate:
    st.subheader("리베이트")
    sel_cl, cid = _client_selector("rebate")
    if cid and sel_cl:
        rebate_rate = float(sel_cl.get("rebate_rate", 0))
        rebates = [r for r in load_rebates() if r.get("client_id") == cid]

        st.info(f"적용 리베이트율: **{rebate_rate:.1f}%** (광고비 합계금액 VAT 포함 × {rebate_rate:.1f}%)")

        with st.expander("➕ 리베이트 입력", expanded=False):
            with st.form("add_rebate", clear_on_submit=True):
                rbc1, rbc2 = st.columns(2)
                with rbc1:
                    rb_year     = st.number_input("연도", 2024, 2030, date.today().year, key="rby")
                    rb_month    = st.number_input("월",   1,    12,   date.today().month, key="rbm")
                    rb_ad_total = st.number_input("광고비 합계(원, VAT포함)", 0, step=1000)
                with rbc2:
                    rb_status    = st.selectbox("지급 상태", REBATE_STATUSES)
                    rb_paid_date = st.date_input("지급일", value=date.today())
                    rb_memo      = st.text_area("메모", height=68)

                if st.form_submit_button("저장", type="primary"):
                    rebate_amt = rb_ad_total * rebate_rate / 100
                    all_rb = load_rebates()
                    all_rb.append({
                        "rebate_id":     str(uuid.uuid4()),
                        "client_id":     cid,
                        "year":          int(rb_year),
                        "month":         int(rb_month),
                        "ad_total":      int(rb_ad_total),
                        "rebate_rate":   rebate_rate,
                        "rebate_amount": rebate_amt,
                        "status":        rb_status,
                        "paid_date":     str(rb_paid_date),
                        "memo":          rb_memo.strip(),
                        "created_at":    str(date.today()),
                    })
                    save_rebates(all_rb)
                    st.success("저장 완료")
                    st.rerun()

        if not rebates:
            st.info("등록된 리베이트 데이터가 없습니다.")
        else:
            total_rb  = sum(r.get("rebate_amount", 0) for r in rebates)
            paid_rb   = sum(r.get("rebate_amount", 0) for r in rebates if r.get("status") == "지급완료")
            pend_rb   = total_rb - paid_rb

            kc = st.columns(3)
            kc[0].markdown(_kpi("총 리베이트 예상액", w(total_rb), "green"),   unsafe_allow_html=True)
            kc[1].markdown(_kpi("지급완료",          w(paid_rb),  "blue"),    unsafe_allow_html=True)
            kc[2].markdown(_kpi("미지급",            w(pend_rb),
                                "negative" if pend_rb > 0 else "neutral"),     unsafe_allow_html=True)

            st.markdown("<div style='margin-top:16px;'></div>", unsafe_allow_html=True)

            for rb in sorted(rebates, key=lambda x: (x.get("year",0), x.get("month",0)), reverse=True):
                rbc1, rbc2, rbc3, rbc4 = st.columns([2, 2, 2, 1])
                with rbc1:
                    st.markdown(f"**{rb.get('year','')}년 {rb.get('month','')}월**")
                    st.caption(f"광고비: {rb.get('ad_total',0):,}원")
                with rbc2:
                    st.markdown(
                        f"<b style='color:#16A34A;font-size:16px;'>{int(round(rb.get('rebate_amount',0))):,}원</b>",
                        unsafe_allow_html=True,
                    )
                    st.caption(f"리베이트율: {rb.get('rebate_rate',0):.1f}%")
                with rbc3:
                    st.markdown(_badge(rb.get("status","—")), unsafe_allow_html=True)
                    st.caption(f"지급일: {rb.get('paid_date','—')}")
                with rbc4:
                    if st.button("삭제", key=f"del_rb_{rb['rebate_id']}"):
                        save_rebates([r for r in load_rebates() if r.get("rebate_id") != rb["rebate_id"]])
                        st.rerun()
                st.divider()

# ═════════════════════════════════════════════════════════════════════════════
# 5. 개선 포인트
# ═════════════════════════════════════════════════════════════════════════════
with t_improve:
    st.subheader("개선 포인트")
    sel_cl, cid = _client_selector("improve")
    if cid:
        improvements = [i for i in load_improvements() if i.get("client_id") == cid]

        with st.expander("➕ 개선 포인트 등록", expanded=False):
            with st.form("add_improve", clear_on_submit=True):
                imc1, imc2 = st.columns(2)
                with imc1:
                    im_date   = st.date_input("날짜", value=date.today())
                    im_item   = st.text_input("개선 항목", placeholder="예: 제외키워드 정리")
                    im_status = st.selectbox("상태", IMPROVEMENT_STATUSES)
                with imc2:
                    im_content = st.text_area("개선 내용", height=80)
                    im_effect  = st.text_area("기대 효과", height=80)

                if st.form_submit_button("저장", type="primary"):
                    all_im = load_improvements()
                    all_im.append({
                        "improve_id": str(uuid.uuid4()),
                        "client_id":  cid,
                        "date":       str(im_date),
                        "item":       im_item.strip(),
                        "content":    im_content.strip(),
                        "effect":     im_effect.strip(),
                        "status":     im_status,
                        "created_at": str(date.today()),
                    })
                    save_improvements(all_im)
                    st.success("저장 완료")
                    st.rerun()

        if not improvements:
            st.info("등록된 개선 포인트가 없습니다.")
        else:
            for im in sorted(improvements, key=lambda x: x.get("date",""), reverse=True):
                irc1, irc2, irc3 = st.columns([2, 4, 1])
                with irc1:
                    st.markdown(f"**{im.get('item','—')}**")
                    st.caption(im.get("date","—"))
                with irc2:
                    st.write(im.get("content",""))
                    if im.get("effect"):
                        st.caption(f"기대효과: {im['effect']}")
                with irc3:
                    st.markdown(_badge(im.get("status","—")), unsafe_allow_html=True)
                    if st.button("삭제", key=f"del_im_{im['improve_id']}"):
                        save_improvements([i for i in load_improvements() if i.get("improve_id") != im["improve_id"]])
                        st.rerun()
                st.divider()

# ═════════════════════════════════════════════════════════════════════════════
# 6. 문의/요청
# ═════════════════════════════════════════════════════════════════════════════
with t_request:
    st.subheader("문의/요청")
    sel_cl, cid = _client_selector("request")
    if cid:
        reqs = [r for r in load_requests() if r.get("client_id") == cid]

        with st.expander("➕ 문의/요청 등록", expanded=False):
            with st.form("add_request", clear_on_submit=True):
                rqc1, rqc2 = st.columns(2)
                with rqc1:
                    rq_date    = st.date_input("요청일", value=date.today())
                    rq_title   = st.text_input("요청 제목")
                    rq_status  = st.selectbox("처리 상태", REQUEST_STATUSES)
                with rqc2:
                    rq_content = st.text_area("요청 내용", height=80)
                    rq_answer  = st.text_area("답변/메모", height=80)

                if st.form_submit_button("저장", type="primary"):
                    all_rq = load_requests()
                    all_rq.append({
                        "request_id": str(uuid.uuid4()),
                        "client_id":  cid,
                        "date":       str(rq_date),
                        "title":      rq_title.strip(),
                        "content":    rq_content.strip(),
                        "answer":     rq_answer.strip(),
                        "status":     rq_status,
                        "created_at": str(date.today()),
                    })
                    save_requests(all_rq)
                    st.success("저장 완료")
                    st.rerun()

        if not reqs:
            st.info("등록된 문의/요청이 없습니다.")
        else:
            total_rq = len(reqs)
            done_rq  = len([r for r in reqs if r.get("status") == "완료"])
            pend_rq  = len([r for r in reqs if r.get("status") in ["접수","처리중"]])

            kc = st.columns(3)
            kc[0].markdown(_kpi("총 요청",      f"{total_rq} 건"),              unsafe_allow_html=True)
            kc[1].markdown(_kpi("완료",          f"{done_rq} 건",  "green"),    unsafe_allow_html=True)
            kc[2].markdown(_kpi("처리중/접수",   f"{pend_rq} 건",
                                "negative" if pend_rq > 0 else "neutral"),       unsafe_allow_html=True)

            st.markdown("<div style='margin-top:16px;'></div>", unsafe_allow_html=True)

            for rq in sorted(reqs, key=lambda x: x.get("date",""), reverse=True):
                rqrc1, rqrc2, rqrc3 = st.columns([2, 4, 1])
                with rqrc1:
                    st.markdown(f"**{rq.get('title','—')}**")
                    st.caption(f"요청일: {rq.get('date','—')}")
                with rqrc2:
                    st.write(rq.get("content",""))
                    if rq.get("answer"):
                        st.caption(f"💬 {rq['answer']}")
                with rqrc3:
                    st.markdown(_badge(rq.get("status","—")), unsafe_allow_html=True)
                    if st.button("삭제", key=f"del_rq_{rq['request_id']}"):
                        save_requests([r for r in load_requests() if r.get("request_id") != rq["request_id"]])
                        st.rerun()
                st.divider()
