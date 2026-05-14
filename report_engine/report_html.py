import json


def _fmt(n):
    if n >= 10_000_000:
        return f"{n//10_000_000}천{(n % 10_000_000)//10_000:,}만"
    if n >= 10_000:
        return f"{n//10_000:,}만"
    return f"{n:,}원"


def generate_html(data, client_name, report_date):
    kws = data["keywords"]
    since, until = data["since"], data["until"]
    period_label = "주간" if data.get("period") == "weekly" else "월간"

    total_clicks = sum(k["clicks"] for k in kws)
    total_impressions = sum(k["impressions"] for k in kws)
    total_conv = sum(k["conversions"] for k in kws)
    total_revenue = sum(k["revenue"] for k in kws)
    avg_ctr = round(total_clicks / total_impressions * 100, 2) if total_impressions else 0

    by_clicks = sorted(kws, key=lambda x: x["clicks"], reverse=True)[:10]
    roas_top10 = sorted([k for k in kws if k["roas"] > 0], key=lambda x: x["roas"], reverse=True)[:10]
    cpa_top10 = sorted([k for k in kws if k["cpa"] > 0], key=lambda x: x["cpa"])[:10]
    no_rev_top = sorted([k for k in kws if k["revenue"] == 0 and k["clicks"] > 0],
                        key=lambda x: x["clicks"], reverse=True)[:7]

    cost_chart = json.dumps([{"k": k["keyword"], "v": k["clicks"]} for k in by_clicks])
    pie_click = json.dumps([{"k": k["keyword"], "v": k["clicks"]} for k in by_clicks[:5]])
    pie_conv = json.dumps([{"k": k["keyword"], "v": k["conversions"]} for k in
                            sorted(kws, key=lambda x: x["conversions"], reverse=True)[:5]])
    pie_rev = json.dumps([{"k": k["keyword"], "v": k["revenue"]} for k in
                           sorted(kws, key=lambda x: x["revenue"], reverse=True)[:5]])

    def kpi(label, val):
        return f'<div class="kpi"><div class="kpi-label">{label}</div><div class="kpi-val">{val}</div></div>'

    def tr_roas(r):
        return (f'<tr><td>{r["keyword"]}</td>'
                f'<td class="num hi">{r["roas"]}%</td>'
                f'<td class="num">{r["conversions"]}</td>'
                f'<td class="num">{_fmt(r["revenue"]) if r["revenue"] else "-"}</td></tr>')

    def tr_cpa(r):
        return (f'<tr><td>{r["keyword"]}</td>'
                f'<td class="num hi">{r["cpa"]:,}</td>'
                f'<td class="num">{r["conversions"]}</td>'
                f'<td class="num">{r["ctr"]}%</td></tr>')

    def tr_norv(r):
        return (f'<tr><td>{r["keyword"]}</td>'
                f'<td class="num">{r["clicks"]:,}</td>'
                f'<td class="num">{r["impressions"]:,}</td>'
                f'<td class="num">{r["conversions"]}</td>'
                f'<td><span class="badge badge-r">매출없음</span></td></tr>')

    roas_rows = "".join(tr_roas(r) for r in roas_top10) or '<tr><td colspan="4" style="text-align:center;color:#999">전환 데이터 없음</td></tr>'
    cpa_rows = "".join(tr_cpa(r) for r in cpa_top10) or '<tr><td colspan="4" style="text-align:center;color:#999">전환 데이터 없음</td></tr>'
    norv_rows = "".join(tr_norv(r) for r in no_rev_top) or '<tr><td colspan="5" style="text-align:center;color:#999">해당 없음</td></tr>'

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<style>
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{font-family:'Malgun Gothic',sans-serif;font-size:13px;color:#222;background:#f5f7fa;padding:20px;}}
.rpt{{max-width:1080px;margin:0 auto;background:#fff;border-radius:10px;overflow:hidden;overflow-x:hidden;box-shadow:0 2px 12px rgba(0,0,0,.08);}}
.rpt-header{{background:#0D47A1;color:#fff;padding:18px 24px;display:flex;justify-content:space-between;align-items:center;}}
.rpt-body{{padding:20px 24px;}}
.section{{margin:18px 0;}}
.section-bar{{background:#0D47A1;color:#fff;font-size:12px;font-weight:600;padding:5px 12px;border-radius:4px;margin-bottom:10px;}}
.kpi-row{{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;}}
.kpi{{background:#f0f4f8;border-radius:6px;padding:10px;text-align:center;}}
.kpi-label{{font-size:11px;color:#666;margin-bottom:4px;}}
.kpi-val{{font-size:18px;font-weight:700;color:#0D47A1;}}
.two-col{{display:grid;grid-template-columns:1fr 1fr;gap:12px;}}
.three-col{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;}}
.panel{{min-width:0;overflow:hidden;}}
canvas{{max-width:100%!important;}}
@media(max-width:600px){{.three-col{{grid-template-columns:1fr;}}.two-col{{grid-template-columns:1fr;}}.kpi-row{{grid-template-columns:repeat(2,1fr);}}}}
.panel{{border:1px solid #dde3ea;border-radius:6px;padding:12px;}}
.panel-title{{font-size:12px;font-weight:600;color:#555;border-bottom:1px solid #eee;padding-bottom:6px;margin-bottom:8px;}}
.rtable{{width:100%;border-collapse:collapse;font-size:11px;}}
.rtable th{{background:#f0f4f8;color:#444;font-weight:600;padding:6px;text-align:left;border-bottom:1px solid #dde3ea;}}
.rtable td{{padding:5px 6px;border-bottom:1px solid #f0f0f0;}}
.rtable .num{{text-align:right;}}
.rtable .hi{{color:#0D47A1;font-weight:700;}}
.rtable tfoot td{{font-weight:700;background:#f7f9fb;}}
.badge{{display:inline-block;font-size:10px;padding:1px 7px;border-radius:3px;}}
.badge-r{{background:#fee2e2;color:#991b1b;}}
.badge-g{{background:#dcfce7;color:#166534;}}
.chart-wrap{{position:relative;width:100%;height:200px;}}
.pie-wrap{{position:relative;height:150px;}}
.leg{{font-size:10px;color:#666;margin-top:6px;display:flex;flex-wrap:wrap;gap:4px;}}
.footer{{text-align:center;padding:14px;font-size:11px;color:#999;border-top:1px solid #eee;}}
</style>
</head>
<body>
<div class="rpt">
<div class="rpt-header">
  <div>
    <div style="font-size:16px;font-weight:700;">검색광고 키워드 성과 보고서</div>
    <div style="font-size:11px;opacity:.8;margin-top:4px;">분석기간: {since} ~ {until} &nbsp;|&nbsp; {client_name} 귀중 &nbsp;|&nbsp; {period_label}</div>
  </div>
  <div style="text-align:right;">
    <div style="font-size:11px;opacity:.75;">총 키워드 수</div>
    <div style="font-size:24px;font-weight:700;">{len(kws)}개</div>
  </div>
</div>

<div class="rpt-body">

<div class="section">
  <div class="section-bar">종합 성과 요약</div>
  <div class="kpi-row">
    {kpi("총 클릭수", f"{total_clicks:,}회")}
    {kpi("총 노출수", f"{total_impressions:,}회")}
    {kpi("평균 CTR", f"{avg_ctr}%")}
    {kpi("총 전환수", f"{total_conv:,}건")}
    {kpi("총 전환매출", _fmt(total_revenue) if total_revenue else "미집계")}
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
          <thead><tr><th>키워드</th><th class="num">ROAS</th><th class="num">전환수</th><th class="num">전환매출</th></tr></thead>
          <tbody>{roas_rows}</tbody>
          <tfoot><tr><td colspan="2">합계</td><td class="num">{sum(r["conversions"] for r in roas_top10)}</td><td class="num">{_fmt(sum(r["revenue"] for r in roas_top10))}</td></tr></tfoot>
        </table>
      </div>
    </div>
    <div>
      <div class="section-bar">CPA 우수 키워드 TOP10</div>
      <div class="panel" style="padding:0;">
        <table class="rtable">
          <thead><tr><th>키워드</th><th class="num">CPA(원)</th><th class="num">전환수</th><th class="num">전환율</th></tr></thead>
          <tbody>{cpa_rows}</tbody>
        </table>
      </div>
    </div>
  </div>
</div>

<div class="section">
  <div class="section-bar">클릭수 / 전환수 / 전환매출 비율 분석</div>
  <div class="three-col">
    <div class="panel">
      <div class="panel-title">클릭수 TOP5 비중</div>
      <div class="pie-wrap"><canvas id="pie1"></canvas></div>
      <div class="leg" id="leg1"></div>
    </div>
    <div class="panel">
      <div class="panel-title">전환수 TOP5 비중</div>
      <div class="pie-wrap"><canvas id="pie2"></canvas></div>
      <div class="leg" id="leg2"></div>
    </div>
    <div class="panel">
      <div class="panel-title">전환매출 TOP5 비중</div>
      <div class="pie-wrap"><canvas id="pie3"></canvas></div>
      <div class="leg" id="leg3"></div>
    </div>
  </div>
</div>

<div class="section">
  <div class="section-bar">클릭 있으나 매출 미집계 키워드 (상위 7개)</div>
  <div class="panel" style="padding:0;">
    <table class="rtable">
      <thead><tr><th>키워드</th><th class="num">클릭수</th><th class="num">노출수</th><th class="num">전환수</th><th>상태</th></tr></thead>
      <tbody>{norv_rows}</tbody>
    </table>
  </div>
</div>

</div>
<div class="footer">본 보고서는 {report_date}에 자동 생성되었습니다. | admarketip.com</div>
</div>

<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<script>
const COLORS=['#0D47A1','#1565C0','#1976D2','#42A5F5','#90CAF9'];
const costData={cost_chart};
new Chart(document.getElementById('costBar'),{{
  type:'bar',
  data:{{labels:costData.map(d=>d.k),datasets:[{{data:costData.map(d=>d.v),backgroundColor:costData.map((_,i)=>i===0?'#c0392b':'#0D47A1'),borderRadius:3}}]}},
  options:{{responsive:true,maintainAspectRatio:false,plugins:{{legend:{{display:false}},tooltip:{{callbacks:{{label:ctx=>ctx.raw.toLocaleString()+'회'}}}}}},scales:{{x:{{ticks:{{font:{{size:11}}}},grid:{{display:false}}}},y:{{ticks:{{font:{{size:10}}}},grid:{{color:'rgba(0,0,0,0.05)'}}}}}}}}
}});
function makePie(id,legId,data){{
  const total=data.reduce((a,d)=>a+d.v,0);
  if(!total)return;
  new Chart(document.getElementById(id),{{type:'doughnut',data:{{labels:data.map(d=>d.k),datasets:[{{data:data.map(d=>d.v),backgroundColor:COLORS,borderWidth:1,borderColor:'#fff'}}]}},options:{{responsive:true,maintainAspectRatio:false,plugins:{{legend:{{display:false}},tooltip:{{callbacks:{{label:ctx=>`${{ctx.label}}: ${{Math.round(ctx.raw/total*100)}}%`}}}}}}}}}});
  const leg=document.getElementById(legId);
  data.forEach((d,i)=>{{const pct=Math.round(d.v/total*100);leg.innerHTML+=`<span style="display:flex;align-items:center;gap:3px;"><span style="width:8px;height:8px;border-radius:2px;background:${{COLORS[i]}};display:inline-block;"></span>${{d.k}} ${{pct}}%</span>`;}});
}}
makePie('pie1','leg1',{pie_click});
makePie('pie2','leg2',{pie_conv});
makePie('pie3','leg3',{pie_rev});
</script>
</body></html>"""
