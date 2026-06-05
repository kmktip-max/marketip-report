"""광고 운영 — 목표순위 자동입찰 보조 시스템"""
import streamlit as st
import os, sys, uuid, hmac, hashlib, base64, time, subprocess, json
import requests

try:
    import psutil
    _PSUTIL = True
except ImportError:
    _PSUTIL = False
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from db import sb_load, sb_save
from utils.bid_calc import calc_bid

# ── 인증 ─────────────────────────────────────────────────────────────────────
auth_type     = st.session_state.get("auth_type", "")
auth_username = st.session_state.get("auth_username", "")

if auth_type not in ("admin", "client"):
    st.error("🔒 로그인이 필요합니다.")
    st.stop()

# ── 클라이언트 ID 결정 ─────────────────────────────────────────────────────
if auth_type == "admin":
    accounts  = sb_load("client_accounts", os.path.join(ROOT, "client_accounts.json")) or []
    options   = ["admin"] + [a.get("username","") for a in accounts if a.get("username")]
    client_id = st.selectbox(
        "클라이언트 선택",
        options=options,
        format_func=lambda x: f"[관리자] {x}" if x == "admin" else x,
        key="bid_client",
    )
else:
    client_id = auth_username

SB_KEY             = f"bidding_{client_id}"
FALLBACK_JSON      = os.path.join(ROOT, f"bidding_{client_id}.json")
MAX_GROUPS         = 5
MAX_KEYWORDS       = 9999  # 사실상 무제한
DEFAULT_INTERVAL_MIN = 15  # 그룹 check_interval 기본값 (분)

STATUS_ICON = {
    "증액중":            "🔴",
    "증액중(노출없음)":  "🔴",
    "감액중":            "🔵",
    "유지":              "🟢",
    "데이터 부족":       "⚪",
    "최대입찰 도달":     "🟠",
    "최대입찰(노출없음)":"🟠",
    "최소입찰 도달":     "🟡",
}

# ── 데이터 ────────────────────────────────────────────────────────────────
def load_data():
    raw = sb_load(SB_KEY, FALLBACK_JSON)
    return raw if isinstance(raw, dict) and "groups" in raw else {"groups": []}

def save_data(d):
    sb_save(SB_KEY, d, FALLBACK_JSON)

# ── 실행 이력 ──────────────────────────────────────────────────────────────
LOG_SB_KEY    = f"bidding_log_{client_id}"
LOG_FALLBACK  = os.path.join(ROOT, f"bidding_log_{client_id}.json")
MAX_LOG_RUNS  = 20   # 최대 보관 실행 횟수

def load_log():
    raw = sb_load(LOG_SB_KEY, LOG_FALLBACK)
    return raw if isinstance(raw, list) else []

def save_log(runs: list):
    sb_save(LOG_SB_KEY, runs[-MAX_LOG_RUNS:], LOG_FALLBACK)

BAT_PATH = os.path.join(ROOT, "run_scheduler.bat")
HB_PATH  = os.path.join(ROOT, "data", "scheduler_heartbeat.json")

def _read_heartbeat() -> dict | None:
    """로컬 heartbeat JSON 읽기. 실패 시 Supabase fallback."""
    try:
        if os.path.exists(HB_PATH):
            with open(HB_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    raw = sb_load("scheduler_heartbeat")
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        return {"last_heartbeat": raw}
    return None

def _sched_status() -> tuple:
    """
    heartbeat 기준 스케줄러 상태 반환.
    반환: (is_alive, diff_sec, hb_dict)
      - is_alive: heartbeat가 2분 이내면 True
      - diff_sec: 경과 초 (음수 = 시계 불일치)
      - hb_dict:  원본 heartbeat 딕셔너리
    """
    hb = _read_heartbeat()
    if not hb:
        return False, None, None
    ts_str = hb.get("last_heartbeat", "")
    if not ts_str:
        return False, None, hb
    try:
        ts   = datetime.fromisoformat(ts_str)
        diff = (datetime.now() - ts).total_seconds()
        diff = max(diff, 0)   # 클럭 오차로 인한 음수 방지
        return (diff <= 120), diff, hb
    except Exception:
        return False, None, hb

def _find_scheduler_pid() -> int | None:
    """실행 중인 scheduler.py 의 python PID 반환. 없으면 None."""
    if not _PSUTIL:
        return None
    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            if "python" not in (p.info.get("name") or "").lower():
                continue
            if "scheduler.py" in " ".join(p.info.get("cmdline") or []):
                return p.info["pid"]
        except Exception:
            pass
    return None

def _kill_scheduler(stored_pid=None):
    """cmd.exe(stored_pid) + python scheduler.py 프로세스 트리 모두 종료."""
    if stored_pid:
        try:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(stored_pid)],
                           capture_output=True)
        except Exception:
            pass
    py_pid = _find_scheduler_pid()
    if py_pid and _PSUTIL:
        try:
            psutil.Process(py_pid).terminate()
        except Exception:
            pass
    # 로컬 heartbeat 파일 삭제
    try:
        if os.path.exists(HB_PATH):
            os.remove(HB_PATH)
    except Exception:
        pass
    # Supabase heartbeat도 "stopped"로 초기화 (fallback 읽기 방지)
    try:
        sb_save("scheduler_heartbeat", {"status": "stopped", "last_heartbeat": ""})
    except Exception:
        pass

def new_kw_obj(keyword, current_bid=None, ncc_keyword_id=None):
    return {
        "keyword":         keyword,
        "ncc_keyword_id":  ncc_keyword_id,
        "current_rank":    None,
        "current_bid":     current_bid,
        "recommended_bid": None,
        "status":          "데이터 부족",
        "last_checked":    None,
        "enabled":         True,
    }


# ── 네이버 검색광고 API ───────────────────────────────────────────────────
# 정확한 API Base URL: api.searchad.naver.com (api.naver.com 아님)
NAVER_API_BASE = "https://api.searchad.naver.com"

AD_ACCOUNTS_SB_KEY = "naver_ad_accounts"
AD_ACCOUNTS_FB     = os.path.join(ROOT, "naver_ad_accounts.json")

def load_ad_accounts():
    raw = sb_load(AD_ACCOUNTS_SB_KEY, AD_ACCOUNTS_FB)
    return raw if isinstance(raw, list) else []

def save_ad_accounts(accounts):
    sb_save(AD_ACCOUNTS_SB_KEY, accounts, AD_ACCOUNTS_FB)

def _naver_sig(secret_key, timestamp, method, uri):
    msg = f"{timestamp}.{method}.{uri}"
    h   = hmac.new(secret_key.encode(), msg.encode(), hashlib.sha256)
    return base64.b64encode(h.digest()).decode()

def _naver_get(uri, api_key, secret_key, customer_id, params=None):
    ts  = str(int(time.time() * 1000))
    sig = _naver_sig(secret_key, ts, "GET", uri)
    headers = {
        "X-Timestamp": ts, "X-API-KEY": api_key,
        "X-Customer":  str(customer_id), "X-Signature": sig,
        "Content-Type": "application/json; charset=UTF-8",
    }
    r = requests.get(NAVER_API_BASE + uri, headers=headers, params=params, timeout=10)
    r.raise_for_status()
    return r.json()

def naver_campaigns(api_key, secret_key, cid):
    return _naver_get("/ncc/campaigns", api_key, secret_key, cid) or []

def naver_adgroups(api_key, secret_key, cid, campaign_id):
    return _naver_get("/ncc/adgroups", api_key, secret_key, cid,
                      params={"nccCampaignId": campaign_id}) or []

def naver_keywords(api_key, secret_key, cid, adgroup_id):
    return _naver_get("/ncc/keywords", api_key, secret_key, cid,
                      params={"nccAdgroupId": adgroup_id}) or []

def _get_id(obj, *keys):
    """여러 키 이름 중 값이 있는 첫 번째 반환 (API 버전별 키 이름 차이 대응)"""
    for k in keys:
        v = obj.get(k)
        if v:
            return str(v)
    return ""

def naver_keyword_stats(api_key, secret_key, cid, keyword_ids: list) -> dict:
    """
    키워드 ID 목록의 전일 평균노출순위(avgRnk) 조회.
    반환: {nccKeywordId: avgRnk(float)}
    """
    if not keyword_ids:
        return {}
    results = {}
    from datetime import date, timedelta
    yesterday = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    # 50개씩 배치
    for i in range(0, len(keyword_ids), 50):
        batch = keyword_ids[i:i+50]
        try:
            rows = _naver_get(
                "/stats",
                api_key, secret_key, cid,
                params={
                    "id":        ",".join(batch),
                    "statType":  "AD_GROUP_KEYWORD",
                    "startDate": yesterday,
                    "endDate":   yesterday,
                    "timeUnit":  "DAY",
                    "fields":    "clkCnt,impCnt,avgRnk",
                }
            ) or []
            for item in rows:
                kid  = item.get("id", "")
                data_rows = item.get("data") or []
                for dr in data_rows:
                    rnk = dr.get("avgRnk")
                    if rnk and float(rnk) > 0:
                        results[kid] = float(rnk)
        except Exception:
            pass
    return results

def naver_refresh_group(api_key, secret_key, cid, group: dict) -> tuple[dict, list]:
    """
    광고그룹 ID 기반으로 그룹의 ncc_keyword_id / current_bid / current_rank 를
    실제 Naver API에서 최신화한다.
    반환: (updated_group, log_lines)
    """
    log = []
    ag_id = group.get("naver_adgroup_id", "")
    if not ag_id:
        log.append("  ⚠ naver_adgroup_id 없음 — 그룹 관리에서 네이버 불러오기로 재등록 필요")
        return group, log

    # 1. 키워드 목록 조회 (nccKeywordId + bidAmt)
    try:
        api_kws = naver_keywords(api_key, secret_key, cid, ag_id)
        log.append(f"  키워드 API 조회: {len(api_kws)}개")
    except Exception as e:
        log.append(f"  ❌ 키워드 조회 실패: {e}")
        return group, log

    # text → API 키워드 매핑
    api_kw_map = {
        (k.get("keyword") or k.get("keywordText","")): k
        for k in api_kws
    }

    # 2. 그룹 키워드에 ncc_keyword_id / current_bid 업데이트
    keyword_ids = []
    matched = 0
    for kw_obj in group.get("keywords", []):
        api_kw = api_kw_map.get(kw_obj["keyword"])
        if not api_kw:
            continue
        kid = _get_id(api_kw, "nccKeywordId", "keywordId", "id")
        if kid:
            kw_obj["ncc_keyword_id"] = kid
            keyword_ids.append(kid)
        raw_bid = api_kw.get("bidAmt", 0)
        try:
            bid_val = int(raw_bid)
        except (TypeError, ValueError):
            bid_val = 0
        # bidAmt가 70(최솟값=기본)이면 광고그룹 기본입찰가 사용
        if bid_val > 70:
            kw_obj["current_bid"] = bid_val
        elif not kw_obj.get("current_bid"):
            kw_obj["current_bid"] = bid_val or None
        matched += 1

    log.append(f"  키워드 매칭: {matched}/{len(group.get('keywords',[]))}개 | ID 확보: {len(keyword_ids)}개")

    # 3. 평균노출순위(avgRnk) 조회
    if keyword_ids:
        try:
            stats = naver_keyword_stats(api_key, secret_key, cid, keyword_ids)
            rank_cnt = 0
            for kw_obj in group.get("keywords", []):
                kid = kw_obj.get("ncc_keyword_id","")
                if kid and kid in stats:
                    kw_obj["current_rank"] = stats[kid]
                    rank_cnt += 1
            log.append(f"  평균노출순위 조회: {rank_cnt}개 (전일 기준)")
        except Exception as e:
            log.append(f"  ⚠ 순위 조회 실패: {e}")
    else:
        log.append("  ⚠ keyword_id 없어 순위 조회 불가")

    return group, log

def _naver_put(uri, api_key, secret_key, customer_id, body: dict, params: dict = None):
    """
    PUT 요청 + 상세 디버그 정보 반환.
    서명은 path만(uri), 실제 요청은 params(쿼리스트링) 별도 전달.
    Naver API: PUT /ncc/keywords/{id}?fields=bidAmt 형태 필요.
    """
    ts  = str(int(time.time() * 1000))
    sig = _naver_sig(secret_key, ts, "PUT", uri)   # 서명: path only
    headers = {
        "X-Timestamp": ts,
        "X-API-KEY":   api_key,
        "X-Customer":  str(customer_id),
        "X-Signature": sig,
        "Content-Type": "application/json; charset=UTF-8",
    }
    full_url = NAVER_API_BASE + uri
    r = requests.put(full_url, headers=headers, json=body, params=params, timeout=10)
    debug = {
        "url":           r.url,          # 실제 요청 URL (쿼리스트링 포함)
        "status_code":   r.status_code,
        "response_body": r.text[:800],
    }
    return r, debug

def naver_get_keyword(api_key, secret_key, cid, keyword_id):
    """
    단건 키워드 조회.
    /ncc/keywords?ids={id} 방식 사용 (단건 경로 /ncc/keywords/{id}는 fields 파라미터 필요).
    """
    try:
        result = _naver_get("/ncc/keywords", api_key, secret_key, cid,
                            params={"ids": keyword_id})
        if isinstance(result, list) and result:
            return result[0]
        if isinstance(result, dict):
            return result
    except Exception:
        pass
    return None

def naver_update_bid(api_key, secret_key, cid, keyword_id, bid_amt,
                     keyword_text="", adgroup_id="", verify=True):
    """
    네이버 API 키워드 입찰가 실제 업데이트.
    흐름:
      1) GET ?ids → 변경 전 bidAmt 확인
      2) PUT ?fields=bidAmt,useGroupBidAmt → 입찰가 변경
      3) verify=True 시 GET 재조회 → 실제 변경 검증
    반환: (put_response, debug_info)
    """
    # ── 1. 변경 전 GET ─────────────────────────────────────────────────
    current_kw = naver_get_keyword(api_key, secret_key, cid, keyword_id)
    before_bid = current_kw.get("bidAmt", "?") if current_kw else "GET실패"
    before_group_bid = current_kw.get("useGroupBidAmt") if current_kw else "?"

    # ── 2. PUT 바디 구성 ───────────────────────────────────────────────
    if current_kw:
        body = dict(current_kw)
    else:
        body = {
            "nccKeywordId": keyword_id,
            "keyword":      keyword_text,
            "nccAdgroupId": adgroup_id,
        }
    body["bidAmt"]         = bid_amt
    body["useGroupBidAmt"] = False

    uri     = f"/ncc/keywords/{keyword_id}"
    qparams = {"fields": "bidAmt,useGroupBidAmt"}
    r, debug = _naver_put(uri, api_key, secret_key, cid, body, params=qparams)

    if not r.ok:
        raise Exception(f"HTTP {r.status_code} | {r.text[:500]}")

    try:
        put_resp = r.json()
    except Exception:
        put_resp = {}

    # ── 3. 변경 후 GET 재조회 (검증) ──────────────────────────────────
    verified_bid       = None
    verified_group_bid = None
    verify_ok          = False
    if verify:
        time.sleep(0.5)   # 짧은 대기 후 재조회
        after_kw = naver_get_keyword(api_key, secret_key, cid, keyword_id)
        if after_kw:
            verified_bid       = after_kw.get("bidAmt")
            verified_group_bid = after_kw.get("useGroupBidAmt")
            verify_ok          = (verified_bid == bid_amt)

    debug.update({
        "keyword_id":          keyword_id,
        "before_bid":          before_bid,
        "before_useGroupBid":  before_group_bid,
        "requested_bid":       bid_amt,
        "after_bid_verified":  verified_bid,
        "after_useGroupBid":   verified_group_bid,
        "verify_ok":           verify_ok,
        "get_before_success":  current_kw is not None,
        "request_body":        {k: v for k, v in body.items()
                                if k not in ("nccSecretKey",)},
    })
    return put_resp, debug


def run_auto_bidding_once(groups: list, acct_map: dict, test_mode: bool = False) -> list:
    """
    등록된 모든 그룹의 키워드를 순회하며:
    1) API로 현재 입찰가·순위 최신화
    2) 추천입찰가 계산
    3) 변경 필요 시 실제 PUT 호출 + 재조회 검증 (test_mode=True 시 계산만)
    4) 키워드별 처리 결과 리스트 반환
    """
    entries = []
    now_str = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    for g in groups:
        acct = acct_map.get(g.get("ad_account_id",""))
        if not acct:
            # 계정 미연결 그룹 전체 기록
            for kw in g.get("keywords",[]):
                entries.append({
                    "time": now_str, "account": "-", "group": g["name"],
                    "keyword": kw["keyword"], "keyword_id": kw.get("ncc_keyword_id",""),
                    "current_rank": None, "target_rank": g["target_rank"],
                    "before_bid": kw.get("current_bid"), "recommended_bid": None,
                    "after_bid": None, "changed": False,
                    "status": "계정 미연결", "api_response": "",
                })
            continue

        ak, sk, ci = acct["api_key"], acct["secret_key"], acct["customer_id"]
        biz = acct["business_name"]

        # ── 1. 현재 입찰가·순위 API 조회 ──────────────────────────────
        updated_g, _ = naver_refresh_group(ak, sk, ci, g)

        # ── 2. 키워드별 처리 ──────────────────────────────────────────
        for kw_obj in updated_g.get("keywords", []):
            kw_name = kw_obj["keyword"]
            kid     = kw_obj.get("ncc_keyword_id","").strip()
            rank    = kw_obj.get("current_rank")
            bid     = kw_obj.get("current_bid")
            t_rank  = g["target_rank"]

            entry = {
                "time":            datetime.now().strftime("%H:%M:%S"),
                "account":         biz,
                "group":           g["name"],
                "keyword":         kw_name,
                "keyword_id":      kid,
                "current_rank":    rank,
                "target_rank":     t_rank,
                "before_bid":      bid,
                "recommended_bid": None,
                "after_bid":       None,
                "changed":         False,
                "status":          "데이터 부족",
                "api_response":    "",
            }

            # 데이터 없으면 건너뜀
            if rank is None or bid is None:
                entry["status"] = "데이터 부족 (순위/입찰가 없음)"
                entries.append(entry)
                continue

            # 추천입찰가 계산
            rec_bid, status = calc_bid(rank, t_rank, bid, g["bid_unit"],
                                       g["min_bid"], g["max_bid"])
            kw_obj["recommended_bid"] = rec_bid
            kw_obj["status"]          = status
            entry["recommended_bid"]  = rec_bid
            entry["status"]           = status

            # 변경 필요 없으면 로그만
            if rec_bid == bid or status in ("유지", "최대입찰 도달", "최소입찰 도달"):
                entries.append(entry)
                continue

            # keyword_id 없으면 변경 불가
            if not kid:
                entry["status"] = "API ID 없음 (조회 필요)"
                entries.append(entry)
                continue

            # ── 3. 테스트 모드: 계산만, API 전송 없음 ─────────────────
            if test_mode:
                entry["status"]    = f"[테스트] {status}"
                entry["after_bid"] = rec_bid
                entries.append(entry)
                continue

            # ── 4. 실제 API 입찰가 변경 + 재조회 검증 ────────────────
            try:
                _, dbg = naver_update_bid(
                    ak, sk, ci, kid, rec_bid,
                    keyword_text=kw_name,
                    adgroup_id=g.get("naver_adgroup_id",""),
                    verify=True,
                )
                after_verified = dbg.get("after_bid_verified")
                verify_ok      = dbg.get("verify_ok", False)
                kw_obj["current_bid"]     = after_verified or rec_bid
                kw_obj["recommended_bid"] = None
                kw_obj["last_checked"]    = now_str
                entry["after_bid"]    = after_verified
                entry["changed"]      = verify_ok
                entry["api_response"] = f"HTTP {dbg['status_code']}"
                entry["status"]       = "변경 성공" if verify_ok else "변경(검증불일치)"
            except Exception as e:
                entry["status"]       = "API 실패"
                entry["api_response"] = str(e)[:120]

            entries.append(entry)

    return entries


# ════════════════════════════════════════════════════════════════════════════
# UI
# ════════════════════════════════════════════════════════════════════════════
st.markdown("""
<style>
/* ── 페이지 헤더 ── */
.bid-page-header {
    padding: 20px 0 4px;
}
.bid-page-title {
    font-size: 24px;
    font-weight: 800;
    color: #111827;
    letter-spacing: -.5px;
    margin: 0 0 4px;
}
.bid-page-sub {
    font-size: 13px;
    color: #6B7280;
    margin: 0 0 20px;
}
/* ── 상태 배너 ── */
.bid-status-on {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 12px 18px;
    background: #EFF6FF;
    border: 1px solid #BFDBFE;
    border-left: 4px solid #0D47A1;
    border-radius: 8px;
    font-size: 14px;
    font-weight: 700;
    color: #1E3A8A;
}
.bid-status-off {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 12px 18px;
    background: #F9FAFB;
    border: 1px solid #E5E7EB;
    border-left: 4px solid #9CA3AF;
    border-radius: 8px;
    font-size: 14px;
    font-weight: 700;
    color: #6B7280;
}
.bid-status-time {
    font-size: 12px;
    font-weight: 400;
    color: #3B82F6;
    margin-left: 4px;
}
/* ── 사용법 안내 ── */
.bid-guide {
    background: #F8FAFC;
    border: 1px solid #E5E7EB;
    border-radius: 8px;
    padding: 10px 16px;
    font-size: 12px;
    color: #6B7280;
    margin: 12px 0 4px;
    line-height: 1.7;
}
.bid-guide b { color: #111827; }
/* ── 섹션 타이틀 ── */
.bid-section {
    font-size: 13px;
    font-weight: 700;
    color: #374151;
    border-left: 3px solid #0D47A1;
    padding-left: 10px;
    margin: 20px 0 10px;
}
/* ── 상태 범례 ── */
.bid-legend {
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
    font-size: 12px;
    color: #6B7280;
    margin: 8px 0 16px;
}
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="bid-page-title">📊 목표순위 자동입찰</div>', unsafe_allow_html=True)
st.markdown('<div class="bid-page-sub">목표순위 근접 유지를 위한 입찰가 자동 계산 · 전송 시스템</div>', unsafe_allow_html=True)

data   = load_data()
groups = data.get("groups", [])

tab1, tab2, tab3, tab4 = st.tabs(["입찰 현황", "그룹 관리", "키워드 관리", "계정 관리"])

# ════════════════════════════════════════════════════════════════════════════
# ════════════════════════════════════════════════════════════════════════════
# 탭1: 입찰 현황
# ════════════════════════════════════════════════════════════════════════════
with tab1:
    import pandas as pd

    ad_accounts = load_ad_accounts()
    acct_map    = {a["id"]: a for a in ad_accounts}

    # ── heartbeat 기준 상태 판단 ──────────────────────────────────────
    bid_state          = data.get("state", {})
    _alive, _diff, _hb = _sched_status()

    # 시작 직후 grace period (heartbeat 첫 기록 전 최대 3분)
    _grace = False
    if not _alive and bid_state.get("running"):
        try:
            _started = datetime.fromisoformat(bid_state.get("started_at", ""))
            _grace   = 0 < (datetime.now() - _started).total_seconds() < 180
        except Exception:
            pass

    is_running = _alive or _grace

    # heartbeat 경과 표시 문자열
    if _diff is None:
        _hb_str = " | ⚪ heartbeat 없음"
    elif _diff < 60:
        _hb_str = f" | 🟢 {int(_diff)}초 전 확인"
    elif _diff < 120:
        _hb_str = f" | 🟡 {int(_diff)}초 전 확인"
    else:
        _hb_str = f" | 🔴 미실행 ({int(_diff/60)}분 전)"

    # 표시용 값 (heartbeat > state 우선)
    _last_run  = (_hb or {}).get("last_run",  bid_state.get("last_run",  ""))
    _next_run  = (_hb or {}).get("next_run",  bid_state.get("next_run",  ""))
    _cycle_cnt = (_hb or {}).get("cycle",     bid_state.get("cycle_count", 0))
    _interval  = bid_state.get("interval_min", DEFAULT_INTERVAL_MIN)

    if is_running:
        _label = "시작 중... (초기화 대기)" if _grace else "자동입찰 실행중 (스케줄러)"
        st.markdown(
            f"<div style='padding:12px 18px;background:#EFF6FF;border-left:4px solid #0D47A1;"
            f"border-radius:8px;font-weight:700;color:#1E3A8A;'>"
            f"● {_label}"
            f"<span style='font-weight:400;font-size:12px;'>"
            f" &nbsp; 마지막: {_last_run} | 다음: {_next_run} | "
            f"사이클: {_cycle_cnt}회 | 주기: {_interval}분{_hb_str}"
            f"</span></div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f"<div style='padding:12px 18px;background:#F9FAFB;border-left:4px solid #9CA3AF;"
            f"border-radius:8px;font-weight:700;color:#6B7280;'>"
            f"● 자동입찰 중지됨"
            f"<span style='font-weight:400;font-size:12px;color:#9CA3AF;'>{_hb_str}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )
    st.caption(
        "자동입찰은 run_scheduler.bat(로컬 실행)이 실제 반복 처리합니다. "
        "Streamlit 화면은 상태 조회 · 제어만 담당합니다."
    )

    # ── 등록 그룹 요약 ────────────────────────────────────────────────────
    if not groups:
        st.info("등록된 그룹이 없습니다. [그룹 관리] 탭에서 그룹을 추가하세요.")
    else:
        # ── 자동입찰 대상 그룹 — 개별 ON/OFF 선택 ──────────────────────
        st.markdown("**자동입찰 대상 그룹** <span style='font-size:12px;color:#64748B;'>— 토글로 포함 여부 선택</span>", unsafe_allow_html=True)
        _gcols = st.columns(len(groups)) if len(groups) <= 4 else st.columns(4)
        _grp_changed = False
        for _gi, _g in enumerate(groups):
            _kws     = _g.get("keywords", [])
            _on_kws  = sum(1 for _k in _kws if _k.get("enabled", True))
            _total   = len(_kws)
            _intv    = _g.get("check_interval", 15)
            _trank   = _g.get("target_rank", "-")
            _minb    = _g.get("min_bid", 0)
            _maxb    = _g.get("max_bid", 0)
            _bid_on  = _g.get("bidding_enabled", True)
            _border  = "#6366F1" if _bid_on else "#E2E8F0"
            _bg      = "#F5F3FF" if _bid_on else "#F8FAFC"
            with _gcols[_gi % 4]:
                st.markdown(
                    f"<div style='border:2px solid {_border};border-radius:8px;"
                    f"padding:10px 14px;background:{_bg};font-size:13px;'>"
                    f"<div style='font-weight:700;color:#1E293B;margin-bottom:4px;'>{_g['name']}</div>"
                    f"<div style='color:#475569;'>목표순위 <b>{_trank}위</b></div>"
                    f"<div style='color:#475569;'>입찰 {_minb:,}~{_maxb:,}원</div>"
                    f"<div style='color:#475569;'>키워드 <b>{_on_kws}/{_total}개</b> ON</div>"
                    f"<div style='color:#64748B;font-size:12px;margin-top:2px;'>⏱ {_intv}분 주기</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
                _new_val = st.toggle(
                    "자동입찰 포함",
                    value=_bid_on,
                    key=f"bid_grp_toggle_{_g['id']}",
                )
                if _new_val != _bid_on:
                    _g["bidding_enabled"] = _new_val
                    _grp_changed = True
        if _grp_changed:
            save_data(data)
            st.rerun()
        st.markdown("<div style='margin-top:4px'></div>", unsafe_allow_html=True)

        # ── 제어 버튼 4개 ───────────────────────────────────────────────
        b1, b2, b3, b4 = st.columns(4)
        with b1:
            if st.button("▶ 자동입찰 시작", use_container_width=True,
                         disabled=is_running):
                _existing_pid = _find_scheduler_pid()
                _now_ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
                if _existing_pid:
                    # 이미 실행 중인 스케줄러에 running=True 신호만 전달
                    data["state"] = {
                        **bid_state,
                        "running":      True,
                        "started_at":   _now_ts,
                        "activated_at": _now_ts,   # 8시간 만료 기준
                    }
                    save_data(data)
                    st.success("✅ 자동입찰이 활성화됐습니다. (스케줄러 실행 중)")
                else:
                    # 스케줄러가 없으면 새로 시작
                    from pathlib import Path as _PL2
                    _pr2 = _PL2(__file__).resolve().parents[1]
                    _bp2 = _pr2 / "run_scheduler.bat"
                    if not _bp2.exists():
                        st.error(f"BAT 파일 없음: {_bp2}")
                    else:
                        try:
                            _cmd2 = f'start "마케팁 자동입찰" cmd.exe /k "{_bp2}"'
                            _proc2 = subprocess.Popen(_cmd2, shell=True, cwd=str(_pr2))
                            data["state"] = {
                                **bid_state,
                                "running":       True,
                                "started_at":    _now_ts,
                                "activated_at":  _now_ts,   # 8시간 만료 기준
                                "scheduler_pid": _proc2.pid,
                            }
                            save_data(data)
                            st.success("✅ 자동입찰 스케줄러가 시작됐습니다.")
                        except Exception as _e2:
                            st.error("[자동입찰] CMD 실행 실패")
                            st.exception(_e2)
        with b2:
            if st.button("⏹ 자동입찰 중지", use_container_width=True,
                         disabled=not is_running):
                _kill_scheduler(stored_pid=bid_state.get("scheduler_pid"))
                data["state"] = {**bid_state, "running": False, "scheduler_pid": None}
                save_data(data)
                st.rerun()
        with b3:
            if st.button("⚡ 지금 한 바퀴 실행", use_container_width=True):
                data["state"] = {**bid_state, "trigger_now": True}
                save_data(data)
                st.info("트리거 전송 — 스케줄러가 실행 중이면 수 초 내 처리됩니다.")
                st.rerun()
        with b4:
            if st.button("🔄 이력 새로고침", use_container_width=True):
                st.rerun()

        st.divider()

        # ── 수동 실행 (그룹 선택) ──────────────────────────────────────
        group_names = [g["name"] for g in groups]
        _col_sel, _col_tm = st.columns([3, 1])
        with _col_sel:
            sel_group = st.selectbox("수동 실행 그룹 선택",
                                     ["전체 그룹"] + group_names, key="rolling_group_sel")
        with _col_tm:
            _test_mode = st.checkbox("🧪 테스트 모드", value=False, key="bid_test_mode",
                                     help="체크 시 입찰가 계산만 하고 실제 API 전송 없음")
        run_groups  = (groups if sel_group == "전체 그룹"
                       else [g for g in groups if g["name"] == sel_group])

        def _run_and_save(entries_: list, mode_label: str):
            data["groups"] = groups
            save_data(data)
            chg_ = sum(1 for e in entries_ if e.get("changed"))
            logs_cur = load_log()
            logs_cur.append({
                "run_time": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
                "mode":     mode_label,
                "summary": {
                    "total":   len(entries_),
                    "changed": chg_,
                    "kept":    sum(1 for e in entries_ if "목표도달" in e.get("status", "")),
                    "no_data": sum(1 for e in entries_ if e.get("status") in
                                   ("데이터없음", "ID없음", "입찰가없음")),
                    "failed":  sum(1 for e in entries_ if e.get("status") == "API실패"),
                },
                "entries": entries_,
            })
            save_log(logs_cur)
            with st.expander(f"📋 실행 로그 ({len(entries_)}개 키워드)", expanded=True):
                for e in entries_:
                    bid_str = (
                        f"{e.get('before_bid','?')}원 → **{e.get('after_bid','?')}원**"
                        if e.get("changed") else
                        f"{e.get('before_bid','?')}원 (변경없음)"
                    )
                    rank_str = (f"{e['current_rank']:.1f}위"
                                if e.get("current_rank") else "순위없음")
                    st.markdown(
                        f"- `{e.get('time','')}` **{e['keyword']}** | "
                        f"`{(e.get('keyword_id') or '')[:18]}` | "
                        f"{rank_str} | {bid_str} | "
                        f"**{e.get('status','')}** {e.get('api_response','')}"
                    )
            if chg_:
                st.success(f"✅ 완료 — 변경 {chg_}개")
            else:
                st.info(f"완료 — 변경 없음 | 처리 {len(entries_)}개")

        ma, mb, mc = st.columns(3)
        with ma:
            if st.button("🧩 첫 키워드 +100원 테스트", use_container_width=True):
                first_g  = run_groups[0] if run_groups else None
                first_kw = (first_g.get("keywords", []) or [None])[0] if first_g else None
                acct     = acct_map.get(first_g.get("ad_account_id", "")) if first_g else None
                if not first_kw:
                    st.error("키워드 없음")
                elif not acct:
                    st.error("광고계정 미연결")
                elif not (first_kw.get("ncc_keyword_id") or "").strip():
                    st.error(f"ncc_keyword_id 없음: {first_kw['keyword']}")
                else:
                    kid = first_kw["ncc_keyword_id"].strip()
                    cur = first_kw.get("current_bid") or 1000
                    tb  = min(cur + 100, first_g["max_bid"])
                    with st.spinner(f"{first_kw['keyword']} 변경 중..."):
                        _, dbg = naver_update_bid(
                            acct["api_key"], acct["secret_key"], acct["customer_id"],
                            kid, tb, keyword_text=first_kw["keyword"],
                            adgroup_id=first_g.get("naver_adgroup_id", ""), verify=True,
                        )
                    v = dbg.get("after_bid_verified")
                    if dbg.get("verify_ok"):
                        st.success(f"✅ {dbg['before_bid']} → {v}원 | HTTP {dbg['status_code']}")
                        first_kw["current_bid"] = v
                        save_data(data)
                    else:
                        st.warning(f"HTTP {dbg['status_code']} | 재조회:{v}원")

        with mb:
            if st.button("⚡ 수동 롤링 (+bid_unit)", use_container_width=True):
                now_str  = datetime.now().strftime("%H:%M:%S")
                entries_ = []
                for g in run_groups:
                    acct = acct_map.get(g.get("ad_account_id", ""))
                    for kw_obj in g.get("keywords", []):
                        kid = (kw_obj.get("ncc_keyword_id") or "").strip()
                        cur = kw_obj.get("current_bid") or 0
                        e   = {
                            "time": now_str, "group": g["name"],
                            "keyword": kw_obj["keyword"], "keyword_id": kid,
                            "current_rank": kw_obj.get("current_rank"),
                            "target_rank":  g["target_rank"],
                            "before_bid": cur, "after_bid": None,
                            "changed": False, "status": "", "api_response": "",
                        }
                        if not acct:
                            e["status"] = "계정미연결"; entries_.append(e); continue
                        if not kid:
                            e["status"] = "ID없음";    entries_.append(e); continue
                        if cur == 0:
                            e["status"] = "입찰가없음"; entries_.append(e); continue
                        if cur >= g["max_bid"]:
                            e["status"] = "최대입찰 도달"; entries_.append(e); continue
                        new_bid = min(cur + g["bid_unit"], g["max_bid"])
                        if _test_mode:
                            e["status"]    = "[테스트] 롤링 시뮬레이션"
                            e["after_bid"] = new_bid
                            entries_.append(e)
                            continue
                        try:
                            _, dbg = naver_update_bid(
                                acct["api_key"], acct["secret_key"], acct["customer_id"],
                                kid, new_bid, keyword_text=kw_obj["keyword"],
                                adgroup_id=g.get("naver_adgroup_id", ""), verify=True,
                            )
                            v  = dbg.get("after_bid_verified")
                            ok = dbg.get("verify_ok", False)
                            kw_obj["current_bid"]  = v or new_bid
                            kw_obj["last_checked"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
                            e["after_bid"] = v; e["changed"] = ok
                            e["status"] = "변경성공" if ok else "검증불일치"
                            e["api_response"] = f"HTTP {dbg['status_code']}"
                        except Exception as ex:
                            e["status"] = "API실패"; e["api_response"] = str(ex)[:60]
                        entries_.append(e)
                _run_and_save(entries_, "수동롤링" if not _test_mode else "수동롤링(테스트)")
                st.rerun()

        with mc:
            if st.button("🔄 순위기반 1회 실행", use_container_width=True):
                with st.spinner("순위 조회 → 계산 → 변경..."):
                    entries_ = run_auto_bidding_once(run_groups, acct_map, test_mode=_test_mode)
                _run_and_save(entries_, "순위기반" if not _test_mode else "순위기반(테스트)")
                st.rerun()

        # ── 실제 입찰가 변경 API 검증 ───────────────────────────────────────
        with st.expander("🔬 실제 입찰가 +100원 변경 테스트 (API 전문 출력)", expanded=False):
            st.warning("⚠️ 실제 네이버 광고 입찰가가 변경됩니다. 테스트 목적으로만 사용하세요.")
            st.caption("순위/광고ON여부와 무관하게 네이버 API를 직접 호출합니다. 테스트모드 체크박스 무시.")

            _t_groups_with_acct = [g for g in groups if acct_map.get(g.get("ad_account_id",""))]
            if not _t_groups_with_acct:
                st.error("광고계정이 연결된 그룹이 없습니다.")
            else:
                _t_g_names = [g["name"] for g in _t_groups_with_acct]
                _t_sel_name = st.selectbox("그룹 선택", _t_g_names, key="force_test_group")
                _t_g    = next(g for g in _t_groups_with_acct if g["name"] == _t_sel_name)
                _t_acct = acct_map[_t_g["ad_account_id"]]
                _t_ak   = _t_acct["api_key"]
                _t_sk   = _t_acct["secret_key"]
                _t_ci   = _t_acct["customer_id"]
                _t_ag_id = _t_g.get("naver_adgroup_id", "")

                st.info(f"customer_id: `{_t_ci}` | adgroup_id: `{_t_ag_id}` | 그룹: {_t_g['name']}")

                if st.button("🚨 실제 입찰가 +100원 변경 테스트", type="primary",
                             use_container_width=True, key="force_test_btn"):
                    _flog = []   # 누적 로그

                    def _flog_write(msg):
                        _flog.append(msg)
                        st.write(msg)

                    st.markdown("---")
                    _flog_write(f"[FORCE_BID_TEST] start — {datetime.now().strftime('%H:%M:%S')}")
                    _flog_write(f"[FORCE_BID_TEST] customer_id  = {_t_ci}")
                    _flog_write(f"[FORCE_BID_TEST] adgroup_id   = {_t_ag_id}")

                    # ── STEP 1: 키워드 목록 GET ──────────────────────────
                    st.markdown("#### STEP 1 — 키워드 목록 GET")
                    if not _t_ag_id:
                        st.error("[FORCE_BID_TEST] FAIL: naver_adgroup_id 없음 → [그룹 관리] 탭에서 네이버 불러오기로 그룹 재등록 필요")
                        st.stop()

                    try:
                        _t_api_kws = naver_keywords(_t_ak, _t_sk, _t_ci, _t_ag_id)
                        _flog_write(f"[FORCE_BID_TEST] keyword_list_count = {len(_t_api_kws)}")
                    except Exception as _e:
                        st.error(f"[FORCE_BID_TEST] FAIL: GET 실패 = {repr(_e)}")
                        st.stop()

                    if not _t_api_kws:
                        st.error("[FORCE_BID_TEST] FAIL: 키워드 0개")
                        st.stop()

                    # ── STEP 2: 첫 키워드 선택 ───────────────────────────
                    st.markdown("#### STEP 2 — 변경 대상 키워드 (1개)")
                    _t_kw      = _t_api_kws[0]
                    _t_kid     = _get_id(_t_kw, "nccKeywordId", "keywordId", "id")
                    _t_kw_text = _t_kw.get("keyword") or _t_kw.get("keywordText", "")
                    _t_raw_bid = _t_kw.get("bidAmt", 0)
                    try:
                        _t_cur_bid = int(_t_raw_bid) if int(_t_raw_bid) > 70 else int(_t_g.get("min_bid", 1000))
                    except (TypeError, ValueError):
                        _t_cur_bid = int(_t_g.get("min_bid", 1000))
                    _t_new_bid = _t_cur_bid + 100

                    _flog_write(f"[FORCE_BID_TEST] keyword       = {_t_kw_text}")
                    _flog_write(f"[FORCE_BID_TEST] keyword_id    = {_t_kid}")
                    _flog_write(f"[FORCE_BID_TEST] current_bidAmt= {_t_cur_bid}")
                    _flog_write(f"[FORCE_BID_TEST] new_bidAmt    = {_t_new_bid}")
                    _flog_write(f"[FORCE_BID_TEST] request method = PUT")
                    _flog_write(f"[FORCE_BID_TEST] request url   = {NAVER_API_BASE}/ncc/keywords/{_t_kid}?fields=bidAmt,useGroupBidAmt")

                    if not _t_kid:
                        st.error("[FORCE_BID_TEST] FAIL: nccKeywordId 추출 실패")
                        st.json(_t_kw)
                        st.stop()

                    # ── STEP 3: 변경 전 단건 GET ─────────────────────────
                    st.markdown("#### STEP 3 — 변경 전 단건 GET")
                    _t_before_kw = naver_get_keyword(_t_ak, _t_sk, _t_ci, _t_kid)
                    if _t_before_kw:
                        _flog_write(f"[FORCE_BID_TEST] before GET bidAmt       = {_t_before_kw.get('bidAmt')}")
                        _flog_write(f"[FORCE_BID_TEST] before GET useGroupBidAmt= {_t_before_kw.get('useGroupBidAmt')}")
                    else:
                        st.warning("[FORCE_BID_TEST] 단건 GET 실패 — 그래도 PUT 시도")

                    # ── STEP 4: PUT 바디 구성 ─────────────────────────────
                    st.markdown("#### STEP 4 — PUT request payload")
                    if _t_before_kw:
                        _t_body = dict(_t_before_kw)
                    else:
                        _t_body = {"nccKeywordId": _t_kid, "keyword": _t_kw_text, "nccAdgroupId": _t_ag_id}
                    _t_body["bidAmt"]         = _t_new_bid
                    _t_body["useGroupBidAmt"] = False
                    _safe_body = {k: v for k, v in _t_body.items() if k not in ("nccSecretKey",)}
                    _flog_write(f"[FORCE_BID_TEST] request payload (key fields) = bidAmt={_t_new_bid} useGroupBidAmt=False")
                    st.json(_safe_body)

                    # ── STEP 5: 실제 PUT 호출 ─────────────────────────────
                    st.markdown("#### STEP 5 — PUT 실행 (실제 API 호출)")
                    _t_uri = f"/ncc/keywords/{_t_kid}"
                    try:
                        _t_r, _ = _naver_put(
                            _t_uri, _t_ak, _t_sk, _t_ci, _t_body,
                            params={"fields": "bidAmt,useGroupBidAmt"}
                        )
                        _flog_write(f"[FORCE_BID_TEST] response status = {_t_r.status_code}")
                        _flog_write(f"[FORCE_BID_TEST] request url (actual) = {_t_r.url}")
                        st.markdown("**[FORCE_BID_TEST] response raw:**")
                        st.code(_t_r.text, language="json")
                    except Exception as _e:
                        st.error(f"[FORCE_BID_TEST] FAIL: PUT 호출 실패 = {repr(_e)}")
                        st.stop()

                    if not _t_r.ok:
                        _flog_write(f"[FORCE_BID_TEST] success = False (HTTP {_t_r.status_code})")
                        st.error(f"[FORCE_BID_TEST] FAIL: HTTP {_t_r.status_code}")
                        st.stop()

                    # ── STEP 6: 변경 후 재조회 ────────────────────────────
                    st.markdown("#### STEP 6 — 변경 후 GET 재조회")
                    time.sleep(1)
                    _t_after_kw = naver_get_keyword(_t_ak, _t_sk, _t_ci, _t_kid)
                    if _t_after_kw:
                        _t_verified = _t_after_kw.get("bidAmt")
                        _t_grp_bid  = _t_after_kw.get("useGroupBidAmt")
                        _flog_write(f"[FORCE_BID_TEST] verified_bidAmt     = {_t_verified}")
                        _flog_write(f"[FORCE_BID_TEST] verified_useGroupBid = {_t_grp_bid}")
                        _ok = (_t_verified == _t_new_bid)
                        _flog_write(f"[FORCE_BID_TEST] success = {_ok}")
                        if _ok:
                            st.success(f"✅ [FORCE_BID_TEST] 변경 성공: {_t_cur_bid}원 → {_t_verified}원")
                            for _kw_obj in _t_g.get("keywords", []):
                                if _kw_obj["keyword"] == _t_kw_text:
                                    _kw_obj["current_bid"]    = _t_verified
                                    _kw_obj["ncc_keyword_id"] = _t_kid
                                    _kw_obj["last_checked"]   = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
                            save_data(data)
                            st.info("[FORCE_BID_TEST] DB 저장 완료")
                        elif _t_grp_bid:
                            st.warning("[FORCE_BID_TEST] useGroupBidAmt=True — 키워드가 광고그룹 기본입찰가 사용 중. 네이버 광고관리자에서 '개별입찰'로 변경 필요.")
                        else:
                            st.warning(f"[FORCE_BID_TEST] PUT 200이나 bidAmt 불일치: 요청={_t_new_bid} / 재조회={_t_verified}")
                    else:
                        _flog_write("[FORCE_BID_TEST] verified_bidAmt = GET실패")
                        st.warning("[FORCE_BID_TEST] 재조회 GET 실패 — PUT 성공 여부 불명확")

                    st.markdown("#### 전체 로그 요약")
                    st.code("\n".join(_flog))

        st.divider()

        # ── 키워드 입찰 현황 요약 메트릭 ───────────────────────────────
        _total_kw = _at_target = _bidding = _at_max_no_imp = _no_bid = 0
        for g in groups:
            for kw in g.get("keywords", []):
                _total_kw += 1
                r = kw.get("current_rank")
                b = kw.get("current_bid")
                if not b:
                    _no_bid += 1
                elif r is None:
                    if b >= g["max_bid"]:
                        _at_max_no_imp += 1   # 최대입찰까지 올렸지만 노출 없음
                    else:
                        _bidding += 1         # 노출 위해 입찰가 올리는 중
                elif abs(r - g["target_rank"]) <= 0.5:
                    _at_target += 1           # 목표순위 도달
                else:
                    _bidding += 1             # 순위 조정 중
        _mc1, _mc2, _mc3, _mc4, _mc5 = st.columns(5)
        _mc1.metric("전체 키워드",    f"{_total_kw}개")
        _mc2.metric("🟢 목표달성",    f"{_at_target}개", help="목표순위 ±0.5 이내")
        _mc3.metric("🔴 입찰중",      f"{_bidding}개",   help="순위 조정 또는 노출 확보 위해 입찰가 변경 중")
        _mc4.metric("🟠 최대도달",    f"{_at_max_no_imp}개", help=f"최대입찰가 도달했으나 노출 없음 — 세팅값 재검토 필요")
        _mc5.metric("⚪ 입찰가없음",  f"{_no_bid}개",    help="current_bid 미설정 — 키워드 관리 탭에서 불러오기 필요")

        st.divider()

        # ── 키워드 현황 테이블 ──────────────────────────────────────────
        rows = []
        for g in groups:
            for kw in g.get("keywords", []):
                s = kw.get("status", "데이터없음")
                _rank = kw.get("current_rank")
                _tgt  = g["target_rank"]
                _delta = round(_rank - _tgt, 1) if _rank is not None else None
                rows.append({
                    "그룹명":      g["name"],
                    "키워드":      kw["keyword"],
                    "현재순위":    _rank,
                    "목표순위":    _tgt,
                    "순위차":      _delta,   # +: 목표보다 낮음(증액필요), -: 목표보다 높음(감액가능)
                    "현재입찰가":  kw.get("current_bid"),
                    "상태":        STATUS_ICON.get(s, "⚪") + " " + s,
                    "마지막 실행": kw.get("last_checked", "") or "",
                })
        st.dataframe(
            pd.DataFrame(rows), use_container_width=True, hide_index=True,
            column_config={
                "현재순위":   st.column_config.NumberColumn(format="%.1f위"),
                "목표순위":   st.column_config.NumberColumn(format="%d위"),
                "순위차":     st.column_config.NumberColumn(
                    format="%.1f",
                    help="양수: 목표보다 낮은 순위(증액필요) / 음수: 목표보다 높은 순위(감액가능)"
                ),
                "현재입찰가": st.column_config.NumberColumn(format="%d원"),
            },
        )
        st.caption("🔴 증액중(노출없음 포함)  🔵 감액중  🟢 목표도달  ⚪ 데이터없음  🟠 최대입찰  🟡 최소입찰")

        st.divider()

        # ── 실행 이력 차트 ──────────────────────────────────────────────
        _log_h1, _log_h2 = st.columns([5, 1])
        _log_h1.markdown("##### 실행 이력")
        if _log_h2.button("🗑️ 이력 삭제", key="clear_log", use_container_width=True):
            save_log([])
            st.rerun()
        logs_all = load_log()
        if not logs_all:
            st.caption("아직 실행 이력이 없습니다.")
        else:
            # 최근 15회 차트 (altair — 레이블 가로 유지)
            _chart_data = []
            for i, run in enumerate(logs_all[-15:]):
                s = run.get("summary", {})
                _t = run.get("run_time", "")
                _label = _t[5:16].replace("T", " ") if len(_t) >= 16 else str(i+1)
                _chart_data.append({"회차": _label, "항목": "변경", "수": s.get("changed", 0)})
                _chart_data.append({"회차": _label, "항목": "유지",  "수": s.get("kept", 0)})
            if _chart_data:
                try:
                    import altair as alt
                    import pandas as _pd_chart
                    _df_c = _pd_chart.DataFrame(_chart_data)
                    _ch = (
                        alt.Chart(_df_c)
                        .mark_bar()
                        .encode(
                            x=alt.X("회차:N", sort=None, axis=alt.Axis(labelAngle=0, labelFontSize=10)),
                            y=alt.Y("수:Q"),
                            color=alt.Color("항목:N", scale=alt.Scale(
                                domain=["변경", "유지"], range=["#3B82F6", "#93C5FD"]
                            )),
                            xOffset="항목:N",
                            tooltip=["회차", "항목", "수"],
                        )
                        .properties(height=180)
                    )
                    st.altair_chart(_ch, use_container_width=True)
                except Exception:
                    pass

            for run in reversed(logs_all[-15:]):
                s   = run.get("summary", {})
                cyc = run.get("cycle", "")
                lbl = (
                    f"🕒 {run['run_time']} [{run.get('mode','')}] — "
                    f"변경 {s.get('changed',0)} · 유지 {s.get('kept',0)} · "
                    f"데이터없음 {s.get('no_data',0)} · 실패 {s.get('failed',0)}"
                    + (f" | 사이클#{cyc}" if cyc else "")
                )
                with st.expander(lbl, expanded=False):
                    hist = [{
                        "시간":      e.get("time", ""),
                        "그룹":      e.get("group", ""),
                        "키워드":    e.get("keyword", ""),
                        "현재순위":  e.get("current_rank"),
                        "목표순위":  e.get("target_rank"),
                        "변경전(원)": e.get("before_bid"),
                        "변경후(원)": e.get("after_bid"),
                        "상태":      e.get("status", ""),
                    } for e in run.get("entries", [])]
                    if hist:
                        st.dataframe(pd.DataFrame(hist),
                                     use_container_width=True, hide_index=True)


# 탭2: 그룹 관리
# ════════════════════════════════════════════════════════════════════════════
with tab2:

    # ── 기존 그룹 목록 ──────────────────────────────────────────────────────
    if groups:
        st.subheader("등록된 그룹")
        for g in groups:
            kw_count = len(g.get("keywords", []))
            with st.expander(
                f"**{g['name']}** — 목표순위 {g['target_rank']}위 / "
                f"키워드 {kw_count}개 / 입찰 {g['min_bid']:,}~{g['max_bid']:,}원",
                expanded=False,
            ):
                with st.form(f"edit_g_{g['id']}"):
                    c1, c2 = st.columns(2)
                    with c1:
                        g_name   = st.text_input("그룹명",        value=g["name"])
                        g_rank   = st.number_input("목표순위",     value=g["target_rank"],    min_value=1, max_value=15)
                        g_min    = st.number_input("최소입찰가",   value=g["min_bid"],        min_value=10, step=10)
                        g_max    = st.number_input("최대입찰가",   value=g["max_bid"],        min_value=10, step=10)
                    with c2:
                        g_unit   = st.number_input("증감단위(원)", value=g["bid_unit"],       min_value=10, step=10)
                        g_intvl  = st.number_input("체크주기(분)", value=g["check_interval"], min_value=1)
                    g_domain = st.text_input(
                        "검색 도메인 (순위 자동조회용)",
                        value=g.get("check_domain",""),
                        placeholder="예: www.example.com",
                        help="run_rank_checker.bat 실행 시 이 도메인의 광고 순위를 자동 조회합니다.",
                    )

                    cs, cd = st.columns(2)
                    with cs:
                        if st.form_submit_button("수정 저장", use_container_width=True):
                            if not g_name.strip():
                                st.error("그룹명 필수")
                            elif g_min >= g_max:
                                st.error("최소입찰가 < 최대입찰가")
                            else:
                                g.update({
                                    "name": g_name.strip(), "target_rank": int(g_rank),
                                    "min_bid": int(g_min), "max_bid": int(g_max),
                                    "bid_unit": int(g_unit), "check_interval": int(g_intvl),
                                    "check_domain": g_domain.strip(),
                                })
                                save_data(data)
                                st.success("수정 완료")
                                st.rerun()
                    with cd:
                        if st.form_submit_button("삭제", use_container_width=True):
                            data["groups"] = [x for x in groups if x["id"] != g["id"]]
                            save_data(data)
                            st.rerun()

        st.divider()

    # ── 새 그룹 추가 ──────────────────────────────────────────────────────
    if len(groups) >= MAX_GROUPS:
        st.warning(f"그룹은 최대 {MAX_GROUPS}개까지 등록 가능합니다.")
    else:
        st.subheader("새 그룹 추가")

        # ── 네이버 광고그룹 불러오기 ─────────────────────────────────────
        ad_accounts = load_ad_accounts()
        acct_names  = [a["business_name"] for a in ad_accounts]

        # ── 저장된 광고계정 선택 ───────────────────────────────────
        if acct_names:
            sel_acct_name = st.selectbox(
                "저장된 광고계정 선택", acct_names, key="n_acct_sel"
            )
            sel_acct = next(
                (a for a in ad_accounts if a["business_name"] == sel_acct_name), None
            )
        else:
            st.info("저장된 광고계정이 없습니다. 아래에서 신규 계정을 등록해주세요.")
            sel_acct = None

        # 계정 변경 시 캠페인/그룹/키워드 초기화
        _acct_id = sel_acct.get("id","") if sel_acct else ""
        if st.session_state.get("_n_acct_id") != _acct_id:
            for _k in ("n_camps","n_ags","n_ags_camp_id","n_kws","n_kws_ag_id"):
                st.session_state.pop(_k, None)
            st.session_state["_n_acct_id"] = _acct_id

        if sel_acct:
            api_key    = sel_acct["api_key"]
            secret_key = sel_acct["secret_key"]
            cid        = sel_acct["customer_id"]

            st.divider()

            # ── 캠페인 ────────────────────────────────────────────────
            if st.button("📥 캠페인 목록 불러오기", key="load_camps"):
                with st.spinner("캠페인 조회 중..."):
                    try:
                        st.session_state["n_camps"] = naver_campaigns(api_key, secret_key, cid)
                        for _k in ("n_ags","n_ags_camp_id","n_kws","n_kws_ag_id"):
                            st.session_state.pop(_k, None)
                    except Exception as e:
                        st.error(f"API 오류: {e}")

            camps = st.session_state.get("n_camps", [])
            if camps:
                camp_map = {f"{c.get('name','(이름없음)')}": c for c in camps}
                sel_camp = camp_map[
                    st.selectbox("캠페인 선택", list(camp_map.keys()), key="n_sel_camp")
                ]
                camp_id = _get_id(sel_camp, "nccCampaignId", "campaignId", "id")

                # 광고그룹 — 캠페인 변경 시 자동 로드
                if camp_id and st.session_state.get("n_ags_camp_id") != camp_id:
                    with st.spinner("광고그룹 조회 중..."):
                        try:
                            st.session_state["n_ags"] = naver_adgroups(
                                api_key, secret_key, cid, camp_id
                            )
                            st.session_state["n_ags_camp_id"] = camp_id
                            st.session_state.pop("n_kws", None)
                            st.session_state.pop("n_kws_ag_id", None)
                        except Exception as e:
                            st.error(f"API 오류: {e}")

                ags = st.session_state.get("n_ags", [])
                if ags:
                    ag_map = {f"{a.get('name','(이름없음)')}": a for a in ags}
                    sel_ag  = ag_map[
                        st.selectbox("광고그룹 선택", list(ag_map.keys()), key="n_sel_ag")
                    ]
                    ag_id = _get_id(sel_ag, "nccAdgroupId", "adgroupId", "adGroupId", "id")

                    if not ag_id:
                        st.warning(f"광고그룹 ID를 찾을 수 없습니다. 키: {list(sel_ag.keys())}")
                    else:
                        # 키워드 — 광고그룹 변경 시 자동 로드
                        if st.session_state.get("n_kws_ag_id") != ag_id:
                            with st.spinner("키워드 조회 중..."):
                                try:
                                    st.session_state["n_kws"] = naver_keywords(
                                        api_key, secret_key, cid, ag_id
                                    )
                                    st.session_state["n_kws_ag_id"] = ag_id
                                except Exception as e:
                                    st.error(f"API 오류: {e}")

                        n_kws = st.session_state.get("n_kws", [])
                        if not n_kws:
                            st.info("키워드가 없는 광고그룹입니다.")
                        else:
                            # 광고그룹 기본 입찰가 (키워드 "기본" 설정 시 fallback)
                            ag_default_bid = sel_ag.get("bidAmt") or 0

                            def _resolve_bid(k):
                                raw = k.get("bidAmt") or k.get("bid") or 0
                                try:
                                    raw = int(raw)
                                except (TypeError, ValueError):
                                    raw = 0
                                return ag_default_bid if raw <= 70 and ag_default_bid > 70 else raw or None

                            # 불러온 키워드 미리보기
                            kw_texts = []
                            for k in n_kws:
                                t = k.get("keyword") or k.get("keywordText") or k.get("text","")
                                if t:
                                    kw_texts.append(t)

                            _KW_STATUS = {
                                "ELIGIBLE":   "노출가능",
                                "PAUSED":     "일시중지",
                                "SUSPENDED":  "중지",
                                "UNAPPROVED": "미승인",
                                "DELETED":    "삭제됨",
                            }

                            st.markdown(f"**불러온 키워드 {len(kw_texts)}개**")
                            import pandas as pd
                            preview = pd.DataFrame([{
                                "키워드":    k.get("keyword") or k.get("keywordText",""),
                                "현재입찰가": _resolve_bid(k) or "",
                                "상태":      _KW_STATUS.get(k.get("status",""), k.get("status","") or "-"),
                            } for k in n_kws])
                            st.dataframe(preview, use_container_width=True, hide_index=True)

                            # 그룹 설정 후 등록
                            st.markdown("**그룹 설정**")
                            with st.form("add_group_naver", clear_on_submit=True):
                                default_name = sel_ag.get("name","")
                                c1, c2 = st.columns(2)
                                with c1:
                                    n_name  = st.text_input("그룹명 *", value=default_name)
                                    n_rank  = st.number_input("목표순위", value=3, min_value=1, max_value=15)
                                    n_min   = st.number_input("최소입찰가", value=10000, min_value=10, step=10)
                                    n_max   = st.number_input("최대입찰가", value=35000, min_value=10, step=10)
                                with c2:
                                    n_unit  = st.number_input("증감단위(원)", value=100, min_value=10, step=10)
                                    n_intvl = st.number_input("체크주기(분)", value=15, min_value=1)

                                n_domain = st.text_input(
                                    "검색 도메인 (순위 자동조회용)",
                                    placeholder="예: www.example.com",
                                    help="run_rank_checker.bat 실행 시 이 도메인의 광고 순위를 자동 조회합니다.",
                                )

                                if st.form_submit_button(
                                    f"✅ 그룹 생성 (키워드 {len(kw_texts)}개 포함)",
                                    type="primary", use_container_width=True,
                                ):
                                    if not n_name.strip():
                                        st.error("그룹명 필수")
                                    elif n_min >= n_max:
                                        st.error("최소입찰가 < 최대입찰가")
                                    else:
                                        existing_kws = {kw["keyword"] for g in groups for kw in g.get("keywords",[])}
                                        kw_objs = []
                                        for k in n_kws:
                                            t    = k.get("keyword") or k.get("keywordText","")
                                            bid  = _resolve_bid(k)
                                            kid  = _get_id(k, "nccKeywordId", "keywordId", "id")
                                            if t and t not in existing_kws:
                                                kw_objs.append(new_kw_obj(t, bid, kid))
                                                if len(kw_objs) >= MAX_KEYWORDS:
                                                    break

                                        data["groups"].append({
                                            "id":               str(uuid.uuid4()),
                                            "name":             n_name.strip(),
                                            "target_rank":      int(n_rank),
                                            "min_bid":          int(n_min),
                                            "max_bid":          int(n_max),
                                            "bid_unit":         int(n_unit),
                                            "check_interval":   int(n_intvl),
                                            "check_domain":      n_domain.strip(),
                                            "keywords":          kw_objs,
                                            "naver_campaign_id": camp_id,
                                            "naver_adgroup_id":  ag_id,
                                            "ad_account_id":     sel_acct.get("id",""),
                                        })
                                        save_data(data)
                                        for k in ["n_camps","n_ags","n_kws"]:
                                            st.session_state.pop(k, None)
                                        st.success(
                                            f"그룹 **{n_name.strip()}** 생성 완료 "
                                            f"(키워드 {len(kw_objs)}개)"
                                        )
                                        st.rerun()

# ════════════════════════════════════════════════════════════════════════════
# 탭3: 키워드 관리 (그룹 선택 후 키워드 추가/삭제)
# ════════════════════════════════════════════════════════════════════════════
with tab3:
    if not groups:
        st.info("그룹을 먼저 추가하세요. ([그룹 관리] 탭)")
    else:
        group_map = {g["name"]: g for g in groups}
        sel_name  = st.selectbox("그룹 선택", list(group_map.keys()), key="kw_tab_grp")
        sel_g     = group_map[sel_name]
        kw_list   = sel_g.get("keywords", [])
        existing  = {k["keyword"] for k in kw_list}

        # ── 키워드 목록 (페이지네이션) ──────────────────────────────────
        _KW_PER_PAGE = 50
        _on_cnt  = sum(1 for k in kw_list if k.get("enabled", True))
        _off_cnt = len(kw_list) - _on_cnt
        _total_pages = max(1, -(-len(kw_list) // _KW_PER_PAGE))  # ceil

        _page_key = f"kw_page_{sel_g['id']}"
        if _page_key not in st.session_state:
            st.session_state[_page_key] = 1
        _cur_page = st.session_state[_page_key]

        _ph, _pnav = st.columns([4, 2])
        _ph.markdown(f"**{sel_name}** — 전체 {len(kw_list)}개 (활성 {_on_cnt} / 비활성 {_off_cnt})")
        if _total_pages > 1:
            _pn1, _pn2, _pn3 = _pnav.columns([1, 2, 1])
            if _pn1.button("◀", key="kw_pg_prev", disabled=_cur_page <= 1):
                st.session_state[_page_key] = _cur_page - 1
                st.rerun()
            _pn2.markdown(
                f"<div style='text-align:center;padding-top:6px;font-size:13px;'>"
                f"{_cur_page} / {_total_pages}</div>",
                unsafe_allow_html=True,
            )
            if _pn3.button("▶", key="kw_pg_next", disabled=_cur_page >= _total_pages):
                st.session_state[_page_key] = _cur_page + 1
                st.rerun()
            _cur_page = st.session_state[_page_key]

        if not kw_list:
            st.info("등록된 키워드가 없습니다.")
        else:
            _page_start = (_cur_page - 1) * _KW_PER_PAGE
            _page_end   = _page_start + _KW_PER_PAGE
            _page_kws   = kw_list[_page_start:_page_end]

            _en_checks  = {}
            _del_checks = {}

            # 헤더
            _hh0, _hh1, _hh2, _hh3, _hh4 = st.columns([1, 3, 2, 2, 1])
            _hh0.markdown("**ON**")
            _hh1.markdown("**키워드**")
            _hh2.markdown("**현재입찰가**")
            _hh3.markdown("**상태**")
            _hh4.markdown("**제거**")

            for kw_obj in _page_kws:
                kw = kw_obj["keyword"]
                _c0, _c1, _c2, _c3, _c4 = st.columns([1, 3, 2, 2, 1])
                _en_checks[kw] = _c0.checkbox(
                    "", key=f"en_{sel_g['id']}_{kw}",
                    value=kw_obj.get("enabled", True),
                    label_visibility="collapsed",
                )
                _c1.write(kw)
                _c2.write(f"{kw_obj['current_bid']:,}원" if kw_obj.get("current_bid") else "—")
                _c3.write(
                    STATUS_ICON.get(kw_obj.get("status", "데이터 부족"), "⚪")
                    + " " + kw_obj.get("status", "데이터 부족")
                )
                _del_checks[kw] = _c4.checkbox(
                    "", key=f"del_{sel_g['id']}_{kw}",
                    label_visibility="collapsed",
                )

            # 일괄 버튼 + 저장
            _ba, _bb, _bc, _bd, _ = st.columns([1, 1, 1, 1, 2])
            _all_on  = _ba.button("전체 ON",  key="kw_all_on")
            _all_off = _bb.button("전체 OFF", key="kw_all_off")
            _del_btn = _bc.button("선택 제거", key="kw_del_btn", type="secondary")
            _save_btn = _bd.button("💾 저장",  key="kw_en_save", type="primary")

            if _all_on:
                for k in kw_list: k["enabled"] = True
                save_data(data); st.rerun()
            if _all_off:
                for k in kw_list: k["enabled"] = False
                save_data(data); st.rerun()
            if _del_btn:
                to_del = {k for k, v in _del_checks.items() if v}
                if not to_del:
                    st.warning("제거할 항목을 체크하세요.")
                else:
                    sel_g["keywords"] = [k for k in kw_list if k["keyword"] not in to_del]
                    save_data(data)
                    st.success(f"{len(to_del)}개 제거 완료")
                    st.rerun()
            if _save_btn:
                for kw_obj in _page_kws:
                    kw_obj["enabled"] = _en_checks.get(kw_obj["keyword"], True)
                save_data(data)
                st.success("저장됐습니다.")
                st.rerun()

# ════════════════════════════════════════════════════════════════════════════
# 탭4: 계정 관리
# ════════════════════════════════════════════════════════════════════════════
with tab4:
    _t4_accounts = load_ad_accounts()
    _t4_names    = [a["business_name"] for a in _t4_accounts]

    # ── 신규 광고계정 등록 ────────────────────────────────────────────────
    st.subheader("신규 광고계정 등록")
    with st.form("add_acct_form", clear_on_submit=True):
        fa, fb = st.columns(2)
        with fa:
            f_biz = st.text_input("업체명 *", placeholder="마케팁")
            f_ak  = st.text_input("API Key *", type="password", placeholder="라이선스 키")
        with fb:
            f_sk  = st.text_input("Secret Key *", type="password", placeholder="비밀 키")
            f_ci  = st.text_input("고객 ID *", placeholder="숫자 고객 ID")
        f_memo = st.text_input("메모", placeholder="선택사항")
        if st.form_submit_button("💾 광고계정 저장", type="primary", use_container_width=True):
            if not all([f_biz.strip(), f_ak.strip(), f_sk.strip(), f_ci.strip()]):
                st.error("필수 항목(*)을 모두 입력해주세요.")
            elif any(a["business_name"] == f_biz.strip() for a in _t4_accounts):
                st.error("이미 등록된 업체명입니다.")
            else:
                _now = datetime.now().isoformat()
                _t4_accounts.append({
                    "id":            str(uuid.uuid4()),
                    "business_name": f_biz.strip(),
                    "api_key":       f_ak.strip(),
                    "secret_key":    f_sk.strip(),
                    "customer_id":   f_ci.strip(),
                    "memo":          f_memo.strip(),
                    "created_at":    _now,
                    "updated_at":    _now,
                })
                save_ad_accounts(_t4_accounts)
                st.success(f"✅ {f_biz.strip()} 저장 완료")
                st.rerun()

    st.divider()

    # ── 계정 수정 / 삭제 ──────────────────────────────────────────────────
    if _t4_names:
        st.subheader("계정 수정 / 삭제")
        _edit_name = st.selectbox("수정할 계정 선택", _t4_names, key="t4_edit_acct_sel")
        _edit_acct = next((a for a in _t4_accounts if a["business_name"] == _edit_name), None)
        if _edit_acct:
            with st.form("edit_acct_form"):
                ea, eb = st.columns(2)
                with ea:
                    ea_biz = st.text_input("업체명 *",   value=_edit_acct["business_name"])
                    ea_ak  = st.text_input("API Key *",  value=_edit_acct["api_key"], type="password")
                with eb:
                    ea_sk  = st.text_input("Secret Key *", value=_edit_acct["secret_key"], type="password")
                    ea_ci  = st.text_input("고객 ID *",   value=_edit_acct["customer_id"])
                ea_memo = st.text_input("메모", value=_edit_acct.get("memo", ""))
                cs, cd = st.columns(2)
                with cs:
                    if st.form_submit_button("수정 저장", use_container_width=True):
                        if not all([ea_biz.strip(), ea_ak.strip(), ea_sk.strip(), ea_ci.strip()]):
                            st.error("필수 항목을 모두 입력해주세요.")
                        else:
                            _edit_acct.update({
                                "business_name": ea_biz.strip(),
                                "api_key":       ea_ak.strip(),
                                "secret_key":    ea_sk.strip(),
                                "customer_id":   ea_ci.strip(),
                                "memo":          ea_memo.strip(),
                                "updated_at":    datetime.now().isoformat(),
                            })
                            save_ad_accounts(_t4_accounts)
                            st.success("수정 완료")
                            st.rerun()
                with cd:
                    if st.form_submit_button("삭제", use_container_width=True):
                        _t4_accounts[:] = [a for a in _t4_accounts if a["id"] != _edit_acct["id"]]
                        save_ad_accounts(_t4_accounts)
                        st.rerun()
    else:
        st.info("등록된 광고계정이 없습니다. 위에서 신규 계정을 등록해주세요.")
