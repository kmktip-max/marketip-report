"""
월간보고서 V2 - 일자별/주차별/키워드 TOP10 분석 보고서
기존 report_html.py와 독립적으로 동작. generate_html() 함수를 수정하지 않음.
"""
import json
import requests
from datetime import date, timedelta


# ──────────────────────────────────────────────────────────────────────────────
# 안전 포맷 헬퍼
# ──────────────────────────────────────────────────────────────────────────────

def _safe_int(v, default=0):
    try:
        return int(v) if v is not None else default
    except (ValueError, TypeError):
        return default


def _safe_float(v, default=0.0):
    try:
        return float(v) if v is not None else default
    except (ValueError, TypeError):
        return default


def _fmt_num(n):
    return f"{_safe_int(n):,}"


def _fmt_won(n):
    n = _safe_int(n)
    if n >= 10_000_000:
        return f"{n // 10_000_000}천{(n % 10_000_000) // 10_000:,}만"
    if n >= 10_000:
        return f"{n // 10_000:,}만"
    return f"{n:,}원"


def _ctr(clicks, imps):
    c, i = _safe_int(clicks), _safe_int(imps)
    return f"{c / i * 100:.2f}%" if i > 0 else "-"


def _cpc_str(cost, clicks):
    co, ck = _safe_int(cost), _safe_int(clicks)
    return f"{co // ck:,}원" if ck > 0 else "-"


def _roas_str(revenue, cost):
    r, c = _safe_int(revenue), _safe_int(cost)
    if c == 0:
        return "-"
    if r == 0:
        return "매출없음"
    val = r / c * 100
    return f"{val:.1f}%" if val >= 0 else "검증필요"


WEEKDAY_KR = ["월", "화", "수", "목", "금", "토", "일"]


def _weekday_kr(date_str):
    try:
        d = date.fromisoformat(date_str) if isinstance(date_str, str) else date_str
        return WEEKDAY_KR[d.weekday()]
    except Exception:
        return ""


def _change_html(curr, prev):
    c, p = _safe_float(curr), _safe_float(prev)
    if p == 0:
        return "-" if c == 0 else '<span style="color:#1565C0;">신규</span>'
    chg = (c - p) / p * 100
    if abs(chg) < 0.005:
        return "0.00%"
    sign = "▲" if chg > 0 else "▼"
    color = "#27ae60" if chg > 0 else "#e74c3c"
    return f'<span style="color:{color};">{sign}{abs(chg):.2f}%</span>'


# ──────────────────────────────────────────────────────────────────────────────
# V2 추가 데이터 수집 (일자별 + 전월)
# ──────────────────────────────────────────────────────────────────────────────
# 네이버 광고 상품 분류
# ──────────────────────────────────────────────────────────────────────────────

# Naver Search Ad API campaignTp 필드값 → 상품명 매핑
# GFA/성과형DA 는 별도 API (api.naver.com/admanager) → 미연동
NAVER_CAMPAIGN_TYPE_LABELS = {
    "WEB_SITE":          "검색광고",
    "SHOPPING":          "쇼핑광고",
    "BRAND":             "브랜드검색",
    "BRAND_SEARCH":      "브랜드검색",
    "POWER_CONTENTS":    "파워콘텐츠",
    "POWERCONTENTS_NCC": "파워콘텐츠",
    "MOBILE_APP":        "모바일앱",
    "AD_BOOST":          "애드부스트",
    "AD_BOOST_CONTENTS": "애드부스트",
}

# 보고서 표시 순서
PRODUCT_ORDER = ["검색광고", "쇼핑광고", "브랜드검색", "파워콘텐츠", "모바일앱", "애드부스트", "기타"]


def classify_naver_product(campaign_tp: str, campaign_name: str = "") -> str:
    """
    Naver 캠페인을 광고 상품별로 분류
    1순위: campaignTp 필드 (API 공식 타입)
    2순위: 캠페인 이름 키워드 매핑
    """
    tp   = (campaign_tp   or "").upper().replace("-", "_").replace(" ", "_")
    name = (campaign_name or "").upper()

    for key, label in NAVER_CAMPAIGN_TYPE_LABELS.items():
        if key in tp:
            return label

    # 이름 기반 보조 분류
    if any(k in name for k in ["쇼핑", "SHOPPING"]):
        return "쇼핑광고"
    if any(k in name for k in ["브랜드", "BRAND"]):
        return "브랜드검색"
    if any(k in name for k in ["애드부스트", "ADBOOST", "AD BOOST", "AD_BOOST"]):
        return "애드부스트"
    if any(k in name for k in ["파워콘텐츠", "POWER CONTENTS", "POWERCONTENTS"]):
        return "파워콘텐츠"

    return "검색광고"  # 기본값: 대부분 파워링크/검색광고


# ──────────────────────────────────────────────────────────────────────────────

def fetch_v2_extra(api, since: str, until: str) -> dict:
    """
    V2 보고서 추가 데이터 수집 (직접 순차 HTTP 호출 방식)
    - api.get_stats() 의 내부 ThreadPoolExecutor 를 우회
    - 주차별 5회 + 전월 1회 직접 호출
    - 에러 발생 시 해당 주차만 0 처리, 나머지 데이터 보존
    """
    from report_engine.naver_api import _headers, BASE_URL

    since_dt   = date.fromisoformat(since) if isinstance(since, str) else since
    until_dt   = date.fromisoformat(until) if isinstance(until, str) else until
    prev_until = since_dt - timedelta(days=1)
    prev_since = prev_until.replace(day=1)

    _FIELDS = json.dumps(
        ["impCnt", "clkCnt", "salesAmt", "ccnt", "ctr", "ror", "cpConv", "avgRnk"]
    )

    result = {
        "daily":        {},
        "weekly":       {},
        "prev_summary": {"impressions": 0, "clicks": 0, "cost": 0,
                         "conversions": 0, "revenue": 0},
        "prev_since":   prev_since.isoformat(),
        "prev_until":   prev_until.isoformat(),
        "debug":        [],
    }

    # ── 캠페인 목록 ──────────────────────────────────────────────────────────
    try:
        camps    = api.get_campaigns()
        camp_ids = [c["nccCampaignId"] for c in camps]
        result["debug"].append(f"캠페인 {len(camp_ids)}개")
    except Exception as e:
        result["debug"].append(f"캠페인 조회 실패: {e}")
        return result

    if not camp_ids:
        result["debug"].append("캠페인 없음")
        return result

    # ── 캠페인 → 상품 분류 ───────────────────────────────────────────────────
    product_camp_map = {}   # {product_name: [camp_id, ...]}
    for camp in camps:
        product = classify_naver_product(
            camp.get("campaignTp", ""),
            camp.get("name", "")
        )
        product_camp_map.setdefault(product, []).append(camp["nccCampaignId"])

    result["product_camp_counts"] = {p: len(ids) for p, ids in product_camp_map.items()}
    result["debug"].append("상품분류: " + ", ".join(
        f"{p}({len(ids)}개)" for p, ids in product_camp_map.items()
    ))

    # ── 직접 순차 통계 호출 헬퍼 ─────────────────────────────────────────────
    def _call(start, end, ids=None):
        """ThreadPoolExecutor 없이 순차 HTTP 호출 — 집계 dict 반환
        ids: None → 전체 캠페인, list → 지정 캠페인만
        """
        _ids = ids if ids is not None else camp_ids
        if not _ids:
            return {"impressions": 0, "clicks": 0, "cost": 0,
                    "conversions": 0, "revenue": 0}

        _s = start.isoformat() if hasattr(start, "isoformat") else str(start)
        _e = end.isoformat()   if hasattr(end,   "isoformat") else str(end)
        _tr = json.dumps({"since": _s, "until": _e})

        agg = {"impressions": 0, "clicks": 0, "cost": 0,
               "conversions": 0, "revenue": 0}

        for i in range(0, len(_ids), 100):
            batch = _ids[i:i + 100]
            path  = "/stats"
            h     = _headers("GET", path, api.api_key, api.secret_key, api.customer_id)
            resp  = requests.get(
                BASE_URL + path, headers=h,
                params={"ids": ",".join(batch), "fields": _FIELDS, "timeRange": _tr},
                timeout=30,
            )
            resp.raise_for_status()
            rj   = resp.json()
            rows = rj.get("data", []) if isinstance(rj, dict) else []

            for row in rows:
                imps   = _safe_int(row.get("impCnt"))
                clks   = _safe_int(row.get("clkCnt"))
                convs  = _safe_int(row.get("ccnt"))
                cpconv = _safe_float(row.get("cpConv"))
                rev    = _safe_int(row.get("salesAmt")) if convs > 0 else 0
                cost   = int(cpconv * convs)            if convs > 0 else 0

                agg["impressions"] += imps
                agg["clicks"]      += clks
                agg["cost"]        += cost
                agg["conversions"] += convs
                agg["revenue"]     += rev

        return agg

    # ── 주차별 통계 (5회 개별 호출) ──────────────────────────────────────────
    for week_num, ws, we in _get_week_ranges(since_dt, until_dt):
        try:
            agg = _call(ws, we)
            agg["days"] = (we - ws).days + 1
            result["weekly"][week_num] = agg
            result["debug"].append(
                f"W{week_num}({ws}~{we}): "
                f"노출{agg['impressions']:,} 클릭{agg['clicks']:,} 비용{agg['cost']:,}"
            )
        except Exception as e:
            result["weekly"][week_num] = {
                "impressions": 0, "clicks": 0, "cost": 0,
                "conversions": 0, "revenue": 0,
                "days": (we - ws).days + 1,
            }
            result["debug"].append(f"W{week_num} 실패: {e}")

    # ── 전월 통계 ─────────────────────────────────────────────────────────────
    try:
        prev_agg = _call(prev_since, prev_until)
        result["prev_summary"] = prev_agg
        result["debug"].append(
            f"전월({prev_since}~{prev_until}): "
            f"노출{prev_agg['impressions']:,} 클릭{prev_agg['clicks']:,}"
        )
    except Exception as e:
        result["debug"].append(f"전월 실패: {e}")

    # ── 상품별 당월/전월 통계 ──────────────────────────────────────────────────
    product_stats      = {}   # 당월 상품별
    product_prev_stats = {}   # 전월 상품별
    for product, p_ids in product_camp_map.items():
        # 당월
        try:
            agg = _call(since_dt, until_dt, ids=p_ids)
            product_stats[product] = agg
            result["debug"].append(
                f"[상품/{product}] 노출{agg['impressions']:,} 클릭{agg['clicks']:,} "
                f"비용{agg['cost']:,} 전환{agg['conversions']:,} 매출{agg['revenue']:,}"
            )
        except Exception as e:
            product_stats[product] = {
                "impressions": 0, "clicks": 0, "cost": 0, "conversions": 0, "revenue": 0
            }
            result["debug"].append(f"[상품/{product}] 실패: {e}")
        # 전월
        try:
            product_prev_stats[product] = _call(prev_since, prev_until, ids=p_ids)
        except Exception:
            product_prev_stats[product] = {
                "impressions": 0, "clicks": 0, "cost": 0, "conversions": 0, "revenue": 0
            }

    result["product_stats"]      = product_stats
    result["product_prev_stats"] = product_prev_stats

    # ── 일자별 통계 (timeUnit=DAY 시도) ──────────────────────────────────────
    daily_map = {}
    try:
        _daily_fields = json.dumps(["impCnt", "clkCnt", "salesAmt", "ccnt", "cpConv"])
        _tr_full = json.dumps({"since": since if isinstance(since, str) else since_dt.isoformat(),
                               "until": until if isinstance(until, str) else until_dt.isoformat()})
        for i in range(0, len(camp_ids), 100):
            batch = camp_ids[i:i + 100]
            path  = "/stats"
            h     = _headers("GET", path, api.api_key, api.secret_key, api.customer_id)
            resp  = requests.get(
                BASE_URL + path, headers=h,
                params={"ids": ",".join(batch), "fields": _daily_fields,
                        "timeRange": _tr_full, "timeUnit": "DAY"},
                timeout=30,
            )
            resp.raise_for_status()
            rj   = resp.json()
            rows = rj.get("data", []) if isinstance(rj, dict) else []
            for row in rows:
                stat_date = row.get("statDate") or row.get("date") or ""
                if not stat_date:
                    continue
                imps   = _safe_int(row.get("impCnt"))
                clks   = _safe_int(row.get("clkCnt"))
                convs  = _safe_int(row.get("ccnt"))
                cpconv = _safe_float(row.get("cpConv"))
                rev    = _safe_int(row.get("salesAmt")) if convs > 0 else 0
                cost   = int(cpconv * convs)            if convs > 0 else 0
                if stat_date not in daily_map:
                    daily_map[stat_date] = {"impressions": 0, "clicks": 0, "cost": 0,
                                            "conversions": 0, "revenue": 0}
                daily_map[stat_date]["impressions"] += imps
                daily_map[stat_date]["clicks"]      += clks
                daily_map[stat_date]["cost"]        += cost
                daily_map[stat_date]["conversions"] += convs
                daily_map[stat_date]["revenue"]     += rev
        if daily_map:
            result["debug"].append(f"일자별 {len(daily_map)}일 수집 성공")
        else:
            result["debug"].append("일자별 timeUnit=DAY 미지원 (주차 평균으로 대체)")
    except Exception as e:
        result["debug"].append(f"일자별 실패: {e}")
        daily_map = {}

    result["daily"] = daily_map
    return result


# ──────────────────────────────────────────────────────────────────────────────
# 일자/주차 집계
# ──────────────────────────────────────────────────────────────────────────────

def _build_daily_list(daily_map: dict, since_str: str, until_str: str) -> list:
    since_dt = date.fromisoformat(since_str) if isinstance(since_str, str) else since_str
    until_dt = date.fromisoformat(until_str) if isinstance(until_str, str) else until_str
    rows = []
    d = since_dt
    while d <= until_dt:
        ds = d.isoformat()
        s = daily_map.get(ds, {})
        rows.append({
            "date":        ds,
            "weekday":     _weekday_kr(ds),
            "impressions": _safe_int(s.get("impressions")),
            "clicks":      _safe_int(s.get("clicks")),
            "cost":        _safe_int(s.get("cost")),
            "conversions": _safe_int(s.get("conversions")),
            "revenue":     _safe_int(s.get("revenue")),
        })
        d += timedelta(days=1)
    return rows


def _get_week_ranges(since_dt, until_dt):
    """월의 주차별 날짜 범위 반환 (1주=1~7일, 2주=8~14일, ...)"""
    ranges = []
    for w in range(1, 6):
        start_day = (w - 1) * 7 + 1
        end_day   = w * 7
        try:
            ws = date(since_dt.year, since_dt.month, start_day)
        except ValueError:
            break
        if start_day > until_dt.day:
            break
        try:
            we = date(since_dt.year, since_dt.month, min(end_day, until_dt.day))
        except ValueError:
            we = until_dt
        ws = max(ws, since_dt)
        we = min(we, until_dt)
        if ws <= we:
            ranges.append((w, ws, we))
    return ranges


def _build_weekly(daily_list: list) -> list:
    """
    주차별 집계: 1~7일=1주차, 8~14일=2주차, 15~21일=3주차,
                22~28일=4주차, 29일~=5주차
    """
    wg = {}
    for row in daily_list:
        day = date.fromisoformat(row["date"]).day
        w = (1 if day <= 7 else 2 if day <= 14 else 3 if day <= 21
             else 4 if day <= 28 else 5)
        if w not in wg:
            wg[w] = {
                "week": w,
                "impressions": 0, "clicks": 0, "cost": 0,
                "conversions": 0, "revenue": 0, "days": 0,
            }
        g = wg[w]
        g["impressions"] += row["impressions"]
        g["clicks"]      += row["clicks"]
        g["cost"]        += row["cost"]
        g["conversions"] += row["conversions"]
        g["revenue"]     += row["revenue"]
        g["days"]        += 1
    return [
        wg.get(w, {
            "week": w, "impressions": 0, "clicks": 0, "cost": 0,
            "conversions": 0, "revenue": 0, "days": 0,
        })
        for w in range(1, 6)
    ]


# ──────────────────────────────────────────────────────────────────────────────
# 자동 운영 코멘트 생성
# ──────────────────────────────────────────────────────────────────────────────

def _auto_comment(curr_sm: dict, prev_sm: dict, kws: list) -> list:
    lines = []
    ci  = _safe_int(curr_sm.get("impressions"))
    pi  = _safe_int(prev_sm.get("impressions"))
    cc  = _safe_int(curr_sm.get("clicks"))
    pc  = _safe_int(prev_sm.get("clicks"))
    cco = _safe_int(curr_sm.get("cost"))
    pco = _safe_int(prev_sm.get("cost"))

    if pi > 0:
        imp_chg = (ci - pi) / pi * 100
        direction = "증가" if imp_chg >= 0 else "감소"
        lines.append(
            f"1. 전월 대비 노출수가 {abs(imp_chg):.1f}% {direction}했습니다"
            f" ({pi:,} → {ci:,}회)."
        )
    else:
        lines.append("1. 전월 노출 데이터 없음 — 이번 달 성과를 기준으로 분석합니다.")

    curr_ctr = cc / ci * 100 if ci > 0 else 0
    prev_ctr = pc / pi * 100 if pi > 0 else 0
    if prev_ctr > 0:
        diff = curr_ctr - prev_ctr
        word = "개선" if diff >= 0 else "하락"
        lines.append(
            f"2. 클릭률이 전월 {prev_ctr:.2f}%에서 {curr_ctr:.2f}%로 {word}되었습니다."
        )
    else:
        lines.append(f"2. 이번 달 클릭률은 {curr_ctr:.2f}%입니다.")

    if pco > 0 and cco > 0:
        cost_chg = (cco - pco) / pco * 100
        lines.append(
            f"3. 총 광고비는 전월 대비 {cost_chg:+.1f}% 변화했습니다"
            f" ({_fmt_won(pco)} → {_fmt_won(cco)})."
        )

    valid_kws = [k for k in kws if k.get("keyword") and k["keyword"] not in ("", "-", None)]
    if valid_kws:
        top_imp = max(valid_kws, key=lambda k: k.get("impressions", 0), default=None)
        if top_imp:
            lines.append(
                f"4. 노출수 1위 키워드 '{top_imp['keyword']}'에 대한 집중 입찰 관리를 권장합니다."
            )

    lines.append(
        "5. 전환 성과 향상을 위해 클릭률 상위 키워드의 랜딩페이지 최적화 및 "
        "소재 테스트를 진행해 주세요."
    )
    return lines


# ──────────────────────────────────────────────────────────────────────────────
# V2 HTML 생성 메인 함수
# ──────────────────────────────────────────────────────────────────────────────

def build_monthly_report_v2(
    data: dict,
    client_name: str,
    report_date: str,
    v2_extra: dict = None,
) -> str:
    """
    월간보고서 V2 HTML 생성
    data      : NaverAdAPI.fetch_report() 반환값
    v2_extra  : fetch_v2_extra() 반환값 (없으면 일자별 섹션 비워짐)
    """
    v2_extra = v2_extra or {}
    since    = data.get("since", "")
    until    = data.get("until", "")
    kws      = data.get("keywords", [])

    # 당월 요약 (캠페인 레벨)
    curr_sm  = data.get("summary", {})
    # 전월 요약
    prev_sm  = v2_extra.get("prev_summary", {})
    prev_since = v2_extra.get("prev_since", "")
    prev_until = v2_extra.get("prev_until", "")

    # 상품별 통계
    product_stats      = v2_extra.get("product_stats",      {})
    product_prev_stats = v2_extra.get("product_prev_stats", {})
    # 데이터가 있는 상품만, PRODUCT_ORDER 순서로 정렬
    active_products = [p for p in PRODUCT_ORDER
                       if p in product_stats and
                       (product_stats[p].get("impressions", 0) > 0 or
                        product_stats[p].get("clicks", 0) > 0)]

    # 일자별/주차별 — 임의 분배 절대 금지, 실제 API 데이터만 사용
    daily_map  = v2_extra.get("daily", {})
    weekly_raw = v2_extra.get("weekly", {})

    # 실제 일자별 데이터 존재 여부 (API timeUnit=DAY 성공 여부)
    has_daily  = bool(daily_map)
    daily_list = _build_daily_list(daily_map, since, until) if has_daily else []

    # 주차별: API 직접 호출 결과 우선 사용
    if weekly_raw:
        weekly_list = [
            {"week": w, **weekly_raw.get(w, {
                "impressions": 0, "clicks": 0, "cost": 0,
                "conversions": 0, "revenue": 0, "days": 0,
            })}
            for w in range(1, 6)
        ]
    else:
        weekly_list = _build_weekly(daily_list)

    # 키워드 (빈값·하이픈 제외)
    valid_kws = [
        k for k in kws
        if k.get("keyword") and k["keyword"] not in ("", "-", "None", None)
    ]
    imp_top10  = sorted(valid_kws, key=lambda k: k.get("impressions", 0), reverse=True)[:10]
    clk_top10  = sorted(valid_kws, key=lambda k: k.get("clicks", 0),      reverse=True)[:10]
    cost_top10 = sorted(valid_kws, key=lambda k: k.get("cost", 0),        reverse=True)[:10]

    # 당월 집계
    ci  = _safe_int(curr_sm.get("impressions"))
    cc  = _safe_int(curr_sm.get("clicks"))
    cco = _safe_int(curr_sm.get("cost"))
    ccv = _safe_int(curr_sm.get("conversions"))
    cr  = _safe_int(curr_sm.get("revenue"))
    # 전월 집계
    pi  = _safe_int(prev_sm.get("impressions"))
    pc  = _safe_int(prev_sm.get("clicks"))
    pco = _safe_int(prev_sm.get("cost"))
    pcv = _safe_int(prev_sm.get("conversions"))
    pr  = _safe_int(prev_sm.get("revenue"))

    def _roas_v2(rev, cost):
        """
        V2 ROAS 계산 — salesAmt 기반 직접 계산
        - revenue = 0 : 'Naver 전환 매출액 미추적'
        - cost = 0    : '-'
        - revenue > 0 : 실제 ROAS 계산
        """
        r, c = _safe_int(rev), _safe_int(cost)
        if c == 0:
            return "-"
        if r == 0:
            return "매출 미추적"
        val = r / c * 100
        return f"{val:.1f}%" if val >= 0 else "검증필요"

    # 운영 코멘트
    comment_lines = _auto_comment(curr_sm, prev_sm, valid_kws)

    # ── 디자인 상수 ────────────────────────────────────────────────────────────
    C_BLUE   = "#0D47A1"
    C_BLUE2  = "#1565C0"
    C_BLUE3  = "#1976D2"
    C_SLATE  = "#546E7A"
    C_GREEN  = "#28B463"
    C_GRAY   = "#F3F4F6"
    C_HBG    = "#E8EAF6"
    C_BORDER = "#DDE3EA"
    C_TEXT   = "#111111"

    # ── HTML 헬퍼 ──────────────────────────────────────────────────────────────
    def sec_bar(text, color=C_BLUE):
        return (
            f'<div style="background:{color};color:#fff;font-size:12px;'
            f'font-weight:700;padding:6px 14px;border-radius:4px 4px 0 0;">'
            f'{text}</div>'
        )

    def th(txt, align="center", w=""):
        wd = f"min-width:{w};" if w else ""
        return (
            f'<th style="{wd}padding:6px 8px;text-align:{align};'
            f'background:{C_HBG};border:1px solid {C_BORDER};'
            f'font-size:11px;font-weight:600;white-space:nowrap;">'
            f'{txt}</th>'
        )

    def td(txt, align="center", bold=False, color="", bg=""):
        fw  = "font-weight:700;" if bold else ""
        cl  = f"color:{color};" if color else ""
        bgs = f"background:{bg};" if bg else ""
        return (
            f'<td style="padding:5px 8px;text-align:{align};'
            f'border:1px solid {C_BORDER};font-size:11px;'
            f'{fw}{cl}{bgs}white-space:nowrap;">'
            f'{txt}</td>'
        )

    # ── 매체별 요약 테이블 (상품별 다중 행) ───────────────────────────────────
    def _media_row(product_name, sm, is_total=False, row_class=""):
        ic = _safe_int(sm.get("impressions"))
        ck = _safe_int(sm.get("clicks"))
        co = _safe_int(sm.get("cost"))
        cv = _safe_int(sm.get("conversions"))
        rv = _safe_int(sm.get("revenue"))
        name_cell = ("TOTAL" if is_total else
                     f'<span style="color:{C_BLUE};font-weight:700;">NAVER</span>')
        prod_cell = ("전체 합산" if is_total else product_name)
        bg_s = f"background:{C_HBG};" if is_total else ""
        attrs = f' class="{row_class}"' if row_class else ""
        rev_cell = _fmt_won(rv) if rv > 0 else "미추적"
        return (
            f"<tr{attrs} style='{bg_s}'>"
            f"{td(name_cell,'center',is_total)}"
            f"{td(prod_cell,'center',is_total)}"
            f"{td(_fmt_num(ic),'right',is_total)}"
            f"{td(_fmt_num(ck),'right',is_total)}"
            f"{td(_ctr(ck,ic),'right',is_total)}"
            f"{td(_cpc_str(co,ck),'right',is_total)}"
            f"{td(_fmt_won(co),'right',is_total)}"
            f"{td(_fmt_num(cv),'right',is_total)}"
            f"{td(rev_cell,'right',is_total)}"
            f"{td(_roas_v2(rv,co),'right',is_total)}"
            f"</tr>"
        )

    def media_table(period_product_stats, period_total_sm):
        """상품별 행 + TOTAL 행 테이블 생성"""
        _thead = f"""<thead><tr>
            {th("매체","center","50px")}
            {th("상품","center","80px")}
            {th("노출수","right")}
            {th("클릭수","right")}
            {th("클릭률","right")}
            {th("평균CPC","right")}
            {th("총광고비","right")}
            {th("전환수","right")}
            {th("전환매출액","right")}
            {th("광고수익률","right")}
          </tr></thead>"""

        product_rows = "".join(
            _media_row(p, period_product_stats.get(p, {}), row_class=f"prow prow-{p}")
            for p in PRODUCT_ORDER
            if p in period_product_stats and
               (period_product_stats[p].get("impressions", 0) > 0 or
                period_product_stats[p].get("clicks", 0) > 0)
        )
        if not product_rows:
            # per-product 데이터 없으면 통합 한 줄
            product_rows = _media_row("검색광고 통합", period_total_sm, row_class="prow prow-all")

        total_row = _media_row("", period_total_sm, is_total=True, row_class="prow prow-all")

        return (
            f'<table style="width:100%;border-collapse:collapse;font-size:11px;">'
            f'{_thead}<tbody>{total_row}{product_rows}</tbody></table>'
            f'<div style="font-size:10px;color:#888;padding:4px 8px;">'
            f'※ Naver 검색광고 계정 전체 (파워링크·쇼핑검색·브랜드검색 등)'
            f'&nbsp;|&nbsp; 전환매출액은 Naver 전환추적 설정 시에만 표시'
            f'&nbsp;|&nbsp; 브랜드검색은 고정비 계약 상품으로 CPC 비용이 API에 나타나지 않을 수 있음'
            f'&nbsp;|&nbsp; GFA/성과형DA: 별도 API 미연동'
            f'</div>'
        )

    # ── 전월대비 비교 테이블 ───────────────────────────────────────────────────
    def cmp_row(label, cv, pv, fmt_fn):
        return (
            f"<tr>{td(label,'left')}"
            f"{td(fmt_fn(pv),'right')}"
            f"{td(fmt_fn(cv),'right',True)}"
            f"{td(_change_html(cv,pv),'center')}</tr>"
        )

    curr_ctr_val = cc / ci * 100 if ci > 0 else 0
    prev_ctr_val = pc / pi * 100 if pi > 0 else 0
    curr_cpc_val = cco // cc if cc > 0 else 0
    prev_cpc_val = pco // pc if pc > 0 else 0
    curr_roas_val = cr / cco * 100 if (cco > 0 and cr > 0) else 0
    prev_roas_val = pr / pco * 100 if (pco > 0 and pr > 0) else 0
    _roas_fmt     = lambda v: f"{_safe_float(v):.1f}%" if _safe_float(v) > 0 else "매출 미추적"

    comparison_html = f"""<table style="width:100%;border-collapse:collapse;font-size:11px;">
      <thead><tr>
        {th("구분","left","100px")}
        {th("전월","right")}
        {th("당월","right")}
        {th("전월대비","center","80px")}
      </tr></thead>
      <tbody>
        {cmp_row("노출수", ci, pi, _fmt_num)}
        {cmp_row("클릭수", cc, pc, _fmt_num)}
        {cmp_row("클릭률(%)", curr_ctr_val, prev_ctr_val, lambda v: f"{_safe_float(v):.2f}%")}
        {cmp_row("평균CPC(원)", curr_cpc_val, prev_cpc_val, lambda v: f"{_safe_int(v):,}원")}
        {cmp_row("총광고비", cco, pco, _fmt_won)}
        {cmp_row("전환수", ccv, pcv, _fmt_num)}
        {cmp_row("전환매출액", cr, pr, lambda v: _fmt_won(v) if v > 0 else "매출 미추적")}
        {cmp_row("광고수익률", curr_roas_val, prev_roas_val, _roas_fmt)}
      </tbody>
    </table>"""

    # ── 주차별 테이블 ──────────────────────────────────────────────────────────
    weekly_rows = ""
    for w in weekly_list:
        wi  = w["impressions"]
        wc  = w["clicks"]
        wco = w["cost"]
        wcv = w["conversions"]
        wr  = w["revenue"]
        wd  = w["days"]
        if wi == 0 and wc == 0 and wd == 0:
            continue
        _wlabel = str(w["week"]) + "주차"
        weekly_rows += (
            f"<tr>"
            f"{td(_wlabel,'center',True,C_BLUE)}"
            f"{td(str(wd) if wd > 0 else '-','center')}"
            f"{td(_fmt_num(wi),'right')}"
            f"{td(_fmt_num(wc),'right')}"
            f"{td(_ctr(wc,wi),'right')}"
            f"{td(_cpc_str(wco,wc),'right')}"
            f"{td(_fmt_won(wco),'right')}"
            f"{td(_fmt_num(wcv),'right')}"
            f"{td(_fmt_won(wr) if wr > 0 else '미추적','right')}"
            f"{td(_roas_v2(wr,wco),'right')}"
            f"</tr>"
        )

    # 주차별 TOTAL: weekly_raw 합산 우선, 없으면 당월 summary
    if weekly_raw:
        ti  = sum(w.get("impressions", 0) for w in weekly_raw.values())
        tc  = sum(w.get("clicks",      0) for w in weekly_raw.values())
        tco = sum(w.get("cost",        0) for w in weekly_raw.values())
        tcv = sum(w.get("conversions", 0) for w in weekly_raw.values())
        tr_ = sum(w.get("revenue",     0) for w in weekly_raw.values())
        td_ = sum(w.get("days",        0) for w in weekly_raw.values())
    else:
        ti, tc, tco, tcv, tr_, td_ = ci, cc, cco, ccv, cr, 0

    weekly_total = (
        f"<tr style='background:{C_HBG};'>"
        f"{td('TOTAL','center',True)}"
        f"{td(str(td_) if td_ > 0 else '-','center',True)}"
        f"{td(_fmt_num(ti),'right',True)}"
        f"{td(_fmt_num(tc),'right',True)}"
        f"{td(_ctr(tc,ti),'right',True)}"
        f"{td(_cpc_str(tco,tc),'right',True)}"
        f"{td(_fmt_won(tco),'right',True)}"
        f"{td(_fmt_num(tcv),'right',True)}"
        f"{td(_fmt_won(tr_) if tr_ > 0 else '미추적','right',True)}"
        f"{td(_roas_v2(tr_,tco),'right',True)}"
        f"</tr>"
    )

    no_data_row = (
        f"<tr><td colspan='10' style='text-align:center;color:#999;"
        f"padding:14px;font-size:11px;'>"
        f"주차별 API 데이터를 불러오지 못했습니다</td></tr>"
    )

    weekly_table = f"""<table style="width:100%;border-collapse:collapse;font-size:11px;">
      <thead><tr>
        {th("주차","center","50px")}
        {th("일수","center","40px")}
        {th("노출수","right")}
        {th("클릭수","right")}
        {th("클릭률","right")}
        {th("평균CPC","right")}
        {th("총광고비","right")}
        {th("전환수","right")}
        {th("전환매출액","right")}
        {th("광고수익률","right")}
      </tr></thead>
      <tbody>
        {weekly_total}
        {weekly_rows if weekly_rows else no_data_row}
      </tbody>
    </table>"""

    # ── 일자별 테이블 (실제 API 데이터 있을 때만 행 표시) ─────────────────────
    _NO_DAILY_MSG = (
        f'<div style="background:#FFF3CD;border:1px solid #FFC107;border-radius:4px;'
        f'padding:14px 18px;font-size:12px;color:#856404;line-height:1.6;">'
        f'<b>일자별 원천 데이터 없음</b><br>'
        f'Naver 검색광고 API가 일자별(timeUnit=DAY) 통계를 제공하지 않습니다.<br>'
        f'주차별 광고요약은 실제 API 데이터를 기반으로 표시됩니다.'
        f'</div>'
    )

    if has_daily:
        daily_rows = ""
        for row in daily_list:
            ri  = row["impressions"]
            rc  = row["clicks"]
            rco = row["cost"]
            rcv = row["conversions"]
            rr  = row["revenue"]
            is_weekend = row["weekday"] in ("토", "일")
            row_bg   = "#FFF8F8" if is_weekend else ""
            wd_color = "#c0392b" if is_weekend else ""
            daily_rows += (
                f"<tr style='background:{row_bg};'>"
                f"{td(row['date'][5:].replace('-','.'),'center')}"
                f"{td(row['weekday'],'center',False,wd_color)}"
                f"{td(_fmt_num(ri),'right')}"
                f"{td(_fmt_num(rc),'right')}"
                f"{td(_ctr(rc,ri),'right')}"
                f"{td(_cpc_str(rco,rc),'right')}"
                f"{td(_fmt_won(rco),'right')}"
                f"{td(_fmt_num(rcv),'right')}"
                f"{td(_roas_v2(rr,rco),'right')}"
                f"</tr>"
            )
        d_ti  = sum(r["impressions"] for r in daily_list)
        d_tc  = sum(r["clicks"]      for r in daily_list)
        d_tco = sum(r["cost"]        for r in daily_list)
        d_tcv = sum(r["conversions"] for r in daily_list)
        d_tr  = sum(r["revenue"]     for r in daily_list)
        daily_total_row = (
            f"<tr style='background:{C_HBG};'>"
            f"{td('합계','center',True)}"
            f"{td('-','center',True)}"
            f"{td(_fmt_num(d_ti),'right',True)}"
            f"{td(_fmt_num(d_tc),'right',True)}"
            f"{td(_ctr(d_tc,d_ti),'right',True)}"
            f"{td(_cpc_str(d_tco,d_tc),'right',True)}"
            f"{td(_fmt_won(d_tco),'right',True)}"
            f"{td(_fmt_num(d_tcv),'right',True)}"
            f"{td(_roas_v2(d_tr,d_tco),'right',True)}"
            f"</tr>"
        )
        daily_table = f"""<table style="width:100%;border-collapse:collapse;font-size:11px;">
          <thead><tr>
            {th("날짜","center","55px")}
            {th("요일","center","35px")}
            {th("노출수","right")}
            {th("클릭수","right")}
            {th("클릭률","right")}
            {th("평균CPC","right")}
            {th("총광고비","right")}
            {th("전환수","right")}
            {th("광고수익률","right")}
          </tr></thead>
          <tbody>
            {daily_total_row}
            {daily_rows}
          </tbody>
        </table>"""
    else:
        daily_table = _NO_DAILY_MSG

    # ── 키워드 TOP10 테이블 ────────────────────────────────────────────────────
    def kw_table_rows(kw_list, val_fn):
        if not kw_list:
            return (
                f"<tr><td colspan='3' style='text-align:center;color:#999;"
                f"padding:12px;font-size:11px;'>데이터 없음</td></tr>"
            )
        rows = ""
        RANK_COLORS = ["#c0392b", "#e67e22", "#f39c12"]
        for i, k in enumerate(kw_list):
            bg = RANK_COLORS[i] if i < 3 else ""
            rank_style = (
                f"background:{bg};color:#fff;font-weight:700;"
                if bg else f"color:{C_BLUE};font-weight:700;"
            )
            rows += (
                f"<tr>"
                f"<td style='padding:5px 8px;text-align:center;"
                f"border:1px solid {C_BORDER};font-size:11px;{rank_style}'>{i+1}</td>"
                f"<td style='padding:5px 8px;text-align:left;"
                f"border:1px solid {C_BORDER};font-size:11px;"
                f"overflow:hidden;text-overflow:ellipsis;white-space:nowrap;"
                f"max-width:130px;'>{k.get('keyword','')}</td>"
                f"<td style='padding:5px 8px;text-align:right;"
                f"border:1px solid {C_BORDER};font-size:11px;"
                f"font-weight:700;'>{val_fn(k)}</td>"
                f"</tr>"
            )
        return rows

    def kw_section(title, rows_html, val_label):
        return f"""
        {sec_bar(title, C_BLUE2)}
        <div style="border:1px solid {C_BORDER};border-radius:0 0 4px 4px;overflow:hidden;">
          <table style="width:100%;border-collapse:collapse;">
            <thead><tr>
              {th("순위","center","30px")}
              {th("키워드","left")}
              {th(val_label,"right","75px")}
            </tr></thead>
            <tbody>{rows_html}</tbody>
          </table>
        </div>"""

    # ── Chart.js 데이터 (JSON) ─────────────────────────────────────────────────
    jd = lambda lst: json.dumps(lst, ensure_ascii=False)

    # 주차별 — 데이터 있는 주차만
    active_weeks = [w for w in weekly_list if w["days"] > 0 or w["impressions"] > 0]
    w_labels = jd([f"{w['week']}주차" for w in active_weeks])
    w_imp    = jd([w["impressions"]   for w in active_weeks])
    w_clk    = jd([w["clicks"]        for w in active_weeks])

    # 일자별
    d_labels = jd([r["date"][5:] for r in daily_list])
    d_imp    = jd([r["impressions"] for r in daily_list])
    d_clk    = jd([r["clicks"]     for r in daily_list])
    d_cost   = jd([r["cost"]       for r in daily_list])
    d_cpc    = jd([r["cost"] // r["clicks"] if r["clicks"] > 0 else 0 for r in daily_list])

    # 키워드 가로 막대
    imp_kw_labels  = jd([k.get("keyword","") for k in imp_top10])
    imp_kw_vals    = jd([k.get("impressions",0) for k in imp_top10])
    clk_kw_labels  = jd([k.get("keyword","") for k in clk_top10])
    clk_kw_vals    = jd([k.get("clicks",0)    for k in clk_top10])
    cost_kw_labels = jd([k.get("keyword","") for k in cost_top10])
    cost_kw_vals   = jd([k.get("cost",0)      for k in cost_top10])

    # 코멘트 HTML
    comment_html = "".join(
        f'<div style="padding:3px 0;font-size:12px;color:{C_TEXT};line-height:1.7;">'
        f'{line}</div>'
        for line in comment_lines
    )

    # ── 상품 필터 탭 HTML + JS 데이터 ─────────────────────────────────────────
    _tab_buttons = ""
    _tab_buttons += (
        '<button class="v2-ptab v2-ptab-active" data-p="all" '
        'onclick="v2FilterProduct(this)">전체</button>'
    )
    for p in PRODUCT_ORDER:
        if p in product_stats and (product_stats[p].get("impressions", 0) > 0 or
                                   product_stats[p].get("clicks", 0) > 0):
            _tab_buttons += (
                f'<button class="v2-ptab" data-p="{p}" '
                f'onclick="v2FilterProduct(this)">{p}</button>'
            )
    _tab_buttons += (
        '<span style="font-size:10px;color:#999;margin-left:8px;">'
        'GFA/성과형DA: 별도 API 미연동</span>'
    )

    _filter_section_html = (
        f'<div style="background:#f0f4f8;padding:10px 16px;border-radius:6px;'
        f'margin-bottom:16px;display:flex;align-items:center;gap:6px;flex-wrap:wrap;">'
        f'<span style="font-size:11px;font-weight:700;color:#0D47A1;margin-right:4px;">'
        f'광고 상품 선택:</span>'
        f'{_tab_buttons}'
        f'</div>'
    )

    # ── 일자별 섹션 HTML (실제 데이터 없으면 완전 비노출) ────────────────────────
    if has_daily:
        _daily_section_html = (
            f'<div class="v2-sec">'
            f'{sec_bar("일자별 광고요약", C_BLUE)}'
            f'<div class="v2-two"><div>{daily_table}</div><div>'
            f'{sec_bar("일자별 노출수 · 클릭수", C_BLUE3)}'
            f'<div class="v2-panel"><div class="v2-chart">'
            f'<canvas id="dailyChart1"></canvas></div></div>'
            f'<div style="height:14px;"></div>'
            f'{sec_bar("일자별 광고비 · 평균CPC", C_BLUE3)}'
            f'<div class="v2-panel"><div class="v2-chart">'
            f'<canvas id="dailyChart2"></canvas></div></div>'
            f'</div></div></div>'
        )
    else:
        _daily_section_html = ""   # 일자별 데이터 없으면 섹션 자체 미표시

    # ── 최종 HTML ─────────────────────────────────────────────────────────────
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<style>
*{{box-sizing:border-box;margin:0;padding:0;}}
html,body{{
  background:#f3f5f8;
  font-family:'Malgun Gothic','Apple SD Gothic Neo',sans-serif;
  font-size:13px;color:{C_TEXT};width:100%;overflow-x:hidden;
}}
.v2-outer{{width:100%;}}
.v2-wrap{{width:100%;max-width:none;background:#fff;overflow:hidden;
  box-shadow:0 2px 16px rgba(0,0,0,.10);}}
.v2-body{{padding:20px 24px;width:100%;}}
.v2-sec{{margin:18px 0;width:100%;}}
.v2-two{{display:flex;gap:16px;width:100%;}}
.v2-two>div{{flex:1;min-width:0;}}
.v2-three{{display:flex;gap:12px;width:100%;}}
.v2-three>div{{flex:1;min-width:0;}}
.v2-panel{{border:1px solid {C_BORDER};border-radius:0 0 4px 4px;
  padding:14px;overflow:hidden;}}
.v2-chart{{position:relative;width:100%;height:220px;}}
.v2-hbar{{position:relative;width:100%;height:280px;}}
canvas{{width:100%!important;max-width:100%!important;}}
.v2-footer{{text-align:center;padding:14px;font-size:11px;color:#aaa;
  border-top:1px solid #eee;width:100%;}}
.v2-ptab{{padding:5px 14px;border:1px solid {C_BLUE};border-radius:20px;
  background:#fff;color:{C_BLUE};font-size:11px;font-weight:600;cursor:pointer;
  transition:all .15s;}}
.v2-ptab:hover{{background:{C_BLUE};color:#fff;}}
.v2-ptab-active{{background:{C_BLUE}!important;color:#fff!important;}}
.prow-hidden{{display:none;}}
@media print{{html,body{{background:#fff;}}.v2-wrap{{box-shadow:none;}}}}
</style>
</head>
<body>
<div class="v2-outer">
<div class="v2-wrap">

<!-- ═══ 헤더 ════════════════════════════════════════════════════════════ -->
<div style="background:{C_BLUE};color:#fff;padding:20px 24px;">
  <div style="display:flex;justify-content:space-between;align-items:center;">
    <div>
      <div style="font-size:10px;letter-spacing:2px;opacity:.7;margin-bottom:4px;">
        NAVER 검색광고 성과 보고서
      </div>
      <div style="font-size:20px;font-weight:700;letter-spacing:-.3px;">
        MONTHLY REPORT
      </div>
      <div style="font-size:12px;opacity:.8;margin-top:6px;">
        분석기간: {since} ~ {until}
        &nbsp;|&nbsp; 광고주: {client_name}
        &nbsp;|&nbsp; 생성일: {report_date}
      </div>
    </div>
    <div style="text-align:right;">
      <div style="font-size:11px;opacity:.7;">총 키워드</div>
      <div style="font-size:30px;font-weight:700;">{len(valid_kws):,}개</div>
    </div>
  </div>
</div>

<div class="v2-body">

<!-- ═══ 상품 필터 탭 ════════════════════════════════════════════════════ -->
{_filter_section_html}

<!-- ═══ COMMENT ════════════════════════════════════════════════════════ -->
<div class="v2-sec">
  {sec_bar("COMMENT")}
  <div style="border:1px solid {C_BORDER};border-radius:0 0 4px 4px;
    background:#F8F9FA;padding:14px 18px;">
    {comment_html}
  </div>
</div>

<!-- ═══ 매체별 전월 / 당월 ════════════════════════════════════════════ -->
<div class="v2-sec">
  <div class="v2-two">
    <div>
      {sec_bar(f"매체별 전월 광고요약 ({prev_since} ~ {prev_until})", C_SLATE)}
      <div class="v2-panel" style="padding:0;">{media_table(product_prev_stats, prev_sm)}</div>
    </div>
    <div>
      {sec_bar(f"매체별 당월 누적 광고요약 ({since} ~ {until})", C_BLUE)}
      <div class="v2-panel" style="padding:0;">{media_table(product_stats, curr_sm)}</div>
    </div>
  </div>
</div>

<!-- ═══ 전월대비 ════════════════════════════════════════════════════════ -->
<div class="v2-sec">
  {sec_bar("전월대비 광고요약", C_BLUE2)}
  <div class="v2-panel" style="padding:0;">{comparison_html}</div>
</div>

<!-- ═══ 주차별 ══════════════════════════════════════════════════════════ -->
<div class="v2-sec">
  <div class="v2-two">
    <div style="flex:1.3;">
      {sec_bar("주차별 광고요약", C_BLUE)}
      <div class="v2-panel" style="padding:0;">{weekly_table}</div>
    </div>
    <div>
      {sec_bar("주차별 광고요약 GRAPH", C_BLUE3)}
      <div class="v2-panel">
        <div class="v2-chart"><canvas id="weeklyChart"></canvas></div>
      </div>
    </div>
  </div>
</div>

{_daily_section_html}

<!-- ═══ 키워드 TOP10 ════════════════════════════════════════════════════ -->
<div class="v2-sec">
  {sec_bar("KEYWORD TOP10", C_BLUE)}
  <div style="height:12px;"></div>
  <div class="v2-three">
    <!-- 노출수 TOP10 -->
    <div>
      {kw_section("노출수 TOP10", kw_table_rows(imp_top10, lambda k: _fmt_num(k.get('impressions',0))), "노출수")}
      <div style="height:10px;"></div>
      {sec_bar("노출수 차트", C_BLUE3)}
      <div class="v2-panel">
        <div class="v2-hbar"><canvas id="kwImpChart"></canvas></div>
      </div>
    </div>
    <!-- 클릭수 TOP10 -->
    <div>
      {kw_section("클릭수 TOP10", kw_table_rows(clk_top10, lambda k: _fmt_num(k.get('clicks',0))), "클릭수")}
      <div style="height:10px;"></div>
      {sec_bar("클릭수 차트", C_BLUE3)}
      <div class="v2-panel">
        <div class="v2-hbar"><canvas id="kwClkChart"></canvas></div>
      </div>
    </div>
    <!-- 광고비 TOP10 -->
    <div>
      {kw_section("광고비 TOP10", kw_table_rows(cost_top10, lambda k: _fmt_won(k.get('cost',0))), "총광고비")}
      <div style="height:10px;"></div>
      {sec_bar("광고비 차트", C_BLUE3)}
      <div class="v2-panel">
        <div class="v2-hbar"><canvas id="kwCostChart"></canvas></div>
      </div>
    </div>
  </div>
</div>

</div><!-- v2-body -->
<div class="v2-footer">
  본 보고서는 {report_date}에 자동 생성되었습니다. &nbsp;|&nbsp; Powered by MarketiP
</div>
</div><!-- v2-wrap -->
</div><!-- v2-outer -->

<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<script>
// ── 주차별 복합 차트 (bar + line) ──────────────────────────────────────────
(function() {{
  var labels = {w_labels};
  var imps   = {w_imp};
  var clks   = {w_clk};
  if (!labels || !labels.length) return;
  new Chart(document.getElementById('weeklyChart'), {{
    type: 'bar',
    data: {{
      labels: labels,
      datasets: [
        {{ type:'bar',  label:'노출수', data:imps, backgroundColor:'rgba(13,71,161,0.7)',
           borderRadius:4, yAxisID:'y' }},
        {{ type:'line', label:'클릭수', data:clks, borderColor:'#e74c3c',
           backgroundColor:'rgba(231,76,60,0.1)', tension:0.3,
           pointRadius:4, yAxisID:'y1' }}
      ]
    }},
    options: {{
      responsive:true, maintainAspectRatio:false,
      plugins:{{ legend:{{ position:'top', labels:{{ font:{{ size:10 }} }} }} }},
      scales:{{
        y:  {{ type:'linear', position:'left',
               ticks:{{ font:{{ size:10 }}, callback:v=>v.toLocaleString() }},
               grid:{{ color:'rgba(0,0,0,0.04)' }} }},
        y1: {{ type:'linear', position:'right',
               ticks:{{ font:{{ size:10 }}, callback:v=>v.toLocaleString() }},
               grid:{{ drawOnChartArea:false }} }},
        x:  {{ ticks:{{ font:{{ size:10 }} }}, grid:{{ display:false }} }}
      }}
    }}
  }});
}})();

// ── 일자별 차트 1: 노출수 + 클릭수 ────────────────────────────────────────
(function() {{
  var labels = {d_labels};
  var imps   = {d_imp};
  var clks   = {d_clk};
  if (!labels || !labels.length) return;
  new Chart(document.getElementById('dailyChart1'), {{
    type: 'bar',
    data: {{
      labels: labels,
      datasets: [
        {{ type:'bar',  label:'노출수', data:imps,
           backgroundColor:'rgba(13,71,161,0.6)', borderRadius:2, yAxisID:'y' }},
        {{ type:'line', label:'클릭수', data:clks,
           borderColor:'#e74c3c', tension:0.2, pointRadius:2, yAxisID:'y1' }}
      ]
    }},
    options: {{
      responsive:true, maintainAspectRatio:false,
      plugins:{{ legend:{{ position:'top', labels:{{ font:{{ size:9 }} }} }} }},
      scales:{{
        y:  {{ ticks:{{ font:{{ size:9 }}, callback:v=>v.toLocaleString() }},
               grid:{{ color:'rgba(0,0,0,0.04)' }} }},
        y1: {{ position:'right',
               ticks:{{ font:{{ size:9 }}, callback:v=>v.toLocaleString() }},
               grid:{{ drawOnChartArea:false }} }},
        x:  {{ ticks:{{ font:{{ size:8 }}, maxRotation:45 }}, grid:{{ display:false }} }}
      }}
    }}
  }});
}})();

// ── 일자별 차트 2: 광고비 + 평균CPC ────────────────────────────────────────
(function() {{
  var labels = {d_labels};
  var costs  = {d_cost};
  var cpcs   = {d_cpc};
  if (!labels || !labels.length) return;
  new Chart(document.getElementById('dailyChart2'), {{
    type: 'bar',
    data: {{
      labels: labels,
      datasets: [
        {{ type:'bar',  label:'총광고비', data:costs,
           backgroundColor:'rgba(40,180,99,0.6)', borderRadius:2, yAxisID:'y' }},
        {{ type:'line', label:'평균CPC', data:cpcs,
           borderColor:'#e67e22', tension:0.2, pointRadius:2, yAxisID:'y1' }}
      ]
    }},
    options: {{
      responsive:true, maintainAspectRatio:false,
      plugins:{{ legend:{{ position:'top', labels:{{ font:{{ size:9 }} }} }} }},
      scales:{{
        y:  {{ ticks:{{ font:{{ size:9 }}, callback:v=>v.toLocaleString() }},
               grid:{{ color:'rgba(0,0,0,0.04)' }} }},
        y1: {{ position:'right',
               ticks:{{ font:{{ size:9 }}, callback:v=>v.toLocaleString() }},
               grid:{{ drawOnChartArea:false }} }},
        x:  {{ ticks:{{ font:{{ size:8 }}, maxRotation:45 }}, grid:{{ display:false }} }}
      }}
    }}
  }});
}})();

// ── 키워드 가로 막대 차트 ────────────────────────────────────────────────────
function makeHBar(canvasId, labels, vals, barColor) {{
  if (!labels || !labels.length) return;
  new Chart(document.getElementById(canvasId), {{
    type: 'bar',
    data: {{
      labels: labels.map(function(l) {{
        return l.length > 12 ? l.substring(0,12)+'…' : l;
      }}),
      datasets: [{{
        data: vals,
        backgroundColor: vals.map(function(_,i) {{
          return i === 0 ? '#e74c3c' : barColor;
        }}),
        borderRadius: 3,
      }}]
    }},
    options: {{
      indexAxis: 'y',
      responsive: true, maintainAspectRatio: false,
      plugins: {{
        legend: {{ display:false }},
        tooltip: {{ callbacks: {{ label: ctx => ctx.raw.toLocaleString() }} }}
      }},
      scales: {{
        x: {{ ticks:{{ font:{{ size:9 }}, callback:v=>v.toLocaleString() }},
               grid:{{ color:'rgba(0,0,0,0.04)' }} }},
        y: {{ ticks:{{ font:{{ size:10 }} }}, grid:{{ display:false }} }}
      }}
    }}
  }});
}}

makeHBar('kwImpChart',  {imp_kw_labels},  {imp_kw_vals},  'rgba(13,71,161,0.7)');
makeHBar('kwClkChart',  {clk_kw_labels},  {clk_kw_vals},  'rgba(33,150,243,0.7)');
makeHBar('kwCostChart', {cost_kw_labels}, {cost_kw_vals}, 'rgba(40,180,99,0.7)');

// ── 상품 필터 탭 ──────────────────────────────────────────────────────────
function v2FilterProduct(btn) {{
  // 탭 버튼 활성화
  document.querySelectorAll('.v2-ptab').forEach(function(b) {{
    b.classList.remove('v2-ptab-active');
  }});
  btn.classList.add('v2-ptab-active');

  var selected = btn.getAttribute('data-p');

  // 매체별 테이블 행 필터 (.prow 클래스)
  document.querySelectorAll('.prow').forEach(function(row) {{
    var cls = row.className || '';
    if (selected === 'all') {{
      row.classList.remove('prow-hidden');
    }} else {{
      // prow-all (TOTAL) 은 항상 표시, 나머지는 선택 상품만
      if (cls.indexOf('prow-all') !== -1) {{
        row.classList.remove('prow-hidden');
      }} else if (cls.indexOf('prow-' + selected) !== -1) {{
        row.classList.remove('prow-hidden');
      }} else {{
        row.classList.add('prow-hidden');
      }}
    }}
  }});
}}
</script>
</body>
</html>"""
