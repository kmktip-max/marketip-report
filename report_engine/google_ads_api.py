"""Google Ads API 월간보고서 수집 모듈.

네이버와 완전히 분리된 독립 모듈이다. 이 파일의 어떤 함수도 네이버 API를
호출하지 않으며, 데이터가 없거나 미설정이어도 절대 네이버 데이터로 대체(fallback)
하지 않는다. 미설정/미구현/오류 시에는 ok=False 결과만 반환한다.

필요 환경변수:
  GOOGLE_ADS_DEVELOPER_TOKEN
  GOOGLE_ADS_CLIENT_ID
  GOOGLE_ADS_CLIENT_SECRET
  GOOGLE_ADS_REFRESH_TOKEN
  GOOGLE_ADS_LOGIN_CUSTOMER_ID   (MCC / 매니저 계정 ID)
조회 대상:
  customer_id (광고주 계정 ID) — 광고주별로 관리 화면에서 저장/선택
"""
from __future__ import annotations

import os

# 환경변수 키 목록 (검증·표시에 공통 사용)
REQUIRED_ENV_KEYS = [
    "GOOGLE_ADS_DEVELOPER_TOKEN",
    "GOOGLE_ADS_CLIENT_ID",
    "GOOGLE_ADS_CLIENT_SECRET",
    "GOOGLE_ADS_REFRESH_TOKEN",
    "GOOGLE_ADS_LOGIN_CUSTOMER_ID",
]


def _get_secret(key: str, default: str = "") -> str:
    """st.secrets 우선, 없으면 환경변수."""
    val = ""
    try:
        import streamlit as st
        val = str(st.secrets.get(key, "")) if hasattr(st, "secrets") else ""
    except Exception:
        val = ""
    if not val:
        val = os.getenv(key, default)
    return (val or "").strip()


def check_google_env() -> tuple[bool, list[str]]:
    """필수 환경변수 검증. (ok, 누락키목록) 반환. 절대 API를 호출하지 않는다."""
    missing = [k for k in REQUIRED_ENV_KEYS if not _get_secret(k)]
    return (len(missing) == 0), missing


def is_library_available() -> bool:
    """google-ads 패키지 설치 여부 (호출 없이 import 가능 여부만 확인)."""
    try:
        import importlib.util
        return importlib.util.find_spec("google.ads.googleads") is not None
    except Exception:
        return False


# ── cost_micros 등 단위 변환 ──────────────────────────────────────────────
def _micros_to_unit(micros) -> float:
    """Google Ads의 micros(백만분의 1) → 통화 단위. cost_micros / 1_000_000."""
    try:
        return (int(micros) or 0) / 1_000_000
    except (TypeError, ValueError):
        return 0.0


# ── GAQL 쿼리 정의 (스펙 6번) ─────────────────────────────────────────────
def _gaql(date_since: str, date_until: str) -> dict:
    """기간(YYYY-MM-DD)별 GAQL 쿼리 모음. 날짜는 'YYYY-MM-DD' 문자열."""
    where = f"segments.date BETWEEN '{date_since}' AND '{date_until}'"
    return {
        "campaigns": f"""
            SELECT campaign.id, campaign.name, campaign.advertising_channel_type,
                   metrics.impressions, metrics.clicks, metrics.ctr,
                   metrics.average_cpc, metrics.cost_micros, metrics.conversions,
                   metrics.cost_per_conversion, metrics.conversions_value
            FROM campaign WHERE {where}
        """,
        "ad_groups": f"""
            SELECT ad_group.id, ad_group.name, campaign.name,
                   metrics.impressions, metrics.clicks, metrics.ctr,
                   metrics.average_cpc, metrics.cost_micros, metrics.conversions,
                   metrics.conversions_value
            FROM ad_group WHERE {where}
        """,
        "keywords": f"""
            SELECT ad_group_criterion.keyword.text, campaign.name, ad_group.name,
                   metrics.impressions, metrics.clicks, metrics.ctr,
                   metrics.average_cpc, metrics.cost_micros, metrics.conversions,
                   metrics.conversions_value
            FROM keyword_view WHERE {where}
        """,
        "search_terms": f"""
            SELECT search_term_view.search_term, campaign.name, ad_group.name,
                   metrics.impressions, metrics.clicks, metrics.ctr,
                   metrics.cost_micros, metrics.conversions, metrics.conversions_value
            FROM search_term_view WHERE {where}
        """,
        "daily": f"""
            SELECT segments.date, metrics.impressions, metrics.clicks,
                   metrics.cost_micros, metrics.conversions, metrics.conversions_value
            FROM customer WHERE {where}
        """,
        "device": f"""
            SELECT segments.device, metrics.impressions, metrics.clicks,
                   metrics.cost_micros, metrics.conversions, metrics.conversions_value
            FROM customer WHERE {where}
        """,
    }


def _roas(conversion_value: float, cost: float):
    """ROAS = 전환가치 / 비용 × 100. 전환가치 없거나 0이면 None('-' 표시용).
    절대 비용을 전환가치로 쓰거나 100% 기본값을 쓰지 않는다."""
    if not conversion_value or conversion_value <= 0 or not cost or cost <= 0:
        return None
    return round(conversion_value / cost * 100, 2)


def _empty_report(advertiser_name: str, customer_id: str, period: str) -> dict:
    return {
        "media": "google",
        "advertiser_name": advertiser_name,
        "customer_id": customer_id,
        "period": period,
        "summary": {
            "impressions": 0, "clicks": 0, "ctr": 0, "avg_cpc": 0, "cost": 0,
            "conversions": 0, "cpa": 0, "conversion_value": 0, "roas": None,
        },
        "currency": "KRW",
        "campaigns": [], "ad_groups": [], "keywords": [],
        "search_terms": [], "daily": [], "device": [],
    }


# ── 메인 진입점 ───────────────────────────────────────────────────────────
def fetch_google_monthly_report_data(
    customer_id: str,
    date_since: str,
    date_until: str,
    advertiser_name: str = "",
    login_customer_id: str = "",
    on_step=None,
) -> dict:
    """구글 월간보고서 데이터 수집.

    반환: {"ok": bool, "message": str, "report_data": dict|None}
      - 환경변수 미설정/라이브러리 미설치 → ok=False (네이버 fallback 절대 없음)
      - 성공 → ok=True, report_data = 공통 구조(_empty_report 형태)

    이 함수는 어떤 경우에도 네이버 API를 호출하지 않는다.
    """
    def _step(m):
        if on_step:
            try:
                on_step(m)
            except Exception:
                pass

    # 1) 환경변수 검증 — 없으면 호출하지 않고 안내만
    env_ok, missing = check_google_env()
    if not env_ok:
        return {
            "ok": False,
            "report_data": None,
            "message": (
                "구글 월간보고서 API 연동이 아직 완료되지 않았습니다.\n"
                "누락된 설정: " + ", ".join(missing)
            ),
            "missing_env": missing,
        }
    if not customer_id:
        return {"ok": False, "report_data": None,
                "message": "구글 광고주 Customer ID가 설정되지 않았습니다."}

    # 2) 라이브러리 설치 검증
    if not is_library_available():
        return {
            "ok": False, "report_data": None,
            "message": "google-ads 라이브러리가 설치되지 않았습니다. (pip install google-ads)",
        }

    # 3) 실제 조회
    try:
        from google.ads.googleads.client import GoogleAdsClient  # type: ignore
        cfg = {
            "developer_token": _get_secret("GOOGLE_ADS_DEVELOPER_TOKEN"),
            "client_id":       _get_secret("GOOGLE_ADS_CLIENT_ID"),
            "client_secret":   _get_secret("GOOGLE_ADS_CLIENT_SECRET"),
            "refresh_token":   _get_secret("GOOGLE_ADS_REFRESH_TOKEN"),
            "login_customer_id": (login_customer_id
                                  or _get_secret("GOOGLE_ADS_LOGIN_CUSTOMER_ID")).replace("-", ""),
            "use_proto_plus": True,
        }
        client = GoogleAdsClient.load_from_dict(cfg)
        ga_service = client.get_service("GoogleAdsService")
        cid = str(customer_id).replace("-", "")
        queries = _gaql(date_since, date_until)

        report = _empty_report(advertiser_name, customer_id, f"{date_since} ~ {date_until}")

        def _run(q):
            return ga_service.search(customer_id=cid, query=q)

        # 캠페인
        _step("구글: 캠페인별 성과 조회...")
        for row in _run(queries["campaigns"]):
            m = row.metrics
            cost = _micros_to_unit(m.cost_micros)
            cval = float(getattr(m, "conversions_value", 0) or 0)
            report["campaigns"].append({
                "id": str(row.campaign.id), "name": row.campaign.name,
                "channel": str(row.campaign.advertising_channel_type),
                "impressions": int(m.impressions), "clicks": int(m.clicks),
                "ctr": round(float(m.ctr) * 100, 2),
                "avg_cpc": _micros_to_unit(m.average_cpc), "cost": cost,
                "conversions": float(m.conversions),
                "cpa": _micros_to_unit(getattr(m, "cost_per_conversion", 0)),
                "conversion_value": cval, "roas": _roas(cval, cost),
            })

        # 광고그룹
        _step("구글: 광고그룹별 성과 조회...")
        for row in _run(queries["ad_groups"]):
            m = row.metrics
            cost = _micros_to_unit(m.cost_micros)
            cval = float(getattr(m, "conversions_value", 0) or 0)
            report["ad_groups"].append({
                "id": str(row.ad_group.id), "name": row.ad_group.name,
                "campaign": row.campaign.name,
                "impressions": int(m.impressions), "clicks": int(m.clicks),
                "ctr": round(float(m.ctr) * 100, 2),
                "avg_cpc": _micros_to_unit(m.average_cpc), "cost": cost,
                "conversions": float(m.conversions),
                "conversion_value": cval, "roas": _roas(cval, cost),
            })

        # 키워드
        _step("구글: 키워드별 성과 조회...")
        for row in _run(queries["keywords"]):
            m = row.metrics
            cost = _micros_to_unit(m.cost_micros)
            cval = float(getattr(m, "conversions_value", 0) or 0)
            report["keywords"].append({
                "keyword": row.ad_group_criterion.keyword.text,
                "campaign": row.campaign.name, "ad_group": row.ad_group.name,
                "impressions": int(m.impressions), "clicks": int(m.clicks),
                "ctr": round(float(m.ctr) * 100, 2),
                "avg_cpc": _micros_to_unit(m.average_cpc), "cost": cost,
                "conversions": float(m.conversions),
                "conversion_value": cval, "roas": _roas(cval, cost),
            })

        # 검색어
        _step("구글: 검색어 보고서 조회...")
        for row in _run(queries["search_terms"]):
            m = row.metrics
            cost = _micros_to_unit(m.cost_micros)
            cval = float(getattr(m, "conversions_value", 0) or 0)
            report["search_terms"].append({
                "search_term": row.search_term_view.search_term,
                "campaign": row.campaign.name, "ad_group": row.ad_group.name,
                "impressions": int(m.impressions), "clicks": int(m.clicks),
                "ctr": round(float(m.ctr) * 100, 2), "cost": cost,
                "conversions": float(m.conversions), "conversion_value": cval,
            })

        # 일자별
        _step("구글: 일자별 성과 조회...")
        for row in _run(queries["daily"]):
            m = row.metrics
            cost = _micros_to_unit(m.cost_micros)
            report["daily"].append({
                "date": row.segments.date,
                "impressions": int(m.impressions), "clicks": int(m.clicks),
                "cost": cost, "conversions": float(m.conversions),
                "conversion_value": float(getattr(m, "conversions_value", 0) or 0),
            })

        # 기기별
        _step("구글: 기기별 성과 조회...")
        for row in _run(queries["device"]):
            m = row.metrics
            cost = _micros_to_unit(m.cost_micros)
            report["device"].append({
                "device": str(row.segments.device),
                "impressions": int(m.impressions), "clicks": int(m.clicks),
                "cost": cost, "conversions": float(m.conversions),
                "conversion_value": float(getattr(m, "conversions_value", 0) or 0),
            })

        # summary 집계 (캠페인 합산 기준)
        s = report["summary"]
        for c in report["campaigns"]:
            s["impressions"] += c["impressions"]; s["clicks"] += c["clicks"]
            s["cost"] += c["cost"]; s["conversions"] += c["conversions"]
            s["conversion_value"] += c["conversion_value"]
        s["ctr"] = round(s["clicks"] / s["impressions"] * 100, 2) if s["impressions"] else 0
        s["avg_cpc"] = round(s["cost"] / s["clicks"], 2) if s["clicks"] else 0
        s["cpa"] = round(s["cost"] / s["conversions"], 2) if s["conversions"] else 0
        s["roas"] = _roas(s["conversion_value"], s["cost"])

        return {"ok": True, "report_data": report, "message": "구글 데이터 수집 완료"}

    except Exception as e:  # noqa: BLE001 — 어떤 오류든 네이버로 넘어가지 않게 가둔다
        return {
            "ok": False, "report_data": None,
            "message": f"구글 Ads API 조회 중 오류: {type(e).__name__}: {e}",
        }


def _fmt_won(v) -> str:
    try:
        return f"₩{float(v):,.0f}"
    except (TypeError, ValueError):
        return "-"


def build_google_report_html(report_data: dict, report_date: str = "") -> str:
    """구글 공통 report_data → 월간보고서 HTML.

    네이버 V2 템플릿(네이버 전용 필드 기반)을 재사용하지 않고, 공통 구조에서
    독립적으로 생성한다. media 값에 따라 제목을 '구글 월간 광고 보고서'로 표시.
    전환가치가 없으면 ROAS는 '-'로 표기(임의 계산 금지).
    """
    s = report_data.get("summary", {})
    name = report_data.get("advertiser_name", "")
    period = report_data.get("period", "")
    cur = report_data.get("currency", "KRW")

    roas = s.get("roas")
    roas_str = f"{roas:.2f}%" if isinstance(roas, (int, float)) else "-"
    cval = s.get("conversion_value") or 0
    cval_note = "" if cval > 0 else '<span style="color:#999;">(전환가치 데이터 없음)</span>'

    def _kpi(label, val):
        return (f'<td style="padding:8px 10px;border:1px solid #eee;">'
                f'<div style="font-size:11px;color:#888;">{label}</div>'
                f'<div style="font-size:15px;font-weight:700;">{val}</div></td>')

    def _rows(items, cols):
        out = []
        for it in items[:20]:
            tds = "".join(f'<td style="padding:6px 8px;border:1px solid #eee;">{it.get(c[0], "-")}</td>'
                          for c in cols)
            out.append(f"<tr>{tds}</tr>")
        return "".join(out)

    camp_rows = "".join(
        f'<tr><td style="padding:6px 8px;border:1px solid #eee;">{c.get("name","-")}</td>'
        f'<td style="padding:6px 8px;border:1px solid #eee;text-align:right;">{c.get("impressions",0):,}</td>'
        f'<td style="padding:6px 8px;border:1px solid #eee;text-align:right;">{c.get("clicks",0):,}</td>'
        f'<td style="padding:6px 8px;border:1px solid #eee;text-align:right;">{_fmt_won(c.get("cost",0))}</td>'
        f'<td style="padding:6px 8px;border:1px solid #eee;text-align:right;">{c.get("conversions",0):g}</td>'
        f'<td style="padding:6px 8px;border:1px solid #eee;text-align:right;">'
        f'{(str(round(c["roas"],2))+"%") if isinstance(c.get("roas"),(int,float)) else "-"}</td></tr>'
        for c in report_data.get("campaigns", [])[:30]
    ) or '<tr><td colspan="6" style="padding:10px;color:#999;">데이터 없음</td></tr>'

    return f"""<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">
<title>구글 월간 광고 보고서 - {name}</title></head>
<body style="font-family:'Malgun Gothic',sans-serif;color:#222;max-width:760px;margin:0 auto;padding:20px;">
  <div style="background:linear-gradient(135deg,#1A73E8,#34A853);color:#fff;padding:20px 24px;border-radius:12px;">
    <div style="font-size:13px;opacity:.85;">Google Ads</div>
    <div style="font-size:22px;font-weight:800;">구글 월간 광고 보고서</div>
    <div style="font-size:13px;margin-top:4px;">{name} · {period} · 발행일 {report_date}</div>
  </div>
  <table style="width:100%;border-collapse:collapse;margin-top:18px;">
    <tr>{_kpi("노출수", f"{s.get('impressions',0):,}")}{_kpi("클릭수", f"{s.get('clicks',0):,}")}
        {_kpi("클릭률", f"{s.get('ctr',0)}%")}{_kpi("평균 CPC", _fmt_won(s.get('avg_cpc',0)))}</tr>
    <tr>{_kpi("비용", _fmt_won(s.get('cost',0)))}{_kpi("전환수", f"{s.get('conversions',0):g}")}
        {_kpi("전환당비용(CPA)", _fmt_won(s.get('cpa',0)))}{_kpi("ROAS", roas_str)}</tr>
  </table>
  <div style="font-size:11px;color:#888;margin-top:6px;">전환가치 {_fmt_won(cval)} {cval_note} · 통화 {cur}</div>
  <h3 style="margin-top:22px;font-size:15px;">캠페인별 성과</h3>
  <table style="width:100%;border-collapse:collapse;font-size:12px;">
    <thead><tr style="background:#f5f7fa;">
      <th style="padding:6px 8px;border:1px solid #eee;text-align:left;">캠페인</th>
      <th style="padding:6px 8px;border:1px solid #eee;">노출</th>
      <th style="padding:6px 8px;border:1px solid #eee;">클릭</th>
      <th style="padding:6px 8px;border:1px solid #eee;">비용</th>
      <th style="padding:6px 8px;border:1px solid #eee;">전환</th>
      <th style="padding:6px 8px;border:1px solid #eee;">ROAS</th></tr></thead>
    <tbody>{camp_rows}</tbody>
  </table>
  <div style="font-size:11px;color:#999;margin-top:14px;">
    ※ 구글 Ads API 기준 집계. 전환가치가 없는 항목의 ROAS는 '-'로 표기됩니다.
  </div>
</body></html>"""


def test_google_connection(customer_id: str, login_customer_id: str = "") -> dict:
    """구글 API 연결 테스트 — 최근 30일 캠페인 성과 합계만 조회.

    반환: {"ok": bool, "message": str, "summary": dict|None}
    어떤 경우에도 네이버 API를 호출하지 않는다.
    """
    import datetime as _dt
    env_ok, missing = check_google_env()
    if not env_ok:
        return {"ok": False, "summary": None,
                "message": "환경변수 미설정: " + ", ".join(missing)}
    if not customer_id:
        return {"ok": False, "summary": None,
                "message": "Google Customer ID가 없습니다."}
    if not is_library_available():
        return {"ok": False, "summary": None,
                "message": "google-ads 라이브러리 미설치 (pip install google-ads)"}

    until = _dt.date.today()
    since = until - _dt.timedelta(days=30)
    res = fetch_google_monthly_report_data(
        customer_id, since.strftime("%Y-%m-%d"), until.strftime("%Y-%m-%d"),
        login_customer_id=login_customer_id,
    )
    if not res.get("ok"):
        # API 에러 메시지를 사람이 이해하기 쉽게 정리
        raw = res.get("message", "")
        hint = ""
        low = raw.lower()
        # 기본 액세스 승인 대기(테스트 액세스)를 가장 먼저 식별 — 정상 대기 상태
        if ("test account" in low or "not_approved" in low
                or "basic or standard" in low):
            hint = (" ⏳ 기본 액세스 승인 대기 중입니다 (개발자 토큰이 아직 테스트 액세스). "
                    "구글 승인 후 자동으로 실데이터가 조회됩니다 — 설정은 정상입니다.")
        elif "refresh" in low or "invalid_grant" in low:
            hint = " (Refresh Token 오류)"
        elif "customer" in low and "not" in low:
            hint = " (Customer ID 오류 — 광고주 계정 번호 확인)"
        elif "permission" in low or "denied" in low:
            hint = " (권한 없음 — MCC에 광고주 계정 연결 확인)"
        return {"ok": False, "summary": None, "message": raw + hint}

    rd = res["report_data"]
    s = rd["summary"]
    return {
        "ok": True,
        "summary": {
            "customer_id": rd.get("customer_id", customer_id),
            "campaigns": len(rd.get("campaigns", [])),
            "impressions": s.get("impressions", 0),
            "clicks": s.get("clicks", 0),
            "cost": s.get("cost", 0),
        },
        "message": "구글 API 연결 성공",
    }
