"""
Google Sheets 기반 광고주 데이터 영구 저장
기존 앱의 gspread 설정 재활용
"""
import json
import os
import streamlit as st


def _get_sheet():
    import gspread
    from google.oauth2.service_account import Credentials

    scopes = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

    # Streamlit Secrets에서 서비스 계정 정보 로드
    try:
        creds_info = dict(st.secrets["gcp_service_account"])
        creds = Credentials.from_service_account_info(creds_info, scopes=scopes)
    except Exception:
        return None

    gc = gspread.authorize(creds)

    # GSHEET_URL에서 스프레드시트 열기
    try:
        gsheet_url = st.secrets.get("GSHEET_URL", "")
        if not gsheet_url:
            return None
        sh = gc.open_by_url(gsheet_url)
    except Exception:
        return None

    # "보고서_광고주" 시트 가져오기 (없으면 생성)
    try:
        ws = sh.worksheet("보고서_광고주")
    except Exception:
        ws = sh.add_worksheet(title="보고서_광고주", rows=100, cols=10)
        ws.append_row(["id", "name", "customer_id", "email", "api_key", "secret_key", "memo", "created_at"])

    return ws


def load_clients():
    """Google Sheets에서 광고주 목록 로드, 실패시 로컬 파일"""
    try:
        ws = _get_sheet()
        if ws is None:
            return _load_local()

        rows = ws.get_all_records()
        return [r for r in rows if r.get("name")]
    except Exception:
        return _load_local()


def save_clients(clients):
    """Google Sheets에 광고주 목록 저장, 실패시 로컬 파일"""
    try:
        ws = _get_sheet()
        if ws is None:
            _save_local(clients)
            return

        # 헤더 제외하고 전체 초기화 후 재작성
        ws.clear()
        ws.append_row(["id", "name", "customer_id", "email", "phone", "api_key", "secret_key", "memo", "created_at"])
        for c in clients:
            ws.append_row([
                c.get("id", ""),
                c.get("name", ""),
                c.get("customer_id", ""),
                c.get("email", ""),
                c.get("phone", ""),
                c.get("api_key", ""),
                c.get("secret_key", ""),
                c.get("memo", ""),
                c.get("created_at", ""),
            ])
    except Exception:
        _save_local(clients)


def _load_local():
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "clients.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def _save_local(clients):
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "clients.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(clients, f, ensure_ascii=False, indent=2)
