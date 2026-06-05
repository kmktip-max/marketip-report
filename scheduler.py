"""
마케팁 OS — 자동입찰 스케줄러 (로컬 실행)
실행: python scheduler.py  또는  run_scheduler.bat 더블클릭

동작:
  - Supabase에서 자동입찰 ON인 그룹 조회
  - 키워드별: Naver API 입찰가/순위 조회 → 목표순위 비교 → 증액/감액
  - 결과를 Supabase에 저장
  - check_interval 분 대기 → 반복

종료: Ctrl+C
"""

import os, sys, time, hmac, hashlib, base64, json
import requests
from datetime import datetime, timedelta

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
from utils.bid_calc import calc_bid

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, ".env"))
except ImportError:
    pass

# ── 기본 설정 ─────────────────────────────────────────────────────────────────
DEFAULT_INTERVAL_MIN = 15   # 그룹 check_interval이 없을 때 기본값
MAX_LOG_RUNS         = 30   # Supabase에 보관할 최대 실행 이력 수
NAVER_API_BASE       = "https://api.searchad.naver.com"
DEBUG_RANK           = True  # 순위 조회 디버그 로그 (문제 해결 후 False로)
HB_PATH              = os.path.join(ROOT, "data", "scheduler_heartbeat.json")

# ── Supabase ──────────────────────────────────────────────────────────────────
def _get_sb():
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_KEY", "")
    if not url or not key:
        return None
    try:
        from supabase import create_client
        return create_client(url, key)
    except Exception as e:
        print(f"[Supabase] 연결 실패: {e}")
        return None

def _save_heartbeat(data: dict):
    """heartbeat를 로컬 JSON + Supabase 양쪽에 저장."""
    os.makedirs(os.path.dirname(HB_PATH), exist_ok=True)
    try:
        with open(HB_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception as e:
        print(f"[Heartbeat] 로컬 저장 실패: {e}")
    sb_save("scheduler_heartbeat", data)

def sb_load(key_):
    sb = _get_sb()
    if not sb:
        return None
    try:
        res = sb.table("app_data").select("data").eq("key", key_).execute()
        if res.data:
            return res.data[0]["data"]
    except Exception as e:
        print(f"[Supabase] 로드 실패 ({key_}): {e}")
    return None

def sb_save(key_, data_):
    sb = _get_sb()
    if not sb:
        return False
    try:
        sb.table("app_data").upsert({
            "key":        key_,
            "data":       data_,
            "updated_at": datetime.utcnow().isoformat() + "Z",
        }, on_conflict="key").execute()
        return True
    except Exception as e:
        print(f"[Supabase] 저장 실패 ({key_}): {e}")
        return False

# ── Naver 검색광고 API ─────────────────────────────────────────────────────────
def _sig(secret_key, ts, method, uri):
    msg = f"{ts}.{method}.{uri}"
    h   = hmac.new(secret_key.encode(), msg.encode(), hashlib.sha256)
    return base64.b64encode(h.digest()).decode()

def _get(uri, ak, sk, cid, params=None):
    ts  = str(int(time.time() * 1000))
    sig = _sig(sk, ts, "GET", uri)
    headers = {
        "X-Timestamp": ts, "X-API-KEY": ak,
        "X-Customer":  str(cid), "X-Signature": sig,
        "Content-Type": "application/json; charset=UTF-8",
    }
    r = requests.get(NAVER_API_BASE + uri, headers=headers, params=params, timeout=15)
    r.raise_for_status()
    return r.json()

def _put(uri, ak, sk, cid, body, params=None):
    ts  = str(int(time.time() * 1000))
    sig = _sig(sk, ts, "PUT", uri)
    headers = {
        "X-Timestamp": ts, "X-API-KEY": ak,
        "X-Customer":  str(cid), "X-Signature": sig,
        "Content-Type": "application/json; charset=UTF-8",
    }
    r = requests.put(NAVER_API_BASE + uri, headers=headers, json=body,
                     params=params, timeout=15)
    r.raise_for_status()
    return r

def get_keyword(ak, sk, cid, kid):
    """단건 키워드 조회 (GET ?ids=)"""
    try:
        res = _get("/ncc/keywords", ak, sk, cid, params={"ids": kid})
        if isinstance(res, list) and res:
            return res[0]
        if isinstance(res, dict):
            return res
    except Exception:
        pass
    return None

def get_keywords_in_adgroup(ak, sk, cid, adgroup_id):
    """광고그룹 내 전체 키워드 조회"""
    try:
        return _get("/ncc/keywords", ak, sk, cid,
                    params={"nccAdgroupId": adgroup_id}) or []
    except Exception:
        return []

def get_keyword_stats(ak, sk, cid, keyword_ids: list) -> dict:
    """전일 평균노출순위(avgRnk) 배치 조회. 반환: {kid: avgRnk}"""
    if not keyword_ids:
        return {}
    results = {}
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    if DEBUG_RANK:
        print(f"  [RANK-DEBUG] stats API 조회 날짜: {yesterday}, 키워드 수: {len(keyword_ids)}")
    for i in range(0, len(keyword_ids), 50):
        batch = keyword_ids[i:i+50]
        try:
            rows = _get("/stats", ak, sk, cid, params={
                "id":        ",".join(batch),
                "statType":  "AD_GROUP_KEYWORD",
                "startDate": yesterday,
                "endDate":   yesterday,
                "timeUnit":  "DAY",
                "fields":    "clkCnt,impCnt,avgRnk",
            }) or []
            if DEBUG_RANK and i == 0:
                print(f"  [RANK-DEBUG] stats API 응답 원문(첫 배치): {str(rows)[:500]}")
            for item in rows:
                kid_ = item.get("id", "")
                for dr in (item.get("data") or []):
                    rnk = dr.get("avgRnk")
                    if rnk and float(rnk) > 0:
                        results[kid_] = float(rnk)
        except Exception as e:
            if DEBUG_RANK:
                print(f"  [RANK-DEBUG] stats API 예외: {e}")
    if DEBUG_RANK:
        print(f"  [RANK-DEBUG] 순위 수신된 키워드 수: {len(results)}/{len(keyword_ids)}")
    return results

def update_bid(ak, sk, cid, kid, new_bid, keyword_text="", adgroup_id=""):
    """
    입찰가 변경:
    1) GET 현재 전체 객체
    2) bidAmt 수정 후 PUT ?fields=bidAmt,useGroupBidAmt
    3) GET 재조회 검증
    반환: (before_bid, after_bid, verify_ok, http_status)
    """
    # GET
    current = get_keyword(ak, sk, cid, kid)
    before  = current.get("bidAmt", 0) if current else 0

    # PUT body
    if current:
        body = dict(current)
    else:
        body = {"nccKeywordId": kid, "keyword": keyword_text, "nccAdgroupId": adgroup_id}
    body["bidAmt"]         = new_bid
    body["useGroupBidAmt"] = False

    try:
        r = _put(f"/ncc/keywords/{kid}", ak, sk, cid, body,
                 params={"fields": "bidAmt,useGroupBidAmt"})
        http_status = r.status_code
    except Exception as e:
        return before, None, False, str(e)

    # 재조회 검증
    time.sleep(0.5)
    after_kw = get_keyword(ak, sk, cid, kid)
    after    = after_kw.get("bidAmt") if after_kw else None
    verify   = (after == new_bid)
    return before, after, verify, http_status


# ── 예약 보고서 실행 ──────────────────────────────────────────────────────────────
_SCHEDULE_PATH = os.path.join(ROOT, "data", "report_schedule.json")
_CLIENTS_PATH  = os.path.join(ROOT, "clients.json")
_HISTORY_PATH  = os.path.join(ROOT, "report_history.json")


def _rpt_load(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _rpt_save(path, data):
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[보고서스케줄] 저장 실패 {path}: {e}")


def _load_schedule_data():
    """Supabase 우선, 로컬 파일 폴백으로 스케줄 데이터 로드."""
    try:
        sb = _get_sb()
        if sb:
            res = sb.table("app_data").select("data").eq("key", "report_schedule").execute()
            if res.data:
                return res.data[0]["data"]
    except Exception as e:
        print(f"[보고서스케줄] Supabase 로드 실패: {e}")
    return _rpt_load(_SCHEDULE_PATH, {"scheduled": [], "auto_monthly": {}})


def _save_schedule_data(data):
    """Supabase + 로컬 파일 양쪽에 저장."""
    try:
        sb = _get_sb()
        if sb:
            sb.table("app_data").upsert(
                {"key": "report_schedule", "data": data,
                 "updated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S")},
                on_conflict="key",
            ).execute()
    except Exception as e:
        print(f"[보고서스케줄] Supabase 저장 실패: {e}")
    _rpt_save(_SCHEDULE_PATH, data)


def _send_one_report(client, since, until, period_key, history, smtp_cfg):
    from report_engine.naver_api import NaverAdAPI
    from report_engine.emailer import send_report
    from report_engine.report_html import generate_html

    api  = NaverAdAPI(client["api_key"], client["secret_key"], client["customer_id"])
    data = api.fetch_report(period=period_key, since=since, until=until)
    html = generate_html(data, client["name"], datetime.now().strftime("%Y-%m-%d"))
    send_report(
        to_email=client["email"],
        client_name=client["name"],
        period=period_key,
        since=since,
        until=until,
        html_body=html,
        **smtp_cfg,
    )
    history.append({
        "client":    client["name"],
        "email":     client["email"],
        "period":    period_key,
        "since":     since,
        "until":     until,
        "sent_at":   datetime.now().strftime("%Y-%m-%d %H:%M"),
        "status":    "성공",
        "send_mode": "scheduled",
    })
    print(f"[보고서스케줄] ✅ {client['name']} → {client['email']}")


def run_scheduled_reports():
    """예약발송 + 자동 정기발송 처리."""
    if not os.path.exists(_SCHEDULE_PATH):
        return

    sched   = _load_schedule_data()
    clients = _rpt_load(_CLIENTS_PATH, [])
    history = _rpt_load(_HISTORY_PATH, [])

    # ID와 이름 양쪽으로 조회 가능하게 맵 구성
    cmap = {}
    for c in clients:
        if c.get("id"):    cmap[c["id"]]   = c
        if c.get("name"):  cmap[c["name"]] = c

    smtp = {
        "smtp_user":     os.getenv("SMTP_USER", ""),
        "smtp_password": os.getenv("SMTP_PASSWORD", ""),
        "smtp_host":     os.getenv("SMTP_HOST", "smtp.naver.com"),
        "smtp_port":     int(os.getenv("SMTP_PORT", "465")),
    }
    now     = datetime.now()
    changed = False

    # ── 1. 예약발송 처리 ─────────────────────────────────────────────
    for item in sched.get("scheduled", []):
        if item.get("status") != "pending":
            continue
        try:
            sched_dt = datetime.strptime(item["scheduled_at"], "%Y-%m-%dT%H:%M:%S")
        except Exception:
            continue
        if sched_dt > now:
            continue

        names = item.get("client_names", item.get("client_ids", []))
        print(f"[보고서스케줄] 예약 실행: {names}")
        errors = []

        _cnames = item.get("client_names", [])
        for i, cid in enumerate(item.get("client_ids", [])):
            client = cmap.get(cid)
            # ID 매칭 실패 시 이름으로 폴백 (GSheets ID ≠ local ID 대응)
            if not client and i < len(_cnames):
                client = cmap.get(_cnames[i])
            if not client:
                errors.append(f"광고주 미발견: {cid}")
                continue
            try:
                _send_one_report(client, item.get("since"), item.get("until"),
                                 item.get("period_key", "monthly"), history, smtp)
            except Exception as e:
                errors.append(f"{client.get('name')}: {e}")
                print(f"[보고서스케줄] 실패: {client.get('name')} — {e}")

        item["status"]   = "failed" if errors else "sent"
        item["sent_at"]  = now.strftime("%Y-%m-%dT%H:%M:%S")
        item["error"]    = "; ".join(str(e) for e in errors[:3]) if errors else ""
        changed = True

    # ── 2. 자동 정기발송 처리 ────────────────────────────────────────
    auto_cfg  = sched.get("auto_monthly", {})
    cur_month = now.strftime("%Y-%m")

    for cid, cfg in auto_cfg.items():
        if cid.startswith("_"):
            continue
        if not cfg.get("enabled"):
            continue
        if cfg.get("last_sent_month") == cur_month:
            continue

        send_day  = int(cfg.get("send_day", 5))
        send_hour = int(cfg.get("send_hour", 9))
        if now.day != send_day or now.hour < send_hour:
            continue

        # cid가 이름일 수도 있고 ID일 수도 있음 — 둘 다 시도
        client = cmap.get(cid) or cmap.get(cfg.get("client_name", ""))
        if not client:
            print(f"[보고서스케줄] 자동월보 광고주 미발견: {cid}")
            continue

        first_this = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        until_d    = first_this - timedelta(days=1)
        since_d    = until_d.replace(day=1)
        since_s    = since_d.strftime("%Y-%m-%d")
        until_s    = until_d.strftime("%Y-%m-%d")

        print(f"[보고서스케줄] 자동월보: {client.get('name')} ({since_s}~{until_s})")
        try:
            _send_one_report(client, since_s, until_s, "monthly", history, smtp)
            cfg["last_sent_month"] = cur_month
            changed = True
        except Exception as e:
            print(f"[보고서스케줄] 자동월보 실패: {client.get('name')} — {e}")

    if changed:
        _save_schedule_data(sched)
        _rpt_save(_HISTORY_PATH, history)


# ── 1회 사이클 실행 ─────────────────────────────────────────────────────────────
def run_cycle(client_id: str) -> list:
    """
    client_id 의 자동입찰 그룹을 순회하며 입찰가 조정.
    반환: 키워드별 처리 결과 리스트
    """
    bdata = sb_load(f"bidding_{client_id}")
    if not bdata or not isinstance(bdata, dict):
        return []
    groups = bdata.get("groups", [])

    # 광고계정 로드
    ad_accounts = sb_load("naver_ad_accounts") or []
    acct_map    = {a["id"]: a for a in ad_accounts}

    entries  = []
    now_str  = datetime.now().strftime("%H:%M:%S")
    changed  = False

    for g in groups:
        if not g.get("bidding_enabled", True):
            print(f"  [{g['name']}] 자동입찰 비활성화 — 스킵")
            continue
        acct = acct_map.get(g.get("ad_account_id",""))
        if not acct:
            print(f"  [{g['name']}] 광고계정 미연결 — 스킵")
            continue

        ak = acct["api_key"]
        sk = acct["secret_key"]
        ci = acct["customer_id"]

        # 광고그룹 키워드 최신화 (ID + bidAmt)
        ag_id    = g.get("naver_adgroup_id","")
        api_kws  = get_keywords_in_adgroup(ak, sk, ci, ag_id) if ag_id else []
        api_map  = {(k.get("keyword") or k.get("keywordText","")): k for k in api_kws}
        if DEBUG_RANK:
            print(f"  [RANK-DEBUG] 그룹={g['name']} | adgroup_id={ag_id!r} | API 키워드 수={len(api_kws)}")

        # 전일 평균순위 조회
        kid_list = []
        for kw in g.get("keywords", []):
            if not kw.get("enabled", True):
                continue  # 비활성 키워드 스킵
            api_kw = api_map.get(kw["keyword"])
            if api_kw:
                kid_ = api_kw.get("nccKeywordId") or api_kw.get("keywordId") or ""
                if kid_:
                    kw["ncc_keyword_id"] = str(kid_)
                    raw_bid = api_kw.get("bidAmt", 0)
                    if raw_bid and int(raw_bid) > 70:
                        kw["current_bid"] = int(raw_bid)
                    kid_list.append(str(kid_))

        stats = get_keyword_stats(ak, sk, ci, kid_list) if kid_list else {}

        for kw in g.get("keywords", []):
            if not kw.get("enabled", True):
                continue  # 비활성 키워드 스킵
            kid = (kw.get("ncc_keyword_id") or "").strip()
            cur_bid = kw.get("current_bid")

            # 실시간 순위(rank_checker.py) 우선, 없으면 avgRnk fallback
            stored_rank = kw.get("current_rank")
            api_rank    = stats.get(kid)
            if stored_rank is not None:
                rank = stored_rank
            elif api_rank:
                rank = api_rank
                kw["current_rank"] = api_rank
            else:
                rank = None

            if DEBUG_RANK:
                in_api_map = kw["keyword"] in api_map
                if rank is None:
                    if not kid:
                        skip = "keyword_id 없음 (api_map 매칭 실패 또는 ID 미저장)"
                    elif kid not in kid_list:
                        skip = "kid_list에 없음 (bidAmt<=70 등으로 제외됨)"
                    else:
                        skip = "stats API 응답 없음 (광고OFF/예산소진/어제노출0)"
                    print(f"  [RANK-DEBUG] {kw['keyword']!r} | kid={kid!r} | "
                          f"api_map={in_api_map} | stored={stored_rank} | "
                          f"api={api_rank} → None 이유: {skip}")
                else:
                    print(f"  [RANK-DEBUG] {kw['keyword']!r} | kid={kid!r} | rank={rank} "
                          f"(stored={stored_rank}, api={api_rank})")

            e = {
                "time":         now_str,
                "group":        g["name"],
                "keyword":      kw["keyword"],
                "keyword_id":   kid,
                "current_rank": rank,
                "target_rank":  g["target_rank"],
                "before_bid":   cur_bid,
                "after_bid":    None,
                "changed":      False,
                "status":       "데이터 부족",
                "api_response": "",
            }

            if not kid:
                e["status"] = "ID없음";   entries.append(e); continue
            if cur_bid is None:
                e["status"] = "데이터 부족"; entries.append(e); continue

            # 입찰 계산
            new_bid, status = calc_bid(rank, g["target_rank"], cur_bid,
                                       g["bid_unit"], g["min_bid"], g["max_bid"])
            e["status"] = status

            if new_bid == cur_bid or status in ("유지", "최대입찰 도달", "최소입찰 도달"):
                # 변경 불필요
                entries.append(e)
                print(f"  {kw['keyword']}: {status} ({cur_bid}원) 순위={rank}")
                continue

            # 실제 입찰가 변경
            print(f"  {kw['keyword']}: {cur_bid}원 → {new_bid}원 ({status})")
            time.sleep(0.3)   # API rate limit
            before, after, verify, http_st = update_bid(
                ak, sk, ci, kid, new_bid,
                keyword_text=kw["keyword"],
                adgroup_id=ag_id,
            )
            kw["current_bid"]  = after or new_bid
            kw["last_checked"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            e["before_bid"]    = before
            e["after_bid"]     = after
            e["changed"]       = verify
            e["status"]        = ("변경성공" if verify else "변경(검증불일치)") + f"/{status}"
            e["api_response"]  = f"HTTP {http_st}"
            changed = True
            entries.append(e)

        print(f"  [{g['name']}] 완료 — {len(g.get('keywords',[]))}개 키워드")

    if changed:
        sb_save(f"bidding_{client_id}", bdata)

    return entries

# ── 메인 루프 ─────────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("  마케팁 OS — 자동입찰 스케줄러")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} 시작")
    print("  종료: Ctrl+C")
    print("=" * 60)

    # ── 이 스케줄러 인스턴스 시작 시각 (activated_at 유효성 기준) ──────────────
    _session_start = datetime.now()

    # ── 시작 시 자동입찰 running 상태 초기화 (수동 클릭 없이 재개 방지) ─────
    print("  [시작] 자동입찰 상태 초기화 — 수동으로 '자동입찰 시작' 버튼을 눌러야 작동합니다.")
    try:
        _init_accounts = sb_load("client_accounts",
                                  os.path.join(ROOT, "client_accounts.json")) or []
        _init_ids = ["admin"] + [a.get("username","") for a in _init_accounts if a.get("username")]
        for _cid in _init_ids:
            _bd = sb_load(f"bidding_{_cid}")
            if _bd and isinstance(_bd, dict):
                _st = _bd.get("state", {})
                if _st.get("running") or _st.get("trigger_now"):
                    _st["running"]     = False
                    _st["trigger_now"] = False
                    _bd["state"] = _st
                    sb_save(f"bidding_{_cid}", _bd)
                    print(f"  [시작] {_cid}: running → False (수동 시작 필요)")
    except Exception as _ie:
        print(f"  [시작] 초기화 오류 (무시): {_ie}")

    cycle_count         = 0
    _last_hb_t          = 0.0   # heartbeat 마지막 저장 시각
    _last_report_check  = 0.0   # 보고서 스케줄 마지막 체크 시각

    while True:
        now = datetime.now()

        # 스케줄러 alive heartbeat (3분마다 로컬 파일 + Supabase 저장)
        if time.time() - _last_hb_t > 180:
            _save_heartbeat({
                "status":         "running",
                "last_heartbeat": now.strftime("%Y-%m-%dT%H:%M:%S"),
            })
            _last_hb_t = time.time()

        print(f"\n[{now.strftime('%H:%M:%S')}] 사이클 #{cycle_count + 1} 시작")

        # client 목록 조회
        accounts = sb_load("client_accounts") or []
        client_ids = ["admin"] + [a.get("username","") for a in accounts if a.get("username")]

        processed_any = False
        for cid in client_ids:
            bdata = sb_load(f"bidding_{cid}")
            if not bdata or not isinstance(bdata, dict):
                continue

            state = bdata.get("state", {})

            # trigger_now 또는 running 상태일 때 실행
            trigger = state.get("trigger_now", False)
            running = state.get("running", False)
            if not running and not trigger:
                continue

            # activated_at 만료 체크
            # ① 8시간 초과 → 만료
            # ② 이번 스케줄러 세션(_session_start) 이전 활성화 → 만료
            #    (재부팅/재시작 후 이전 세션 activated_at으로 자동 재개 방지)
            if running and not trigger:
                _activated = state.get("activated_at", "")
                _expired = True
                if _activated:
                    try:
                        _act_dt = datetime.fromisoformat(_activated)
                        _elapsed = (datetime.now() - _act_dt).total_seconds()
                        if _elapsed <= 8 * 3600 and _act_dt >= _session_start:
                            _expired = False
                    except Exception:
                        pass
                if _expired:
                    print(f"  [{cid}] activated_at 만료/이전세션 — running 초기화 (수동 재시작 필요)")
                    state["running"] = False
                    bdata["state"] = state
                    sb_save(f"bidding_{cid}", bdata)
                    continue

            print(f"\n  클라이언트: {cid} ({'트리거' if trigger else '자동'})")

            # trigger 초기화
            if trigger:
                state["trigger_now"] = False

            entries = run_cycle(cid)
            cycle_count += 1
            processed_any = True

            # 상태 업데이트
            state["last_run"]    = now.strftime("%Y-%m-%dT%H:%M:%S")
            state["cycle_count"] = state.get("cycle_count", 0) + 1

            # 다음 실행 예정 (그룹 최소 interval 기준)
            groups_   = bdata.get("groups", [])
            intervals = [g.get("check_interval", DEFAULT_INTERVAL_MIN) for g in groups_]
            min_int   = min(intervals) if intervals else DEFAULT_INTERVAL_MIN
            state["next_run"]    = (now + timedelta(minutes=min_int)).strftime("%Y-%m-%dT%H:%M:%S")
            state["interval_min"] = min_int
            bdata["state"] = state

            # 이력 저장
            log_key  = f"bidding_log_{cid}"
            logs     = sb_load(log_key) or []
            summary_ = {
                "total":   len(entries),
                "changed": sum(1 for e in entries if e.get("changed")),
                "kept":    sum(1 for e in entries if e.get("status") in ("유지", "최대입찰 도달", "최소입찰 도달")),
                "no_data": sum(1 for e in entries if e.get("status") in ("데이터 부족", "ID없음")),
                "failed":  sum(1 for e in entries if "API 실패" in e.get("status","")),
            }
            logs.append({
                "run_time": now.strftime("%Y-%m-%dT%H:%M:%S"),
                "cycle":    state["cycle_count"],
                "mode":     "자동(스케줄러)",
                "summary":  summary_,
                "entries":  entries,
            })
            sb_save(log_key, logs[-MAX_LOG_RUNS:])
            sb_save(f"bidding_{cid}", bdata)

            chg = summary_["changed"]
            print(f"  결과: 변경 {chg}개 / 유지 {summary_['kept']}개 / 데이터없음 {summary_['no_data']}개")

            # 사이클 완료 heartbeat 갱신
            _save_heartbeat({
                "status":         "running",
                "last_heartbeat": now.strftime("%Y-%m-%dT%H:%M:%S"),
                "last_run":       state["last_run"],
                "next_run":       state["next_run"],
                "cycle":          state["cycle_count"],
            })
            _last_hb_t = time.time()

        # 예약 보고서 체크 (5분마다)
        if time.time() - _last_report_check > 300:
            try:
                run_scheduled_reports()
            except Exception as _rse:
                print(f"[보고서스케줄] 오류: {_rse}")
            _last_report_check = time.time()

        if not processed_any:
            print(f"  자동입찰 ON 클라이언트 없음 — 60초 후 재확인")
            time.sleep(60)
            continue

        # 다음 사이클까지 대기 (최소 interval)
        wait_min = min_int if 'min_int' in dir() else DEFAULT_INTERVAL_MIN
        print(f"\n  다음 실행: {wait_min}분 후 ({(now + timedelta(minutes=wait_min)).strftime('%H:%M:%S')})")
        time.sleep(wait_min * 60)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n자동입찰 스케줄러 종료.")
