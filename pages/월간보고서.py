import streamlit as st
import streamlit.components.v1 as components
import json
import os
import sys
from datetime import datetime

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
c1, c2 = st.columns([5, 1])
with c1:
    st.title("📊 광고 보고서 관리")
with c2:
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
        c1, c2 = st.columns(2)
        with c1:
            name       = st.text_input("광고주명 *")
            cust_id    = st.text_input("Customer ID *", help="searchad.naver.com → URL 숫자")
            email      = st.text_input("수신 이메일 *")
        with c2:
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
        for i, c in enumerate(clients):
            with st.expander(f"**{c['name']}** | {c['email']} | ID: {c['customer_id']}"):
                c1, c2, c3 = st.columns([4, 1, 1])
                with c1:
                    st.caption(f"등록일: {c.get('created_at','-')} | 메모: {c.get('memo','-') or '-'}")
                    st.caption(f"API Key: {c['api_key'][:20]}...")
                with c2:
                    if st.button("🔌 연결 테스트", key=f"test_{i}"):
                        with st.spinner("확인 중..."):
                            try:
                                api = NaverAdAPI(c["api_key"], c["secret_key"], c["customer_id"])
                                ok, msg = api.test_connection()
                                st.success(msg) if ok else st.error(msg)
                            except Exception as e:
                                st.error(str(e))
                with c3:
                    if st.button("🗑️ 삭제", key=f"del_{i}"):
                        clients.pop(i)
                        save_clients(clients)
                        st.rerun()


# ═══════════════════════════════════════════════════════════════════════
# 탭2: 보고서 발송 (미리보기 → 승인 → 발송)
# ═══════════════════════════════════════════════════════════════════════
with tab2:
    clients = load_clients()
    if not clients:
        st.warning("먼저 광고주를 등록해주세요.")
        st.stop()

    # ── 1단계: 설정 ──
    st.subheader("① 발송 설정")
    c1, c2 = st.columns([2, 1])
    with c1:
        selected_names = st.multiselect(
            "광고주 선택",
            options=[c["name"] for c in clients],
            default=[]
        )
    with c2:
        period_label = st.radio("기간", ["주간 (지난 7일)", "월간 (지난달)"], horizontal=True)
        period_key = "weekly" if "주간" in period_label else "monthly"

    if not selected_names:
        st.info("광고주를 선택하세요.")
    else:
        selected_clients = [c for c in clients if c["name"] in selected_names]

        # ── 2단계: 미리보기 생성 ──
        st.subheader("② 보고서 미리보기")
        if st.button("🔍 보고서 데이터 수집 및 미리보기 생성", type="secondary", use_container_width=True):
            results = []
            with st.spinner("데이터 수집 중..."):
                for client in selected_clients:
                    try:
                        api = NaverAdAPI(client["api_key"], client["secret_key"], client["customer_id"])
                        data = api.fetch_report(period_key)
                        kws = data["keywords"]

                        import pandas as pd
                        sm   = data.get("summary",    {})
                        kwsm = data.get("kw_summary", {})
                        dbg  = data.get("debug_params", {})

                        with st.expander(f"🔎 {client['name']} 데이터 검증", expanded=True):
                            # ① API 요청 정보
                            st.markdown("**① API 요청 정보**")
                            c1, c2, c3 = st.columns(3)
                            c1.text(f"Customer ID : {dbg.get('customer_id','')}")
                            c2.text(f"조회 시작일  : {dbg.get('since','')}")
                            c3.text(f"조회 종료일  : {dbg.get('until','')}")
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

                            # ② 캠페인 레벨 (KPI 카드 기준 — 네이버 대시보드와 비교)
                            st.markdown("**② 캠페인 레벨 집계 (KPI 카드 기준 / 네이버 대시보드와 비교)**")
                            c1, c2, c3, c4, c5 = st.columns(5)
                            c1.metric("클릭수",   f"{sm.get('clicks',0):,}")
                            c2.metric("노출수",   f"{sm.get('impressions',0):,}")
                            c3.metric("전환수",   f"{sm.get('conversions',0):,}")
                            c4.metric("전환매출", f"{sm.get('revenue',0):,}")
                            c5.metric("추정비용", f"{sm.get('cost',0):,}")

                            # ③ 키워드 레벨 (차이 delta 표시)
                            st.markdown("**③ 키워드 레벨 합산 (테이블 기준 / 차이 = 미귀속 트래픽)**")
                            c1, c2, c3, c4, c5 = st.columns(5)
                            c1.metric("클릭수",   f"{kwsm.get('clicks',0):,}",
                                      delta=f"{kwsm.get('clicks',0)-sm.get('clicks',0):+,}")
                            c2.metric("노출수",   f"{kwsm.get('impressions',0):,}",
                                      delta=f"{kwsm.get('impressions',0)-sm.get('impressions',0):+,}")
                            c3.metric("전환수",   f"{kwsm.get('conversions',0):,}")
                            c4.metric("전환매출", f"{kwsm.get('revenue',0):,}")
                            c5.metric("추정비용", f"{kwsm.get('cost',0):,}")

                            st.divider()

                            # ④ 캠페인별 성과 테이블 (네이버 관리자 화면 1:1 비교)
                            camp_table = data.get("camp_table", [])
                            if camp_table:
                                st.markdown("**④ 캠페인별 성과 (네이버 관리자 화면 1:1 비교)**")
                                df_camp = pd.DataFrame(camp_table)
                                st.dataframe(df_camp, use_container_width=True, hide_index=True)

                            # ⑤ 키워드 원본 상위 10행
                            if kws:
                                st.markdown("**⑤ 키워드 성과 상위 10행**")
                                cols = ["keyword","clicks","impressions","conversions",
                                        "revenue","cost","ctr","cpc","roas","avg_rnk"]
                                st.dataframe(
                                    pd.DataFrame(kws[:10])[[c for c in cols if c in kws[0]]],
                                    use_container_width=True, hide_index=True
                                )

                            # ⑥ 디버그 로그
                            with st.expander("디버그 로그"):
                                for line in data.get("debug", []):
                                    st.caption(line)

                        html = generate_html(data, client["name"], datetime.now().strftime("%Y-%m-%d"))
                        results.append({
                            "client": client,
                            "data": data,
                            "html": html,
                            "status": "ok"
                        })
                        st.success(
                            f"✅ {client['name']} 완료 — "
                            f"캠페인 {data['total_campaigns']}개 | 키워드 {data['total_keywords']}개 | "
                            f"클릭 {sm.get('clicks',0):,}회 (캠페인 레벨) | "
                            f"노출 {sm.get('impressions',0):,}회"
                        )
                    except Exception as e:
                        results.append({
                            "client": client,
                            "error": str(e),
                            "status": "error"
                        })
                        st.error(f"❌ {client['name']} 오류: {e}")

            st.session_state.preview_results = results
            st.session_state.preview_period = period_key

        # ── 미리보기 표시 ──
        if "preview_results" in st.session_state:
            results = st.session_state.preview_results
            ok_results = [r for r in results if r["status"] == "ok"]

            if ok_results:
                st.divider()
                preview_idx = st.selectbox(
                    "미리볼 광고주 선택",
                    options=range(len(ok_results)),
                    format_func=lambda i: ok_results[i]["client"]["name"]
                )
                r = ok_results[preview_idx]
                d = r["data"]

                with st.expander(f"📊 {r['client']['name']} 보고서 미리보기", expanded=True):
                    st.caption(f"기간: {d['since']} ~ {d['until']} | 키워드: {d['total_keywords']}개 | "
                               f"클릭: {sum(k['clicks'] for k in d['keywords']):,}회 | "
                               f"노출: {sum(k['impressions'] for k in d['keywords']):,}회")
                    components.html(r["html"], height=1200, scrolling=True)

                # ── 3단계: 승인 및 발송 ──
                st.divider()
                st.subheader("③ 이메일 발송")

                smtp_user = get_secret("SMTP_USER", "")
                if not smtp_user:
                    st.error("⚙️ 이메일 설정 탭에서 SMTP 설정을 먼저 해주세요.")
                else:
                    for r in ok_results:
                        period_k = st.session_state.get("preview_period", "monthly")
                        period_str = "주간" if period_k == "weekly" else "월간"
                        st.info(
                            f"**{r['client']['name']}** → `{r['client']['email']}`  \n"
                            f"제목: [광고 성과 보고서] {r['client']['name']} | {period_str} "
                            f"({r['data']['since']} ~ {r['data']['until']})"
                        )

                    st.warning("⚠️ 위 내용을 확인하셨나요? 아래 버튼을 누르면 실제 이메일이 발송됩니다.")

                    if st.button("✉️ 이메일 발송 확인 및 실행", type="primary", use_container_width=True):
                        smtp_cfg = {
                            "smtp_user": smtp_user,
                            "smtp_password": get_secret("SMTP_PASSWORD", ""),
                            "smtp_host": get_secret("SMTP_HOST", "smtp.naver.com"),
                            "smtp_port": int(get_secret("SMTP_PORT", "465")),
                        }
                        history = load_history()
                        period_k = st.session_state.get("preview_period", "monthly")

                        for r in ok_results:
                            client = r["client"]
                            try:
                                send_report(
                                    to_email=client["email"],
                                    client_name=client["name"],
                                    period=period_k,
                                    since=r["data"]["since"],
                                    until=r["data"]["until"],
                                    html_body=r["html"],
                                    **smtp_cfg,
                                )
                                st.success(f"✅ **{client['name']}** → {client['email']} 발송 완료!")
                                history.append({
                                    "client": client["name"],
                                    "email": client["email"],
                                    "period": period_k,
                                    "since": r["data"]["since"],
                                    "until": r["data"]["until"],
                                    "keywords": r["data"]["total_keywords"],
                                    "sent_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                                    "status": "성공",
                                })
                            except Exception as e:
                                st.error(f"❌ **{client['name']}** 발송 실패: {e}")
                                history.append({
                                    "client": client["name"],
                                    "sent_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                                    "status": f"실패: {str(e)[:100]}",
                                })

                        save_history(history)
                        st.session_state.pop("preview_results", None)


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
