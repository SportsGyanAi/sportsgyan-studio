"""Motion-graphics reel renderer (1080x1920, 30fps).

Static layers are pre-rendered once per scene; each frame only moves/fades them,
so the background is perfectly smooth (sub-pixel affine, eased, no jitter).
"""
import math, subprocess, json, random
from functools import lru_cache
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance, ImageOps
from .config import W, H, FPS, SR, FONT, BG, BRAND, C_NEON, C_HOT, C_GOLD, C_WHITE, C_BG
from . import sfx

# ---------- easing ----------
def clamp(x, a=0.0, b=1.0): return max(a, min(b, x))
def ease_io(t): t = clamp(t); return t * t * (3 - 2 * t)
def ease_out(t): t = clamp(t); return 1 - (1 - t) ** 3
def ease_back(t, s=1.6): t = clamp(t) - 1; return 1 + t * t * ((s + 1) * t + s)

@lru_cache(None)
def font(name, size): return ImageFont.truetype(str(FONT[name]), size)

def is_hindi(s): return any("\u0900" <= ch <= "\u097F" for ch in s)
def fk(s, latin="head", hindi="hi_bold"): return hindi if is_hindi(s) else latin

# ---------- text with neon glow ----------
import re as _re
_EMOJI = _re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F\u200d]+")
def clean(t): return _EMOJI.sub("", str(t)).strip()

def text_layer(text, fname, size, fill=C_WHITE, glow=C_NEON, glow_r=18, stroke=0, max_w=W - 140, align="center"):
    f = font(fname, size); text = clean(text) or " "
    lines, cur = [], ""
    for w in text.split():
        t = (cur + " " + w).strip()
        if f.getlength(t) <= max_w or not cur: cur = t
        else: lines.append(cur); cur = w
    if cur: lines.append(cur)
    if not lines: return Image.new("RGBA", (2, 2), (0, 0, 0, 0))  # emoji-only / empty text
    lh = int(size * (1.25 if fname.startswith("hi") else 1.08))
    tw = int(max(f.getlength(l) for l in lines)) + 2 * glow_r + 20
    th = lh * len(lines) + 2 * glow_r + 20
    base = Image.new("RGBA", (tw, th), (0, 0, 0, 0)); d = ImageDraw.Draw(base)
    for i, l in enumerate(lines):
        x = (tw - f.getlength(l)) / 2 if align == "center" else glow_r
        d.text((x, glow_r + i * lh), l, font=f, fill=fill + (255,), stroke_width=stroke, stroke_fill=(0, 0, 0, 255))
    if glow:
        a = base.split()[3]
        g = Image.new("RGBA", base.size, glow + (0,)); g.putalpha(a.filter(ImageFilter.GaussianBlur(glow_r)))
        g2 = Image.new("RGBA", base.size, glow + (0,)); g2.putalpha(a.filter(ImageFilter.GaussianBlur(glow_r // 3)))
        out = Image.alpha_composite(Image.alpha_composite(Image.new("RGBA", base.size), g), g2)
        out = Image.alpha_composite(out, g)  # double outer bloom
        return Image.alpha_composite(out, base)
    return base

def paste(canvas, layer, cx, cy, alpha=1.0, scale=1.0):
    if alpha <= 0.01: return
    if abs(scale - 1) > 0.002:
        layer = layer.resize((max(1, int(layer.width * scale)), max(1, int(layer.height * scale))), Image.BICUBIC)
    if alpha < 0.999:
        layer = layer.copy(); a = layer.split()[3].point(lambda v: int(v * alpha)); layer.putalpha(a)
    canvas.alpha_composite(layer, (int(cx - layer.width / 2), int(cy - layer.height / 2)))

# ---------- background ----------
def load_bg(src):
    p = Path(src) if src else None
    if not p or not p.exists():
        cands = sorted(BG.glob("*.png")) + sorted(BG.glob("*.jpg"))
        p = random.choice(cands)
    im = Image.open(p).convert("RGB")
    im = ImageOps.fit(im, (int(W * 1.18), int(H * 1.18)), Image.LANCZOS)
    # pro grade: contrast, slight desat, cool shadows
    im = ImageEnhance.Contrast(im).enhance(1.12); im = ImageEnhance.Color(im).enhance(0.9)
    return im

def bg_frame(im, t, seed):
    """Smooth Ken Burns: eased zoom 1.0->1.07 and gentle pan, sub-pixel via affine."""
    e = ease_io(t)
    z = 1.0 + 0.07 * e
    rnd = random.Random(seed); dx = rnd.uniform(-1, 1) * 40 * e; dy = rnd.uniform(-1, 1) * 60 * e
    sw, sh = W / z, H / z
    cx, cy = im.width / 2 + dx, im.height / 2 + dy
    x0, y0 = cx - sw / 2, cy - sh / 2
    return im.transform((W, H), Image.AFFINE, (sw / W, 0, x0, 0, sh / H, y0), resample=Image.BICUBIC)

@lru_cache(None)
def overlay():
    """Vignette + bottom/top gradient for text legibility."""
    y = np.linspace(0, 1, H)[:, None]; x = np.linspace(-1, 1, W)[None, :]
    vig = np.clip((x ** 2 * 0.5 + (y * 2 - 1) ** 2 * 0.6), 0, 1) * 160
    grad = (np.clip((y - 0.45) / 0.55, 0, 1) ** 1.3) * 200 + (np.clip((0.18 - y) / 0.18, 0, 1)) * 120
    a = np.clip(vig + grad + 70, 0, 235).astype(np.uint8)
    o = Image.new("RGBA", (W, H), C_BG + (0,)); o.putalpha(Image.fromarray(a)); return o

@lru_cache(None)
def light_streak():
    s = Image.new("RGBA", (W * 2, 260), (0, 0, 0, 0)); d = ImageDraw.Draw(s)
    for i in range(130):
        a = int(70 * math.sin(math.pi * i / 130) ** 2)
        d.line([(0, i * 2), (W * 2, i * 2)], fill=C_NEON + (a,))
    return s.filter(ImageFilter.GaussianBlur(30)).rotate(-28, expand=True, resample=Image.BICUBIC)

@lru_cache(None)
def brand_tag():
    return text_layer(BRAND, "bold", 34, fill=C_WHITE, glow=C_NEON, glow_r=8)

def particles(canvas, t_abs, n=26):
    d = ImageDraw.Draw(canvas); rnd = random.Random(7)
    for i in range(n):
        x0, sp, r, ph = rnd.uniform(0, W), rnd.uniform(25, 70), rnd.uniform(2, 5), rnd.uniform(0, H)
        y = (ph - t_abs * sp) % H; x = x0 + 18 * math.sin(t_abs * 0.6 + i)
        a = int(90 + 80 * math.sin(t_abs * 2 + i))
        d.ellipse([x - r, y - r, x + r, y + r], fill=(C_NEON if i % 3 else C_GOLD) + (a,))

# ---------- scene builders ----------
def build_scene(sc):
    """Pre-render all static layers for one scene."""
    L = {}
    title, sub = sc.get("title", ""), sc.get("sub", "")
    kind = sc.get("type", "point")
    if clean(sc.get("kicker", "")):
        L["kicker"] = text_layer(sc["kicker"].upper() if not is_hindi(sc["kicker"]) else sc["kicker"],
                                 fk(sc["kicker"], "black", "hi_bold"), 46, fill=(10, 10, 20), glow=None)
    if title:
        L["title"] = text_layer(title if is_hindi(title) else title.upper(), fk(title), 120 if kind in ("hook", "cta") else 100,
                                glow=C_HOT if kind == "hook" else C_NEON, glow_r=22, stroke=2)
    if sub:
        L["sub"] = text_layer(sub, fk(sub, "semi", "hi"), 58, glow=None, stroke=0)
    if sc.get("rows"):
        L["rows"] = []
        for i, (a, b) in enumerate(sc["rows"][:6]):
            row = Image.new("RGBA", (W - 140, 112), (0, 0, 0, 0)); d = ImageDraw.Draw(row)
            hl = sc.get("highlight") == i
            d.rounded_rectangle([0, 0, row.width - 1, 111], 26, fill=(255, 46, 99, 210) if hl else (12, 18, 40, 200),
                                outline=C_NEON + (255,), width=3)
            d.text((40, 56), f"{i + 1}. {a}", font=font(fk(a, "bold", "hi_bold"), 50), fill=C_WHITE, anchor="lm")
            d.text((row.width - 40, 56), str(b), font=font("head", 64), fill=C_GOLD if not hl else C_WHITE, anchor="rm")
            L["rows"].append(row)
    return L

def kicker_box(layer):
    box = Image.new("RGBA", (layer.width + 30, layer.height + 4), C_GOLD + (255,))
    box.alpha_composite(layer, (15, 2)); return box

def number_layer(val, unit, glow):
    return text_layer(f"{val}{(' ' + unit) if unit else ''}", "head", 260, fill=C_WHITE, glow=glow, glow_r=30, stroke=3)

def caption_chunks(text, n=3):
    w = [x for x in text.replace(",", " ").replace(".", " ").replace("!", " ").split() if x]; out = []
    for i in range(0, len(w), n): out.append(" ".join(w[i:i + n]))
    return out

def draw_frame(sc, L, bgim, t, dur, t_abs, idx, total_dur):
    p = t / dur
    frame = bg_frame(bgim, p, idx).convert("RGBA")
    frame.alpha_composite(overlay())
    st = light_streak(); sx = -st.width + (W + st.width) * ((t_abs * 0.12 + idx * 0.37) % 1.4) / 1.4
    frame.alpha_composite(st, (int(sx), int(H * 0.25)))
    particles(frame, t_abs)
    kind = sc.get("type", "point")
    # punch-in scale at scene start
    punch = 1 + 0.06 * (1 - ease_out(t / 0.35))
    y = H * 0.36
    if "kicker" in L:
        a = ease_out(t / 0.3); paste(frame, kicker_box(L["kicker"]), W / 2 - (1 - a) * 300, y - 170, a)
    if "title" in L:
        a = ease_out((t - 0.08) / 0.35); s = ease_back((t - 0.08) / 0.45) if t < 0.53 else 1
        pulse = 1 + 0.012 * math.sin(t_abs * 4)
        paste(frame, L["title"], W / 2, y + (1 - a) * 80, a, max(0.01, s * punch * pulse))
        y += L["title"].height / 2 + 40
    if sc.get("number") is not None:
        num = str(sc["number"]); target = float(num.replace(",", "")) if num.replace(",", "").replace(".", "").isdigit() else None
        k = ease_out((t - 0.2) / 0.9)
        shown = (f"{int(round(target * k)):,}" if target is not None and "." not in num else num) if k < 1 else num
        nl = number_layer(shown, sc.get("unit", ""), C_GOLD)
        paste(frame, nl, W / 2, y + nl.height / 2, ease_out((t - 0.15) / 0.25), 1 + 0.08 * (1 - ease_out((t - 1.1) / 0.3)) if t > 1.1 else 1)
        y += nl.height + 10
    if "rows" in L:
        for i, row in enumerate(L["rows"]):
            a = ease_out((t - 0.3 - i * 0.22) / 0.3)
            paste(frame, row, W / 2 + (1 - a) * (W if i % 2 else -W) * 0.5, y + 70 + i * 128, a)
        y += 128 * len(L["rows"]) + 40
    if "sub" in L:
        a = ease_out((t - 0.45) / 0.4); paste(frame, L["sub"], W / 2, max(y + 40, H * 0.60) + (1 - a) * 40, a)
    # captions (synced chunks of the voice line)
    chunks = sc.get("_chunks") or []
    if chunks:
        ci = min(len(chunks) - 1, int(p * len(chunks)))
        cl = caption_layer(chunks[ci])
        cp = (p * len(chunks)) % 1
        paste(frame, cl, W / 2, H * 0.80, 1, 1 + 0.05 * (1 - ease_out(cp / 0.15)))
    # top HUD: progress + brand
    d = ImageDraw.Draw(frame)
    d.rounded_rectangle([60, 70, W - 60, 80], 5, fill=(255, 255, 255, 50))
    d.rounded_rectangle([60, 70, 60 + (W - 120) * (t_abs / total_dur), 80], 5, fill=C_NEON + (255,))
    paste(frame, brand_tag(), W / 2, 130, 0.85)
    # flash transition
    if t < 0.12 and idx > 0:
        fl = Image.new("RGBA", (W, H), (255, 255, 255, int(200 * (1 - t / 0.12)))); frame.alpha_composite(fl)
    if kind == "hook" and t < 0.5:  # RGB split glitch on hook only
        r, g, b, a = frame.split(); off = int(14 * (1 - t / 0.5))
        frame = Image.merge("RGBA", (ImageChops_offset(r, off), g, ImageChops_offset(b, -off), a))
    return frame.convert("RGB")

def ImageChops_offset(ch, dx):
    from PIL import ImageChops
    return ImageChops.offset(ch, dx, 0)

@lru_cache(256)
def caption_layer(txt):
    return text_layer(txt, fk(txt, "black", "hi_bold"), 72, fill=C_GOLD if is_hindi(txt) else C_WHITE,
                      glow=(0, 0, 0), glow_r=10, stroke=4)

# ---------- audio ----------
def mix_audio(scenes, starts, total, vo_files, out_wav):
    import soundfile as sf
    n = int(total * SR); vo = np.zeros(n, np.float32); fx = np.zeros(n, np.float32)
    def add(buf, sig, t, g=1.0):
        s = int(t * SR); e = min(n, s + len(sig))
        if e > s: buf[s:e] += sig[:e - s] * g
    for sc, st, vf in zip(scenes, starts, vo_files):
        v, sr = sf.read(vf, dtype="float32")
        if v.ndim > 1: v = v.mean(1)
        add(vo, v, st + sc.get("_lead", 0.25))
        add(fx, sfx.whoosh(), max(0, st - 0.25), 0.8)
        if sc.get("type") == "hook": add(fx, sfx.impact(), st + 0.05, 0.9)
        if sc.get("number") is not None:
            for k in range(10): add(fx, sfx.tick(), st + 0.2 + k * 0.09, 0.8)
            add(fx, sfx.impact(), st + 1.1, 0.7)
        if sc.get("rows"):
            for i in range(len(sc["rows"][:6])): add(fx, sfx.tick(), st + 0.3 + i * 0.22, 1.0)
    add(fx, sfx.riser(), max(0, starts[-1] - 1.2), 0.6)
    music = sfx.music_bed(total)
    # sidechain duck music under voice
    env = np.abs(vo); k = int(SR * 0.15); env = np.convolve(env, np.ones(k) / k, "same")
    duck = 1 - 0.75 * np.clip(env / (env.max() * 0.25 + 1e-9), 0, 1)
    mix = vo * 1.0 + fx * 0.55 + music * duck * 0.55
    mix = mix / (np.abs(mix).max() + 1e-9) * 0.95
    sf.write(out_wav, mix, SR)

# ---------- main ----------
def render(job, workdir, tts_speak, tts_dur):
    workdir = Path(workdir); workdir.mkdir(parents=True, exist_ok=True)
    scenes = job["scenes"]; vo_files, starts, t = [], [], 0.0
    engines = set()
    for i, sc in enumerate(scenes):
        vf = workdir / f"vo_{i:02d}.wav"; engines.add(tts_speak(sc["voice"], vf)); vo_files.append(vf)
        sc["_lead"] = 0.25
        sc["_dur"] = max(sc.get("min_dur", 2.2), tts_dur(vf) + 0.25 + 0.35)
        sc["_chunks"] = caption_chunks(sc.get("caption", sc["voice"]))
        starts.append(t); t += sc["_dur"]
    total = t
    audio = workdir / "mix.wav"; mix_audio(scenes, starts, total, vo_files, audio)
    out = workdir / "reel.mp4"
    ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                           "-r", str(FPS), "-i", "-", "-i", str(audio), "-c:v", "libx264", "-preset", "medium", "-crf", "19",
                           "-pix_fmt", "yuv420p", "-profile:v", "high", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                           "-movflags", "+faststart", "-shortest", str(out)], stdin=subprocess.PIPE)
    for i, sc in enumerate(scenes):
        L = build_scene(sc); bgim = load_bg(sc.get("image_path"))
        nf = int(round(sc["_dur"] * FPS))
        for f in range(nf):
            tt = f / FPS
            ff.stdin.write(draw_frame(sc, L, bgim, tt, sc["_dur"], starts[i] + tt, i, total).tobytes())
    ff.stdin.close(); ff.wait()
    return {"video": str(out), "duration": round(total, 2), "tts": sorted(engines)}
