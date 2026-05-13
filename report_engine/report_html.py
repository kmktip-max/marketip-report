import json

def _fmt(n):
    if n >= 10_000_000:
        return f"{n//10_000_000}천{(n%10_000_000)//10_000:,}만"
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
    avg_rnk = round(sum(k.get("avg_rnk", 0) for k in kws if k.get("avg_rnk", 0) > 0) /
                    max(1, sum(1 for k in kws if k.get("avg_rnk", 0) > 0)), 1)

    by_clicks = sorted(kws, key=lambda x: x["clicks"], reverse=True)[:10]
    roas_top = sorted([k for k in kws if k["roas"] > 0], key=lambda x: x["roas"], reverse=True)[:10]
    by_revenue = sorted([k for k in kws if k["revenue"] > 0], key=lambda x: x["revenue"], reverse=True)[:10]

    def row(rank, kw):
        return f"""<tr>
          <td style="padding:6px 8px;border-bottom:1px solid #eee;text-align:center;color:#666;">{rank}</td>
          <td style="padding:6px 8px;border-bottom:1px solid #eee;">{kw['keyword']}</td>
          <td style="padding:6px 8px;border-bottom:1px solid #eee;text-align:right;">{kw['clicks']:,}</td>
          <td style="padding:6px 8px;border-bottom:1px solid #eee;text-align:right;">{kw['impressions']:,}</td>
          <td style="padding:6px 8px;border-bottom:1px solid #eee;text-align:right;">{kw['ctr']}%</td>
          <td style="padding:6px 8px;border-bottom:1px solid #eee;text-align:right;color:#0D47A1;font-weight:600;">{_fmt(kw['revenue']) if kw['revenue'] else '-'}</td>
        </tr>"""

    click_rows = "".join(row(i+1, k) for i, k in enumerate(by_clicks))

    def roas_row(rank, kw):
        return f"""<tr>
          <td style="padding:6px 8px;border-bottom:1px solid #eee;text-align:center;color:#666;">{rank}</td>
          <td style="padding:6px 8px;border-bottom:1px solid #eee;">{kw['keyword']}</td>
          <td style="padding:6px 8px;border-bottom:1px solid #eee;text-align:right;color:#0D47A1;font-weight:600;">{kw['roas']}%</td>
          <td style="padding:6px 8px;border-bottom:1px solid #eee;text-align:right;">{kw['conversions']:,}</td>
          <td style="padding:6px 8px;border-bottom:1px solid #eee;text-align:right;">{_fmt(kw['revenue']) if kw['revenue'] else '-'}</td>
        </tr>"""

    roas_rows = "".join(roas_row(i+1, k) for i, k in enumerate(roas_top)) if roas_top else \
        '<tr><td colspan="5" style="padding:12px;text-align:center;color:#999;">전환 데이터 없음</td></tr>'

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#f5f7fa;font-family:'Malgun Gothic',Arial,sans-serif;font-size:13px;">
<div style="max-width:700px;margin:20px auto;background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.08);">

  <!-- 헤더 -->
  <div style="background:#0D47A1;color:#fff;padding:20px 24px;display:flex;justify-content:space-between;align-items:center;">
    <div>
      <div style="font-size:17px;font-weight:700;">검색광고 키워드 성과 보고서</div>
      <div style="font-size:12px;opacity:0.8;margin-top:4px;">분석 기간: {since} ~ {until} &nbsp;|&nbsp; {client_name} 귀중</div>
    </div>
    <div style="text-align:right;">
      <div style="font-size:11px;opacity:0.75;">총 키워드 수</div>
      <div style="font-size:24px;font-weight:700;">{len(kws)}개</div>
    </div>
  </div>

  <div style="padding:20px 24px;">

    <!-- KPI -->
    <div style="margin-bottom:20px;">
      <div style="background:#0D47A1;color:#fff;font-size:13px;font-weight:600;padding:6px 14px;border-radius:4px;margin-bottom:12px;">종합 성과 요약</div>
      <table style="width:100%;border-collapse:collapse;">
        <tr>
          <td style="width:20%;background:#f0f4f8;border-radius:6px;padding:12px;text-align:center;margin:4px;">
            <div style="font-size:11px;color:#666;margin-bottom:4px;">총 클릭수</div>
            <div style="font-size:22px;font-weight:700;color:#0D47A1;">{total_clicks:,}회</div>
          </td>
          <td style="width:4%;"></td>
          <td style="width:20%;background:#f0f4f8;border-radius:6px;padding:12px;text-align:center;">
            <div style="font-size:11px;color:#666;margin-bottom:4px;">총 노출수</div>
            <div style="font-size:22px;font-weight:700;color:#0D47A1;">{total_impressions:,}회</div>
          </td>
          <td style="width:4%;"></td>
          <td style="width:20%;background:#f0f4f8;border-radius:6px;padding:12px;text-align:center;">
            <div style="font-size:11px;color:#666;margin-bottom:4px;">평균 CTR</div>
            <div style="font-size:22px;font-weight:700;color:#0D47A1;">{avg_ctr}%</div>
          </td>
          <td style="width:4%;"></td>
          <td style="width:20%;background:#f0f4f8;border-radius:6px;padding:12px;text-align:center;">
            <div style="font-size:11px;color:#666;margin-bottom:4px;">총 전환수</div>
            <div style="font-size:22px;font-weight:700;color:#0D47A1;">{total_conv:,}건</div>
          </td>
          <td style="width:4%;"></td>
          <td style="width:20%;background:#f0f4f8;border-radius:6px;padding:12px;text-align:center;">
            <div style="font-size:11px;color:#666;margin-bottom:4px;">총 전환매출</div>
            <div style="font-size:22px;font-weight:700;color:#0D47A1;">{"미집계" if not total_revenue else _fmt(total_revenue)}</div>
          </td>
        </tr>
      </table>
    </div>

    <!-- 클릭수 TOP10 -->
    <div style="margin-bottom:20px;">
      <div style="background:#0D47A1;color:#fff;font-size:13px;font-weight:600;padding:6px 14px;border-radius:4px;margin-bottom:10px;">클릭수 순위 키워드 TOP10</div>
      <table style="width:100%;border-collapse:collapse;font-size:12px;">
        <thead>
          <tr style="background:#f0f4f8;">
            <th style="padding:8px;text-align:center;border-bottom:2px solid #dde3ea;width:40px;">#</th>
            <th style="padding:8px;text-align:left;border-bottom:2px solid #dde3ea;">키워드</th>
            <th style="padding:8px;text-align:right;border-bottom:2px solid #dde3ea;">클릭수</th>
            <th style="padding:8px;text-align:right;border-bottom:2px solid #dde3ea;">노출수</th>
            <th style="padding:8px;text-align:right;border-bottom:2px solid #dde3ea;">CTR</th>
            <th style="padding:8px;text-align:right;border-bottom:2px solid #dde3ea;">전환매출</th>
          </tr>
        </thead>
        <tbody>{click_rows}</tbody>
      </table>
    </div>

    <!-- ROAS TOP10 -->
    <div style="margin-bottom:20px;">
      <div style="background:#0D47A1;color:#fff;font-size:13px;font-weight:600;padding:6px 14px;border-radius:4px;margin-bottom:10px;">ROAS 순위 키워드 TOP10</div>
      <table style="width:100%;border-collapse:collapse;font-size:12px;">
        <thead>
          <tr style="background:#f0f4f8;">
            <th style="padding:8px;text-align:center;border-bottom:2px solid #dde3ea;width:40px;">#</th>
            <th style="padding:8px;text-align:left;border-bottom:2px solid #dde3ea;">키워드</th>
            <th style="padding:8px;text-align:right;border-bottom:2px solid #dde3ea;">ROAS</th>
            <th style="padding:8px;text-align:right;border-bottom:2px solid #dde3ea;">전환수</th>
            <th style="padding:8px;text-align:right;border-bottom:2px solid #dde3ea;">전환매출</th>
          </tr>
        </thead>
        <tbody>{roas_rows}</tbody>
      </table>
    </div>

  </div>

  <!-- 푸터 -->
  <div style="background:#f8f9fa;padding:14px 24px;text-align:center;font-size:11px;color:#999;border-top:1px solid #eee;">
    본 보고서는 {report_date}에 자동 생성되었습니다. &nbsp;|&nbsp; admarketip.com
  </div>
</div>
</body>
</html>"""

    return html
