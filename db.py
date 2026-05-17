"""
영구 저장소 모듈 — Supabase 우선, JSON 파일 폴백

사용 방법:
  from db import sb_load, sb_save

Supabase secrets (Streamlit Cloud > Settings > Secrets):
  SUPABASE_URL = "https://xxx.supabase.co"
  SUPABASE_KEY = "eyJ..."   # service_role 또는 anon key

Supabase 테이블 (1개만 생성):
  CREATE TABLE app_data (
    key  text PRIMARY KEY,
    data jsonb NOT NULL DEFAULT '[]',
    updated_at timestamptz NOT NULL DEFAULT now()
  );
  ALTER TABLE app_data ENABLE ROW LEVEL SECURITY;
  CREATE POLICY "allow_all" ON app_data USING (true) WITH CHECK (true);
"""

import json
import os
import time

_sb_client = None
_sb_checked = False

def _get_supabase():
    """Supabase 클라이언트 반환 (캐시). 미설정 시 None."""
    global _sb_client, _sb_checked
    if _sb_checked:
        return _sb_client
    _sb_checked = True
    try:
        import streamlit as st
        url = (getattr(st, "secrets", {}) or {}).get("SUPABASE_URL", "") or os.getenv("SUPABASE_URL", "")
        key = (getattr(st, "secrets", {}) or {}).get("SUPABASE_KEY", "") or os.getenv("SUPABASE_KEY", "")
        if not url or not key:
            return None
        from supabase import create_client
        _sb_client = create_client(url, key)
    except Exception:
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
    """
    Supabase에서 데이터 로드.
    - Supabase 미설정 또는 실패 시 → JSON 파일 폴백
    - 데이터 없으면 빈 리스트 반환
    """
    sb = _get_supabase()
    if sb:
        try:
            res = sb.table("app_data").select("data").eq("key", collection).execute()
            if res.data:
                return res.data[0]["data"]
            return []
        except Exception:
            pass
    # JSON 폴백
    if fallback_path:
        return _json_load(fallback_path)
    return []

def sb_save(collection: str, data, fallback_path: str = None):
    """
    Supabase에 데이터 저장 + JSON 파일 백업.
    - Supabase 미설정 시 JSON 파일에만 저장
    """
    # JSON 백업 (항상)
    if fallback_path:
        _json_save(fallback_path, data)

    sb = _get_supabase()
    if sb:
        try:
            sb.table("app_data").upsert({
                "key":        collection,
                "data":       data,
                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
            }, on_conflict="key").execute()
        except Exception:
            pass

def is_supabase_connected() -> bool:
    """Supabase 연결 여부 확인"""
    return _get_supabase() is not None
