"""부정클릭 SQLite 데이터 레이어"""
import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "click_fraud.db"


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


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
        created_at    TEXT    DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now', 'localtime'))
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
        updated_at    TEXT    DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now', 'localtime')),
        UNIQUE(client_id, ip_address)
    );

    CREATE TABLE IF NOT EXISTS blocked_ips (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id     TEXT    NOT NULL,
        ip_address    TEXT    NOT NULL,
        reason        TEXT    DEFAULT '',
        blocked_by    TEXT    DEFAULT '',
        created_at    TEXT    DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now', 'localtime')),
        active        INTEGER DEFAULT 1,
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
        updated_at            TEXT    DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now', 'localtime'))
    );
    """)
    conn.commit()
    conn.close()


# ── 클릭 로그 ────────────────────────────────────────────────────────────────

def hash_ip(ip: str) -> str:
    return hashlib.sha256(ip.encode()).hexdigest()[:16]


def log_click(data: dict) -> int:
    conn = get_conn()
    ip = data.get("ip_address", "")
    fields = [
        "client_id", "ip_address", "ip_hash", "user_agent", "landing_url",
        "referrer", "keyword", "campaign", "source", "medium",
        "device", "browser", "os", "session_id", "is_conversion",
        "stay_seconds", "created_at",
    ]
    row = {f: data.get(f, "") for f in fields}
    row["ip_hash"] = hash_ip(ip) if ip else ""
    if not row["created_at"]:
        row["created_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cols = ", ".join(fields)
    ph   = ", ".join("?" for _ in fields)
    vals = [row[f] for f in fields]
    cur  = conn.execute(f"INSERT INTO click_logs ({cols}) VALUES ({ph})", vals)
    conn.commit()
    last_id = cur.lastrowid
    conn.close()
    return last_id


def get_clicks(client_id: str, hours: int = 24, limit: int = 5000) -> list[dict]:
    conn = get_conn()
    cur = conn.execute(
        """SELECT * FROM click_logs
           WHERE client_id = ?
             AND created_at >= strftime('%Y-%m-%d %H:%M:%S', 'now', ?, 'localtime')
           ORDER BY created_at DESC LIMIT ?""",
        (client_id, f"-{hours} hours", limit),
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def get_all_clicks(
    client_id: str,
    start_date: str = None,
    end_date: str = None,
    limit: int = 500,
) -> list[dict]:
    conn = get_conn()
    q = "SELECT * FROM click_logs WHERE client_id = ?"
    params: list = [client_id]
    if start_date:
        q += " AND created_at >= ?"
        params.append(start_date)
    if end_date:
        q += " AND created_at <= ?"
        params.append(end_date + " 23:59:59")
    q += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    rows = [dict(r) for r in conn.execute(q, params).fetchall()]
    conn.close()
    return rows


def update_click(log_id: int, **kwargs):
    if not kwargs:
        return
    conn = get_conn()
    sets = ", ".join(f"{k} = ?" for k in kwargs)
    conn.execute(f"UPDATE click_logs SET {sets} WHERE id = ?", [*kwargs.values(), log_id])
    conn.commit()
    conn.close()


# ── 의심 IP ──────────────────────────────────────────────────────────────────

def upsert_suspicious_ip(client_id: str, ip: str, data: dict):
    conn = get_conn()
    conn.execute(
        """INSERT INTO suspicious_ips
               (client_id, ip_address, reason, click_count, keyword_count,
                first_seen, last_seen, risk_score, status, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, strftime('%Y-%m-%d %H:%M:%S','now','localtime'))
           ON CONFLICT(client_id, ip_address) DO UPDATE SET
               reason        = excluded.reason,
               click_count   = excluded.click_count,
               keyword_count = excluded.keyword_count,
               first_seen    = COALESCE(NULLIF(first_seen,''), excluded.first_seen),
               last_seen     = excluded.last_seen,
               risk_score    = excluded.risk_score,
               status        = CASE WHEN status = 'blocked' THEN 'blocked'
                                    ELSE excluded.status END,
               updated_at    = strftime('%Y-%m-%d %H:%M:%S','now','localtime')""",
        (
            client_id, ip,
            data.get("reason", ""),
            data.get("click_count", 0),
            data.get("keyword_count", 0),
            data.get("first_seen", ""),
            data.get("last_seen", ""),
            data.get("risk_score", 0),
            data.get("status", "suspect"),
        ),
    )
    conn.commit()
    conn.close()


def get_suspicious_ips(client_id: str) -> list[dict]:
    conn = get_conn()
    rows = [dict(r) for r in conn.execute(
        """SELECT * FROM suspicious_ips
           WHERE client_id = ? AND status IN ('suspect','strong_suspect')
           ORDER BY risk_score DESC, last_seen DESC""",
        (client_id,),
    ).fetchall()]
    conn.close()
    return rows


def update_suspicious_memo(client_id: str, ip: str, memo: str):
    conn = get_conn()
    conn.execute(
        "UPDATE suspicious_ips SET memo = ? WHERE client_id = ? AND ip_address = ?",
        (memo, client_id, ip),
    )
    conn.commit()
    conn.close()


def clear_suspect(client_id: str, ip: str):
    conn = get_conn()
    conn.execute(
        "UPDATE suspicious_ips SET status = 'cleared' WHERE client_id = ? AND ip_address = ?",
        (client_id, ip),
    )
    conn.commit()
    conn.close()


# ── 차단 IP ──────────────────────────────────────────────────────────────────

def block_ip(client_id: str, ip: str, reason: str, blocked_by: str, memo: str = ""):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_conn()
    conn.execute(
        """INSERT INTO blocked_ips (client_id, ip_address, reason, blocked_by, created_at)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(client_id, ip_address) DO UPDATE SET
               active = 1, reason = excluded.reason,
               blocked_by = excluded.blocked_by, created_at = excluded.created_at""",
        (client_id, ip, reason, blocked_by, now),
    )
    conn.execute(
        """UPDATE suspicious_ips SET status = 'blocked', blocked_at = ?, memo = ?
           WHERE client_id = ? AND ip_address = ?""",
        (now, memo, client_id, ip),
    )
    conn.commit()
    conn.close()


def unblock_ip(client_id: str, ip: str):
    conn = get_conn()
    conn.execute(
        "UPDATE blocked_ips SET active = 0 WHERE client_id = ? AND ip_address = ?",
        (client_id, ip),
    )
    conn.execute(
        "UPDATE suspicious_ips SET status = 'cleared' WHERE client_id = ? AND ip_address = ?",
        (client_id, ip),
    )
    conn.commit()
    conn.close()


def get_blocked_ips(client_id: str) -> list[dict]:
    conn = get_conn()
    rows = [dict(r) for r in conn.execute(
        """SELECT * FROM blocked_ips WHERE client_id = ? AND active = 1
           ORDER BY created_at DESC""",
        (client_id,),
    ).fetchall()]
    conn.close()
    return rows


def is_blocked(client_id: str, ip: str) -> bool:
    conn = get_conn()
    row = conn.execute(
        "SELECT 1 FROM blocked_ips WHERE client_id = ? AND ip_address = ? AND active = 1 LIMIT 1",
        (client_id, ip),
    ).fetchone()
    conn.close()
    return row is not None


# ── 클라이언트 설정 ───────────────────────────────────────────────────────────

_DEFAULT_SETTINGS = {
    "max_clicks_24h": 5,
    "max_clicks_1h": 3,
    "max_keyword_repeats": 3,
    "min_stay_seconds": 10,
    "auto_suspect_score": 50,
    "auto_block_enabled": 0,
    "safe_ips": [],
    "avg_cpc": 500,
}


def get_client_settings(client_id: str) -> dict:
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM client_fraud_settings WHERE client_id = ?", (client_id,)
    ).fetchone()
    conn.close()
    if row:
        d = dict(row)
        try:
            d["safe_ips"] = json.loads(d.get("safe_ips") or "[]")
        except Exception:
            d["safe_ips"] = []
        return d
    return {"client_id": client_id, **_DEFAULT_SETTINGS}


def save_client_settings(client_id: str, settings: dict):
    conn = get_conn()
    conn.execute(
        """INSERT INTO client_fraud_settings
               (client_id, max_clicks_24h, max_clicks_1h, max_keyword_repeats,
                min_stay_seconds, auto_suspect_score, auto_block_enabled, safe_ips, avg_cpc, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, strftime('%Y-%m-%d %H:%M:%S','now','localtime'))
           ON CONFLICT(client_id) DO UPDATE SET
               max_clicks_24h      = excluded.max_clicks_24h,
               max_clicks_1h       = excluded.max_clicks_1h,
               max_keyword_repeats = excluded.max_keyword_repeats,
               min_stay_seconds    = excluded.min_stay_seconds,
               auto_suspect_score  = excluded.auto_suspect_score,
               auto_block_enabled  = excluded.auto_block_enabled,
               safe_ips            = excluded.safe_ips,
               avg_cpc             = excluded.avg_cpc,
               updated_at          = excluded.updated_at""",
        (
            client_id,
            settings.get("max_clicks_24h", 5),
            settings.get("max_clicks_1h", 3),
            settings.get("max_keyword_repeats", 3),
            settings.get("min_stay_seconds", 10),
            settings.get("auto_suspect_score", 50),
            1 if settings.get("auto_block_enabled") else 0,
            json.dumps(settings.get("safe_ips", []), ensure_ascii=False),
            settings.get("avg_cpc", 500),
        ),
    )
    conn.commit()
    conn.close()


# ── 대시보드 통계 ─────────────────────────────────────────────────────────────

def get_dashboard_stats(client_id: str) -> dict:
    conn = get_conn()
    today = datetime.now().strftime("%Y-%m-%d")

    today_total = conn.execute(
        "SELECT COUNT(*) FROM click_logs WHERE client_id = ? AND created_at >= ?",
        (client_id, today),
    ).fetchone()[0]

    today_suspect_ips = conn.execute(
        """SELECT COUNT(DISTINCT cl.ip_address)
           FROM click_logs cl
           JOIN suspicious_ips si
             ON cl.client_id = si.client_id AND cl.ip_address = si.ip_address
           WHERE cl.client_id = ? AND cl.created_at >= ?
             AND si.status IN ('suspect','strong_suspect','blocked')""",
        (client_id, today),
    ).fetchone()[0]

    today_suspect_clicks = conn.execute(
        """SELECT COUNT(*)
           FROM click_logs cl
           JOIN suspicious_ips si
             ON cl.client_id = si.client_id AND cl.ip_address = si.ip_address
           WHERE cl.client_id = ? AND cl.created_at >= ?
             AND si.status IN ('suspect','strong_suspect','blocked')""",
        (client_id, today),
    ).fetchone()[0]

    suspect_count = conn.execute(
        """SELECT COUNT(*) FROM suspicious_ips
           WHERE client_id = ? AND status IN ('suspect','strong_suspect')""",
        (client_id,),
    ).fetchone()[0]

    blocked_count = conn.execute(
        "SELECT COUNT(*) FROM blocked_ips WHERE client_id = ? AND active = 1",
        (client_id,),
    ).fetchone()[0]

    top_ips = [dict(r) for r in conn.execute(
        """SELECT ip_address, COUNT(*) AS cnt
           FROM click_logs
           WHERE client_id = ?
             AND created_at >= strftime('%Y-%m-%d %H:%M:%S','now','-24 hours','localtime')
           GROUP BY ip_address ORDER BY cnt DESC LIMIT 10""",
        (client_id,),
    ).fetchall()]

    top_keywords = [dict(r) for r in conn.execute(
        """SELECT keyword, COUNT(*) AS cnt
           FROM click_logs
           WHERE client_id = ?
             AND created_at >= strftime('%Y-%m-%d %H:%M:%S','now','-24 hours','localtime')
             AND keyword != ''
           GROUP BY keyword ORDER BY cnt DESC LIMIT 10""",
        (client_id,),
    ).fetchall()]

    conn.close()
    ratio = round(today_suspect_clicks / today_total * 100, 1) if today_total else 0
    return {
        "today_total":         today_total,
        "today_suspect_clicks": today_suspect_clicks,
        "today_suspect_ips":   today_suspect_ips,
        "suspect_count":       suspect_count,
        "blocked_count":       blocked_count,
        "suspect_ratio":       ratio,
        "top_ips":             top_ips,
        "top_keywords":        top_keywords,
    }


def get_report_data(client_id: str, start_date: str, end_date: str) -> dict:
    conn = get_conn()
    total = conn.execute(
        "SELECT COUNT(*) FROM click_logs WHERE client_id=? AND created_at BETWEEN ? AND ?",
        (client_id, start_date, end_date + " 23:59:59"),
    ).fetchone()[0]

    suspect_clicks = conn.execute(
        """SELECT COUNT(*) FROM click_logs cl
           JOIN suspicious_ips si ON cl.client_id=si.client_id AND cl.ip_address=si.ip_address
           WHERE cl.client_id=? AND cl.created_at BETWEEN ? AND ?
             AND si.status IN ('suspect','strong_suspect','blocked')""",
        (client_id, start_date, end_date + " 23:59:59"),
    ).fetchone()[0]

    suspect_ip_count = conn.execute(
        """SELECT COUNT(DISTINCT cl.ip_address) FROM click_logs cl
           JOIN suspicious_ips si ON cl.client_id=si.client_id AND cl.ip_address=si.ip_address
           WHERE cl.client_id=? AND cl.created_at BETWEEN ? AND ?
             AND si.status IN ('suspect','strong_suspect','blocked')""",
        (client_id, start_date, end_date + " 23:59:59"),
    ).fetchone()[0]

    blocked_count = conn.execute(
        "SELECT COUNT(*) FROM blocked_ips WHERE client_id=? AND active=1",
        (client_id,),
    ).fetchone()[0]

    top_keywords = [dict(r) for r in conn.execute(
        """SELECT keyword, COUNT(*) AS cnt FROM click_logs cl
           JOIN suspicious_ips si ON cl.client_id=si.client_id AND cl.ip_address=si.ip_address
           WHERE cl.client_id=? AND cl.created_at BETWEEN ? AND ?
             AND cl.keyword!='' AND si.status IN ('suspect','strong_suspect','blocked')
           GROUP BY keyword ORDER BY cnt DESC LIMIT 10""",
        (client_id, start_date, end_date + " 23:59:59"),
    ).fetchall()]

    top_ips = [dict(r) for r in conn.execute(
        """SELECT ip_address, COUNT(*) AS cnt FROM click_logs
           WHERE client_id=? AND created_at BETWEEN ? AND ?
           GROUP BY ip_address ORDER BY cnt DESC LIMIT 10""",
        (client_id, start_date, end_date + " 23:59:59"),
    ).fetchall()]

    conn.close()
    return {
        "total": total,
        "suspect_clicks": suspect_clicks,
        "suspect_ip_count": suspect_ip_count,
        "blocked_count": blocked_count,
        "top_keywords": top_keywords,
        "top_ips": top_ips,
    }
