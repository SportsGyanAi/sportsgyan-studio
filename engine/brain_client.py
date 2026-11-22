"""Talks to the Brain (Cloudflare Worker): claim job -> render -> upload media -> mark rendered."""
import json, os, time, logging, urllib.request, tempfile
log = logging.getLogger("brain")
BRAIN = os.environ.get("BRAIN_URL", "https://sportsgyan-brain.sportsgyan.workers.dev")
KEY = os.environ["BRAIN_KEY"]

def call(method, path, body=None, raw=None, ctype="application/json"):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(BRAIN + path, data=data, method=method,
                                 headers={"Authorization": f"Bearer {KEY}", "Content-Type": ctype})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                t = r.read(); return json.loads(t) if t else {}
        except Exception as e:
            log.warning("%s %s failed (%s), retry %d", method, path, e, attempt); time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"brain call failed {path}")

def poll_and_run(run_job, max_jobs=3):
    for _ in range(max_jobs):
        job = call("POST", "/api/jobs/claim", {"worker": os.getenv("GITHUB_RUN_ID", "local")}).get("job")
        if not job: log.info("no jobs"); return
        jid = job["id"]
        try:
            res = run_job(job, tempfile.mkdtemp(prefix=f"job-{jid}-"))
            call("PUT", f"/api/media/{jid}/video.mp4", raw=open(res["video"], "rb").read(), ctype="video/mp4")
            call("PUT", f"/api/media/{jid}/cover.jpg", raw=open(res["cover"], "rb").read(), ctype="image/jpeg")
            call("POST", f"/api/jobs/{jid}/rendered", {"duration": res["duration"], "tts": res["tts"]})
        except Exception as e:
            log.exception("job %s failed", jid)
            call("POST", f"/api/jobs/{jid}/failed", {"error": str(e)[:500]})
