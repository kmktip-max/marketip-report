import hashlib
import hmac
import base64
import time
import json
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
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


def _dedup(items, key):
    seen, result = set(), []
    for item in items:
        k = item.get(key)
        if k and k not in seen:
            seen.add(k)
            result.append(item)
    return result


class NaverAdAPI:
    def __init__(self, api_key, secret_key, customer_id):
        self.api_key     = api_key.strip()
        self.secret_key  = secret_key.strip()
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
            return _dedup(self._get("/ncc/campaigns") or [], "nccCampaignId")
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
        return _dedup(all_ag, "nccAdgroupId")

    def get_keywords(self, adgroup_ids):
        def _fetch(ag_id):
            try:
                r = self._get("/ncc/keywords", {"nccAdgroupId": ag_id})
                return r if isinstance(r, list) else []
            except:
                return []

        all_kw = []
        with ThreadPoolExecutor(max_workers=10) as ex:
            for f in as_completed([ex.submit(_fetch, ag) for ag in adgroup_ids]):
                all_kw.extend(f.result())
        return _dedup(all_kw, "nccKeywordId")

    def get_stats(self, entity_ids, since, until):
        _s = since.isoformat() if hasattr(since, "isoformat") else str(since)
        _u = until.isoformat() if hasattr(until, "isoformat") else str(until)
        tr     = json.dumps({"since": _s, "until": _u})
        fields = json.dumps(["impCnt", "clkCnt", "salesAmt", "ccnt", "ctr", "ror", "cpConv", "avgRnk"])
        batches = [entity_ids[i:i+100] for i in range(0, len(entity_ids), 100)]

        def _fetch(batch):
            try:
                r = self._get("/stats", {
                    "ids":       ",".join(batch),
                    "fields":    fields,
                    "timeRange": tr,
                })
                return r.get("data", []) if isinstance(r, dict) else []
            except:
                return []

        all_stats = []
        with ThreadPoolExecutor(max_workers=20) as ex:
            for f in as_completed([ex.submit(_fetch, b) for b in batches]):
                all_stats.extend(f.result())
        return _dedup(all_stats, "id")

    def _parse_row(self, s, keyword=None):
        clicks  = int(s.get("clkCnt", 0))
        imps    = int(s.get("impCnt", 0))
        convs   = int(s.get("ccnt", 0))
        cpconv  = float(s.get("cpConv", 0))
        api_ror = float(s.get("ror", 0))
        revenue = int(s.get("salesAmt", 0)) if convs > 0 else 0
        cost    = int(cpconv * convs)        if convs > 0 else 0

        ctr  = round(clicks / imps  * 100, 2) if imps  > 0 else 0
        cpc  = round(cost   / clicks)          if clicks > 0 and cost > 0 else 0
        cvr  = round(convs  / clicks * 100, 2) if clicks > 0 else 0
        cpa  = round(cost   / convs)            if convs  > 0 and cost > 0 else 0
        roas = round(revenue / cost * 100, 1)   if cost   > 0 and revenue > 0 else round(api_ror, 1)

        row = {
            "id":          s.get("id", ""),
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
            "avg_rnk":     round(float(s.get("avgRnk", 0)), 1),
        }
        if keyword is not None:
            row["keyword"] = keyword
        return row

    def fetch_report(self, period="weekly", on_step=None, since=None, until=None):
        def _step(msg):
            if callable(on_step):
                on_step(msg)

        if since is not None and until is not None:
            if isinstance(since, str): since = date.fromisoformat(since)
            if isinstance(until, str): until = date.fromisoformat(until)
        else:
            since, until = get_date_range(period)
        debug_log = []

        # ── 1. 캠페인 목록 ────────────────────────────────────────────
        _step("캠페인 목록 조회 중...")
        campaigns = self.get_campaigns()
        camp_ids  = [c["nccCampaignId"] for c in campaigns]
        camp_map  = {c["nccCampaignId"]: c.get("name", c["nccCampaignId"]) for c in campaigns}
        _step(f"✅ 캠페인 {len(campaigns)}개 확인")
        debug_log.append(f"캠페인 수: {len(campaigns)} | IDs: {camp_ids}")

        # ── 2. 캠페인 통계 + 광고그룹 목록 병렬 수집 ─────────────────
        _step(f"캠페인 통계 + 광고그룹 조회 중... (병렬)")
        with ThreadPoolExecutor(max_workers=2) as ex:
            f_cstat = ex.submit(self.get_stats, camp_ids, since, until)
            f_ag    = ex.submit(self.get_adgroups, camp_ids)
            camp_stats = f_cstat.result()
            adgroups   = f_ag.result()

        ag_ids = [g["nccAdgroupId"] for g in adgroups]
        _step(f"✅ 광고그룹 {len(adgroups)}개 확인")
        debug_log.append(f"캠페인 통계 row: {len(camp_stats)}")
        debug_log.append(f"광고그룹 수: {len(adgroups)}")

        # ── 3. 키워드 목록 + 키워드 통계 병렬 수집 ───────────────────
        _step(f"키워드 목록 조회 중... (광고그룹 {len(ag_ids)}개)")
        keywords  = self.get_keywords(ag_ids)
        kw_map    = {k["nccKeywordId"]: k.get("keyword", "") for k in keywords}
        kw_ids    = list(kw_map.keys())
        batches   = max(1, (len(kw_ids) + 99) // 100)
        _step(f"키워드 통계 수집 중... (키워드 {len(kw_ids)}개 · {batches}배치)")
        kw_stats  = self.get_stats(kw_ids, since, until)
        _step(f"✅ 키워드 {len(kw_ids)}개 통계 수집 완료")
        debug_log.append(f"키워드 수: {len(kw_ids)} | 키워드 통계 row: {len(kw_stats)}")

        # ── 4. 캠페인 레벨 집계 (KPI 카드 + 캠페인 테이블) ──────────
        summary    = {"clicks": 0, "impressions": 0, "conversions": 0, "revenue": 0, "cost": 0}
        camp_table = []
        for s in camp_stats:
            row = self._parse_row(s)
            for k in summary:
                summary[k] += row[k]
            camp_table.append({
                "캠페인ID":  row["id"],
                "캠페인명":  camp_map.get(row["id"], row["id"]),
                "노출수":    row["impressions"],
                "클릭수":    row["clicks"],
                "CTR(%)":   row["ctr"],
                "평균CPC":   row["cpc"],
                "비용":      row["cost"],
                "전환수":    row["conversions"],
                "전환매출":  row["revenue"],
            })
        debug_log.append(
            f"캠페인 레벨 합계 — 클릭: {summary['clicks']:,} / 노출: {summary['impressions']:,}"
        )

        # ── 5. 키워드 레벨 집계 ──────────────────────────────────────
        kw_rows = [self._parse_row(s, kw_map.get(s.get("id", ""), s.get("id", "")))
                   for s in kw_stats]
        kw_summary = {
            "clicks":      sum(r["clicks"]      for r in kw_rows),
            "impressions": sum(r["impressions"] for r in kw_rows),
            "conversions": sum(r["conversions"] for r in kw_rows),
            "revenue":     sum(r["revenue"]     for r in kw_rows),
            "cost":        sum(r["cost"]        for r in kw_rows),
        }
        debug_log.append(
            f"키워드 레벨 합계 — 클릭: {kw_summary['clicks']:,} / 노출: {kw_summary['impressions']:,}"
        )

        since_s = since.isoformat() if hasattr(since, "isoformat") else str(since)
        until_s = until.isoformat() if hasattr(until, "isoformat") else str(until)

        return {
            "period":    period,
            "since":     since_s,
            "until":     until_s,
            "keywords":  kw_rows,
            "summary":   summary,
            "kw_summary": kw_summary,
            "camp_table": camp_table,
            "total_campaigns": len(campaigns),
            "total_keywords":  len(kw_ids),
            "debug": debug_log,
            "debug_params": {
                "customer_id":     self.customer_id,
                "since":           since_s,
                "until":           until_s,
                "endpoint":        BASE_URL + "/stats",
                "fields":          "impCnt,clkCnt,salesAmt,ccnt,ctr,ror,cpConv,avgRnk",
                "camp_stat_rows":  len(camp_stats),
                "kw_stat_rows":    len(kw_stats),
                "total_campaigns": len(campaigns),
                "total_adgroups":  len(adgroups),
                "total_keywords":  len(kw_ids),
            },
        }


def get_date_range(period):
    today = datetime.now(KST).date()
    if period == "weekly":
        until = today - timedelta(days=1)
        since = until - timedelta(days=6)
    else:
        first = today.replace(day=1)
        until = first - timedelta(days=1)
        since = until.replace(day=1)
    return since.strftime("%Y-%m-%d"), until.strftime("%Y-%m-%d")
