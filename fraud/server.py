"""
부정클릭 추적 서버 (FastAPI)
━━━━━━━━━━━━━━━━━━━━━━━━━━
실행:
    pip install fastapi uvicorn
    uvicorn fraud.server:app --host 0.0.0.0 --port 8502

광고 랜딩페이지 삽입 예시:
    <script src="http://your-server:8502/track.js?client_id=CLIENT_ID"></script>

전환 발생 시 JS 호출:
    window.mktipConversion({type: 'inquiry'});
"""
import os
import sys

# 프로젝트 루트를 sys.path에 추가 (단독 실행 시)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from fastapi import FastAPI, Request, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from fraud.db import init_db, log_click, is_blocked, update_click
from fraud.detector import classify_device

app = FastAPI(title="MarketIP Click Tracker", docs_url="/docs")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    allow_credentials=False,
)

# ── 추적 스크립트 템플릿 ──────────────────────────────────────────────────────
_TRACK_JS = r"""(function(){
  var CID='{client_id}', URL='{track_url}';
  function p(n){try{return new URLSearchParams(location.search).get(n)||'';}catch(e){return '';}}
  function sid(){var k='_mktip_'+CID,v=sessionStorage.getItem(k);if(!v){v='s'+Date.now().toString(36)+Math.random().toString(36).slice(2,8);sessionStorage.setItem(k,v);}return v;}
  function dev(){var ua=navigator.userAgent.toLowerCase();return /ipad/.test(ua)?'tablet':/iphone|android|mobile/.test(ua)?'mobile':'desktop';}
  var t0=Date.now(),logId=null;
  var d={client_id:CID,session_id:sid(),landing_url:location.href,referrer:document.referrer,
    utm_source:p('utm_source'),utm_medium:p('utm_medium'),utm_campaign:p('utm_campaign'),
    utm_term:p('utm_term'),keyword:p('utm_term')||p('kw')||p('query')||p('keyword')||'',
    device_type:dev(),user_agent:navigator.userAgent};
  fetch(URL+'/track',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(d),keepalive:true})
    .then(function(r){return r.json();}).then(function(r){logId=r.id;});
  window.addEventListener('beforeunload',function(){
    var s=Math.round((Date.now()-t0)/1000);
    if(logId&&s>0)navigator.sendBeacon(URL+'/track/stay',JSON.stringify({log_id:logId,stay_seconds:s}));
  });
  window.mktipConversion=function(meta){
    if(logId)navigator.sendBeacon(URL+'/track/convert',JSON.stringify({log_id:logId,meta:meta||{}}));
  };
})();
"""


@app.on_event("startup")
def startup():
    init_db()


def _real_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ── 엔드포인트 ────────────────────────────────────────────────────────────────

@app.get("/track.js", response_class=Response)
async def get_track_js(request: Request, client_id: str = Query(...)):
    base = str(request.base_url).rstrip("/")
    script = _TRACK_JS.replace("{client_id}", client_id).replace("{track_url}", base)
    return Response(
        content=script,
        media_type="application/javascript",
        headers={"Cache-Control": "no-cache, no-store"},
    )


@app.post("/track")
async def track_click(request: Request):
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid json"}, status_code=400)

    client_id = (data.get("client_id") or "").strip()
    if not client_id:
        return JSONResponse({"error": "client_id required"}, status_code=400)

    ip = _real_ip(request)
    ua = (data.get("user_agent") or "")[:500]
    device, browser, os_name = classify_device(ua)

    log_data = {
        "client_id":    client_id,
        "ip_address":   ip,
        "user_agent":   ua,
        "landing_url":  (data.get("landing_url") or "")[:500],
        "referrer":     (data.get("referrer") or "")[:500],
        "keyword":      (data.get("keyword") or "")[:200],
        "campaign":     (data.get("utm_campaign") or "")[:200],
        "source":       (data.get("utm_source") or "")[:100],
        "medium":       (data.get("utm_medium") or "")[:100],
        "device":       device,
        "browser":      browser,
        "os":           os_name,
        "session_id":   (data.get("session_id") or "")[:100],
        "is_conversion": 0,
        "stay_seconds":  0,
    }
    log_id = log_click(log_data)

    return JSONResponse({"id": log_id, "blocked": is_blocked(client_id, ip), "status": "ok"})


@app.post("/track/stay")
async def track_stay(request: Request):
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid json"}, status_code=400)
    log_id = data.get("log_id")
    stay   = int(data.get("stay_seconds") or 0)
    if log_id and stay > 0:
        update_click(int(log_id), stay_seconds=stay)
    return JSONResponse({"status": "ok"})


@app.post("/track/convert")
async def track_convert(request: Request):
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid json"}, status_code=400)
    log_id = data.get("log_id")
    if log_id:
        update_click(int(log_id), is_conversion=1)
    return JSONResponse({"status": "ok"})


@app.get("/check/{ip}")
async def check_blocked(ip: str, client_id: str = Query(...)):
    return JSONResponse({"ip": ip, "blocked": is_blocked(client_id, ip)})


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("fraud.server:app", host="0.0.0.0", port=8502, reload=False)
