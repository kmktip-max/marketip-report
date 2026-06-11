"""
광고주 데이터 영구 저장소

저장 우선순위: Supabase(app_data['report_clients']) → Google Sheets → 로컬 clients.json

Supabase 를 단일 소스로 사용하므로 로컬 8501 / Streamlit Cloud / 비즈머니 알림이
모두 동일한 광고주 목록을 공유합니다. (Supabase 가 비어있으면 Google Sheets/로컬에서
최초 1회 자동 마이그레이션하여 Supabase 에 채워 넣습니다.)
"""
import json
import os
from datetime import datetime

import streamlit as st

_SB_CLIENTS_KEY  = "report_clients"
_SB_MIGRATED_KEY = "report_clients_migrated"   # Sheets→Supabase 1회 이관 완료 표식


# ── 공통 유틸 ─────────────────────────────────────────────────────────────────
def _str(v):
    """어떤 값이든 문자열로 변환. falsy 비문자열(0, None)은 빈 문자열."""
    if isinstance(v, str):
        return v
    return "" if not v else str(v)


def _norm(rows):
    """name 이 있는 행만, 모든 필드를 문자열로 정규화."""
    out = []
    for r in rows or []:
        if isinstance(r, dict) and r.get("name"):
            out.append({k: _str(v) for k, v in r.items()})
    return out


def _local_path():
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "clients.json"
    )


# ── Supabase ──────────────────────────────────────────────────────────────────
def _sb():
    try:
        url = (getattr(st, "secrets", {}).get("SUPABASE_URL", "")
               or os.getenv("SUPABASE_URL", ""))
        key = (getattr(st, "secrets", {}).get("SUPABASE_KEY", "")
               or os.getenv("SUPABASE_KEY", ""))
        if not url or not key:
            return None
        from supabase import create_client
        return create_client(url, key)
    except Exception:
        return None


def _sb_load_clients(sb):
    try:
        res = sb.table("app_data").select("data").eq("key", _SB_CLIENTS_KEY).execute()
        if res.data:
            d = res.data[0]["data"]
            if isinstance(d, list):
                return d
    except Exception:
        pass
    return None


def _sb_save_clients(sb, clients):
    try:
        sb.table("app_data").upsert(
            {"key": _SB_CLIENTS_KEY, "data": clients,
             "updated_at": datetime.utcnow().isoformat() + "Z"},
            on_conflict="key",
        ).execute()
        return True
    except Exception:
        return False


def _sb_migrated(sb):
    """Sheets→Supabase 1회 이관이 완료되었는지 여부."""
    try:
        res = sb.table("app_data").select("data").eq("key", _SB_MIGRATED_KEY).execute()
        if res.data:
            d = res.data[0]["data"]
            return bool(d.get("done")) if isinstance(d, dict) else bool(d)
    except Exception:
        pass
    return False


def _sb_set_migrated(sb):
    try:
        sb.table("app_data").upsert(
            {"key": _SB_MIGRATED_KEY, "data": {"done": True},
             "updated_at": datetime.utcnow().isoformat() + "Z"},
            on_conflict="key",
        ).execute()
    except Exception:
        pass


# ── Google Sheets (마이그레이션 소스 / 백업) ──────────────────────────────────
def _get_sheet():
    import gspread
    from google.oauth2.service_account import Credentials

    scopes = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

    try:
        creds_info = dict(st.secrets["gcp_service_account"])
        creds = Credentials.from_service_account_info(creds_info, scopes=scopes)
    except Exception:
        return None

    gc = gspread.authorize(creds)

    try:
        gsheet_url = st.secrets.get("GSHEET_URL", "")
        if not gsheet_url:
            return None
        sh = gc.open_by_url(gsheet_url)
    except Exception:
        return None

    try:
        ws = sh.worksheet("보고서_광고주")
    except Exception:
        ws = sh.add_worksheet(title="보고서_광고주", rows=100, cols=10)
        ws.append_row(["id", "name", "customer_id", "email", "phone",
                       "api_key", "secret_key", "memo", "created_at"])

    return ws


def _load_sheets():
    try:
        ws = _get_sheet()
        if ws is None:
            return []
        return _norm(ws.get_all_records())
    except Exception:
        return []


def _save_sheets(clients):
    try:
        ws = _get_sheet()
        if ws is None:
            return
        ws.clear()
        ws.append_row(["id", "name", "customer_id", "email", "phone",
                       "api_key", "secret_key", "memo", "created_at"])
        for c in clients:
            ws.append_row([
                c.get("id", ""), c.get("name", ""), c.get("customer_id", ""),
                c.get("email", ""), c.get("phone", ""), c.get("api_key", ""),
                c.get("secret_key", ""), c.get("memo", ""), c.get("created_at", ""),
            ])
    except Exception:
        pass


# ── 로컬 파일 ─────────────────────────────────────────────────────────────────
def _load_local():
    path = _local_path()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return _norm(json.load(f))
        except Exception:
            pass
    return []


def _save_local(clients):
    try:
        with open(_local_path(), "w", encoding="utf-8") as f:
            json.dump(clients, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ── 공개 API ──────────────────────────────────────────────────────────────────
def load_clients():
    """
    광고주 목록 로드 — Supabase 단일 소스.

    동작:
      · 클라우드(Google Sheets 접근 가능): 최초 1회 Sheets(완전한 광고주 목록)로
        Supabase 를 덮어쓰고 이관 표식을 남김. 이후엔 Sheets 를 읽지 않음.
      · 이관 후: 로컬·클라우드 모두 Supabase 를 읽으므로 항상 동일한 목록.
    """
    sb = _sb()

    if sb:
        # 최초 1회: Sheets 가 있으면(=클라우드) Sheets → Supabase 이관
        if not _sb_migrated(sb):
            sheets = _load_sheets()
            if sheets:
                _sb_save_clients(sb, sheets)
                _sb_set_migrated(sb)

        data = _sb_load_clients(sb)
        if data:
            _save_local(data)          # 오프라인 백업
            return _norm(data)

    # Supabase 미연결 환경 폴백: Sheets → 로컬 파일
    sheets = _load_sheets()
    if sheets:
        _save_local(sheets)
        return sheets
    return _load_local()


def save_clients(clients):
    """광고주 목록 저장. Supabase + Sheets + 로컬 동시 반영."""
    sb = _sb()
    if sb:
        _sb_save_clients(sb, clients)
    _save_sheets(clients)
    _save_local(clients)
