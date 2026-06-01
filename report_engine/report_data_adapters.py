"""
보고서 데이터 정규화 어댑터
각 플랫폼 raw 데이터 → V2 보고서 표준 구조 변환

표준 구조:
{
  "platform":       str,   # "naver" | "google" | "kakao" | "daangn"
  "period":         {"since": str, "until": str},
  "summary":        {impressions, clicks, cost, conversions, revenue},
  "prev_summary":   {동일},
  "prev_since":     str,
  "prev_until":     str,
  "daily":          {date_str: {impressions, clicks, cost, conversions, revenue}},
  "weekly":         {week_num(int): {impressions, clicks, cost, conversions, revenue, days}},
  "keywords":       [{keyword, impressions, clicks, cost, conversions, revenue, ctr, cpc, roas}],
  "total_keywords": int,
  "debug":          [str],
}
"""


def _empty_summary():
    return {"impressions": 0, "clicks": 0, "cost": 0, "conversions": 0, "revenue": 0}


# ──────────────────────────────────────────────────────────────────────────────
# 네이버 검색광고
# ──────────────────────────────────────────────────────────────────────────────

def normalize_naver_data(fetch_report_data: dict, v2_extra: dict = None) -> dict:
    """
    NaverAdAPI.fetch_report() + fetch_v2_extra() 결과를 표준 구조로 변환
    """
    v2e = v2_extra or {}
    return {
        "platform":       "naver",
        "period":         {
            "since": fetch_report_data.get("since", ""),
            "until": fetch_report_data.get("until", ""),
        },
        "summary":        fetch_report_data.get("summary", _empty_summary()),
        "prev_summary":   v2e.get("prev_summary", _empty_summary()),
        "prev_since":     v2e.get("prev_since", ""),
        "prev_until":     v2e.get("prev_until", ""),
        "daily":          v2e.get("daily", {}),
        "weekly":         v2e.get("weekly", {}),
        "keywords":       fetch_report_data.get("keywords", []),
        "total_keywords": fetch_report_data.get("total_keywords", 0),
        "debug":          v2e.get("debug", []),
    }


# ──────────────────────────────────────────────────────────────────────────────
# 구글 광고 (엑셀 업로드 기반 — 추후 구현)
# ──────────────────────────────────────────────────────────────────────────────

def normalize_google_excel_data(file) -> dict:
    """
    구글 월간보고서 엑셀 파일 → 표준 구조 변환
    TODO: openpyxl/pandas 로 파싱 후 매핑
    """
    return {
        "platform":       "google",
        "period":         {"since": "", "until": ""},
        "summary":        _empty_summary(),
        "prev_summary":   _empty_summary(),
        "prev_since":     "",
        "prev_until":     "",
        "daily":          {},
        "weekly":         {},
        "keywords":       [],
        "total_keywords": 0,
        "debug":          ["Google Ads 엑셀 업로드 기능 준비 중"],
        "_stub":          True,
    }


def normalize_google_ads_api_data(raw: dict) -> dict:
    """
    Google Ads API 데이터 → 표준 구조 변환
    TODO: Google Ads API 연동 후 구현
    """
    return {
        "platform": "google",
        "_stub":    True,
        "debug":    ["Google Ads API 연동 준비 중"],
    }


# ──────────────────────────────────────────────────────────────────────────────
# 카카오 광고 (추후 구현)
# ──────────────────────────────────────────────────────────────────────────────

def normalize_kakao_data(raw: dict) -> dict:
    """카카오 광고 API 데이터 → 표준 구조 변환 (추후 구현)"""
    return {
        "platform": "kakao",
        "_stub":    True,
        "debug":    ["카카오 광고 API 연동 준비 중"],
    }


# ──────────────────────────────────────────────────────────────────────────────
# 당근마켓 광고 (추후 구현)
# ──────────────────────────────────────────────────────────────────────────────

def normalize_daangn_data(raw: dict) -> dict:
    """당근마켓 광고 API 데이터 → 표준 구조 변환 (추후 구현)"""
    return {
        "platform": "daangn",
        "_stub":    True,
        "debug":    ["당근마켓 광고 API 연동 준비 중"],
    }
