"""부정클릭 데이터 레이어 — Supabase 우선 (로컬 SQLite 폴백)"""
import hashlib
import json
import os
import random
import sqlite3
import string
from datetime import datetime, timedelta
from pathlib import Path

# .env 로드 (uvicorn/scheduler 등 비-Streamlit 컨텍스트에서도 동작)
try:
    from dotenv import load_dotenv
    _root = Path(__file__).parent.parent
    load_dotenv(_root / ".env")
except Exception:
    pass

DB_PATH = Path(__file__).parent.parent / "data" / "click_fraud.db"

_DEFAULT_SETTINGS = {
    "max_clicks_24h":       5,
    "max_clicks_1h":        3,
    "max_keyword_repeats":  3,
    "min_stay_seconds":     10,
    "auto_suspect_score":   50,
    "auto_block_enabled":   False,
    "safe_ips":             [],
    "avg_cpc":              500,
    "auto_block_naver":     False,
    "auto_block_days":      7,
    "auto_block_clicks":    5,
    "lte_auto_block":       False,
    "naver_api_key":        "",
    "naver_api_secret":     "",
    "naver_customer_id":    "",
    "alert_enabled":        False,
    "alert_clicks":         5,
    "alert_phone":          "",
    "track_server_url":     "",  # 추적 서버 URL (빈값 = 미설정)
}


# ══════════════════════════════════════════════════════════════════════════════
# Supabase 헬퍼
# ══════════════════════════════════════════════════════════════════════════════

def _get_sb():
    try:
        import streamlit as st
        secrets = getattr(st, "secrets", {}) or {}
        url = secrets.get("SUPABASE_URL", "") or os.getenv("SUPABASE_URL", "")
        key = secrets.get("SUPABASE_KEY", "") or os.getenv("SUPABASE_KEY", "")
    except Exception:
        url = os.getenv("SUPABASE_URL", "")
        key = os.getenv("SUPABASE_KEY", "")
    if not url or not key:
        return None
    try:
        from supabase import create_client
        return create_client(url, key)
    except Exception:
        return None


def _use_sb() -> bool:
    return _get_sb() is not None


def _sb_url() -> str:
    try:
        import streamlit as st
        return (getattr(st, "secrets", {}) or {}).get("SUPABASE_URL", "") or os.getenv("SUPABASE_URL", "")
    except Exception:
        return os.getenv("SUPABASE_URL", "")


def _click_key(client_id: str, ts_ms: int | None = None) -> str:
    """클릭 로그 Supabase 키: fc_{cid}_{ts_ms:016d}_{random6}"""
    import time
    if ts_ms is None:
        ts_ms = int(time.time() * 1000)
    rnd = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
    return f"fc_{client_id}_{ts_ms:016d}_{rnd}"


def _date_to_ms(date_str: str, end_of_day: bool = False) -> int:
    """'YYYY-MM-DD' → unix milliseconds"""
    try:
        dt = datetime.strptime(date_str[:10], "%Y-%m-%d")
        if end_of_day:
            dt = dt.replace(hour=23, minute=59, second=59)
        return int(dt.timestamp() * 1000)
    except Exception:
        return 0


# ══════════════════════════════════════════════════════════════════════════════
# SQLite 초기화 (로컬 폴백)
# ══════════════════════════════════════════════════════════════════════════════

def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _migrate(conn):
    for table, col, definition in [
        ("click_logs", "carrier",    "TEXT DEFAULT ''"),
        ("click_logs", "phone_model","TEXT DEFAULT ''"),
        ("click_logs", "phone_type", "TEXT DEFAULT ''"),
        ("click_logs", "ad_type",    "TEXT DEFAULT 'naver'"),
        ("click_logs", "ad_rank",    "INTEGER DEFAULT 0"),
        ("client_fraud_settings", "auto_block_naver",  "INTEGER DEFAULT 0"),
        ("client_fraud_settings", "auto_block_days",   "INTEGER DEFAULT 7"),
        ("client_fraud_settings", "auto_block_clicks", "INTEGER DEFAULT 5"),
        ("client_fraud_settings", "alert_clicks",      "INTEGER DEFAULT 5"),
        ("client_fraud_settings", "alert_phone",       "TEXT DEFAULT ''"),
        ("client_fraud_settings", "alert_enabled",     "INTEGER DEFAULT 0"),
        ("client_fraud_settings", "lte_auto_block",    "INTEGER DEFAULT 0"),
        ("client_fraud_settings", "naver_api_key",     "TEXT DEFAULT ''"),
        ("client_fraud_settings", "naver_api_secret",  "TEXT DEFAULT ''"),
        ("client_fraud_settings", "naver_customer_id", "TEXT DEFAULT ''"),
        ("client_fraud_settings", "track_server_url",  "TEXT DEFAULT ''"),
    ]:
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {definition}")
            conn.commit()
        except Exception:
            pass


def init_db():
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = get_conn()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS click_logs (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id     TEXT    NOT NULL,
        ip_address    TEXT    DEFAULT '',
        ip_hash       TEXT    DEFAULT '',
        user_agent    TEXT    DEFAULT '',
        landing_url   TEXT    DEFAULT '',
        referrer      TEXT    DEFAULT '',
        keyword       TEXT    DEFAULT '',
        campaign      TEXT    DEFAULT '',
        source        TEXT    DEFAULT '',
        medium        TEXT    DEFAULT '',
        device        TEXT    DEFAULT '',
        browser       TEXT    DEFAULT '',
        os            TEXT    DEFAULT '',
        session_id    TEXT    DEFAULT '',
        is_conversion INTEGER DEFAULT 0,
        stay_seconds  INTEGER DEFAULT 0,
        created_at    TEXT    DEFAULT (strftime('%Y-%m-%d %H:%M:%S','now','localtime'))
    );
    CREATE INDEX IF NOT EXISTS idx_cl_client_ip ON click_logs(client_id, ip_address);
    CREATE INDEX IF NOT EXISTS idx_cl_created   ON click_logs(created_at);

    CREATE TABLE IF NOT EXISTS suspicious_ips (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id     TEXT    NOT NULL,
        ip_address    TEXT    NOT NULL,
        reason        TEXT    DEFAULT '',
        click_count   INTEGER DEFAULT 0,
        keyword_count INTEGER DEFAULT 0,
        first_seen    TEXT    DEFAULT '',
        last_seen     TEXT    DEFAULT '',
        risk_score    INTEGER DEFAULT 0,
        status        TEXT    DEFAULT 'suspect',
        blocked_at    TEXT    DEFAULT '',
        memo          TEXT    DEFAULT '',
        updated_at    TEXT    DEFAULT (strftime('%Y-%m-%d %H:%M:%S','now','localtime')),
        UNIQUE(client_id, ip_address)
    );

    CREATE TABLE IF NOT EXISTS blocked_ips (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id  TEXT    NOT NULL,
        ip_address TEXT    NOT NULL,
        reason     TEXT    DEFAULT '',
        blocked_by TEXT    DEFAULT '',
        created_at TEXT    DEFAULT (strftime('%Y-%m-%d %H:%M:%S','now','localtime')),
        active     INTEGER DEFAULT 1,
        UNIQUE(client_id, ip_address)
    );

    CREATE TABLE IF NOT EXISTS client_fraud_settings (
        client_id             TEXT PRIMARY KEY,
        max_clicks_24h        INTEGER DEFAULT 5,
        max_clicks_1h         INTEGER DEFAULT 3,
        max_keyword_repeats   INTEGER DEFAULT 3,
        min_stay_seconds      INTEGER DEFAULT 10,
        auto_suspect_score    INTEGER DEFAULT 50,
        auto_block_enabled    INTEGER DEFAULT 0,
        safe_ips              TEXT    DEFAULT '[]',
        avg_cpc               INTEGER DEFAULT 500,
        updated_at            TEXT    DEFAULT (strftime('%Y-%m-%d %H:%M:%S','now','localtime'))
    );

    CREATE TABLE IF NOT EXISTS naver_excluded_ips (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id       TEXT    NOT NULL,
        ip_address      TEXT    NOT NULL,
        memo            TEXT    DEFAULT '',
        registered_at   TEXT    DEFAULT (strftime('%Y-%m-%d %H:%M:%S','now','localtime')),
        ad_clicks_valid INTEGER DEFAULT 0,
        ad_clicks_total INTEGER DEFAULT 0,
        daily_visits    INTEGER DEFAULT 0,
        conversions     INTEGER DEFAULT 0,
        status          TEXT    DEFAULT 'active',
        naver_synced    INTEGER DEFAULT 0,
        UNIQUE(client_id, ip_address)
    );
    CREATE INDEX IF NOT EXISTS idx_nei_client ON naver_excluded_ips(client_id);
    """)
    conn.commit()
    _migrate(conn)
    conn.close()


# ══════════════════════════════════════════════════════════════════════════════
# 클릭 로그
# ══════════════════════════════════════════════════════════════════════════════

def hash_ip(ip: str) -> str:
    return hashlib.sha256(ip.encode()).hexdigest()[:16]


def log_click(data: dict) -> bool:
    """클릭 로그 저장. Supabase 우선, 로컬 SQLite 폴백."""
    import time
    if _use_sb():
        _log_click_sb(data)
        return True

    # SQLite 폴백
    conn = get_conn()
    fields = [
        "client_id", "ip_address", "ip_hash", "user_agent", "landing_url",
        "referrer", "keyword", "campaign", "source", "medium",
        "device", "browser", "os", "session_id", "is_conversion",
        "stay_seconds", "carrier", "phone_model", "phone_type", "ad_type", "ad_rank",
        "created_at",
    ]
    row = {f: data.get(f, "") for f in fields}
    ip = data.get("ip_address", "")
    row["ip_hash"] = hash_ip(ip) if ip else ""
    row["is_conversion"] = int(row.get("is_conversion") or 0)
    row["stay_seconds"]  = int(row.get("stay_seconds") or 0)
    row["ad_rank"]       = int(row.get("ad_rank") or 0)
    if not row["created_at"]:
        row["created_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cols = ", ".join(fields)
    ph   = ", ".join("?" for _ in fields)
    cur  = conn.execute(f"INSERT INTO click_logs ({cols}) VALUES ({ph})", [row[f] for f in fields])
    conn.commit()
    last_id = cur.lastrowid
    conn.close()
    return last_id


def _log_click_sb(data: dict):
    sb = _get_sb()
    if not sb:
        return
    import time
    ip = data.get("ip_address", "")
    click_data = {
        "client_id":    data.get("client_id", ""),
        "ip_address":   ip,
        "ip_hash":      hash_ip(ip) if ip else "",
        "user_agent":   (data.get("user_agent") or "")[:300],
        "landing_url":  (data.get("landing_url") or "")[:300],
        "referrer":     (data.get("referrer") or "")[:200],
        "keyword":      (data.get("keyword") or "")[:100],
        "campaign":     (data.get("campaign") or "")[:100],
        "source":       (data.get("source") or "")[:50],
        "medium":       (data.get("medium") or "")[:50],
        "device":       data.get("device") or data.get("device_type") or "",
        "browser":      data.get("browser") or "",
        "os":           data.get("os") or "",
        "session_id":   (data.get("session_id") or "")[:80],
        "is_conversion": int(data.get("is_conversion") or data.get("converted") or 0),
        "stay_seconds": int(data.get("stay_seconds") or data.get("stay_sec") or 0),
        "carrier":      data.get("carrier") or "",
        "phone_model":  data.get("phone_model") or "",
        "phone_type":   data.get("phone_type") or "",
        "ad_type":      data.get("ad_type") or "naver",
        "ad_rank":      int(data.get("ad_rank") or 0),
        "created_at":   data.get("created_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    key = _click_key(click_data["client_id"])
    try:
        sb.table("app_data").insert({
            "key": key,
            "data": click_data,
            "updated_at": datetime.utcnow().isoformat() + "Z",
        }).execute()
    except Exception as e:
        print(f"[fraud/sb] log_click 실패: {e}")


def _fetch_clicks_sb(client_id: str, start_date: str, end_date: str, limit: int = 5000) -> list[dict]:
    """Supabase app_data에서 클릭 로그 조회 (LIKE + Python 날짜 필터)."""
    sb = _get_sb()
    if not sb:
        return []
    prefix = f"fc_{client_id}_"
    start_s = start_date + " 00:00:00"
    end_s   = end_date   + " 23:59:59"
    try:
        res = (
            sb.table("app_data")
            .select("data")
            .like("key", prefix + "%")
            .limit(limit)
            .execute()
        )
        rows = [r["data"] for r in (res.data or []) if isinstance(r.get("data"), dict)]
        return [r for r in rows if start_s <= (r.get("created_at") or "") <= end_s]
    except Exception as e:
        print(f"[fraud/sb] fetch_clicks 실패: {e}")
        return []


def get_recent_clicks_sb(client_id: str, limit: int = 50) -> list[dict]:
    """실시간 로그용 — 최근 N개 클릭 (날짜 무관)."""
    sb = _get_sb()
    if not sb:
        return []
    prefix = f"fc_{client_id}_"
    try:
        res = (
            sb.table("app_data")
            .select("key,data")
            .like("key", prefix + "%")
            .order("key", desc=True)
            .limit(limit)
            .execute()
        )
        return [r["data"] for r in (res.data or []) if isinstance(r.get("data"), dict)]
    except Exception as e:
        print(f"[fraud/sb] get_recent_clicks 실패: {e}")
        return []


def get_ip_summary(client_id: str, start_date: str, end_date: str) -> list[dict]:
    if _use_sb():
        return _get_ip_summary_sb(client_id, start_date, end_date)
    conn = get_conn()
    rows = [dict(r) for r in conn.execute("""
        SELECT
            ip_address,
            MAX(carrier)            AS carrier,
            COUNT(*)                AS total_clicks,
            SUM(is_conversion)      AS conversions,
            SUM(stay_seconds)       AS total_stay,
            MAX(ad_type)            AS ad_type,
            MAX(keyword)            AS last_keyword,
            MAX(created_at)         AS last_click,
            MIN(created_at)         AS first_click,
            COUNT(DISTINCT keyword) AS keyword_count
        FROM click_logs
        WHERE client_id = ?
          AND created_at BETWEEN ? AND ?
          AND ip_address != ''
        GROUP BY ip_address
        ORDER BY total_clicks DESC
    """, (client_id, start_date, end_date + " 23:59:59")).fetchall()]
    conn.close()
    return rows


def _get_ip_summary_sb(client_id: str, start_date: str, end_date: str) -> list[dict]:
    clicks = _fetch_clicks_sb(client_id, start_date, end_date)
    ip_map: dict = {}
    for d in clicks:
        ip = d.get("ip_address", "")
        if not ip:
            continue
        if ip not in ip_map:
            ip_map[ip] = {
                "ip_address": ip, "carrier": d.get("carrier", ""),
                "total_clicks": 0, "conversions": 0, "total_stay": 0,
                "ad_type": d.get("ad_type", "naver"),
                "last_keyword": d.get("keyword", ""),
                "last_click": d.get("created_at", ""),
                "first_click": d.get("created_at", ""),
                "keyword_count": set(),
                "device": d.get("device", ""),
            }
        m = ip_map[ip]
        m["total_clicks"] += 1
        m["total_stay"] += int(d.get("stay_seconds") or 0)
        if d.get("is_conversion"):
            m["conversions"] += 1
        if d.get("keyword"):
            m["keyword_count"].add(d["keyword"])
            m["last_keyword"] = d["keyword"]
        if not m["carrier"] and d.get("carrier"):
            m["carrier"] = d["carrier"]
        c = d.get("created_at", "")
        if c > m["last_click"]:
            m["last_click"] = c
        if c < m["first_click"] or not m["first_click"]:
            m["first_click"] = c
    result = []
    for m in ip_map.values():
        m["keyword_count"] = len(m["keyword_count"])
        result.append(m)
    return sorted(result, key=lambda x: x["total_clicks"], reverse=True)


def get_mobile_sessions(client_id: str, start_date: str, end_date: str) -> list[dict]:
    if _use_sb():
        return _get_mobile_sessions_sb(client_id, start_date, end_date)
    conn = get_conn()
    rows = [dict(r) for r in conn.execute("""
        SELECT
            CASE WHEN session_id != '' THEN session_id ELSE ip_address END AS session_key,
            ip_address,
            MAX(carrier)       AS carrier,
            MAX(phone_type)    AS phone_type,
            MAX(phone_model)   AS phone_model,
            MAX(os)            AS os,
            COUNT(*)           AS total_clicks,
            MAX(ad_type)       AS ad_type,
            MAX(keyword)       AS last_keyword,
            MAX(created_at)    AS last_click,
            SUM(is_conversion) AS conversions
        FROM click_logs
        WHERE client_id = ?
          AND device IN ('mobile', 'tablet')
          AND created_at BETWEEN ? AND ?
          AND ip_address != ''
        GROUP BY session_key
        ORDER BY total_clicks DESC
    """, (client_id, start_date, end_date + " 23:59:59")).fetchall()]
    conn.close()
    return rows


def _get_mobile_sessions_sb(client_id: str, start_date: str, end_date: str) -> list[dict]:
    clicks = _fetch_clicks_sb(client_id, start_date, end_date)
    sess: dict = {}
    for d in clicks:
        if d.get("device") not in ("mobile", "tablet"):
            continue
        ip  = d.get("ip_address", "")
        sid = d.get("session_id", "")
        sk  = sid if sid else ip
        if sk not in sess:
            sess[sk] = {
                "session_key": sk, "ip_address": ip,
                "carrier": d.get("carrier", ""), "phone_type": d.get("phone_type", ""),
                "phone_model": d.get("phone_model", ""), "os": d.get("os", ""),
                "total_clicks": 0, "ad_type": d.get("ad_type", "naver"),
                "last_keyword": d.get("keyword", ""), "last_click": d.get("created_at", ""),
                "conversions": 0,
            }
        m = sess[sk]
        m["total_clicks"] += 1
        if d.get("is_conversion"):
            m["conversions"] += 1
        c = d.get("created_at", "")
        if c > m["last_click"]:
            m["last_click"] = c
            m["last_keyword"] = d.get("keyword", m["last_keyword"])
    return sorted(sess.values(), key=lambda x: x["total_clicks"], reverse=True)


def get_clicks_for_ip(client_id: str, ip: str, start_date: str, end_date: str, limit: int = 200) -> list[dict]:
    if _use_sb():
        clicks = _fetch_clicks_sb(client_id, start_date, end_date, limit=limit * 10)
        return [d for d in clicks if d.get("ip_address") == ip][:limit]
    conn = get_conn()
    rows = [dict(r) for r in conn.execute(
        """SELECT * FROM click_logs
           WHERE client_id = ? AND ip_address = ?
             AND created_at BETWEEN ? AND ?
           ORDER BY created_at DESC LIMIT ?""",
        (client_id, ip, start_date, end_date + " 23:59:59", limit),
    ).fetchall()]
    conn.close()
    return rows


def update_click(log_id: int, **kwargs):
    if _use_sb():
        return  # Supabase 모드에서는 개별 업데이트 미지원
    if not kwargs:
        return
    conn = get_conn()
    sets = ", ".join(f"{k} = ?" for k in kwargs)
    conn.execute(f"UPDATE click_logs SET {sets} WHERE id = ?", [*kwargs.values(), log_id])
    conn.commit()
    conn.close()


def get_clicks(client_id: str, hours: int = 24, limit: int = 10000) -> list[dict]:
    """최근 N시간 클릭 로그 반환 (detector.run_detection 에서 사용)."""
    if _use_sb():
        end   = datetime.now().strftime("%Y-%m-%d")
        start = (datetime.now() - timedelta(hours=hours)).strftime("%Y-%m-%d")
        return _fetch_clicks_sb(client_id, start, end, limit=limit)
    conn = get_conn()
    rows = [dict(r) for r in conn.execute(
        """SELECT * FROM click_logs
           WHERE client_id = ?
             AND created_at >= strftime('%Y-%m-%d %H:%M:%S', 'now', ?, 'localtime')
           ORDER BY created_at DESC LIMIT ?""",
        (client_id, f"-{hours} hours", limit),
    ).fetchall()]
    conn.close()
    return rows


def upsert_suspicious_ip(client_id: str, ip: str, data: dict):
    """의심 IP 갱신 (detector.run_detection 에서 사용 — Supabase 모드에서는 동적 계산으로 대체)."""
    if _use_sb():
        return  # Supabase 모드에서는 get_suspect_ip_set()이 동적으로 계산
    conn = get_conn()
    conn.execute(
        """INSERT INTO suspicious_ips
               (client_id, ip_address, reason, click_count, keyword_count,
                first_seen, last_seen, risk_score, status, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, strftime('%Y-%m-%d %H:%M:%S','now','localtime'))
           ON CONFLICT(client_id, ip_address) DO UPDATE SET
               reason=excluded.reason, click_count=excluded.click_count,
               keyword_count=excluded.keyword_count,
               first_seen=COALESCE(NULLIF(first_seen,''), excluded.first_seen),
               last_seen=excluded.last_seen, risk_score=excluded.risk_score,
               status=CASE WHEN status='blocked' THEN 'blocked' ELSE excluded.status END,
               updated_at=strftime('%Y-%m-%d %H:%M:%S','now','localtime')""",
        (
            client_id, ip,
            data.get("reason", ""), data.get("click_count", 0),
            data.get("keyword_count", 0), data.get("first_seen", ""),
            data.get("last_seen", ""), data.get("risk_score", 0),
            data.get("status", "suspect"),
        ),
    )
    conn.commit()
    conn.close()


def is_blocked(client_id: str, ip: str) -> bool:
    if _use_sb():
        return ip in get_naver_excluded_ip_set(client_id)
    conn = get_conn()
    row = conn.execute(
        "SELECT 1 FROM blocked_ips WHERE client_id = ? AND ip_address = ? AND active = 1 LIMIT 1",
        (client_id, ip),
    ).fetchone()
    conn.close()
    return row is not None


# ══════════════════════════════════════════════════════════════════════════════
# 의심 IP / 차단 IP
# ══════════════════════════════════════════════════════════════════════════════

def get_suspect_ip_set(client_id: str) -> dict:
    """IP → {risk_score, status} 매핑."""
    if _use_sb():
        cfg = get_client_settings(client_id)
        threshold = int(cfg.get("max_clicks_24h", 5))
        today = datetime.now().strftime("%Y-%m-%d")
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        summary = get_ip_summary(client_id, yesterday, today)
        result = {}
        for row in summary:
            c = row["total_clicks"]
            if c >= threshold * 2:
                result[row["ip_address"]] = {"risk_score": min(100, c * 10), "status": "strong_suspect"}
            elif c >= threshold:
                result[row["ip_address"]] = {"risk_score": min(80, c * 8), "status": "suspect"}
        return result
    conn = get_conn()
    rows = conn.execute(
        "SELECT ip_address, risk_score, status FROM suspicious_ips WHERE client_id = ?",
        (client_id,),
    ).fetchall()
    conn.close()
    return {r["ip_address"]: {"risk_score": r["risk_score"], "status": r["status"]} for r in rows}


def get_blocked_ip_set(client_id: str) -> set:
    if _use_sb():
        return get_naver_excluded_ip_set(client_id)
    conn = get_conn()
    rows = conn.execute(
        "SELECT ip_address FROM blocked_ips WHERE client_id = ? AND active = 1",
        (client_id,),
    ).fetchall()
    conn.close()
    return {r["ip_address"] for r in rows}


def block_ip(client_id: str, ip: str, reason: str, blocked_by: str, memo: str = ""):
    if _use_sb():
        add_naver_excluded_ip(client_id, ip, memo or reason)
        return
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_conn()
    conn.execute(
        """INSERT INTO blocked_ips (client_id, ip_address, reason, blocked_by, created_at)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(client_id, ip_address) DO UPDATE SET
               active=1, reason=excluded.reason,
               blocked_by=excluded.blocked_by, created_at=excluded.created_at""",
        (client_id, ip, reason, blocked_by, now),
    )
    conn.execute(
        "UPDATE suspicious_ips SET status='blocked', blocked_at=?, memo=? WHERE client_id=? AND ip_address=?",
        (now, memo, client_id, ip),
    )
    conn.commit()
    conn.close()


def unblock_ip(client_id: str, ip: str):
    if _use_sb():
        remove_naver_excluded_ip(client_id, ip)
        return
    conn = get_conn()
    conn.execute("UPDATE blocked_ips SET active=0 WHERE client_id=? AND ip_address=?", (client_id, ip))
    conn.execute("UPDATE suspicious_ips SET status='cleared' WHERE client_id=? AND ip_address=?", (client_id, ip))
    conn.commit()
    conn.close()


def clear_suspect(client_id: str, ip: str):
    if _use_sb():
        return  # Supabase 모드에서는 동적 계산
    conn = get_conn()
    conn.execute(
        "UPDATE suspicious_ips SET status='cleared' WHERE client_id=? AND ip_address=?",
        (client_id, ip),
    )
    conn.commit()
    conn.close()


# ══════════════════════════════════════════════════════════════════════════════
# 네이버 노출제한 IP
# ══════════════════════════════════════════════════════════════════════════════

def _naver_ips_key(client_id: str) -> str:
    return f"fraud_naver_{client_id}"


def get_naver_excluded_ips(client_id: str) -> list[dict]:
    if _use_sb():
        sb = _get_sb()
        if not sb:
            return []
        try:
            res = sb.table("app_data").select("data").eq("key", _naver_ips_key(client_id)).execute()
            if res.data and res.data[0].get("data"):
                return res.data[0]["data"]
        except Exception:
            pass
        return []
    conn = get_conn()
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM naver_excluded_ips WHERE client_id=? ORDER BY registered_at DESC",
        (client_id,),
    ).fetchall()]
    conn.close()
    return rows


def _save_naver_excluded_ips(client_id: str, ips: list[dict]) -> bool:
    sb = _get_sb()
    if not sb:
        return False
    try:
        sb.table("app_data").upsert({
            "key": _naver_ips_key(client_id),
            "data": ips,
            "updated_at": datetime.utcnow().isoformat() + "Z",
        }, on_conflict="key").execute()
        return True
    except Exception as e:
        print(f"[fraud/sb] save_naver_ips 실패: {e}")
        return False


def get_naver_excluded_ip_set(client_id: str) -> set:
    if _use_sb():
        return {x.get("ip_address") for x in get_naver_excluded_ips(client_id) if x.get("ip_address")}
    conn = get_conn()
    rows = conn.execute(
        "SELECT ip_address FROM naver_excluded_ips WHERE client_id=? AND status='active'",
        (client_id,),
    ).fetchall()
    conn.close()
    return {r["ip_address"] for r in rows}


def add_naver_excluded_ip(client_id: str, ip: str, memo: str = "",
                          clicks_valid: int = 0, clicks_total: int = 0) -> bool:
    if _use_sb():
        ips = get_naver_excluded_ips(client_id)
        for ex in ips:
            if ex.get("ip_address") == ip:
                return False
        ips.append({
            "ip_address": ip, "memo": memo,
            "registered_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "ad_clicks_valid": clicks_valid, "ad_clicks_total": clicks_total,
            "daily_visits": 0, "conversions": 0,
            "status": "active", "naver_synced": False,
        })
        return _save_naver_excluded_ips(client_id, ips)
    conn = get_conn()
    try:
        conn.execute("""
            INSERT INTO naver_excluded_ips
                (client_id, ip_address, memo, ad_clicks_valid, ad_clicks_total)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(client_id, ip_address) DO UPDATE SET
                memo=excluded.memo, status='active',
                ad_clicks_valid=excluded.ad_clicks_valid,
                ad_clicks_total=excluded.ad_clicks_total,
                registered_at=strftime('%Y-%m-%d %H:%M:%S','now','localtime')
        """, (client_id, ip, memo, clicks_valid, clicks_total))
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()


def remove_naver_excluded_ip(client_id: str, ip: str):
    if _use_sb():
        ips = [x for x in get_naver_excluded_ips(client_id) if x.get("ip_address") != ip]
        _save_naver_excluded_ips(client_id, ips)
        return
    conn = get_conn()
    conn.execute(
        "UPDATE naver_excluded_ips SET status='removed' WHERE client_id=? AND ip_address=?",
        (client_id, ip),
    )
    conn.commit()
    conn.close()


def mark_naver_synced(client_id: str, ip: str):
    if _use_sb():
        ips = get_naver_excluded_ips(client_id)
        for item in ips:
            if item.get("ip_address") == ip:
                item["naver_synced"] = True
                break
        _save_naver_excluded_ips(client_id, ips)
        return
    conn = get_conn()
    conn.execute(
        "UPDATE naver_excluded_ips SET naver_synced=1 WHERE client_id=? AND ip_address=?",
        (client_id, ip),
    )
    conn.commit()
    conn.close()


def check_auto_block_candidates(client_id: str) -> list[dict]:
    """자동차단 조건 초과 IP 목록 (노출제한 미등록 IP)."""
    settings = get_client_settings(client_id)
    days   = int(settings.get("auto_block_days", 7))
    clicks = int(settings.get("auto_block_clicks", 5))

    end   = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    if _use_sb():
        summary = get_ip_summary(client_id, start, end)
    else:
        conn = get_conn()
        summary = [dict(r) for r in conn.execute("""
            SELECT ip_address, COUNT(*) AS total_clicks
            FROM click_logs
            WHERE client_id = ?
              AND created_at >= strftime('%Y-%m-%d %H:%M:%S','now',?,'localtime')
              AND ip_address != ''
            GROUP BY ip_address
            HAVING total_clicks >= ?
            ORDER BY total_clicks DESC
        """, (client_id, f"-{days} days", clicks)).fetchall()]
        conn.close()

    existing = get_naver_excluded_ip_set(client_id)
    safe_ips = set(settings.get("safe_ips") or [])
    return [
        r for r in summary
        if r.get("total_clicks", 0) >= clicks
        and r.get("ip_address", "") not in existing
        and r.get("ip_address", "") not in safe_ips
    ]


# ══════════════════════════════════════════════════════════════════════════════
# 클라이언트 설정
# ══════════════════════════════════════════════════════════════════════════════

def _settings_key(client_id: str) -> str:
    return f"fraud_cfg_{client_id}"


def get_client_settings(client_id: str) -> dict:
    if _use_sb():
        sb = _get_sb()
        if sb:
            try:
                res = sb.table("app_data").select("data").eq("key", _settings_key(client_id)).execute()
                if res.data and res.data[0].get("data"):
                    d = res.data[0]["data"]
                    for k, v in _DEFAULT_SETTINGS.items():
                        if k not in d or d[k] is None:
                            d[k] = v
                    return d
            except Exception:
                pass
        return {"client_id": client_id, **_DEFAULT_SETTINGS}

    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM client_fraud_settings WHERE client_id=?", (client_id,)
    ).fetchone()
    conn.close()
    if row:
        d = dict(row)
        try:
            d["safe_ips"] = json.loads(d.get("safe_ips") or "[]")
        except Exception:
            d["safe_ips"] = []
        for k, v in _DEFAULT_SETTINGS.items():
            if k not in d or d[k] is None:
                d[k] = v
        return d
    return {"client_id": client_id, **_DEFAULT_SETTINGS}


def save_client_settings(client_id: str, settings: dict):
    if _use_sb():
        sb = _get_sb()
        if not sb:
            return
        payload = {"client_id": client_id, **_DEFAULT_SETTINGS, **settings}
        try:
            sb.table("app_data").upsert({
                "key": _settings_key(client_id),
                "data": payload,
                "updated_at": datetime.utcnow().isoformat() + "Z",
            }, on_conflict="key").execute()
        except Exception as e:
            print(f"[fraud/sb] save_settings 실패: {e}")
        return

    conn = get_conn()
    conn.execute(
        """INSERT INTO client_fraud_settings
               (client_id, max_clicks_24h, max_clicks_1h, max_keyword_repeats,
                min_stay_seconds, auto_suspect_score, auto_block_enabled, safe_ips, avg_cpc,
                auto_block_naver, auto_block_days, auto_block_clicks, lte_auto_block,
                naver_api_key, naver_api_secret, naver_customer_id,
                alert_enabled, alert_clicks, alert_phone, track_server_url,
                updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,
                   strftime('%Y-%m-%d %H:%M:%S','now','localtime'))
           ON CONFLICT(client_id) DO UPDATE SET
               max_clicks_24h=excluded.max_clicks_24h,
               max_clicks_1h=excluded.max_clicks_1h,
               max_keyword_repeats=excluded.max_keyword_repeats,
               min_stay_seconds=excluded.min_stay_seconds,
               auto_suspect_score=excluded.auto_suspect_score,
               auto_block_enabled=excluded.auto_block_enabled,
               safe_ips=excluded.safe_ips, avg_cpc=excluded.avg_cpc,
               auto_block_naver=excluded.auto_block_naver,
               auto_block_days=excluded.auto_block_days,
               auto_block_clicks=excluded.auto_block_clicks,
               lte_auto_block=excluded.lte_auto_block,
               naver_api_key=excluded.naver_api_key,
               naver_api_secret=excluded.naver_api_secret,
               naver_customer_id=excluded.naver_customer_id,
               alert_enabled=excluded.alert_enabled,
               alert_clicks=excluded.alert_clicks,
               alert_phone=excluded.alert_phone,
               track_server_url=excluded.track_server_url,
               updated_at=excluded.updated_at""",
        (
            client_id,
            settings.get("max_clicks_24h", 5),
            settings.get("max_clicks_1h", 3),
            settings.get("max_keyword_repeats", 3),
            settings.get("min_stay_seconds", 10),
            settings.get("auto_suspect_score", 50),
            1 if settings.get("auto_block_enabled") else 0,
            json.dumps(settings.get("safe_ips") or [], ensure_ascii=False),
            settings.get("avg_cpc", 500),
            1 if settings.get("auto_block_naver") else 0,
            settings.get("auto_block_days", 7),
            settings.get("auto_block_clicks", 5),
            1 if settings.get("lte_auto_block") else 0,
            settings.get("naver_api_key", ""),
            settings.get("naver_api_secret", ""),
            settings.get("naver_customer_id", ""),
            1 if settings.get("alert_enabled") else 0,
            settings.get("alert_clicks", 5),
            settings.get("alert_phone", ""),
            settings.get("track_server_url", ""),
        ),
    )
    conn.commit()
    conn.close()


# ══════════════════════════════════════════════════════════════════════════════
# 대시보드 통계
# ══════════════════════════════════════════════════════════════════════════════

def get_dashboard_stats(client_id: str) -> dict:
    today = datetime.now().strftime("%Y-%m-%d")
    if _use_sb():
        summary = get_ip_summary(client_id, today, today)
        total   = sum(r["total_clicks"] for r in summary)
        suspect = sum(1 for r in summary if r["total_clicks"] >= 5)
        return {"today_total": total, "today_suspect_ips": suspect, "today_blocked": 0}
    conn = get_conn()
    total = conn.execute(
        "SELECT COUNT(*) FROM click_logs WHERE client_id=? AND created_at>=?",
        (client_id, today),
    ).fetchone()[0]
    suspect = conn.execute(
        "SELECT COUNT(DISTINCT ip_address) FROM suspicious_ips WHERE client_id=? AND status IN ('suspect','strong_suspect')",
        (client_id,),
    ).fetchone()[0]
    blocked = conn.execute(
        "SELECT COUNT(*) FROM blocked_ips WHERE client_id=? AND active=1",
        (client_id,),
    ).fetchone()[0]
    conn.close()
    return {"today_total": total, "today_suspect_ips": suspect, "today_blocked": blocked}
