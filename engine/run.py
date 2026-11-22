"""Entry point: python -m engine.run job.json OUTDIR  (or --poll to fetch jobs from the Brain)."""
import json, sys, os, logging, urllib.request
from pathlib import Path
from . import tts
from .render import render
from .cover import make_cover
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
log = logging.getLogger("run")

def is_graphic(path):
    """True for infographics / text cards (lots of flat white or flat colour), which look bad as a background."""
    from PIL import Image
    import numpy as np
    a = np.asarray(Image.open(path).convert("RGB").resize((160, 90))).astype(int)
    white = ((a > 225).all(2)).mean()
    flat = (np.abs(np.diff(a, axis=1)).sum(2) < 6).mean()
    return white > 0.25 or flat > 0.6

def fetch_images(job, workdir):
    """Download per-scene/cover images (match photos supplied by the Brain)."""
    for i, item in enumerate(job["scenes"] + [job.get("cover", {})]):
        url = item.get("image")
        if url and url.startswith("http"):
            p = Path(workdir) / f"img_{i:02d}.jpg"
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                p.write_bytes(urllib.request.urlopen(req, timeout=30).read())
                if is_graphic(p): log.info("skip text-graphic image %s", url); continue
                item["image_path"] = str(p)
            except Exception as e: log.warning("image fail %s: %s", url, e)

def run_job(job, outdir):
    out = Path(outdir); out.mkdir(parents=True, exist_ok=True)
    fetch_images(job, out)
    res = render(job, out, tts.speak, tts.duration)
    cv = job.get("cover") or {"title": job["scenes"][0].get("title", "")}
    res["cover"] = str(make_cover(cv, out / "cover.jpg"))
    (out / "result.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
    log.info("done %s", res); return res

if __name__ == "__main__":
    if sys.argv[1] == "--poll":
        from .brain_client import poll_and_run
        poll_and_run(run_job)
    else:
        run_job(json.loads(Path(sys.argv[1]).read_text()), sys.argv[2])
