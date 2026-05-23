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

import os, sys, time, hmac, hashlib, base64
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
            for item in rows:
                kid_ = item.get("id", "")
                for dr in (item.get("data") or []):
                    rnk = dr.get("avgRnk")
                    if rnk and float(rnk) > 0:
                        results[kid_] = float(rnk)
        except Exception:
            pass
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

        # 전일 평균순위 조회
        kid_list = []
        for kw in g.get("keywords", []):
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

    cycle_count  = 0
    _last_hb_t   = 0.0   # heartbeat 마지막 저장 시각

    while True:
        now = datetime.now()

        # 스케줄러 alive heartbeat (3분마다 Supabase 저장)
        if time.time() - _last_hb_t > 180:
            sb_save("scheduler_heartbeat", now.strftime("%Y-%m-%dT%H:%M:%S"))
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
