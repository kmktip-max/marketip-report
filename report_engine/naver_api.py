import hashlib
import hmac
import base64
import time
import json
import requests
from datetime import datetime, timedelta

BASE_URL = "https://api.searchad.naver.com"


def _sign(timestamp, method, path, secret_key):
    msg = f"{timestamp}.{method}.{path}"
    return base64.b64encode(
        hmac.new(secret_key.encode(), msg.encode(), hashlib.sha256).digest()
    ).decode()


def _headers(method, path, api_key, secret_key, customer_id):
    ts = str(int(time.time() * 1000))
    return {
        "Content-Type": "application/json; charset=UTF-8",
        "X-Timestamp": ts,
        "X-API-KEY": api_key,
        "X-Customer": str(customer_id),
        "X-Signature": _sign(ts, method, path, secret_key),
    }


class NaverAdAPI:
    def __init__(self, api_key, secret_key, customer_id):
        self.api_key = api_key.strip()
        self.secret_key = secret_key.strip()
        self.customer_id = str(customer_id).strip()

    def _get(self, path, params=None):
        h = _headers("GET", path, self.api_key, self.secret_key, self.customer_id)
        r = requests.get(BASE_URL + path, headers=h, params=params, timeout=30)
        r.raise_for_status()
        return r.json()

    def test_connection(self):
        try:
            result = self._get("/ncc/campaigns")
            return True, f"연결 성공 (캠페인 {len(result)}개)"
        except Exception as e:
            return False, str(e)

    def get_campaigns(self):
        try:
            return self._get("/ncc/campaigns") or []
        except:
            return []

    def get_adgroups(self, campaign_ids):
        all_ag = []
        for i in range(0, len(campaign_ids), 10):
            batch = campaign_ids[i:i+10]
            try:
                r = self._get("/ncc/adgroups", {"campaignIds": ",".join(batch)})
                if isinstance(r, list):
                    all_ag.extend(r)
            except:
                continue
        return all_ag

    def get_keywords(self, adgroup_ids, max_adgroups=79):
        all_kw = []
        for ag_id in adgroup_ids[:max_adgroups]:
            try:
                r = self._get("/ncc/keywords", {"nccAdgroupId": ag_id})
                if isinstance(r, list):
                    all_kw.extend(r)
            except:
                continue
        return all_kw

    def get_stats(self, entity_ids, since, until):
        """통계 조회 - 여러 파라미터 형식 시도"""
        tr = json.dumps({"since": since, "until": until})
        fields = json.dumps(["impCnt", "clkCnt", "salesAmt", "ccnt", "ctr", "ror", "cpConv", "avgRnk"])

        all_stats = []
        for i in range(0, len(entity_ids), 20):
            batch = entity_ids[i:i+20]
            try:
                r = self._get("/stats", {
                    "ids": ",".join(batch),
                    "fields": fields,
                    "timeRange": tr,
                })
                data = r.get("data", []) if isinstance(r, dict) else []
                all_stats.extend(data)
            except:
                continue
        return all_stats

    def fetch_report(self, period="weekly"):
        since, until = get_date_range(period)

        campaigns = self.get_campaigns()
        camp_ids = [c["nccCampaignId"] for c in campaigns]

        adgroups = self.get_adgroups(camp_ids)
        ag_ids = [g["nccAdgroupId"] for g in adgroups]

        keywords = self.get_keywords(ag_ids)
        kw_map = {k["nccKeywordId"]: k.get("keyword", "") for k in keywords}
        kw_ids = list(kw_map.keys())

        stats = self.get_stats(kw_ids, since, until)

        rows = []
        for s in stats:
            kid       = s.get("id", "")
            clicks    = int(s.get("clkCnt", 0))
            imps      = int(s.get("impCnt", 0))
            convs     = int(s.get("ccnt", 0))
            revenue   = int(s.get("salesAmt", 0)) if int(s.get("ccnt", 0)) > 0 else 0
            cpconv    = float(s.get("cpConv", 0))
            api_ror   = float(s.get("ror", 0))

            # 비용: API가 cost 필드 미제공 → cpConv * ccnt 근사
            cost = int(cpconv * convs) if convs > 0 else 0

            # 파생 지표 — 분모 0 방지
            ctr  = round(clicks / imps * 100, 2) if imps > 0 else 0
            cpc  = round(cost / clicks) if clicks > 0 and cost > 0 else 0
            cvr  = round(convs / clicks * 100, 2) if clicks > 0 else 0
            cpa  = round(cost / convs) if convs > 0 and cost > 0 else 0
            roas = round(revenue / cost * 100, 1) if cost > 0 and revenue > 0 else \
                   round(api_ror, 1)

            rows.append({
                "keyword":     kw_map.get(kid, kid),
                "clicks":      clicks,
                "impressions": imps,
                "conversions": convs,
                "revenue":     revenue,
                "cost":        cost,
                "ctr":         ctr,
                "cpc":         cpc,
                "cvr":         cvr,
                "cpa":         cpa,
                "roas":        roas,
                "avg_rnk":     round(s.get("avgRnk", 0), 1),
            })

        return {
            "period": period,
            "since": since,
            "until": until,
            "keywords": rows,
            "total_campaigns": len(campaigns),
            "total_keywords": len(kw_ids),
        }


def get_date_range(period):
    today = datetime.now()
    if period == "weekly":
        until = today - timedelta(days=1)
        since = until - timedelta(days=6)
    else:
        first = today.replace(day=1)
        until = first - timedelta(days=1)
        since = until.replace(day=1)
    return since.strftime("%Y-%m-%d"), until.strftime("%Y-%m-%d")
