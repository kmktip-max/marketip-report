BLUE        = "#0064FF"
BLUE_DARK   = "#0052D9"
BLUE_LIGHT  = "#E8F1FF"

BADGE_STYLES: dict[str, str] = {
    "연동신청":     "background:#E8F1FF; color:#0064FF;",
    "네이버 확인중": "background:#FFF3CD; color:#856404;",
    "이관승인대기": "background:#FFE8D6; color:#CC5500;",
    "연동완료":    "background:#E8F5E9; color:#2E7D32;",
    "반려":       "background:#FFE8E8; color:#C62828;",
}

STATUS_LIST = ["연동신청", "네이버 확인중", "이관승인대기", "연동완료", "반려"]


def badge(status: str) -> str:
    style = BADGE_STYLES.get(status, "background:#eee; color:#555;")
    return f'<span style="display:inline-block;padding:3px 12px;border-radius:100px;font-size:11px;font-weight:700;{style}">{status}</span>'


PAYBACK_CSS = """
<style>
/* ── layout ── */
.block-container { padding-top: 1.8rem !important; max-width: 960px !important; }

/* ── typography ── */
.pb-h1 { font-size:26px; font-weight:800; color:#111; margin:0 0 6px; letter-spacing:-.5px; }
.pb-sub { font-size:15px; color:#666; margin:0 0 20px; }

/* ── info cards ── */
.info-card {
  background:#fff;
  border-radius:16px;
  padding:24px 28px;
  box-shadow:0 1px 10px rgba(0,0,0,.06);
  height:100%;
}
.info-card-ttl {
  font-size:14px; font-weight:700; color:#111; margin-bottom:22px;
}

/* ── step ── */
.steps {
  display:flex; align-items:flex-start; justify-content:space-between; gap:0;
}
.step { display:flex; flex-direction:column; align-items:center; flex:1; }
.step-num {
  width:44px; height:44px; border-radius:50%;
  background:#0064FF; color:#fff;
  font-size:17px; font-weight:800;
  display:flex; align-items:center; justify-content:center;
  margin-bottom:10px;
  box-shadow:0 3px 10px rgba(0,100,255,.25);
}
.step-lbl { font-size:12px; font-weight:700; color:#111; text-align:center; }
.step-desc { font-size:11px; color:#aaa; text-align:center; margin-top:3px; }
.step-line { flex:1; height:2px; background:#E0E7FF; margin-top:22px; }

/* ── notice ── */
.notice-wrap {
  background:#FFFCF0;
  border-radius:12px;
  border-left:3px solid #F5A623;
  padding:18px 20px;
}
.notice-ttl { font-size:13px; font-weight:800; color:#F5A623; margin-bottom:14px; }
.notice-row { display:flex; gap:12px; margin-bottom:10px; align-items:flex-start; }
.notice-row:last-child { margin-bottom:0; }
.notice-key { font-size:12px; font-weight:700; color:#555; min-width:88px; flex-shrink:0; }
.notice-val { font-size:12px; color:#333; line-height:1.6; }
em-blue { color:#0064FF; font-style:normal; font-weight:700; }
em-red  { color:#CC5500; font-style:normal; font-weight:700; }

/* ── section header ── */
.sec-hdr {
  display:flex; justify-content:space-between; align-items:center;
  margin:32px 0 16px;
}
.sec-ttl { font-size:17px; font-weight:800; color:#111; }
.count-pill {
  background:#E8F1FF; color:#0064FF;
  font-size:12px; font-weight:700;
  padding:2px 10px; border-radius:100px; margin-left:8px;
}

/* ── account card ── */
.acc-card {
  background:#fff;
  border-radius:14px;
  padding:20px 24px;
  border:1.5px solid #F0F2F5;
  margin-bottom:12px;
  display:flex;
  justify-content:space-between;
  align-items:flex-start;
  transition:box-shadow .18s, border-color .18s;
}
.acc-card:hover {
  box-shadow:0 4px 18px rgba(0,100,255,.09);
  border-color:#C8D8FF;
}
.acc-name { font-size:15px; font-weight:700; color:#111; margin-bottom:5px; }
.acc-meta { font-size:12px; color:#999; line-height:1.8; }

/* ── empty ── */
.empty-wrap { text-align:center; padding:64px 0; }
.empty-ico { font-size:42px; margin-bottom:14px; }
.empty-ttl { font-size:14px; font-weight:700; color:#555; margin-bottom:4px; }
.empty-desc { font-size:12px; color:#aaa; }
</style>
"""
