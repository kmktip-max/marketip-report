import json


def _fmt_won(n):
    if n >= 10_000_000:
        return f"{n // 10_000_000}천{(n % 10_000_000) // 10_000:,}만"
    if n >= 10_000:
        return f"{n // 10_000:,}만"
    return f"{n:,}원"


def _fmt_pct(v):
    return f"{v:.2f}%"


def generate_html(data: dict, client_name: str, report_date: str) -> str:
    kws   = data.get("keywords", [])
    since = data.get("since", "")
    until = data.get("until", "")
    period_label = "주간" if data.get("period") == "weekly" else "월간"

    # ── 집계 ──────────────────────────────────────────────────────────
    total_clicks  = sum(k["clicks"]      for k in kws)
    total_imps    = sum(k["impressions"] for k in kws)
    total_convs   = sum(k["conversions"] for k in kws)
    total_revenue = sum(k["revenue"]     for k in kws)
    total_cost    = sum(k["cost"]        for k in kws)

    avg_ctr  = _fmt_pct(total_clicks / total_imps * 100) if total_imps  else "-"
    avg_cpc  = f"{round(total_cost / total_clicks):,}원"  if total_clicks and total_cost else "-"
    avg_cpa  = f"{round(total_cost / total_convs):,}원"   if total_convs and total_cost else "-"
    avg_roas = _fmt_pct(total_revenue / total_cost * 100) if total_cost and total_revenue else "-"

    # ── 정렬 ──────────────────────────────────────────────────────────
    by_clicks  = sorted(kws, key=lambda k: k["clicks"],    reverse=True)[:10]
    roas_top10 = sorted(
        [k for k in kws if k["roas"] > 0 and k["cost"] > 0 and k["revenue"] > 0],
        key=lambda k: k["roas"], reverse=True
    )[:10]
    cpa_top10  = sorted(
        [k for k in kws if k["cpa"]  > 0 and k["conversions"] > 0],
        key=lambda k: k["cpa"]
    )[:10]
    no_conv    = sorted(
        [k for k in kws if (k["conversions"] == 0 or k["revenue"] == 0) and k["clicks"] > 0],
        key=lambda k: k["clicks"], reverse=True
    )[:7]

    # ── 차트 JSON ─────────────────────────────────────────────────────
    def jd(lst): return json.dumps(lst, ensure_ascii=False)

    bar_data   = jd([{"k": k["keyword"], "v": k["clicks"]}  for k in by_clicks])
    pie_click  = jd([{"k": k["keyword"], "v": k["clicks"]}  for k in by_clicks[:5] if k["clicks"]  > 0])
    pie_conv   = jd([{"k": k["keyword"], "v": k["conversions"]} for k in
                      sorted(kws, key=lambda k: k["conversions"], reverse=True)[:5]
                      if k["conversions"] > 0])
    pie_rev    = jd([{"k": k["keyword"], "v": k["revenue"]}  for k in
                      sorted(kws, key=lambda k: k["revenue"], reverse=True)[:5]
                      if k["revenue"] > 0])

    # ── 테이블 행 생성 ────────────────────────────────────────────────
    NONE_ROW = '<tr><td colspan="5" style="text-align:center;color:#999;padding:12px;">전환 데이터가 없어 분석 제외</td></tr>'

    click_rows = "".join(
        f'<tr>'
        f'<td style="padding:5px 6px;border-bottom:1px solid #f0f0f0;">{k["keyword"]}</td>'
        f'<td style="padding:5px 6px;border-bottom:1px solid #f0f0f0;text-align:right;">{k["clicks"]:,}</td>'
        f'<td style="padding:5px 6px;border-bottom:1px solid #f0f0f0;text-align:right;">{k["impressions"]:,}</td>'
        f'<td style="padding:5px 6px;border-bottom:1px solid #f0f0f0;text-align:right;">{_fmt_pct(k["ctr"])}</td>'
        f'<td style="padding:5px 6px;border-bottom:1px solid #f0f0f0;text-align:right;">{_fmt_won(k["revenue"]) if k["revenue"] else "-"}</td>'
        f'</tr>'
        for k in by_clicks
    ) or NONE_ROW

    roas_rows = "".join(
        f'<tr>'
        f'<td style="padding:5px 6px;border-bottom:1px solid #f0f0f0;">{k["keyword"]}</td>'
        f'<td style="padding:5px 6px;border-bottom:1px solid #f0f0f0;text-align:right;color:#0D47A1;font-weight:700;">{_fmt_pct(k["roas"])}</td>'
        f'<td style="padding:5px 6px;border-bottom:1px solid #f0f0f0;text-align:right;">{k["conversions"]:,}</td>'
        f'<td style="padding:5px 6px;border-bottom:1px solid #f0f0f0;text-align:right;">{_fmt_won(k["revenue"])}</td>'
        f'</tr>'
        for k in roas_top10
    ) or NONE_ROW

    cpa_rows = "".join(
        f'<tr>'
        f'<td style="padding:5px 6px;border-bottom:1px solid #f0f0f0;">{k["keyword"]}</td>'
        f'<td style="padding:5px 6px;border-bottom:1px solid #f0f0f0;text-align:right;color:#0D47A1;font-weight:700;">{_fmt_won(k["cpa"])}</td>'
        f'<td style="padding:5px 6px;border-bottom:1px solid #f0f0f0;text-align:right;">{k["conversions"]:,}</td>'
        f'<td style="padding:5px 6px;border-bottom:1px solid #f0f0f0;text-align:right;">{_fmt_pct(k["cvr"])}</td>'
        f'</tr>'
        for k in cpa_top10
    ) or NONE_ROW

    norv_rows = "".join(
        f'<tr>'
        f'<td style="padding:5px 6px;border-bottom:1px solid #f0f0f0;">{k["keyword"]}</td>'
        f'<td style="padding:5px 6px;border-bottom:1px solid #f0f0f0;text-align:right;">{k["clicks"]:,}</td>'
        f'<td style="padding:5px 6px;border-bottom:1px solid #f0f0f0;text-align:right;">{k["impressions"]:,}</td>'
        f'<td style="padding:5px 6px;border-bottom:1px solid #f0f0f0;text-align:right;">{k["conversions"]:,}</td>'
        f'<td style="padding:5px 6px;border-bottom:1px solid #f0f0f0;">'
        f'<span style="background:#fee2e2;color:#991b1b;font-size:10px;padding:1px 7px;border-radius:3px;">미집계</span>'
        f'</td>'
        f'</tr>'
        for k in no_conv
    ) or '<tr><td colspan="5" style="text-align:center;color:#999;padding:12px;">해당 없음</td></tr>'

    # ── KPI 카드 ──────────────────────────────────────────────────────
    def kpi(label, val):
        return (
            f'<div style="background:#f0f4f8;border-radius:6px;padding:12px;text-align:center;">'
            f'<div style="font-size:11px;color:#666;margin-bottom:4px;">{label}</div>'
            f'<div style="font-size:20px;font-weight:700;color:#0D47A1;">{val}</div>'
            f'</div>'
        )

    th = 'style="padding:6px 8px;text-align:left;background:#f0f4f8;border-bottom:2px solid #dde3ea;font-weight:600;font-size:11px;"'
    thr = 'style="padding:6px 8px;text-align:right;background:#f0f4f8;border-bottom:2px solid #dde3ea;font-weight:600;font-size:11px;"'
    sb = 'style="background:#0D47A1;color:#fff;font-size:12px;font-weight:700;padding:6px 14px;border-radius:4px;margin-bottom:10px;"'

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<style>
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{font-family:'Malgun Gothic',sans-serif;font-size:13px;color:#222;background:#f5f7fa;padding:16px;}}
.rpt{{max-width:1080px;margin:0 auto;background:#fff;border-radius:10px;overflow:hidden;overflow-x:hidden;box-shadow:0 2px 12px rgba(0,0,0,.08);}}
.rpt-body{{padding:20px 24px;}}
.section{{margin:18px 0;}}
.two-col{{display:grid;grid-template-columns:1fr 1fr;gap:12px;}}
.three-col{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;}}
.kpi-grid{{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;}}
.panel{{border:1px solid #dde3ea;border-radius:6px;padding:12px;min-width:0;overflow:hidden;}}
.panel-title{{font-size:12px;font-weight:600;color:#555;border-bottom:1px solid #eee;padding-bottom:6px;margin-bottom:8px;}}
.rtable{{width:100%;border-collapse:collapse;font-size:11px;table-layout:fixed;}}
.rtable td,.rtable th{{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}}
.chart-wrap{{position:relative;width:100%;height:200px;}}
.pie-wrap{{position:relative;height:150px;width:100%;}}
canvas{{max-width:100%!important;}}
.leg{{font-size:10px;color:#555;margin-top:6px;display:flex;flex-wrap:wrap;gap:4px;}}
.footer{{text-align:center;padding:14px;font-size:11px;color:#999;border-top:1px solid #eee;margin-top:4px;}}
@media(max-width:600px){{
  .three-col{{grid-template-columns:1fr;}}
  .two-col{{grid-template-columns:1fr;}}
  .kpi-grid{{grid-template-columns:repeat(2,1fr);}}
}}
</style>
</head>
<body>
<div class="rpt">

<!-- 헤더 -->
<div style="background:#0D47A1;color:#fff;padding:18px 24px;display:flex;justify-content:space-between;align-items:center;">
  <div>
    <div style="font-size:17px;font-weight:700;">검색광고 키워드 성과 보고서</div>
    <div style="font-size:11px;opacity:.8;margin-top:4px;">분석기간: {since} ~ {until} &nbsp;|&nbsp; {client_name} 귀중 &nbsp;|&nbsp; {period_label}</div>
  </div>
  <div style="text-align:right;">
    <div style="font-size:11px;opacity:.75;">총 키워드 수</div>
    <div style="font-size:26px;font-weight:700;">{len(kws)}개</div>
  </div>
</div>

<div class="rpt-body">

<!-- KPI -->
<div class="section">
  <div {sb}>종합 성과 요약</div>
  <div class="kpi-grid">
    {kpi("총 클릭수", f"{total_clicks:,}회")}
    {kpi("총 노출수", f"{total_imps:,}회")}
    {kpi("평균 CTR", avg_ctr)}
    {kpi("총 전환수", f"{total_convs:,}건")}
    {kpi("총 전환매출", _fmt_won(total_revenue) if total_revenue else "미집계")}
  </div>
</div>

<!-- 클릭수 바 차트 -->
<div class="section">
  <div {sb}>클릭수 순위 키워드 TOP10</div>
  <div class="chart-wrap"><canvas id="barChart"></canvas></div>
</div>

<!-- ROAS / CPA 테이블 -->
<div class="section">
  <div class="two-col">
    <div>
      <div {sb}>ROAS 순위 TOP10</div>
      <div class="panel" style="padding:0;">
        <table class="rtable">
          <thead><tr>
            <th {th} style="width:40%;">키워드</th>
            <th {thr} style="width:20%;">ROAS</th>
            <th {thr} style="width:20%;">전환수</th>
            <th {thr} style="width:20%;">전환매출</th>
          </tr></thead>
          <tbody>{roas_rows}</tbody>
          <tfoot><tr>
            <td colspan="2" style="padding:5px 8px;font-weight:700;background:#f7f9fb;">합계</td>
            <td style="padding:5px 8px;text-align:right;font-weight:700;background:#f7f9fb;">{sum(k['conversions'] for k in roas_top10):,}</td>
            <td style="padding:5px 8px;text-align:right;font-weight:700;background:#f7f9fb;">{_fmt_won(sum(k['revenue'] for k in roas_top10))}</td>
          </tr></tfoot>
        </table>
      </div>
    </div>
    <div>
      <div {sb}>CPA 우수 키워드 TOP10</div>
      <div class="panel" style="padding:0;">
        <table class="rtable">
          <thead><tr>
            <th {th} style="width:40%;">키워드</th>
            <th {thr} style="width:25%;">CPA(원)</th>
            <th {thr} style="width:15%;">전환수</th>
            <th {thr} style="width:20%;">전환율</th>
          </tr></thead>
          <tbody>{cpa_rows}</tbody>
        </table>
      </div>
    </div>
  </div>
</div>

<!-- 클릭수 TOP10 테이블 -->
<div class="section">
  <div {sb}>클릭수 순위 키워드 TOP10 (상세)</div>
  <div class="panel" style="padding:0;">
    <table class="rtable">
      <thead><tr>
        <th {th} style="width:35%;">키워드</th>
        <th {thr} style="width:15%;">클릭수</th>
        <th {thr} style="width:15%;">노출수</th>
        <th {thr} style="width:15%;">CTR</th>
        <th {thr} style="width:20%;">전환매출</th>
      </tr></thead>
      <tbody>{click_rows}</tbody>
    </table>
  </div>
</div>

<!-- 도넛 차트 3개 -->
<div class="section">
  <div {sb}>클릭수 / 전환수 / 전환매출 비율 분석</div>
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

<!-- 전환 미집계 키워드 -->
<div class="section">
  <div {sb}>클릭 있으나 전환 미집계 키워드 (상위 7개)</div>
  <div class="panel" style="padding:0;">
    <table class="rtable">
      <thead><tr>
        <th {th} style="width:35%;">키워드</th>
        <th {thr} style="width:15%;">클릭수</th>
        <th {thr} style="width:15%;">노출수</th>
        <th {thr} style="width:15%;">전환수</th>
        <th {th} style="width:20%;">상태</th>
      </tr></thead>
      <tbody>{norv_rows}</tbody>
    </table>
  </div>
</div>

</div><!-- rpt-body -->
<div class="footer">본 보고서는 {report_date}에 자동 생성되었습니다. | admarketip.com</div>
</div><!-- rpt -->

<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<script>
const COLORS = ['#0D47A1','#1565C0','#1976D2','#42A5F5','#90CAF9','#BBDEFB'];

// 바 차트
(function(){{
  const d = {bar_data};
  if(!d.length) return;
  new Chart(document.getElementById('barChart'), {{
    type: 'bar',
    data: {{
      labels: d.map(x => x.k),
      datasets: [{{ data: d.map(x => x.v), backgroundColor: d.map((_,i) => i===0?'#c0392b':'#0D47A1'), borderRadius: 3 }}]
    }},
    options: {{
      responsive: true, maintainAspectRatio: false,
      plugins: {{ legend: {{ display: false }}, tooltip: {{ callbacks: {{ label: ctx => ctx.raw.toLocaleString() + '회' }} }} }},
      scales: {{
        x: {{ ticks: {{ font: {{ size: 11 }}, maxRotation: 30 }}, grid: {{ display: false }} }},
        y: {{ ticks: {{ font: {{ size: 10 }} }} }}
      }}
    }}
  }});
}})();

// 도넛 차트
function makePie(id, legId, data) {{
  if(!data || !data.length) {{
    document.getElementById(legId).innerHTML = '<span style="color:#999;">데이터 없음</span>';
    return;
  }}
  const total = data.reduce((a,d) => a + d.v, 0);
  if(!total) return;
  new Chart(document.getElementById(id), {{
    type: 'doughnut',
    data: {{
      labels: data.map(d => d.k),
      datasets: [{{ data: data.map(d => d.v), backgroundColor: COLORS, borderWidth: 1, borderColor: '#fff' }}]
    }},
    options: {{
      responsive: true, maintainAspectRatio: false,
      plugins: {{
        legend: {{ display: false }},
        tooltip: {{ callbacks: {{ label: ctx => `${{ctx.label}}: ${{Math.round(ctx.raw/total*100)}}%` }} }}
      }}
    }}
  }});
  const leg = document.getElementById(legId);
  data.forEach((d, i) => {{
    const pct = Math.round(d.v / total * 100);
    leg.innerHTML += `<span style="display:flex;align-items:center;gap:3px;max-width:100%;"><span style="width:8px;height:8px;border-radius:2px;background:${{COLORS[i]}};flex-shrink:0;display:inline-block;"></span><span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${{d.k}} ${{pct}}%</span></span>`;
  }});
}}

makePie('pie1', 'leg1', {pie_click});
makePie('pie2', 'leg2', {pie_conv});
makePie('pie3', 'leg3', {pie_rev});
</script>
</body>
</html>"""
