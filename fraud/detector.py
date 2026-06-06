"""부정클릭 탐지 엔진 — 위험 점수 계산 + 의심 IP 갱신"""
import re
from collections import defaultdict
from datetime import datetime, timedelta

from .db import get_clicks, get_client_settings, upsert_suspicious_ip

# ── User-Agent 봇 패턴 ────────────────────────────────────────────────────────
_BOT_RE = re.compile(
    r"bot|crawler|spider|scraper|headless|phantomjs|selenium|puppeteer"
    r"|curl|wget|python-requests|python-urllib|java/|go-http-client|httpclient",
    re.IGNORECASE,
)


def is_bot_ua(user_agent: str) -> bool:
    return bool(_BOT_RE.search(user_agent or ""))


def classify_device(user_agent: str) -> tuple[str, str, str]:
    """(device, browser, os) 반환"""
    ua = (user_agent or "").lower()

    if "ipad" in ua:
        device = "tablet"
    elif any(x in ua for x in ("iphone", "android", "mobile")):
        device = "mobile"
    else:
        device = "desktop"

    if "edg/" in ua or "edgA/" in ua:
        browser = "Edge"
    elif "chrome" in ua:
        browser = "Chrome"
    elif "firefox" in ua:
        browser = "Firefox"
    elif "safari" in ua:
        browser = "Safari"
    else:
        browser = "Other"

    if "windows" in ua:
        os_name = "Windows"
    elif "android" in ua:
        os_name = "Android"
    elif "iphone" in ua or "ipad" in ua:
        os_name = "iOS"
    elif "mac os" in ua or "macintosh" in ua:
        os_name = "macOS"
    elif "linux" in ua:
        os_name = "Linux"
    else:
        os_name = "Other"

    return device, browser, os_name


# ── 위험 점수 계산 ────────────────────────────────────────────────────────────

def calculate_risk(ip: str, all_clicks: list[dict], settings: dict) -> tuple[int, list[str]]:
    """
    (risk_score, reasons) 반환.
    all_clicks: 해당 client_id의 최근 24h 클릭 전체
    """
    safe_ips: list = settings.get("safe_ips", [])
    if ip in safe_ips:
        return 0, []

    ip_clicks = [c for c in all_clicks if c.get("ip_address") == ip]
    if not ip_clicks:
        return 0, []

    score = 0
    reasons: list[str] = []
    now = datetime.now()

    total = len(ip_clicks)

    # Rule 1: 24시간 내 반복 클릭
    max_24h: int = settings.get("max_clicks_24h", 5)
    if total >= max_24h:
        score += 30
        reasons.append(f"24시간 내 {total}회 유입 (기준 {max_24h}회+)")

    # Rule 2: 1시간 내 반복 클릭
    cutoff_1h = now - timedelta(hours=1)
    clicks_1h = [
        c for c in ip_clicks
        if _parse_dt(c.get("created_at", "")) >= cutoff_1h
    ]
    max_1h: int = settings.get("max_clicks_1h", 3)
    if len(clicks_1h) >= max_1h:
        score += 30
        reasons.append(f"1시간 내 {len(clicks_1h)}회 유입 (기준 {max_1h}회+)")

    # Rule 3: 동일 키워드 반복
    kw_counts: dict[str, int] = defaultdict(int)
    for c in ip_clicks:
        kw = (c.get("keyword") or "").strip()
        if kw:
            kw_counts[kw] += 1
    max_kw: int = settings.get("max_keyword_repeats", 3)
    repeat_kws = {k: v for k, v in kw_counts.items() if v >= max_kw}
    if repeat_kws:
        score += 20
        kw_str = ", ".join(f"{k}({v}회)" for k, v in list(repeat_kws.items())[:3])
        reasons.append(f"키워드 반복: {kw_str}")

    # Rule 4: 평균 체류시간 짧음
    stays = [int(c.get("stay_seconds") or 0) for c in ip_clicks]
    avg_stay = sum(stays) / len(stays) if stays else 0
    min_stay: int = settings.get("min_stay_seconds", 10)
    if 0 < avg_stay <= min_stay:
        score += 20
        reasons.append(f"평균 체류시간 {avg_stay:.0f}초 (기준 {min_stay}초 이하)")

    # Rule 5: 전환 없이 반복
    conversions = [c for c in ip_clicks if c.get("is_conversion")]
    if not conversions and total >= 3:
        score += 10
        reasons.append("전환 없이 클릭 반복")

    # Rule 6: 봇 UA
    if any(is_bot_ua(c.get("user_agent", "")) for c in ip_clicks):
        score += 10
        reasons.append("봇 패턴 User-Agent 감지")

    # 오탐 방지 감점
    if conversions:
        score = max(0, score - 20)
    if avg_stay > 60:
        score = max(0, score - 10)

    return score, reasons


def _parse_dt(s: str) -> datetime:
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
    except Exception:
        return datetime.min


# ── 전체 탐지 실행 ────────────────────────────────────────────────────────────

def run_detection(client_id: str) -> int:
    """의심 IP를 탐지하고 suspicious_ips 테이블을 갱신. 신규/갱신 건수 반환."""
    settings = get_client_settings(client_id)
    safe_ips: list = settings.get("safe_ips", [])
    clicks = get_clicks(client_id, hours=24, limit=10000)
    if not clicks:
        return 0

    auto_score: int = settings.get("auto_suspect_score", 50)
    ip_set = {c["ip_address"] for c in clicks if c.get("ip_address") and c["ip_address"] not in safe_ips}

    updated = 0
    for ip in ip_set:
        score, reasons = calculate_risk(ip, clicks, settings)
        if score < auto_score:
            continue

        ip_clicks = [c for c in clicks if c.get("ip_address") == ip]
        keywords = list({
            (c.get("keyword") or "").strip()
            for c in ip_clicks
            if (c.get("keyword") or "").strip()
        })
        times = sorted(c["created_at"] for c in ip_clicks if c.get("created_at"))

        status = "strong_suspect" if score >= 80 else "suspect"
        upsert_suspicious_ip(client_id, ip, {
            "reason":        " / ".join(reasons),
            "click_count":   len(ip_clicks),
            "keyword_count": len(keywords),
            "first_seen":    times[0] if times else "",
            "last_seen":     times[-1] if times else "",
            "risk_score":    score,
            "status":        status,
        })
        updated += 1

    return updated
