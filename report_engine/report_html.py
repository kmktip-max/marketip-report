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

    avg_ctr  = _fmt_pct(total_clicks / total_imps * 100)    if total_imps              else "-"
    avg_cpa  = f"{round(total_cost / total_convs):,}원"     if total_convs and total_cost else "-"

    # ── 정렬 ──────────────────────────────────────────────────────────
    by_clicks  = sorted(kws, key=lambda k: k["clicks"],  reverse=True)[:10]
    roas_top10 = sorted(
        [k for k in kws if k["roas"] > 0 and k["cost"] > 0 and k["revenue"] > 0],
        key=lambda k: k["roas"], reverse=True
    )[:10]
    cpa_top10  = sorted(
        [k for k in kws if k["cpa"] > 0 and k["conversions"] > 0],
        key=lambda k: k["cpa"]
    )[:10]
    no_conv    = sorted(
        [k for k in kws if (k["conversions"] == 0 or k["revenue"] == 0) and k["clicks"] > 0],
        key=lambda k: k["clicks"], reverse=True
    )[:7]

    # ── 차트 JSON ─────────────────────────────────────────────────────
    def jd(lst): return json.dumps(lst, ensure_ascii=False)

    bar_data  = jd([{"k": k["keyword"], "v": k["clicks"]} for k in by_clicks])
    pie_click = jd([{"k": k["keyword"], "v": k["clicks"]} for k in by_clicks[:5] if k["clicks"] > 0])
    pie_conv  = jd([{"k": k["keyword"], "v": k["conversions"]}
                    for k in sorted(kws, key=lambda k: k["conversions"], reverse=True)[:5]
                    if k["conversions"] > 0])
    pie_rev   = jd([{"k": k["keyword"], "v": k["revenue"]}
                    for k in sorted(kws, key=lambda k: k["revenue"], reverse=True)[:5]
                    if k["revenue"] > 0])

    # ── 공통 스타일 문자열 ─────────────────────────────────────────────
    NONE_MSG = '<tr><td colspan="5" style="text-align:center;color:#999;padding:14px;font-size:12px;">전환 데이터가 없어 분석 제외</td></tr>'

    # ── 테이블 행 ─────────────────────────────────────────────────────
    TD = 'style="padding:5px 8px;border-bottom:1px solid #f0f0f0;font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;"'
    TDR = 'style="padding:5px 8px;border-bottom:1px solid #f0f0f0;text-align:right;font-size:12px;"'
    TDH = 'style="padding:5px 8px;border-bottom:1px solid #f0f0f0;text-align:right;font-size:12px;color:#0D47A1;font-weight:700;"'

    click_rows = "".join(
        f'<tr><td {TD}>{k["keyword"]}</td>'
        f'<td {TDR}>{k["clicks"]:,}</td>'
        f'<td {TDR}>{k["impressions"]:,}</td>'
        f'<td {TDR}>{_fmt_pct(k["ctr"])}</td>'
        f'<td {TDR}>{_fmt_won(k["revenue"]) if k["revenue"] else "-"}</td></tr>'
        for k in by_clicks
    ) or NONE_MSG

    roas_rows = "".join(
        f'<tr><td {TD}>{k["keyword"]}</td>'
        f'<td {TDH}>{_fmt_pct(k["roas"])}</td>'
        f'<td {TDR}>{k["conversions"]:,}</td>'
        f'<td {TDR}>{_fmt_won(k["revenue"])}</td></tr>'
        for k in roas_top10
    ) or NONE_MSG

    cpa_rows = "".join(
        f'<tr><td {TD}>{k["keyword"]}</td>'
        f'<td {TDH}>{_fmt_won(k["cpa"])}</td>'
        f'<td {TDR}>{k["conversions"]:,}</td>'
        f'<td {TDR}>{_fmt_pct(k["cvr"])}</td></tr>'
        for k in cpa_top10
    ) or NONE_MSG

    norv_rows = "".join(
        f'<tr><td {TD}>{k["keyword"]}</td>'
        f'<td {TDR}>{k["clicks"]:,}</td>'
        f'<td {TDR}>{k["impressions"]:,}</td>'
        f'<td {TDR}>{k["conversions"]:,}</td>'
        f'<td style="padding:5px 8px;border-bottom:1px solid #f0f0f0;">'
        f'<span style="background:#fee2e2;color:#991b1b;font-size:10px;padding:2px 8px;border-radius:3px;">미집계</span>'
        f'</td></tr>'
        for k in no_conv
    ) or '<tr><td colspan="5" style="text-align:center;color:#999;padding:14px;font-size:12px;">해당 없음</td></tr>'

    # ── KPI 카드 ──────────────────────────────────────────────────────
    def kpi(label, val):
        return (
            f'<div style="background:#f0f4f8;border-radius:8px;padding:14px 10px;text-align:center;flex:1;">'
            f'<div style="font-size:11px;color:#555;margin-bottom:6px;">{label}</div>'
            f'<div style="font-size:22px;font-weight:700;color:#0D47A1;">{val}</div>'
            f'</div>'
        )

    def section_bar(title):
        return (f'<div style="background:#0D47A1;color:#fff;font-size:13px;font-weight:700;'
                f'padding:6px 14px;border-radius:4px;margin-bottom:10px;">{title}</div>')

    def th_cell(txt, align="left", w=""):
        wd = f"width:{w};" if w else ""
        return (f'<th style="{wd}padding:7px 8px;text-align:{align};background:#f0f4f8;'
                f'border-bottom:2px solid #dde3ea;font-weight:600;font-size:11px;'
                f'overflow:hidden;white-space:nowrap;">{txt}</th>')

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
html, body {{ background: #f3f5f8; font-family: 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif; font-size: 13px; color: #222; }}

.rpt-outer {{
  width: 1600px;
  transform-origin: top left;
}}
.rpt {{
  width: 1600px;
  background: #fff;
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 2px 16px rgba(0,0,0,.10);
}}
.rpt-body {{ padding: 20px 28px; }}
.section {{ margin: 16px 0; }}
.row {{ display: flex; gap: 14px; }}
.kpi-row {{ display: flex; gap: 10px; }}
.two-col {{ display: flex; gap: 14px; }}
.two-col > div {{ flex: 1; min-width: 0; }}
.three-col {{ display: flex; gap: 12px; }}
.three-col > div {{ flex: 1; min-width: 0; }}
.panel {{
  border: 1px solid #dde3ea;
  border-radius: 8px;
  padding: 14px;
  min-width: 0;
  overflow: hidden;
}}
.panel-title {{ font-size: 12px; font-weight: 600; color: #444; border-bottom: 1px solid #eee; padding-bottom: 7px; margin-bottom: 10px; }}
.rtable {{ width: 100%; border-collapse: collapse; font-size: 11.5px; table-layout: fixed; }}
.rtable td, .rtable th {{ overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
.chart-wrap {{ position: relative; width: 100%; height: 200px; }}
.pie-wrap {{ position: relative; width: 100%; height: 160px; }}
canvas {{ max-width: 100% !important; }}
.leg {{ font-size: 10px; color: #555; margin-top: 8px; display: flex; flex-wrap: wrap; gap: 4px; }}
.leg-item {{ display: flex; align-items: center; gap: 3px; max-width: 100%; }}
.leg-dot {{ width: 8px; height: 8px; border-radius: 2px; flex-shrink: 0; }}
.footer {{ text-align: center; padding: 14px; font-size: 11px; color: #aaa; border-top: 1px solid #eee; }}

@media print {{
  html, body {{ background: #fff; }}
  .rpt-outer {{ transform: none !important; }}
  .rpt {{ box-shadow: none; }}
}}
</style>
</head>
<body>
<div style="padding: 20px;">
<div class="rpt-outer" id="rptOuter">
<div class="rpt" id="rpt">

<!-- ══ 헤더 ══════════════════════════════════════════════════════════ -->
<div style="background:#0D47A1;color:#fff;padding:20px 28px;display:flex;justify-content:space-between;align-items:center;">
  <div>
    <div style="font-size:19px;font-weight:700;letter-spacing:-.3px;">검색광고 키워드 성과 보고서</div>
    <div style="font-size:12px;opacity:.8;margin-top:5px;">분석기간: {since} ~ {until} &nbsp;|&nbsp; {client_name} 귀중 &nbsp;|&nbsp; {period_label} &nbsp;|&nbsp; 생성일: {report_date}</div>
  </div>
  <div style="text-align:right;">
    <div style="font-size:11px;opacity:.75;">총 키워드 수</div>
    <div style="font-size:28px;font-weight:700;">{len(kws):,}개</div>
  </div>
</div>

<div class="rpt-body">

<!-- ══ KPI ══════════════════════════════════════════════════════════ -->
<div class="section">
  {section_bar("종합 성과 요약")}
  <div class="kpi-row">
    {kpi("총 클릭수",   f"{total_clicks:,}회")}
    {kpi("총 노출수",   f"{total_imps:,}회")}
    {kpi("평균 CTR",    avg_ctr)}
    {kpi("총 전환수",   f"{total_convs:,}건")}
    {kpi("총 전환매출", _fmt_won(total_revenue) if total_revenue else "미집계")}
  </div>
</div>

<!-- ══ 바 차트 ════════════════════════════════════════════════════════ -->
<div class="section">
  {section_bar("클릭수 순위 키워드 TOP10")}
  <div class="chart-wrap"><canvas id="barChart"></canvas></div>
</div>

<!-- ══ ROAS / CPA 테이블 ════════════════════════════════════════════ -->
<div class="section">
  <div class="two-col">
    <div>
      {section_bar("ROAS 순위 TOP10")}
      <div class="panel" style="padding:0;">
        <table class="rtable">
          <thead><tr>
            {th_cell("키워드", "left", "38%")}
            {th_cell("ROAS", "right", "22%")}
            {th_cell("전환수", "right", "18%")}
            {th_cell("전환매출", "right", "22%")}
          </tr></thead>
          <tbody>{roas_rows}</tbody>
          <tfoot><tr>
            <td colspan="2" style="padding:6px 8px;font-weight:700;background:#f7f9fb;font-size:11px;">합계</td>
            <td style="padding:6px 8px;text-align:right;font-weight:700;background:#f7f9fb;font-size:11px;">{sum(k['conversions'] for k in roas_top10):,}</td>
            <td style="padding:6px 8px;text-align:right;font-weight:700;background:#f7f9fb;font-size:11px;">{_fmt_won(sum(k['revenue'] for k in roas_top10))}</td>
          </tr></tfoot>
        </table>
      </div>
    </div>
    <div>
      {section_bar("CPA 우수 키워드 TOP10")}
      <div class="panel" style="padding:0;">
        <table class="rtable">
          <thead><tr>
            {th_cell("키워드", "left", "38%")}
            {th_cell("CPA(원)", "right", "22%")}
            {th_cell("전환수", "right", "18%")}
            {th_cell("전환율", "right", "22%")}
          </tr></thead>
          <tbody>{cpa_rows}</tbody>
        </table>
      </div>
    </div>
  </div>
</div>

<!-- ══ 도넛 차트 3열 ══════════════════════════════════════════════════ -->
<div class="section">
  {section_bar("클릭수 / 전환수 / 전환매출 비율 분석")}
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

<!-- ══ 클릭수 상세 테이블 ═════════════════════════════════════════════ -->
<div class="section">
  {section_bar("클릭수 순위 키워드 상세")}
  <div class="panel" style="padding:0;">
    <table class="rtable">
      <thead><tr>
        {th_cell("키워드",   "left",  "30%")}
        {th_cell("클릭수",   "right", "14%")}
        {th_cell("노출수",   "right", "14%")}
        {th_cell("CTR",      "right", "14%")}
        {th_cell("전환매출", "right", "14%")}
        {th_cell("ROAS",     "right", "14%")}
      </tr></thead>
      <tbody>{"".join(
          f'<tr><td {TD}>{k["keyword"]}</td>'
          f'<td {TDR}>{k["clicks"]:,}</td>'
          f'<td {TDR}>{k["impressions"]:,}</td>'
          f'<td {TDR}>{_fmt_pct(k["ctr"])}</td>'
          f'<td {TDR}>{_fmt_won(k["revenue"]) if k["revenue"] else "-"}</td>'
          f'<td {TDR}>{_fmt_pct(k["roas"]) if k["roas"] > 0 else "-"}</td></tr>'
          for k in by_clicks
      )}</tbody>
    </table>
  </div>
</div>

<!-- ══ 전환 미집계 키워드 ════════════════════════════════════════════ -->
<div class="section">
  {section_bar("클릭 있으나 전환 미집계 키워드 (상위 7개)")}
  <div class="panel" style="padding:0;">
    <table class="rtable">
      <thead><tr>
        {th_cell("키워드",   "left",  "35%")}
        {th_cell("클릭수",   "right", "16%")}
        {th_cell("노출수",   "right", "16%")}
        {th_cell("전환수",   "right", "16%")}
        {th_cell("상태",     "left",  "17%")}
      </tr></thead>
      <tbody>{norv_rows}</tbody>
    </table>
  </div>
</div>

</div><!-- rpt-body -->
<div class="footer">본 보고서는 {report_date}에 자동 생성되었습니다. &nbsp;|&nbsp; admarketip.com</div>
</div><!-- rpt -->
</div><!-- rpt-outer -->
</div>

<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<script>
// ── 화면 너비에 맞게 스케일 축소 (1600px 기준) ──────────────────────
(function scaleReport() {{
  var outer = document.getElementById('rptOuter');
  function doScale() {{
    var avail = (window.innerWidth || document.documentElement.clientWidth) - 40;
    var scale = avail < 1600 ? avail / 1600 : 1;
    outer.style.transform = 'scale(' + scale + ')';
    outer.style.transformOrigin = 'top left';
    document.querySelector('body > div').style.height = (1600 * scale) + 'px';
  }}
  doScale();
  window.addEventListener('resize', doScale);
}})();

const COLORS = ['#0D47A1','#1565C0','#1976D2','#42A5F5','#90CAF9','#BBDEFB'];

// 바 차트
(function() {{
  var d = {bar_data};
  if (!d || !d.length) return;
  new Chart(document.getElementById('barChart'), {{
    type: 'bar',
    data: {{
      labels: d.map(x => x.k),
      datasets: [{{
        data: d.map(x => x.v),
        backgroundColor: d.map((_, i) => i === 0 ? '#c0392b' : '#0D47A1'),
        borderRadius: 4
      }}]
    }},
    options: {{
      responsive: true,
      maintainAspectRatio: false,
      plugins: {{
        legend: {{ display: false }},
        tooltip: {{ callbacks: {{ label: ctx => ctx.raw.toLocaleString() + '회' }} }}
      }},
      scales: {{
        x: {{ ticks: {{ font: {{ size: 11 }}, maxRotation: 20 }}, grid: {{ display: false }} }},
        y: {{ ticks: {{ font: {{ size: 10 }}, callback: v => v.toLocaleString() }}, grid: {{ color: 'rgba(0,0,0,0.04)' }} }}
      }}
    }}
  }});
}})();

// 도넛 차트
function makePie(id, legId, rawData) {{
  var data = rawData || [];
  var leg = document.getElementById(legId);
  if (!data.length) {{
    leg.innerHTML = '<span style="color:#aaa;font-size:11px;">데이터 없음</span>';
    return;
  }}
  var total = data.reduce(function(a, d) {{ return a + d.v; }}, 0);
  if (!total) return;
  new Chart(document.getElementById(id), {{
    type: 'doughnut',
    data: {{
      labels: data.map(function(d) {{ return d.k; }}),
      datasets: [{{
        data: data.map(function(d) {{ return d.v; }}),
        backgroundColor: COLORS,
        borderWidth: 1,
        borderColor: '#fff'
      }}]
    }},
    options: {{
      responsive: true,
      maintainAspectRatio: false,
      plugins: {{
        legend: {{ display: false }},
        tooltip: {{
          callbacks: {{
            label: function(ctx) {{
              return ctx.label + ': ' + Math.round(ctx.raw / total * 100) + '%';
            }}
          }}
        }}
      }}
    }}
  }});
  data.forEach(function(d, i) {{
    var pct = Math.round(d.v / total * 100);
    var item = document.createElement('span');
    item.className = 'leg-item';
    item.innerHTML =
      '<span class="leg-dot" style="background:' + COLORS[i] + '"></span>' +
      '<span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:120px;">' + d.k + ' ' + pct + '%</span>';
    leg.appendChild(item);
  }});
}}

makePie('pie1', 'leg1', {pie_click});
makePie('pie2', 'leg2', {pie_conv});
makePie('pie3', 'leg3', {pie_rev});
</script>
</body>
</html>"""
