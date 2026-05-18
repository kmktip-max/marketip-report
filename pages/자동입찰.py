"""광고 운영 — 목표순위 자동입찰 보조 시스템"""
import streamlit as st
import os, sys, uuid, hmac, hashlib, base64, time, re
import requests
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from db import sb_load, sb_save

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

SB_KEY        = f"bidding_{client_id}"
FALLBACK_JSON = os.path.join(ROOT, f"bidding_{client_id}.json")
MAX_GROUPS    = 5
MAX_KEYWORDS  = 30

STATUS_ICON = {
    "증액중":       "🔴",
    "감액중":       "🔵",
    "유지":         "🟢",
    "데이터 부족":  "⚪",
    "최대입찰 도달":"🟠",
    "최소입찰 도달":"🟡",
}

# ── 데이터 ────────────────────────────────────────────────────────────────
def load_data():
    raw = sb_load(SB_KEY, FALLBACK_JSON)
    return raw if isinstance(raw, dict) and "groups" in raw else {"groups": []}

def save_data(d):
    sb_save(SB_KEY, d, FALLBACK_JSON)

def new_kw_obj(keyword, current_bid=None, ncc_keyword_id=None):
    return {
        "keyword":         keyword,
        "ncc_keyword_id":  ncc_keyword_id,
        "current_rank":    None,
        "current_bid":     current_bid,
        "recommended_bid": None,
        "status":          "데이터 부족",
        "last_checked":    None,
    }

# ── 입찰 계산 ─────────────────────────────────────────────────────────────
def calc_bid(current_rank, target_rank, current_bid, bid_unit, min_bid, max_bid):
    MAX_SINGLE = 500
    if current_rank is None or current_bid is None:
        return current_bid, "데이터 부족"
    diff = current_rank - target_rank
    if diff > 0.5:
        delta   = min(bid_unit, MAX_SINGLE)
        new_bid = min(current_bid + delta, max_bid)
        status  = "최대입찰 도달" if new_bid >= max_bid else "증액중"
    elif diff < -0.5:
        delta   = min(bid_unit // 2 or bid_unit, MAX_SINGLE)
        new_bid = max(current_bid - delta, min_bid)
        status  = "최소입찰 도달" if new_bid <= min_bid else "감액중"
    else:
        new_bid = current_bid
        status  = "유지"
    return round(new_bid / 10) * 10, status

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

def _naver_put(uri, api_key, secret_key, customer_id, body: dict):
    """PUT 요청 + 상세 디버그 정보 반환"""
    ts  = str(int(time.time() * 1000))
    sig = _naver_sig(secret_key, ts, "PUT", uri)
    headers = {
        "X-Timestamp": ts,
        "X-API-KEY":   api_key,
        "X-Customer":  str(customer_id),
        "X-Signature": sig,
        "Content-Type": "application/json; charset=UTF-8",
    }
    full_url = NAVER_API_BASE + uri
    r = requests.put(full_url, headers=headers, json=body, timeout=10)
    debug = {
        "url":           full_url,
        "status_code":   r.status_code,
        "response_body": r.text[:800],
    }
    return r, debug

def naver_update_bid(api_key, secret_key, cid, keyword_id, bid_amt):
    """
    네이버 API 키워드 입찰가 실제 업데이트.
    1) GET으로 현재 키워드 전체 객체 조회
    2) bidAmt만 수정 후 PUT (전체 객체 전송 — Naver API 요구사항)
    반환: (before_bid, response_body, debug_info)
    """
    # 1. 현재 키워드 전체 데이터 GET
    try:
        current_kw = _naver_get(
            f"/ncc/keywords/{keyword_id}", api_key, secret_key, cid
        )
    except Exception as e:
        current_kw = None

    before_bid = current_kw.get("bidAmt", "?") if current_kw else "조회실패"

    # 2. 전체 객체에 bidAmt만 교체해서 PUT
    if current_kw:
        body = dict(current_kw)
        body["bidAmt"] = bid_amt
    else:
        # GET 실패 시 최소 필드로 시도
        body = {"nccKeywordId": keyword_id, "bidAmt": bid_amt}

    uri = f"/ncc/keywords/{keyword_id}"
    r, debug = _naver_put(uri, api_key, secret_key, cid, body)
    debug["before_bid"] = before_bid
    debug["after_bid"]  = bid_amt
    debug["keyword_id"] = keyword_id
    debug["request_body_keys"] = list(body.keys())

    if not r.ok:
        raise Exception(
            f"HTTP {r.status_code} | {r.text[:300]}"
        )

    try:
        return r.json(), debug
    except Exception:
        return {}, debug


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

tab1, tab2, tab3 = st.tabs(["입찰 현황", "그룹 관리", "키워드 관리"])

# ════════════════════════════════════════════════════════════════════════════
# 탭1: 입찰 현황
# ════════════════════════════════════════════════════════════════════════════
with tab1:
    import pandas as pd

    bid_state  = data.get("state", {})
    is_running = bid_state.get("running", False)

    # ── 자동입찰 상태 패널 ────────────────────────────────────────────
    sc1, sc2 = st.columns([4, 1])
    with sc1:
        if is_running:
            started = bid_state.get("started_at", "")
            st.markdown(
                f'<div class="bid-status-on">'
                f'<span style="font-size:16px;">●</span> 자동입찰 실행 중'
                f'<span class="bid-status-time">시작: {started}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div class="bid-status-off">'
                '<span style="font-size:16px;">●</span> 자동입찰 중지됨'
                '</div>',
                unsafe_allow_html=True,
            )
    with sc2:
        if is_running:
            if st.button("⏹ 중지", use_container_width=True):
                data["state"] = {"running": False, "started_at": None}
                save_data(data)
                st.rerun()
        else:
            if st.button("▶ 시작", type="primary", use_container_width=True):
                data["state"] = {
                    "running":    True,
                    "started_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
                }
                save_data(data)
                st.rerun()

    st.markdown(
        '<div class="bid-guide">'
        '<b>사용법</b> &nbsp;'
        '① API 데이터 조회 (입찰가·순위 자동 로드) → '
        '② 입찰가 계산 → '
        '③ 입찰가 적용 (네이버 실제 전송)'
        '&nbsp;&nbsp;|&nbsp;&nbsp;⚠ 순위는 전일 평균노출순위 기준 (Naver API 제공)'
        '</div>',
        unsafe_allow_html=True,
    )

    # ── ① API 데이터 조회 버튼 ──────────────────────────────────────────
    ad_accounts = load_ad_accounts()
    acct_map    = {a["id"]: a for a in ad_accounts}

    if not groups:
        st.info("등록된 그룹이 없습니다. [그룹 관리] 탭에서 그룹을 추가하세요.")

    # ── 그룹 연결 상태 진단 ──────────────────────────────────────────────
    diag_lines = []
    for g in groups:
        acct = acct_map.get(g.get("ad_account_id",""))
        kws  = g.get("keywords",[])
        has_ids = sum(1 for k in kws if k.get("ncc_keyword_id","").strip())
        diag_lines.append(
            f"**{g['name']}** — "
            f"광고계정: {'✅ ' + acct['business_name'] if acct else '❌ 미연결'} | "
            f"keyword ID: {has_ids}/{len(kws)}개"
        )
    if diag_lines:
        with st.expander("🔎 그룹 연결 상태", expanded=any("❌" in l for l in diag_lines)):
            for l in diag_lines:
                st.markdown(l)

    if groups and st.button("📡 API 데이터 조회 (입찰가 · 순위)", use_container_width=True):
        log_lines = []
        any_updated = False
        now_str = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

        for g in groups:
            acct = acct_map.get(g.get("ad_account_id",""))
            if not acct:
                log_lines.append(f"⏭ **{g['name']}**: 광고계정 미연결 — [그룹 관리]에서 네이버 불러오기로 재등록 필요")
                continue

            log_lines.append(f"🔑 **{g['name']}** ({acct['business_name']})")
            updated_g, g_log = naver_refresh_group(
                acct["api_key"], acct["secret_key"], acct["customer_id"], g
            )
            log_lines.extend(g_log)

            # 조회 후 자동 계산
            calc_cnt = 0
            for kw_obj in updated_g.get("keywords", []):
                if (kw_obj.get("current_rank") is not None
                        and kw_obj.get("current_bid") is not None):
                    nb, st_ = calc_bid(
                        kw_obj["current_rank"], g["target_rank"],
                        kw_obj["current_bid"],  g["bid_unit"],
                        g["min_bid"], g["max_bid"],
                    )
                    kw_obj["recommended_bid"] = nb
                    kw_obj["status"]          = st_
                    kw_obj["last_checked"]    = now_str
                    calc_cnt += 1
                else:
                    kw_obj["recommended_bid"] = None
                    kw_obj["status"]          = "데이터 부족"

            log_lines.append(f"  입찰가 계산: {calc_cnt}개")
            any_updated = True

        if any_updated:
            data["groups"] = groups
            save_data(data)

        with st.expander("📋 조회 로그", expanded=True):
            st.markdown("\n\n".join(log_lines))

        if any_updated:
            st.rerun()

    if groups:
        st.divider()

        # ── 키워드 테이블 ─────────────────────────────────────────────
        rows = []
        for g in groups:
            for kw in g.get("keywords", []):
                has_rank = kw.get("current_rank") is not None
                rec_bid  = kw.get("recommended_bid") if has_rank else None
                status   = kw.get("status","데이터 부족") if has_rank else "데이터 부족"
                rows.append({
                    "_gid":       g["id"],
                    "_kw":        kw["keyword"],
                    "_kwid":      kw.get("ncc_keyword_id",""),
                    "_acct_id":   g.get("ad_account_id",""),
                    "그룹명":     g["name"],
                    "키워드":     kw["keyword"],
                    "현재순위":   kw.get("current_rank"),
                    "목표순위":   g["target_rank"],
                    "현재입찰가": kw.get("current_bid"),
                    "추천입찰가": rec_bid,
                    "상태":       STATUS_ICON.get(status,"⚪") + " " + status,
                    "마지막체크": kw.get("last_checked","") or "",
                })

        df      = pd.DataFrame(rows)
        HIDDEN  = {"_gid","_kw","_kwid","_acct_id"}
        disp_df = df[[c for c in df.columns if c not in HIDDEN]].copy()

        edited = st.data_editor(
            disp_df,
            use_container_width=True, hide_index=True, num_rows="fixed",
            column_config={
                "그룹명":     st.column_config.TextColumn(disabled=True),
                "키워드":     st.column_config.TextColumn(disabled=True),
                "현재순위":   st.column_config.NumberColumn("현재순위", format="%.1f",
                              help="API 조회 시 자동 입력 / 직접 입력도 가능"),
                "목표순위":   st.column_config.NumberColumn(disabled=True),
                "현재입찰가": st.column_config.NumberColumn("현재입찰가(원)", format="%d"),
                "추천입찰가": st.column_config.NumberColumn("추천입찰가(원)", disabled=True, format="%d"),
                "상태":       st.column_config.TextColumn(disabled=True),
                "마지막체크": st.column_config.TextColumn(disabled=True),
            },
            key="bid_editor",
        )

        st.markdown(
            '<div class="bid-legend">'
            '<span>🔴 증액중</span><span>🔵 감액중</span><span>🟢 유지</span>'
            '<span>⚪ 데이터 부족</span><span>🟠 최대입찰 도달</span><span>🟡 최소입찰 도달</span>'
            '</div>',
            unsafe_allow_html=True,
        )

        b1, b2 = st.columns(2)

        # ── ② 입찰가 계산 (수동 입력값 반영) ────────────────────────────
        with b1:
            if st.button("🔄 입찰가 계산", use_container_width=True):
                now_str = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
                recs    = edited.to_dict(orient="records")
                calc_cnt = skip_cnt = 0
                for i, rec in enumerate(recs):
                    gid    = df.iloc[i]["_gid"]
                    kw_str = df.iloc[i]["_kw"]
                    g      = next((x for x in groups if x["id"] == gid), None)
                    if not g: continue
                    kw_obj = next((x for x in g["keywords"] if x["keyword"] == kw_str), None)
                    if not kw_obj: continue
                    kw_obj["current_rank"] = rec.get("현재순위")
                    raw = rec.get("현재입찰가")
                    kw_obj["current_bid"]  = int(raw) if raw is not None else None
                    if kw_obj["current_rank"] is None or kw_obj["current_bid"] is None:
                        kw_obj["recommended_bid"] = None
                        kw_obj["status"]          = "데이터 부족"
                        skip_cnt += 1
                        continue
                    nb, st_ = calc_bid(
                        kw_obj["current_rank"], g["target_rank"],
                        kw_obj["current_bid"],  g["bid_unit"],
                        g["min_bid"], g["max_bid"],
                    )
                    kw_obj["recommended_bid"] = nb
                    kw_obj["status"]          = st_
                    kw_obj["last_checked"]    = now_str
                    calc_cnt += 1
                data["groups"] = groups
                save_data(data)
                st.success(f"계산 완료 — {calc_cnt}개 / 데이터 부족 {skip_cnt}개")
                st.rerun()

        # ── ③ 입찰가 적용 (Naver API 실제 전송 + 전체 디버그) ────────────
        with b2:
            has_rec = any(
                kw.get("recommended_bid") is not None
                for g in groups for kw in g.get("keywords",[])
            )
            if st.button("🚀 입찰가 적용", type="primary",
                         use_container_width=True, disabled=not has_rec):
                ok_cnt = err_cnt = skip_cnt = 0
                now_str = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
                result_log = []   # 전체 결과 로그
                api_debugs = []   # API 응답 raw 데이터

                for g in groups:
                    acct = acct_map.get(g.get("ad_account_id",""))
                    for kw_obj in g.get("keywords", []):
                        kw_name = kw_obj["keyword"]
                        bid = kw_obj.get("recommended_bid")

                        # --- 사전 검증 ---
                        if bid is None:
                            skip_cnt += 1
                            result_log.append(f"⏭ {kw_name}: 추천입찰가 없음 (계산 먼저)")
                            continue
                        if not acct:
                            skip_cnt += 1
                            result_log.append(f"⚠ {kw_name}: 광고계정 미연결 (그룹에 ad_account_id 없음)")
                            continue
                        kid = kw_obj.get("ncc_keyword_id","").strip()
                        if not kid:
                            skip_cnt += 1
                            result_log.append(
                                f"⚠ {kw_name}: ncc_keyword_id 없음 → "
                                f"[📡 API 데이터 조회] 먼저 실행 필요"
                            )
                            continue

                        # 범위 클램프
                        bid = max(g["min_bid"], min(g["max_bid"], bid))

                        # --- 실제 API 호출 ---
                        try:
                            resp_body, dbg = naver_update_bid(
                                acct["api_key"], acct["secret_key"],
                                acct["customer_id"], kid, bid,
                            )
                            kw_obj["current_bid"]     = bid
                            kw_obj["recommended_bid"] = None
                            kw_obj["last_checked"]    = now_str
                            ok_cnt += 1
                            result_log.append(
                                f"✅ {kw_name} | "
                                f"변경 전: {dbg['before_bid']}원 → "
                                f"변경 후: {bid}원 | "
                                f"keywordId: {kid} | "
                                f"HTTP {dbg['status_code']}"
                            )
                            api_debugs.append({
                                "keyword": kw_name,
                                **dbg,
                                "response_body": resp_body,
                            })
                        except Exception as e:
                            err_cnt += 1
                            result_log.append(f"❌ {kw_name}: {e}")
                            api_debugs.append({
                                "keyword": kw_name,
                                "keyword_id": kid,
                                "error": str(e),
                            })

                data["groups"] = groups
                save_data(data)

                # 요약
                if ok_cnt:
                    st.success(f"✅ 네이버 전송 성공: {ok_cnt}개 | 건너뜀: {skip_cnt}개 | 실패: {err_cnt}개")
                elif err_cnt:
                    st.error(f"❌ 전송 실패: {err_cnt}개 | 건너뜀: {skip_cnt}개")
                else:
                    st.warning(f"전송 없음 (건너뜀: {skip_cnt}개) — 위 로그 확인")

                # 상세 결과 로그
                with st.expander("📋 입찰 적용 상세 결과", expanded=True):
                    for line in result_log:
                        st.markdown(line)

                # API 원시 응답 (개발 디버그)
                if api_debugs:
                    with st.expander("🔍 API 요청/응답 Raw (디버그)"):
                        import json as _json
                        for d in api_debugs:
                            st.markdown(f"**{d.get('keyword','')}**")
                            st.code(
                                _json.dumps(d, ensure_ascii=False, indent=2,
                                            default=str),
                                language="json"
                            )
                st.rerun()

        # ── 🧪 단일 키워드 API 테스트 ────────────────────────────────────
        st.divider()
        st.markdown("#### 🧪 단일 키워드 API 테스트")
        st.caption("입찰가 변경이 실제로 동작하는지 키워드 1개로 먼저 검증합니다.")

        all_kws = [
            (g["name"], kw["keyword"], kw.get("ncc_keyword_id",""), kw.get("current_bid"), g)
            for g in groups for kw in g.get("keywords",[])
        ]
        if all_kws:
            kw_labels = [f"{gn} / {kw}" for gn, kw, kid, bid, g in all_kws]
            sel_idx   = st.selectbox("테스트할 키워드 선택", range(len(kw_labels)),
                                     format_func=lambda i: kw_labels[i],
                                     key="test_kw_sel")
            t_gname, t_kwname, t_kid, t_cur_bid, t_g = all_kws[sel_idx]
            t_acct = acct_map.get(t_g.get("ad_account_id",""))

            col_a, col_b = st.columns(2)
            with col_a:
                st.markdown(f"""
| 항목 | 값 |
|------|-----|
| 그룹 | {t_gname} |
| 키워드 | {t_kwname} |
| ncc_keyword_id | `{t_kid or '❌ 없음'}` |
| 현재입찰가 | {f'{t_cur_bid:,}원' if t_cur_bid else '미조회'} |
| 광고계정 | {'✅ ' + t_acct['business_name'] if t_acct else '❌ 미연결'} |
""")
            with col_b:
                default_test_bid = (t_cur_bid or 1000) + 100
                test_bid_val = st.number_input(
                    "테스트 입찰가 (원)",
                    min_value=10, max_value=100000,
                    value=int(default_test_bid), step=10,
                    key="test_bid_input",
                )

            can_test = bool(t_kid and t_acct)
            if not can_test:
                if not t_kid:
                    st.warning("⚠ ncc_keyword_id 없음 → 위의 [📡 API 데이터 조회] 먼저 실행")
                if not t_acct:
                    st.warning("⚠ 광고계정 미연결 → [그룹 관리]에서 네이버 불러오기로 재등록 필요")

            if st.button("🧪 테스트 실행 (네이버 실제 API 호출)", type="primary",
                         disabled=not can_test, key="test_run_btn"):
                import json as _json
                st.markdown(f"**실행:** `PUT /ncc/keywords/{t_kid}` → bidAmt={test_bid_val}")
                try:
                    with st.spinner("Naver API 호출 중..."):
                        resp_data, dbg = naver_update_bid(
                            t_acct["api_key"], t_acct["secret_key"],
                            t_acct["customer_id"], t_kid, test_bid_val,
                        )
                    st.success(
                        f"✅ API 성공! HTTP {dbg['status_code']} | "
                        f"변경 전: {dbg['before_bid']}원 → 변경 후: {test_bid_val}원"
                    )
                    st.markdown("**API Response Body:**")
                    st.code(_json.dumps(resp_data, ensure_ascii=False, indent=2, default=str),
                            language="json")
                    st.markdown("**Request 상세:**")
                    st.code(_json.dumps({
                        "url":              dbg["url"],
                        "keyword_id":       t_kid,
                        "before_bid":       dbg["before_bid"],
                        "after_bid":        test_bid_val,
                        "request_keys":     dbg.get("request_body_keys", []),
                        "http_status":      dbg["status_code"],
                    }, ensure_ascii=False, indent=2), language="json")
                    st.info("📌 네이버 광고관리자에서 해당 키워드 입찰가 확인해주세요.")
                except Exception as e:
                    st.error(f"❌ API 실패: {e}")
                    st.markdown("**디버그 정보:**")
                    st.code(str(e))

# ════════════════════════════════════════════════════════════════════════════
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
                        g_auto   = st.checkbox("자동적용",         value=g.get("auto_apply", False))
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
                                    "auto_apply": g_auto,
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

        _methods = ["📋 키워드 직접 입력"]
        if auth_type == "admin":
            _methods.append("📡 네이버 광고그룹 불러오기")
        add_method = st.radio(
            "그룹 추가 방식",
            _methods,
            horizontal=True,
            key="add_method",
        )

        # ── 방식 1: 직접 입력 ─────────────────────────────────────────────
        if add_method == "📋 키워드 직접 입력":
            with st.form("add_group_direct", clear_on_submit=True):
                st.markdown("**그룹 기본 설정**")
                c1, c2 = st.columns(2)
                with c1:
                    n_name  = st.text_input("그룹명 *", placeholder="예: 이혼메인")
                    n_rank  = st.number_input("목표순위", value=3, min_value=1, max_value=15)
                    n_min   = st.number_input("최소입찰가", value=10000, min_value=10, step=10)
                    n_max   = st.number_input("최대입찰가", value=35000, min_value=10, step=10)
                with c2:
                    n_unit  = st.number_input("증감단위(원)", value=100, min_value=10, step=10)
                    n_intvl = st.number_input("체크주기(분)", value=15, min_value=1)
                    n_auto  = st.checkbox("자동적용", value=False)

                n_domain = st.text_input(
                    "검색 도메인 (순위 자동조회용)",
                    placeholder="예: www.example.com",
                    help="run_rank_checker.bat 실행 시 이 도메인의 광고 순위를 자동 조회합니다.",
                )
                st.markdown("**키워드 입력** (줄바꿈 또는 쉼표로 구분)")
                kw_input = st.text_area(
                    "키워드",
                    placeholder="이혼변호사\n이혼전문변호사\n위자료변호사",
                    height=140,
                    label_visibility="collapsed",
                )

                if st.form_submit_button("그룹 생성", type="primary", use_container_width=True):
                    if not n_name.strip():
                        st.error("그룹명을 입력해주세요.")
                    elif n_min >= n_max:
                        st.error("최소입찰가는 최대입찰가보다 작아야 합니다.")
                    else:
                        raw_kws = re.split(r"[\n,]+", kw_input or "")
                        kws     = [k.strip() for k in raw_kws if k.strip()][:MAX_KEYWORDS]

                        new_group = {
                            "id":             str(uuid.uuid4()),
                            "name":           n_name.strip(),
                            "target_rank":    int(n_rank),
                            "min_bid":        int(n_min),
                            "max_bid":        int(n_max),
                            "bid_unit":       int(n_unit),
                            "check_interval": int(n_intvl),
                            "auto_apply":     n_auto,
                            "check_domain":   n_domain.strip(),
                            "keywords":       [new_kw_obj(k) for k in kws],
                        }
                        data["groups"].append(new_group)
                        save_data(data)
                        st.success(
                            f"그룹 **{n_name.strip()}** 생성 완료 "
                            f"(키워드 {len(kws)}개)"
                        )
                        st.rerun()

        # ── 방식 2: 네이버 광고그룹 불러오기 (관리자 전용) ──────────────
        else:
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

            # ── 신규 계정 등록 ─────────────────────────────────────────
            with st.expander("➕ 신규 광고계정 등록", expanded=not acct_names):
                with st.form("add_acct_form", clear_on_submit=True):
                    fa, fb = st.columns(2)
                    with fa:
                        f_biz = st.text_input("업체명 *", placeholder="마케팁")
                        f_ak  = st.text_input("API Key *", type="password",
                                              placeholder="라이선스 키")
                    with fb:
                        f_sk  = st.text_input("Secret Key *", type="password",
                                              placeholder="비밀 키")
                        f_ci  = st.text_input("고객 ID *", placeholder="숫자 고객 ID")
                    f_memo = st.text_input("메모", placeholder="선택사항")
                    if st.form_submit_button("💾 광고계정 저장", type="primary",
                                             use_container_width=True):
                        if not all([f_biz.strip(), f_ak.strip(), f_sk.strip(), f_ci.strip()]):
                            st.error("필수 항목(*)을 모두 입력해주세요.")
                        elif any(a["business_name"] == f_biz.strip() for a in ad_accounts):
                            st.error("이미 등록된 업체명입니다.")
                        else:
                            now = datetime.now().isoformat()
                            ad_accounts.append({
                                "id":            str(uuid.uuid4()),
                                "business_name": f_biz.strip(),
                                "api_key":       f_ak.strip(),
                                "secret_key":    f_sk.strip(),
                                "customer_id":   f_ci.strip(),
                                "memo":          f_memo.strip(),
                                "created_at":    now,
                                "updated_at":    now,
                            })
                            save_ad_accounts(ad_accounts)
                            st.success(f"✅ {f_biz.strip()} 저장 완료")
                            st.rerun()

            # ── 계정 수정 / 삭제 ───────────────────────────────────────
            if acct_names:
                with st.expander("✏️ 계정 수정 / 삭제", expanded=False):
                    edit_name = st.selectbox(
                        "수정할 계정 선택", acct_names, key="edit_acct_sel"
                    )
                    edit_acct = next(
                        (a for a in ad_accounts if a["business_name"] == edit_name), None
                    )
                    if edit_acct:
                        with st.form("edit_acct_form"):
                            ea, eb = st.columns(2)
                            with ea:
                                ea_biz = st.text_input("업체명 *",
                                                       value=edit_acct["business_name"])
                                ea_ak  = st.text_input("API Key *",
                                                       value=edit_acct["api_key"],
                                                       type="password")
                            with eb:
                                ea_sk  = st.text_input("Secret Key *",
                                                       value=edit_acct["secret_key"],
                                                       type="password")
                                ea_ci  = st.text_input("고객 ID *",
                                                       value=edit_acct["customer_id"])
                            ea_memo = st.text_input("메모",
                                                    value=edit_acct.get("memo",""))
                            cs, cd = st.columns(2)
                            with cs:
                                if st.form_submit_button("수정 저장",
                                                         use_container_width=True):
                                    if not all([ea_biz.strip(), ea_ak.strip(),
                                                ea_sk.strip(), ea_ci.strip()]):
                                        st.error("필수 항목을 모두 입력해주세요.")
                                    else:
                                        edit_acct.update({
                                            "business_name": ea_biz.strip(),
                                            "api_key":       ea_ak.strip(),
                                            "secret_key":    ea_sk.strip(),
                                            "customer_id":   ea_ci.strip(),
                                            "memo":          ea_memo.strip(),
                                            "updated_at":    datetime.now().isoformat(),
                                        })
                                        save_ad_accounts(ad_accounts)
                                        st.success("수정 완료")
                                        st.rerun()
                            with cd:
                                if st.form_submit_button("삭제",
                                                         use_container_width=True):
                                    ad_accounts[:] = [
                                        a for a in ad_accounts if a["id"] != edit_acct["id"]
                                    ]
                                    save_ad_accounts(ad_accounts)
                                    st.rerun()

            if not sel_acct:
                st.stop()

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
            if not camps:
                st.stop()

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
            if not ags:
                st.stop()

            ag_map = {f"{a.get('name','(이름없음)')}": a for a in ags}
            sel_ag  = ag_map[
                st.selectbox("광고그룹 선택", list(ag_map.keys()), key="n_sel_ag")
            ]
            ag_id = _get_id(sel_ag, "nccAdgroupId", "adgroupId", "adGroupId", "id")

            if not ag_id:
                st.warning(f"광고그룹 ID를 찾을 수 없습니다. 키: {list(sel_ag.keys())}")
                st.stop()

            # 키워드 — 광고그룹 변경 시 자동 로드
            if ag_id and st.session_state.get("n_kws_ag_id") != ag_id:
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
                st.stop()

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
                    n_auto  = st.checkbox("자동적용", value=False)

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
                            "auto_apply":        n_auto,
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
        st.stop()

    group_map = {g["name"]: g for g in groups}
    sel_name  = st.selectbox("그룹 선택", list(group_map.keys()), key="kw_tab_grp")
    sel_g     = group_map[sel_name]
    kw_list   = sel_g.get("keywords", [])
    existing  = {k["keyword"] for k in kw_list}

    st.markdown(f"**{sel_name}** — {len(kw_list)} / {MAX_KEYWORDS}개")

    # 키워드 추가
    if len(kw_list) < MAX_KEYWORDS:
        kw_text = st.text_area(
            "키워드 추가 (줄바꿈 또는 쉼표로 구분)",
            placeholder="이혼변호사\n이혼전문변호사",
            height=120,
            key="kw_tab_input",
        )
        if st.button("추가", type="primary", key="kw_tab_add"):
            raw = re.split(r"[\n,]+", kw_text or "")
            new = [k.strip() for k in raw if k.strip() and k.strip() not in existing]
            new = new[:MAX_KEYWORDS - len(kw_list)]
            if not new:
                st.warning("추가할 새 키워드가 없습니다.")
            else:
                for k in new:
                    sel_g["keywords"].append(new_kw_obj(k))
                save_data(data)
                st.success(f"{len(new)}개 추가 완료")
                st.rerun()
    else:
        st.warning(f"키워드 최대 {MAX_KEYWORDS}개 도달")

    st.divider()

    # 현재 키워드 목록
    st.markdown("**등록 키워드**")
    if not kw_list:
        st.info("등록된 키워드가 없습니다.")
    else:
        del_check = {}
        h1, h2, h3, h4 = st.columns([3, 2, 2, 1])
        h1.markdown("**키워드**")
        h2.markdown("**현재입찰가**")
        h3.markdown("**상태**")
        h4.markdown("**삭제**")

        for kw_obj in kw_list:
            kw = kw_obj["keyword"]
            c1, c2, c3, c4 = st.columns([3, 2, 2, 1])
            c1.write(kw)
            c2.write(f"{kw_obj['current_bid']:,}" if kw_obj.get("current_bid") else "—")
            c3.write(
                STATUS_ICON.get(kw_obj.get("status","데이터 부족"),"⚪")
                + " " + kw_obj.get("status","데이터 부족")
            )
            del_check[kw] = c4.checkbox(
                "", key=f"del_{sel_g['id']}_{kw}",
                label_visibility="collapsed",
            )

        if st.button("선택 삭제", key="kw_del_btn"):
            to_del = {k for k, v in del_check.items() if v}
            if not to_del:
                st.warning("삭제할 항목을 선택하세요.")
            else:
                sel_g["keywords"] = [k for k in kw_list if k["keyword"] not in to_del]
                save_data(data)
                st.success(f"{len(to_del)}개 삭제 완료")
                st.rerun()
