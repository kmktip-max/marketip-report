import streamlit as st
import json
import os
import sys
from datetime import datetime
from dotenv import load_dotenv

# 경로 설정 (로컬 + Streamlit Cloud 모두 지원)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from report_engine.naver_api import NaverAdAPI
from report_engine.emailer import send_report
from report_engine.report_html import generate_html
from report_engine.storage import load_clients, save_clients

load_dotenv()

st.set_page_config(page_title="보고서 관리", page_icon="📊", layout="wide")

def get_secret(key, default=""):
    try:
        if hasattr(st, "secrets") and key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass
    return os.getenv(key, default)

ADMIN_PW = get_secret("ADMIN_PASSWORD", "mktip")
HISTORY_FILE = os.path.join(ROOT, "report_history.json")


# ── 인증 ────────────────────────────────────────────────────────────
def check_admin():
    if st.session_state.get("report_admin_auth"):
        return True
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("## 🔐 관리자 전용 페이지")
        pw = st.text_input("비밀번호", type="password", placeholder="관리자 비밀번호 입력")
        if st.button("로그인", type="primary", use_container_width=True):
            if pw == ADMIN_PW:
                st.session_state.report_admin_auth = True
                st.rerun()
            else:
                st.error("비밀번호가 틀렸습니다.")
    return False

if not check_admin():
    st.stop()


# ── 히스토리 로드/저장 ───────────────────────────────────────────────
def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_history(history):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


# ── 메인 UI ─────────────────────────────────────────────────────────
col_title, col_logout = st.columns([5, 1])
with col_title:
    st.title("📊 광고 보고서 관리")
with col_logout:
    if st.button("로그아웃"):
        st.session_state.report_admin_auth = False
        st.rerun()

tab1, tab2, tab3, tab4 = st.tabs(["👥 광고주 관리", "🚀 보고서 발송", "📋 발송 이력", "⚙️ 이메일 설정"])


# ── 탭1: 광고주 관리 ──────────────────────────────────────────────────
with tab1:
    st.subheader("새 광고주 추가")
    with st.form("add_client_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            name = st.text_input("광고주명 *")
            customer_id = st.text_input("Customer ID *", help="searchad.naver.com 로그인 후 URL에서 확인")
            email = st.text_input("보고서 수신 이메일 *")
        with col2:
            api_key = st.text_input("API Access License *")
            secret_key = st.text_input("Secret Key *", type="password")
            memo = st.text_input("메모 (선택)")

        if st.form_submit_button("✅ 광고주 추가", type="primary"):
            if not all([name, customer_id, email, api_key, secret_key]):
                st.error("* 표시된 항목을 모두 입력해주세요.")
            else:
                clients = load_clients()
                clients.append({
                    "id": datetime.now().strftime("%Y%m%d%H%M%S"),
                    "name": name,
                    "customer_id": customer_id.strip(),
                    "email": email.strip(),
                    "api_key": api_key.strip(),
                    "secret_key": secret_key.strip(),
                    "memo": memo,
                    "created_at": datetime.now().strftime("%Y-%m-%d"),
                })
                save_clients(clients)
                st.success(f"✅ {name} 추가됐습니다!")
                st.rerun()

    st.divider()
    st.subheader("등록된 광고주")
    clients = load_clients()
    if not clients:
        st.info("등록된 광고주가 없습니다. 위에서 추가해주세요.")
    else:
        for i, c in enumerate(clients):
            with st.expander(f"**{c['name']}** | {c['email']} | ID: {c['customer_id']}"):
                col1, col2, col3 = st.columns([3, 1, 1])
                with col1:
                    st.write(f"- 등록일: {c.get('created_at', '-')}")
                    st.write(f"- 메모: {c.get('memo', '-') or '-'}")
                    st.write(f"- API Key: {c['api_key'][:20]}...")
                with col2:
                    if st.button("🔌 연결 테스트", key=f"test_{i}"):
                        with st.spinner("확인 중..."):
                            api = NaverAdAPI(c["api_key"], c["secret_key"], c["customer_id"])
                            ok, msg = api.test_connection()
                            if ok:
                                st.success(msg)
                            else:
                                st.error(f"실패: {msg}")
                with col3:
                    if st.button("🗑️ 삭제", key=f"del_{i}"):
                        clients.pop(i)
                        save_clients(clients)
                        st.rerun()


# ── 탭2: 보고서 발송 ──────────────────────────────────────────────────
with tab2:
    clients = load_clients()
    if not clients:
        st.warning("먼저 광고주를 등록해주세요.")
    else:
        col1, col2 = st.columns([2, 1])
        with col1:
            selected = st.multiselect(
                "발송할 광고주 선택",
                options=[c["name"] for c in clients],
                default=[c["name"] for c in clients],
                help="전체 선택하거나 개별 선택 가능"
            )
        with col2:
            period = st.radio("보고서 기간", ["주간 (지난 7일)", "월간 (지난달)"], horizontal=True)
            period_key = "weekly" if "주간" in period else "monthly"

        st.divider()
        if st.button("🚀 보고서 발송 시작", type="primary", use_container_width=True, disabled=not selected):
            smtp_cfg = {
                "smtp_user": get_secret("SMTP_USER", ""),
                "smtp_password": get_secret("SMTP_PASSWORD", ""),
                "smtp_host": get_secret("SMTP_HOST", "smtp.naver.com"),
                "smtp_port": int(get_secret("SMTP_PORT", "465")),
            }

            if not smtp_cfg["smtp_user"]:
                st.error("이메일 설정이 없습니다. ⚙️ 이메일 설정 탭을 확인해주세요.")
            else:
                history = load_history()
                target = [c for c in clients if c["name"] in selected]
                progress = st.progress(0, text="준비 중...")

                for idx, client in enumerate(target):
                    progress.progress((idx) / len(target), text=f"⏳ {client['name']} 처리 중...")
                    try:
                        api = NaverAdAPI(client["api_key"], client["secret_key"], client["customer_id"])
                        data = api.fetch_report(period_key)

                        # 통계 없어도 캠페인/키워드 현황 보고서 발송
                        html = generate_html(data, client["name"], datetime.now().strftime("%Y-%m-%d"))
                        if True:
                            send_report(
                                to_email=client["email"],
                                client_name=client["name"],
                                period=period_key,
                                since=data["since"],
                                until=data["until"],
                                html_body=html,
                                **smtp_cfg,
                            )
                            st.success(f"✅ **{client['name']}** → {client['email']} 발송 완료!")
                            history.append({
                                "client": client["name"],
                                "email": client["email"],
                                "period": period_key,
                                "since": data["since"],
                                "until": data["until"],
                                "sent_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                                "status": "성공",
                                "keywords": data["total_keywords"],
                            })

                    except Exception as e:
                        st.error(f"❌ **{client['name']}** 오류: {e}")
                        history.append({
                            "client": client["name"],
                            "period": period_key,
                            "sent_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                            "status": f"실패: {str(e)[:80]}",
                        })

                    progress.progress((idx + 1) / len(target), text=f"완료: {idx+1}/{len(target)}")

                save_history(history)
                st.balloons()


# ── 탭3: 발송 이력 ────────────────────────────────────────────────────
with tab3:
    history = load_history()
    if not history:
        st.info("발송 이력이 없습니다.")
    else:
        import pandas as pd
        df = pd.DataFrame(list(reversed(history)))
        st.dataframe(df, use_container_width=True, hide_index=True)

        col1, col2 = st.columns([1, 5])
        with col1:
            if st.button("🗑️ 이력 초기화"):
                save_history([])
                st.rerun()


# ── 탭4: 이메일 설정 ──────────────────────────────────────────────────
with tab4:
    st.subheader("⚙️ 이메일 발송 설정")

    current_user = get_secret("SMTP_USER", "미설정")
    if current_user != "미설정":
        st.success(f"✅ 현재 발송 계정: {current_user}")
    else:
        st.error("❌ 이메일 설정이 없습니다.")

    st.info("""
**Streamlit Cloud 배포 시 설정 방법:**
1. [share.streamlit.io](https://share.streamlit.io) → 앱 설정 → Secrets
2. 아래 내용 입력 후 저장
""")
    st.code("""
SMTP_USER = "발송계정@naver.com"
SMTP_PASSWORD = "네이버앱비밀번호12자리"
SMTP_HOST = "smtp.naver.com"
SMTP_PORT = "465"
ADMIN_PASSWORD = "관리자비밀번호"
""", language="toml")

    st.divider()
    st.subheader("📧 테스트 이메일 발송")
    test_to = st.text_input("테스트 수신 이메일", value=get_secret("SMTP_USER", ""))
    if st.button("테스트 발송"):
        smtp_user = get_secret("SMTP_USER", "")
        if not smtp_user:
            st.error(".env 파일 또는 Secrets에 SMTP_USER를 설정해주세요.")
        else:
            try:
                send_report(
                    to_email=test_to,
                    client_name="테스트",
                    period="weekly",
                    since="2026-01-01",
                    until="2026-01-07",
                    html_body="<h2>✅ 테스트 이메일입니다. 발송 시스템이 정상 작동 중입니다.</h2>",
                    smtp_user=smtp_user,
                    smtp_password=get_secret("SMTP_PASSWORD", ""),
                    smtp_host=get_secret("SMTP_HOST", "smtp.naver.com"),
                    smtp_port=int(get_secret("SMTP_PORT", "465")),
                )
                st.success(f"✅ {test_to} 로 테스트 이메일 발송 성공!")
            except Exception as e:
                st.error(f"❌ 실패: {e}")
