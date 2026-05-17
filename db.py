"""
영구 저장소 모듈 — Supabase 우선, JSON 파일 폴백
"""

import json
import os
import time

_sb_client = None
_sb_checked = False
_sb_error = ""   # 마지막 오류 메시지

def _get_supabase():
    global _sb_client, _sb_checked, _sb_error
    if _sb_checked:
        return _sb_client
    _sb_checked = True
    try:
        import streamlit as st
        url = st.secrets.get("SUPABASE_URL", "") or os.getenv("SUPABASE_URL", "")
        key = st.secrets.get("SUPABASE_KEY", "") or os.getenv("SUPABASE_KEY", "")
        if not url or not key:
            _sb_error = "SUPABASE_URL 또는 SUPABASE_KEY 누락"
            return None
        from supabase import create_client
        _sb_client = create_client(url, key)
        # 실제 연결 테스트
        _sb_client.table("app_data").select("key").limit(1).execute()
        _sb_error = ""
    except Exception as e:
        _sb_error = str(e)
        _sb_client = None
    return _sb_client

def _json_load(path):
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return []

def _json_save(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def sb_load(collection: str, fallback_path: str = None):
    sb = _get_supabase()
    if sb:
        try:
            res = sb.table("app_data").select("data").eq("key", collection).execute()
            if res.data:
                return res.data[0]["data"]
            return []
        except Exception as e:
            global _sb_error
            _sb_error = str(e)
    if fallback_path:
        return _json_load(fallback_path)
    return []

def sb_save(collection: str, data, fallback_path: str = None):
    global _sb_error
    if fallback_path:
        _json_save(fallback_path, data)

    sb = _get_supabase()
    if sb:
        try:
            sb.table("app_data").upsert({
                "key":        collection,
                "data":       data,
                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }, on_conflict="key").execute()
            _sb_error = ""
            return True
        except Exception as e:
            _sb_error = str(e)
    return False

def is_supabase_connected() -> bool:
    return _get_supabase() is not None

def get_supabase_error() -> str:
    _get_supabase()  # 한 번은 시도
    return _sb_error
