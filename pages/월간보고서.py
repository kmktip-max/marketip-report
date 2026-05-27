import streamlit as st
import streamlit.components.v1 as components
import json
import os
import sys
from datetime import datetime, date, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from report_engine.naver_api import NaverAdAPI
from report_engine.emailer import send_report
from report_engine.report_html import generate_html
from report_engine.storage import load_clients, save_clients


# ── 유틸 ──────────────────────────────────────────────────────────────
def get_secret(key, default=""):
    try:
        if hasattr(st, "secrets") and key in st.secrets:
            return str(st.secrets[key])
    except Exception:
        pass
    return os.getenv(key, default)


def load_history():
    path = os.path.join(ROOT, "report_history.json")
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return []


def save_history(history):
    path = os.path.join(ROOT, "report_history.json")
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ── 일괄 발송 헬퍼 ────────────────────────────────────────────────────
def _client_sendable(c):
    """필수 필드 검증. (can_send: bool, missing: list[str]) 반환."""
    missing = []
    if not str(c.get("name", "")).strip():         missing.append("광고주명")
    if not str(c.get("customer_id", "")).strip():  missing.append("Customer ID")
    if not str(c.get("api_key", "")).strip():      missing.append("API Key")
    if not str(c.get("secret_key", "")).strip():   missing.append("Secret Key")
    if not str(c.get("email", "")).strip():        missing.append("수신 이메일")
    return len(missing) == 0, missing


def _get_period_range(period_key):
    """(since, until) 문자열 반환."""
    today = date.today()
    if period_key == "weekly":
        until = today - timedelta(days=1)
        since = until - timedelta(days=6)
    else:
        first = today.replace(day=1)
        until = first - timedelta(days=1)
        since = until.replace(day=1)
    return since.strftime("%Y-%m-%d"), until.strftime("%Y-%m-%d")


def _already_sent(history, client_name, period_key, since, until):
    """동일 광고주·기간으로 이미 성공 발송된 이력이 있는지 확인."""
    for h in history:
        if (h.get("client") == client_name
                and h.get("period") == period_key
                and h.get("since") == since
                and h.get("until") == until
                and "성공" in str(h.get("status", ""))):
            return True
    return False


def _get_last_sent(history, client_name):
    """해당 광고주의 마지막 성공 발송일시 반환."""
    for h in reversed(history):
        if h.get("client") == client_name and "성공" in str(h.get("status", "")):
            return h.get("sent_at", "-")
    return "-"


# ── 인증 ──────────────────────────────────────────────────────────────
ADMIN_PW = get_secret("ADMIN_PASSWORD", "mktip")


def check_admin():
    if st.session_state.get("report_admin_auth"):
        return True
    _, col, _ = st.columns([1, 2, 1])
    with col:
        st.markdown("## 🔐 관리자 전용")
        pw = st.text_input("비밀번호", type="password")
        if st.button("로그인", type="primary", use_container_width=True):
            if pw == ADMIN_PW:
                st.session_state.report_admin_auth = True
                st.rerun()
            else:
                st.error("비밀번호가 틀렸습니다.")
    return False


if not check_admin():
    st.stop()


# ── 헤더 ──────────────────────────────────────────────────────────────
_hc1, _hc2 = st.columns([5, 1])
with _hc1:
    st.title("📊 광고 보고서 관리")
with _hc2:
    if st.button("로그아웃"):
        st.session_state.report_admin_auth = False
        st.session_state.pop("preview_results", None)
        st.rerun()

tab1, tab2, tab3, tab4 = st.tabs(["👥 광고주 관리", "📋 보고서 발송", "📜 발송 이력", "⚙️ 설정"])


# ═══════════════════════════════════════════════════════════════════════
# 탭1: 광고주 관리
# ═══════════════════════════════════════════════════════════════════════
with tab1:
    st.subheader("새 광고주 추가")
    with st.form("add_client", clear_on_submit=True):
        fc1, fc2 = st.columns(2)
        with fc1:
            name       = st.text_input("광고주명 *")
            cust_id    = st.text_input("Customer ID *", help="searchad.naver.com → URL 숫자")
            email      = st.text_input("수신 이메일 *")
            phone      = st.text_input("카카오 알림 전화번호", placeholder="010-0000-0000",
                                       help="보고서 발송 시 SMS/카카오 알림 수신 번호")
        with fc2:
            api_key    = st.text_input("API Access License *")
            secret_key = st.text_input("Secret Key *", type="password")
            memo       = st.text_input("메모")

        if st.form_submit_button("➕ 추가", type="primary"):
            if not all([name, cust_id, email, api_key, secret_key]):
                st.error("* 항목을 모두 입력해주세요.")
            else:
                clients = load_clients()
                clients.append({
                    "id": datetime.now().strftime("%Y%m%d%H%M%S"),
                    "name": name.strip(),
                    "customer_id": cust_id.strip(),
                    "email": email.strip(),
                    "phone": phone.strip(),
                    "api_key": api_key.strip(),
                    "secret_key": secret_key.strip(),
                    "memo": memo,
                    "created_at": datetime.now().strftime("%Y-%m-%d"),
                })
                save_clients(clients)
                st.success(f"✅ {name} 추가 완료!")
                st.rerun()

    st.divider()
    st.subheader("등록된 광고주")
    clients = load_clients()
    if not clients:
        st.info("등록된 광고주가 없습니다.")
    else:
        for i, cl in enumerate(clients):
            with st.expander(f"**{cl['name']}** | {cl['email']} | ID: {cl['customer_id']}"):
                ec1, ec2, ec3, ec4 = st.columns([4, 1, 1, 1])
                with ec1:
                    st.caption(
                        f"등록일: {cl.get('created_at','-')} | "
                        f"전화: {cl.get('phone','-') or '-'} | "
                        f"메모: {cl.get('memo','-') or '-'}"
                    )
                    st.caption(f"API Key: {cl['api_key'][:20]}...")
                with ec2:
                    if st.button("🔌 연결 테스트", key=f"test_{i}"):
                        with st.spinner("확인 중..."):
                            try:
                                api = NaverAdAPI(cl["api_key"], cl["secret_key"], cl["customer_id"])
                                ok, msg = api.test_connection()
                                st.success(msg) if ok else st.error(msg)
                            except Exception as e:
                                st.error(str(e))
                with ec3:
                    if st.button("✏️ 편집", key=f"edit_btn_{i}"):
                        st.session_state[f"editing_{i}"] = True
                with ec4:
                    if st.button("🗑️ 삭제", key=f"del_{i}"):
                        clients.pop(i)
                        save_clients(clients)
                        st.rerun()

                if st.session_state.get(f"editing_{i}"):
                    st.divider()
                    with st.form(key=f"edit_form_{i}"):
                        ef1, ef2 = st.columns(2)
                        with ef1:
                            e_name   = st.text_input("광고주명",   value=cl.get("name", ""),        key=f"e_name_{i}")
                            e_email  = st.text_input("수신 이메일", value=cl.get("email", ""),       key=f"e_email_{i}")
                            e_phone  = st.text_input("카카오 알림 전화번호", value=cl.get("phone", ""),
                                                     placeholder="010-0000-0000", key=f"e_phone_{i}")
                        with ef2:
                            e_apikey = st.text_input("API Access License", value=cl.get("api_key", ""),    key=f"e_api_{i}")
                            e_secret = st.text_input("Secret Key", value=cl.get("secret_key", ""),
                                                     type="password", key=f"e_secret_{i}")
                            e_memo   = st.text_input("메모", value=cl.get("memo", ""),               key=f"e_memo_{i}")

                        esub1, esub2 = st.columns(2)
                        _save = esub1.form_submit_button("💾 저장", type="primary", use_container_width=True)
                        _cancel = esub2.form_submit_button("취소", use_container_width=True)

                        if _save:
                            clients[i].update({
                                "name":       e_name.strip(),
                                "email":      e_email.strip(),
                                "phone":      e_phone.strip(),
                                "api_key":    e_apikey.strip(),
                                "secret_key": e_secret.strip(),
                                "memo":       e_memo,
                            })
                            save_clients(clients)
                            st.session_state.pop(f"editing_{i}", None)
                            st.rerun()
                        if _cancel:
                            st.session_state.pop(f"editing_{i}", None)
                            st.rerun()


# ═══════════════════════════════════════════════════════════════════════
# 탭2: 보고서 발송
# ═══════════════════════════════════════════════════════════════════════
with tab2:
    clients = load_clients()
    if not clients:
        st.warning("먼저 광고주를 등록해주세요.")
        st.stop()

    send_mode = st.radio(
        "발송 방식",
        ["단일 발송", "일괄 발송"],
        horizontal=True,
        key="send_mode_radio",
    )

    # ─────────────────────────────────────────────────────────────────
    # 단일 발송 (기존 로직 유지)
    # ─────────────────────────────────────────────────────────────────
    if send_mode == "단일 발송":
        st.subheader("① 발송 설정")
        sc1, sc2 = st.columns([2, 1])
        with sc1:
            selected_names = st.multiselect(
                "광고주 선택",
                options=[c["name"] for c in clients],
                default=[],
            )
        with sc2:
            period_label = st.radio("기간", ["주간 (지난 7일)", "월간 (지난달)"], horizontal=True)
            period_key = "weekly" if "주간" in period_label else "monthly"

        if not selected_names:
            st.info("광고주를 선택하세요.")
        else:
            selected_clients = [c for c in clients if c["name"] in selected_names]

            st.subheader("② 보고서 미리보기")
            if st.button("🔍 보고서 데이터 수집 및 미리보기 생성", type="secondary", use_container_width=True):
                import pandas as pd
                results = []
                for client in selected_clients:
                    with st.status(
                        f"📡 {client['name']} 데이터 수집 중...",
                        expanded=True,
                    ) as _col_status:
                        _step_msg = st.empty()

                        def _on_step(msg, _el=_step_msg):
                            _el.write(msg)

                        try:
                            api  = NaverAdAPI(client["api_key"], client["secret_key"], client["customer_id"])
                            data = api.fetch_report(period_key, on_step=_on_step)
                            html = generate_html(data, client["name"], datetime.now().strftime("%Y-%m-%d"))
                            results.append({"client": client, "data": data, "html": html, "status": "ok"})
                            sm = data.get("summary", {})
                            _col_status.update(
                                label=(
                                    f"✅ {client['name']} 완료 — "
                                    f"캠페인 {data['total_campaigns']}개 | "
                                    f"키워드 {data['total_keywords']}개 | "
                                    f"클릭 {sm.get('clicks', 0):,}회"
                                ),
                                state="complete",
                                expanded=False,
                            )
                        except Exception as e:
                            results.append({"client": client, "error": str(e), "status": "error"})
                            _col_status.update(
                                label=f"❌ {client['name']} 오류",
                                state="error",
                            )
                            st.error(f"❌ {client['name']} 오류: {e}")

                for r in results:
                    if r["status"] != "ok":
                        continue
                    client = r["client"]
                    data   = r["data"]
                    sm     = data.get("summary", {})
                    kwsm   = data.get("kw_summary", {})
                    dbg    = data.get("debug_params", {})
                    kws    = data["keywords"]

                    with st.expander(f"🔎 {client['name']} 데이터 검증", expanded=True):
                        st.markdown("**① API 요청 정보**")
                        dc1, dc2, dc3 = st.columns(3)
                        dc1.text(f"Customer ID : {dbg.get('customer_id','')}")
                        dc2.text(f"조회 시작일  : {dbg.get('since','')}")
                        dc3.text(f"조회 종료일  : {dbg.get('until','')}")
                        st.caption(
                            f"Endpoint: {dbg.get('endpoint','')}  |  "
                            f"Fields: {dbg.get('fields','')}  |  "
                            f"캠페인 통계 row: {dbg.get('camp_stat_rows',0)}  |  "
                            f"키워드 통계 row: {dbg.get('kw_stat_rows',0)}  |  "
                            f"캠페인: {dbg.get('total_campaigns',0)}개  "
                            f"광고그룹: {dbg.get('total_adgroups',0)}개  "
                            f"키워드: {dbg.get('total_keywords',0)}개"
                        )
                        st.divider()
                        st.markdown("**② 캠페인 레벨 집계 (KPI 카드 기준)**")
                        mc1, mc2, mc3, mc4, mc5 = st.columns(5)
                        mc1.metric("클릭수",   f"{sm.get('clicks',0):,}")
                        mc2.metric("노출수",   f"{sm.get('impressions',0):,}")
                        mc3.metric("전환수",   f"{sm.get('conversions',0):,}")
                        mc4.metric("전환매출", f"{sm.get('revenue',0):,}")
                        mc5.metric("추정비용", f"{sm.get('cost',0):,}")
                        st.markdown("**③ 키워드 레벨 합산**")
                        kc1, kc2, kc3, kc4, kc5 = st.columns(5)
                        kc1.metric("클릭수", f"{kwsm.get('clicks',0):,}",
                                   delta=f"{kwsm.get('clicks',0)-sm.get('clicks',0):+,}")
                        kc2.metric("노출수", f"{kwsm.get('impressions',0):,}",
                                   delta=f"{kwsm.get('impressions',0)-sm.get('impressions',0):+,}")
                        kc3.metric("전환수",   f"{kwsm.get('conversions',0):,}")
                        kc4.metric("전환매출", f"{kwsm.get('revenue',0):,}")
                        kc5.metric("추정비용", f"{kwsm.get('cost',0):,}")
                        st.divider()
                        camp_table = data.get("camp_table", [])
                        if camp_table:
                            st.markdown("**④ 캠페인별 성과**")
                            st.dataframe(pd.DataFrame(camp_table), use_container_width=True, hide_index=True)
                        if kws:
                            st.markdown("**⑤ 키워드 성과 상위 10행**")
                            _cols = ["keyword", "clicks", "impressions", "conversions",
                                     "revenue", "cost", "ctr", "cpc", "roas", "avg_rnk"]
                            st.dataframe(
                                pd.DataFrame(kws[:10])[[col for col in _cols if col in kws[0]]],
                                use_container_width=True, hide_index=True,
                            )
                        with st.expander("디버그 로그"):
                            for line in data.get("debug", []):
                                st.caption(line)

                st.session_state.preview_results = results
                st.session_state.preview_period  = period_key

            if "preview_results" in st.session_state:
                results    = st.session_state.preview_results
                ok_results = [r for r in results if r["status"] == "ok"]

                if ok_results:
                    st.divider()
                    preview_idx = st.selectbox(
                        "미리볼 광고주 선택",
                        options=range(len(ok_results)),
                        format_func=lambda i: ok_results[i]["client"]["name"],
                    )
                    r = ok_results[preview_idx]
                    d = r["data"]
                    with st.expander(f"📊 {r['client']['name']} 보고서 미리보기", expanded=True):
                        st.caption(
                            f"기간: {d['since']} ~ {d['until']} | "
                            f"키워드: {d['total_keywords']}개 | "
                            f"클릭: {sum(k['clicks'] for k in d['keywords']):,}회"
                        )
                        components.html(r["html"], height=1200, scrolling=True)

                    st.divider()
                    st.subheader("③ 이메일 발송")
                    smtp_user = get_secret("SMTP_USER", "")
                    if not smtp_user:
                        st.error("⚙️ 이메일 설정 탭에서 SMTP 설정을 먼저 해주세요.")
                    else:
                        period_k = st.session_state.get("preview_period", "monthly")
                        period_str = "주간" if period_k == "weekly" else "월간"
                        for r in ok_results:
                            st.info(
                                f"**{r['client']['name']}** → `{r['client']['email']}`  \n"
                                f"제목: [광고 성과 보고서] {r['client']['name']} | {period_str} "
                                f"({r['data']['since']} ~ {r['data']['until']})"
                            )
                        st.warning("⚠️ 위 내용을 확인하셨나요? 아래 버튼을 누르면 실제 이메일이 발송됩니다.")

                        _has_phone = all(r["client"].get("phone") for r in ok_results)
                        _any_phone = any(r["client"].get("phone") for r in ok_results)

                        _btn_col1, _btn_col2 = st.columns(2)
                        _send_email_only  = _btn_col1.button(
                            "✉️ 이메일만 발송", type="secondary", use_container_width=True,
                            key="btn_send_email_only",
                        )
                        _send_email_kakao = _btn_col2.button(
                            "✉️📱 이메일 + 카톡 발송", type="primary", use_container_width=True,
                            key="btn_send_email_kakao",
                            disabled=not _any_phone,
                            help="전화번호가 등록된 광고주에게만 카톡 알림 발송",
                        )

                        _do_send  = _send_email_only or _send_email_kakao
                        _do_kakao = _send_email_kakao

                        if _do_send:
                            smtp_cfg = {
                                "smtp_user":     smtp_user,
                                "smtp_password": get_secret("SMTP_PASSWORD", ""),
                                "smtp_host":     get_secret("SMTP_HOST", "smtp.naver.com"),
                                "smtp_port":     int(get_secret("SMTP_PORT", "465")),
                            }
                            history  = load_history()
                            period_k = st.session_state.get("preview_period", "monthly")

                            for r in ok_results:
                                client = r["client"]
                                _since = r["data"]["since"]
                                _until = r["data"]["until"]
                                try:
                                    send_report(
                                        to_email=client["email"],
                                        client_name=client["name"],
                                        period=period_k,
                                        since=_since,
                                        until=_until,
                                        html_body=r["html"],
                                        **smtp_cfg,
                                    )
                                    st.success(f"✅ **{client['name']}** → {client['email']} 이메일 발송 완료!")
                                    history.append({
                                        "client":    client["name"],
                                        "email":     client["email"],
                                        "period":    period_k,
                                        "since":     _since,
                                        "until":     _until,
                                        "keywords":  r["data"]["total_keywords"],
                                        "sent_at":   datetime.now().strftime("%Y-%m-%d %H:%M"),
                                        "status":    "성공",
                                        "send_mode": "single",
                                    })

                                    if _do_kakao:
                                        _phone = client.get("phone", "").strip()
                                        if _phone:
                                            try:
                                                from notifications import _solapi_send
                                                _sms_text = (
                                                    f"[마케팁] 광고 성과 보고서 발송 완료\n"
                                                    f"광고주: {client['name']}\n"
                                                    f"기간: {_since} ~ {_until}\n"
                                                    f"이메일({client['email']})로 전송되었습니다."
                                                )
                                                _sms_r = _solapi_send(_phone, _sms_text)
                                                if _sms_r.get("status") == "success":
                                                    st.info(f"📱 **{client['name']}** → {_phone} 카톡/SMS 발송 완료!")
                                                else:
                                                    st.warning(
                                                        f"📱 카톡/SMS 발송 실패: "
                                                        f"{_sms_r.get('reason') or _sms_r.get('error','')}"
                                                    )
                                            except Exception as _sms_e:
                                                st.warning(f"📱 카톡/SMS 오류: {_sms_e}")
                                        else:
                                            st.caption(f"📱 {client['name']} — 전화번호 미등록, SMS 건너뜀")

                                except Exception as e:
                                    st.error(f"❌ **{client['name']}** 발송 실패: {e}")
                                    history.append({
                                        "client":    client["name"],
                                        "sent_at":   datetime.now().strftime("%Y-%m-%d %H:%M"),
                                        "status":    f"실패: {str(e)[:100]}",
                                        "send_mode": "single",
                                    })

                            save_history(history)
                            st.session_state.pop("preview_results", None)

    # ─────────────────────────────────────────────────────────────────
    # 일괄 발송
    # ─────────────────────────────────────────────────────────────────
    else:
        st.subheader("① 발송 설정")

        bc1, bc2 = st.columns([2, 1])
        with bc1:
            period_label = st.radio(
                "발송 기간", ["주간 (지난 7일)", "월간 (지난달)"],
                horizontal=True, key="bulk_period",
            )
            period_key = "weekly" if "주간" in period_label else "monthly"
            since, until = _get_period_range(period_key)
            st.caption(f"분석 기간: **{since} ~ {until}**")
        with bc2:
            dedup_on = st.checkbox(
                "중복 발송 방지",
                value=True,
                help="동일 광고주·기간 이미 성공 발송 시 스킵",
            )

        test_mode  = st.checkbox("🧪 테스트 모드 (실제 발송 없이 검증 / 관리자 이메일로 샘플 발송)")
        test_email = ""
        if test_mode:
            test_email = st.text_input(
                "테스트 수신 이메일",
                value=get_secret("SMTP_USER", ""),
                key="bulk_test_email",
            )

        st.divider()

        # 전체 선택/해제
        history_cur   = load_history()
        sendable_ids  = {c["id"] for c in clients if _client_sendable(c)[0]}

        sel_c1, sel_c2, _ = st.columns([1, 1, 4])
        if sel_c1.button("✅ 전체 선택"):
            for c in clients:
                can, _ = _client_sendable(c)
                already = _already_sent(history_cur, c["name"], period_key, since, until) if dedup_on else False
                st.session_state[f"bck_{c['id']}"] = can and not already
            st.rerun()
        if sel_c2.button("⬜ 전체 해제"):
            for c in clients:
                st.session_state[f"bck_{c['id']}"] = False
            st.rerun()

        # 광고주 테이블 헤더
        st.subheader("② 광고주 목록")
        th = st.columns([0.5, 2, 1.5, 2.2, 0.8, 1.5, 2])
        for col, hdr in zip(th, ["선택", "광고주명", "Customer ID", "수신 이메일", "API", "최근 발송", "비고"]):
            col.markdown(f"**{hdr}**")
        st.markdown("---")

        selected_bulk = []
        for c in clients:
            can_send, missing = _client_sendable(c)
            already   = _already_sent(history_cur, c["name"], period_key, since, until) if dedup_on else False
            last_sent = _get_last_sent(history_cur, c["name"])
            has_api   = bool(str(c.get("api_key", "")).strip() and str(c.get("secret_key", "")).strip())

            default_val = st.session_state.get(f"bck_{c['id']}", can_send and not already)

            row = st.columns([0.5, 2, 1.5, 2.2, 0.8, 1.5, 2])
            checked = row[0].checkbox("", key=f"bck_{c['id']}", value=default_val, disabled=not can_send)
            row[1].write(c.get("name", "-"))
            row[2].caption(c.get("customer_id", "") or "❌")
            row[3].caption(c.get("email", "") or "❌ 없음")
            row[4].markdown("✅" if has_api else "❌")
            row[5].caption(last_sent)

            if not can_send:
                row[6].caption(f"🚫 누락: {', '.join(missing)}")
            elif already and dedup_on:
                row[6].caption("⚠️ 이미 발송됨")
            else:
                row[6].caption("✅ 발송 대상")

            if checked and can_send:
                selected_bulk.append(c)

        st.divider()

        # 요약 지표
        st.subheader("③ 선택 현황")
        total_n    = len(clients)
        sendable_n = len([c for c in clients if _client_sendable(c)[0]])
        selected_n = len(selected_bulk)
        already_n  = sum(
            1 for c in clients
            if _client_sendable(c)[0] and _already_sent(history_cur, c["name"], period_key, since, until)
        ) if dedup_on else 0

        sm1, sm2, sm3, sm4 = st.columns(4)
        sm1.metric("전체 광고주",    total_n)
        sm2.metric("발송 가능",      sendable_n)
        sm3.metric("선택됨",         selected_n)
        sm4.metric("중복(기발송)",   already_n if dedup_on else "-")

        # 발송 실행
        st.divider()
        smtp_user = get_secret("SMTP_USER", "")
        if not smtp_user and not test_mode:
            st.warning("⚙️ 설정 탭에서 SMTP 설정을 먼저 해주세요.")
        elif selected_n == 0:
            st.info("발송할 광고주를 선택하세요.")
        else:
            btn_label = (
                f"🧪 테스트 검증 실행 ({selected_n}명)"
                if test_mode
                else f"✉️ 선택 광고주 월간보고서 일괄 발송 ({selected_n}명)"
            )
            if st.button(btn_label, type="primary", use_container_width=True):
                smtp_cfg = {
                    "smtp_user":     smtp_user,
                    "smtp_password": get_secret("SMTP_PASSWORD", ""),
                    "smtp_host":     get_secret("SMTP_HOST", "smtp.naver.com"),
                    "smtp_port":     int(get_secret("SMTP_PORT", "465")),
                }
                history = load_history()

                progress_bar = st.progress(0, text="일괄 발송 준비 중...")
                status_box   = st.empty()

                success_list, fail_list, skip_list, log_list = [], [], [], []
                total_sel = len(selected_bulk)

                for idx, client in enumerate(selected_bulk):
                    progress_bar.progress(idx / total_sel, text=f"{idx+1}/{total_sel} {client['name']} 처리 중...")
                    status_box.info(f"⏳ {idx+1}/{total_sel} — **{client['name']}** 보고서 생성 중...")

                    # 실행 시점 중복 재확인
                    if dedup_on and _already_sent(history, client["name"], period_key, since, until):
                        skip_list.append(client["name"])
                        log_list.append(f"⏭️ {client['name']}: 이미 발송됨 (스킵)")
                        history.append({
                            "client":    client["name"],
                            "email":     client.get("email", ""),
                            "period":    period_key,
                            "since":     since,
                            "until":     until,
                            "sent_at":   datetime.now().strftime("%Y-%m-%d %H:%M"),
                            "status":    "스킵: 중복",
                            "send_mode": "bulk",
                        })
                        continue

                    try:
                        api  = NaverAdAPI(client["api_key"], client["secret_key"], client["customer_id"])
                        data = api.fetch_report(period_key)
                        html = generate_html(data, client["name"], datetime.now().strftime("%Y-%m-%d"))

                        to_addr = test_email if test_mode else client["email"]
                        status_box.info(f"📧 {idx+1}/{total_sel} — **{client['name']}** → {to_addr} 발송 중...")

                        if not test_mode or to_addr:
                            send_report(
                                to_email=to_addr,
                                client_name=f"[테스트] {client['name']}" if test_mode else client["name"],
                                period=period_key,
                                since=data["since"],
                                until=data["until"],
                                html_body=html,
                                **smtp_cfg,
                            )

                        label = f"{client['name']} (테스트→{to_addr})" if test_mode else f"{client['name']} / {client['email']}"
                        success_list.append(label)
                        log_list.append(f"✅ {client['name']}: {'테스트 완료' if test_mode else '발송 완료'} → {to_addr}")
                        history.append({
                            "client":    client["name"],
                            "email":     to_addr,
                            "period":    period_key,
                            "since":     data["since"],
                            "until":     data["until"],
                            "keywords":  data.get("total_keywords", 0),
                            "sent_at":   datetime.now().strftime("%Y-%m-%d %H:%M"),
                            "status":    "테스트" if test_mode else "성공",
                            "send_mode": "bulk_test" if test_mode else "bulk",
                        })

                    except Exception as e:
                        err = str(e)[:120]
                        fail_list.append(f"{client['name']} — {err}")
                        log_list.append(f"❌ {client['name']}: 실패 — {err}")
                        history.append({
                            "client":    client["name"],
                            "email":     client.get("email", ""),
                            "period":    period_key,
                            "since":     since,
                            "until":     until,
                            "sent_at":   datetime.now().strftime("%Y-%m-%d %H:%M"),
                            "status":    f"실패: {err}",
                            "send_mode": "bulk",
                        })

                progress_bar.progress(1.0, text="완료!")
                status_box.empty()
                save_history(history)

                # 결과 요약
                st.divider()
                st.subheader("📋 발송 결과 요약")
                rs1, rs2, rs3, rs4 = st.columns(4)
                rs1.metric("총 선택",  total_sel)
                rs2.metric("✅ 성공",  len(success_list))
                rs3.metric("❌ 실패",  len(fail_list))
                rs4.metric("⏭️ 스킵",  len(skip_list))

                if success_list:
                    st.success("**발송 성공:**\n" + "\n".join(f"• {s}" for s in success_list))
                if fail_list:
                    st.error("**발송 실패:**\n" + "\n".join(f"• {f}" for f in fail_list))
                if skip_list:
                    st.info("**스킵 (중복):**\n" + "\n".join(f"• {s}" for s in skip_list))
                with st.expander("📄 상세 로그"):
                    for log in log_list:
                        st.caption(log)


# ═══════════════════════════════════════════════════════════════════════
# 탭3: 발송 이력
# ═══════════════════════════════════════════════════════════════════════
with tab3:
    history = load_history()
    if not history:
        st.info("발송 이력이 없습니다.")
    else:
        import pandas as pd
        df = pd.DataFrame(list(reversed(history)))
        st.dataframe(df, use_container_width=True, hide_index=True)
        if st.button("🗑️ 이력 초기화"):
            save_history([])
            st.rerun()


# ═══════════════════════════════════════════════════════════════════════
# 탭4: 설정
# ═══════════════════════════════════════════════════════════════════════
with tab4:
    st.subheader("이메일 발송 설정")
    smtp_user = get_secret("SMTP_USER", "")
    if smtp_user:
        st.success(f"✅ 발송 계정: {smtp_user}")
    else:
        st.error("❌ 이메일 설정 없음")

    st.info("Streamlit Cloud → 앱 Settings → Secrets 에 아래 내용 입력")
    st.code("""SMTP_USER = "발송계정@naver.com"
SMTP_PASSWORD = "네이버앱비밀번호12자리"
SMTP_HOST = "smtp.naver.com"
SMTP_PORT = "465"
ADMIN_PASSWORD = "관리자비밀번호"
""", language="toml")

    st.divider()
    st.subheader("테스트 이메일 발송")
    test_to = st.text_input("수신 이메일", value=smtp_user)
    if st.button("📧 테스트 발송"):
        if not smtp_user:
            st.error("SMTP 설정을 먼저 해주세요.")
        else:
            try:
                send_report(
                    to_email=test_to,
                    client_name="테스트",
                    period="weekly",
                    since="2026-01-01",
                    until="2026-01-07",
                    html_body="<html><body><h2>✅ 테스트 이메일 - 발송 시스템 정상 작동</h2></body></html>",
                    smtp_user=smtp_user,
                    smtp_password=get_secret("SMTP_PASSWORD", ""),
                    smtp_host=get_secret("SMTP_HOST", "smtp.naver.com"),
                    smtp_port=int(get_secret("SMTP_PORT", "465")),
                )
                st.success(f"✅ {test_to} 발송 성공!")
            except Exception as e:
                st.error(f"❌ 실패: {e}")
