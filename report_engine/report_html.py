from jinja2 import Template
import json

TEMPLATE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<style>
*{box-sizing:border-box;margin:0;padding:0;}
body{font-family:'Malgun Gothic',sans-serif;font-size:13px;color:#222;background:#f5f7fa;padding:20px;}
.rpt{max-width:860px;margin:0 auto;background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.08);}
.rpt-header{background:#0D47A1;color:#fff;padding:18px 24px;display:flex;justify-content:space-between;align-items:center;}
.rpt-header-title{font-size:16px;font-weight:600;}
.rpt-header-sub{font-size:11px;opacity:0.75;margin-top:4px;}
.rpt-body{padding:20px;}
.section{margin:18px 0;}
.section-bar{background:#0D47A1;color:#fff;font-size:12px;font-weight:500;padding:5px 12px;border-radius:4px;margin-bottom:10px;}
.kpi-row{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin-bottom:12px;}
.kpi{background:#f0f4f8;border-radius:6px;padding:10px 12px;text-align:center;}
.kpi-label{font-size:11px;color:#666;margin-bottom:4px;}
.kpi-val{font-size:18px;font-weight:600;color:#0D47A1;}
.two-col{display:grid;grid-template-columns:1fr 1fr;gap:12px;}
.three-col{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;}
.panel{background:#fff;border:1px solid #dde3ea;border-radius:6px;padding:12px;}
.panel-title{font-size:12px;font-weight:500;color:#555;border-bottom:1px solid #eee;padding-bottom:6px;margin-bottom:8px;}
.rtable{width:100%;border-collapse:collapse;font-size:11px;}
.rtable th{background:#f0f4f8;color:#444;font-weight:600;padding:6px;text-align:left;border-bottom:1px solid #dde3ea;}
.rtable td{padding:5px 6px;border-bottom:1px solid #f0f0f0;color:#333;}
.rtable tr:last-child td{border-bottom:none;}
.rtable .num{text-align:right;}
.rtable .hi{color:#0D47A1;font-weight:600;}
.rtable tfoot td{font-weight:600;background:#f7f9fb;}
.badge{display:inline-block;font-size:10px;padding:1px 7px;border-radius:3px;}
.badge-g{background:#dcfce7;color:#166534;}
.badge-r{background:#fee2e2;color:#991b1b;}
.chart-wrap{position:relative;width:100%;height:220px;}
.pie-wrap{position:relative;height:160px;}
.leg{font-size:10px;color:#666;margin-top:6px;display:flex;flex-wrap:wrap;gap:4px;}
.footer{text-align:center;padding:16px;font-size:11px;color:#999;border-top:1px solid #eee;}
</style>
</head>
<body>
<div class="rpt">
<div class="rpt-header">
  <div>
    <div class="rpt-header-title">검색광고 키워드 성과 보고서</div>
    <div class="rpt-header-sub">분석 기간: {{ since }} ~ {{ until }} &nbsp;|&nbsp; {{ client_name }} 귀중</div>
  </div>
  <div style="text-align:right;">
    <div style="font-size:11px;opacity:0.75;">총 키워드 수</div>
    <div style="font-size:22px;font-weight:600;">{{ total_keywords }}개</div>
  </div>
</div>
<div class="rpt-body">

<div class="section">
<div class="section-bar">종합 성과 요약</div>
<div class="kpi-row">
  <div class="kpi"><div class="kpi-label">총 클릭수</div><div class="kpi-val">{{ total_clicks_str }}</div></div>
  <div class="kpi"><div class="kpi-label">총 노출수</div><div class="kpi-val">{{ total_impressions_str }}</div></div>
  <div class="kpi"><div class="kpi-label">평균 CTR</div><div class="kpi-val">{{ avg_ctr_str }}</div></div>
  <div class="kpi"><div class="kpi-label">총 전환매출</div><div class="kpi-val">{{ total_revenue_str }}</div></div>
  <div class="kpi"><div class="kpi-label">평균 노출순위</div><div class="kpi-val">{{ avg_rnk_str }}</div></div>
</div>
</div>

<div class="section">
<div class="section-bar">클릭수 순위 키워드 TOP10</div>
<div class="chart-wrap"><canvas id="costBar"></canvas></div>
</div>

<div class="section">
<div class="two-col">
  <div>
    <div class="section-bar">ROAS 순위 TOP10</div>
    <div class="panel" style="padding:0;">
      <table class="rtable">
        <thead><tr><th>키워드</th><th class="num">ROAS</th><th class="num">전환수</th><th class="num">비용(원)</th></tr></thead>
        <tbody>
        {% for r in roas_top10 %}
          <tr><td>{{ r.keyword }}</td><td class="num hi">{{ r.roas }}%</td><td class="num">{{ r.conversions }}</td><td class="num">{{ '{:,}'.format(r.cost) }}</td></tr>
        {% endfor %}
        </tbody>
        <tfoot><tr><td colspan="2">합계</td><td class="num">{{ roas_top10_conv }}</td><td class="num">{{ '{:,}'.format(roas_top10_cost) }}</td></tr></tfoot>
      </table>
    </div>
  </div>
  <div>
    <div class="section-bar">CPA 우수 키워드 TOP10</div>
    <div class="panel" style="padding:0;">
      <table class="rtable">
        <thead><tr><th>키워드</th><th class="num">CPA(원)</th><th class="num">전환수</th><th class="num">전환율</th></tr></thead>
        <tbody>
        {% for r in cpa_top10 %}
          <tr><td>{{ r.keyword }}</td><td class="num hi">{{ '{:,}'.format(r.cpa) }}</td><td class="num">{{ r.conversions }}</td><td class="num">{{ r.ctr }}%</td></tr>
        {% endfor %}
        </tbody>
        <tfoot><tr><td colspan="2">평균 CPA</td><td class="num" colspan="2">{{ avg_cpa_str }}</td></tr></tfoot>
      </table>
    </div>
  </div>
</div>
</div>

<div class="section">
<div class="section-bar">비용 상위 키워드 (매출 미집계 포함)</div>
<div class="panel" style="padding:0;">
<table class="rtable">
<thead><tr><th>키워드</th><th class="num">총비용(원)</th><th class="num">클릭수</th><th class="num">전환수</th><th class="num">전환율</th><th>상태</th></tr></thead>
<tbody>
{% for r in cost_top %}
<tr>
  <td>{{ r.keyword }}</td>
  <td class="num">{{ '{:,}'.format(r.cost) }}</td>
  <td class="num">{{ r.clicks }}</td>
  <td class="num">{{ r.conversions }}</td>
  <td class="num">{{ r.ctr }}%</td>
  <td><span class="badge {{ 'badge-g' if r.revenue > 0 else 'badge-r' }}">{{ '매출있음' if r.revenue > 0 else '매출없음' }}</span></td>
</tr>
{% endfor %}
</tbody>
</table>
</div>
</div>

</div>
<div class="footer">본 보고서는 {{ report_date }}에 자동 생성되었습니다. &nbsp;|&nbsp; admarketip.com</div>
</div>

<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<script>
const costData = {{ cost_chart_json }};
new Chart(document.getElementById('costBar'),{
  type:'bar',
  data:{
    labels:costData.map(d=>d.k),
    datasets:[{data:costData.map(d=>d.v),backgroundColor:costData.map((_,i)=>i===0?'#c0392b':'#0D47A1'),borderRadius:3}]
  },
  options:{
    responsive:true,maintainAspectRatio:false,
    plugins:{legend:{display:false},tooltip:{callbacks:{label:ctx=>ctx.raw.toLocaleString()+'원'}}},
    scales:{x:{ticks:{font:{size:11}},grid:{display:false}},y:{ticks:{callback:v=>Math.round(v/10000)+'만',font:{size:10}}}}
  }
});
</script>
</body>
</html>"""


def _fmt(n):
    if n >= 10_000_000:
        return f"{n//10_000_000}천{(n%10_000_000)//10_000:,}만"
    if n >= 10_000:
        return f"{n//10_000:,}만"
    return f"{n:,}원"


def generate_html(data, client_name, report_date):
    kws = data["keywords"]
    since, until = data["since"], data["until"]

    total_clicks = sum(k["clicks"] for k in kws)
    total_impressions = sum(k["impressions"] for k in kws)
    total_conv = sum(k["conversions"] for k in kws)
    total_revenue = sum(k["revenue"] for k in kws)
    avg_ctr = round(sum(k["ctr"] for k in kws) / len(kws), 2) if kws else 0
    avg_rnk = round(sum(k.get("roas", 0) for k in kws) / len(kws), 1) if kws else 0

    by_clicks = sorted(kws, key=lambda x: x["clicks"], reverse=True)
    roas_top10 = sorted([k for k in kws if k["roas"] > 0], key=lambda x: x["roas"], reverse=True)[:10]
    cpa_top10 = sorted([k for k in kws if k["cpa"] > 0], key=lambda x: x["cpa"])[:10]

    ctx = {
        "client_name": client_name,
        "since": since, "until": until,
        "report_date": report_date,
        "total_keywords": len(kws),
        "total_clicks_str": f"{total_clicks:,}회",
        "total_impressions_str": f"{total_impressions:,}회",
        "total_conv_str": f"{total_conv:,}건",
        "total_revenue_str": _fmt(total_revenue) if total_revenue > 0 else "미집계",
        "avg_ctr_str": f"{avg_ctr}%",
        "avg_rnk_str": f"{avg_rnk}위",
        "avg_cpa_str": "미집계",
        "roas_top10": roas_top10,
        "roas_top10_conv": sum(k["conversions"] for k in roas_top10),
        "roas_top10_cost": sum(k["cost"] for k in roas_top10),
        "cpa_top10": cpa_top10,
        "cost_top": by_clicks[:10],
        "cost_chart_json": json.dumps([{"k": k["keyword"], "v": k["clicks"]} for k in by_clicks[:10]]),
    }
    return Template(TEMPLATE).render(**ctx)
