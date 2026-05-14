import hashlib
import hmac
import base64
import time
import json
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
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
        targets = adgroup_ids[:max_adgroups]

        def _fetch(ag_id):
            try:
                r = self._get("/ncc/keywords", {"nccAdgroupId": ag_id})
                return r if isinstance(r, list) else []
            except:
                return []

        all_kw = []
        with ThreadPoolExecutor(max_workers=10) as ex:
            futures = {ex.submit(_fetch, ag_id): ag_id for ag_id in targets}
            for f in as_completed(futures):
                all_kw.extend(f.result())
        return all_kw

    def get_stats(self, entity_ids, since, until):
        tr = json.dumps({"since": since, "until": until})
        fields = json.dumps(["impCnt", "clkCnt", "salesAmt", "ccnt", "ctr", "ror", "cpConv", "avgRnk"])
        batches = [entity_ids[i:i+20] for i in range(0, len(entity_ids), 20)]

        def _fetch(batch):
            try:
                r = self._get("/stats", {
                    "ids": ",".join(batch),
                    "fields": fields,
                    "timeRange": tr,
                })
                return r.get("data", []) if isinstance(r, dict) else []
            except:
                return []

        all_stats = []
        with ThreadPoolExecutor(max_workers=10) as ex:
            futures = [ex.submit(_fetch, b) for b in batches]
            for f in as_completed(futures):
                all_stats.extend(f.result())
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

        # 캠페인 레벨 통계 (KPI 요약용) + 키워드 레벨 통계 병렬 수집
        with ThreadPoolExecutor(max_workers=2) as ex:
            f_camp  = ex.submit(self.get_stats, camp_ids, since, until)
            f_kw    = ex.submit(self.get_stats, kw_ids,   since, until)
            camp_stats = f_camp.result()
            stats      = f_kw.result()

        # 캠페인 레벨 합산 (KPI 카드용)
        summary = {"clicks": 0, "impressions": 0, "conversions": 0, "revenue": 0, "cost": 0}
        for s in camp_stats:
            convs  = int(s.get("ccnt", 0))
            cpconv = float(s.get("cpConv", 0))
            summary["clicks"]      += int(s.get("clkCnt", 0))
            summary["impressions"] += int(s.get("impCnt", 0))
            summary["conversions"] += convs
            summary["revenue"]     += int(s.get("salesAmt", 0)) if convs > 0 else 0
            summary["cost"]        += int(cpconv * convs) if convs > 0 else 0

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
            "summary": summary,
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
