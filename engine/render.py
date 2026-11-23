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
from . import sfx, hero
import os

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
from .hindi_text import for_screen
def clean(t): return for_screen(_EMOJI.sub("", str(t)))

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
def grade(im, warm=0.5):
    """Cinematic teal-orange grade + clarity, the 'edited' look for real match photos."""
    a = np.asarray(im).astype(np.float32) / 255.0
    lum = a.mean(2, keepdims=True)
    shadows, highs = np.clip(1 - lum * 2, 0, 1), np.clip(lum * 2 - 1, 0, 1)
    a = a + shadows * np.array([-0.04, 0.03, 0.07]) * 1.2 + highs * np.array([0.07, 0.03, -0.04]) * (0.6 + warm)
    a = np.clip((a - 0.5) * 1.12 + 0.5, 0, 1)
    out = Image.fromarray((a * 255).astype(np.uint8))
    out = out.filter(ImageFilter.UnsharpMask(radius=3, percent=60, threshold=3))
    return ImageEnhance.Color(out).enhance(1.08)

def load_bg(src, seed=0):
    p = Path(src) if src else None
    rnd = random.Random(seed)
    real = bool(p and p.exists())
    if not real:
        cands = sorted(BG.glob("*.png")) + sorted(BG.glob("*.jpg"))
        p = cands[seed % len(cands)]
    im = Image.open(p).convert("RGB")
    if not real:  # vary generic art: mirror, crop window, hue shift
        if rnd.random() < 0.5: im = ImageOps.mirror(im)
        w, h = im.size; cw, ch = int(w * rnd.uniform(0.75, 1)), int(h * rnd.uniform(0.75, 1))
        x, y = rnd.randint(0, w - cw), rnd.randint(0, h - ch); im = im.crop((x, y, x + cw, y + ch))
        hsv = np.asarray(im.convert("HSV")).copy(); hsv[..., 0] = (hsv[..., 0].astype(int) + rnd.randint(-18, 18)) % 256
        im = Image.fromarray(hsv, "HSV").convert("RGB")
    elif im.width > im.height * 0.8:  # landscape press photo: blurred fill + sharp photo, keeps the players in frame
        fill = ImageOps.fit(im, (int(W * 1.18), int(H * 1.18)), Image.LANCZOS).filter(ImageFilter.GaussianBlur(28))
        fg = ImageOps.fit(im, (int(W * 1.18), int(W * 1.18 * 1.25)), Image.LANCZOS, centering=(0.5, 0.35))
        fill.paste(fg, (0, int(H * 1.18 * 0.12)))
        mask = Image.new("L", fg.size, 255); d = ImageDraw.Draw(mask)
        for i in range(140): d.rectangle([0, i, fg.width, i + 1], fill=int(255 * i / 140)); d.rectangle([0, fg.height - 1 - i, fg.width, fg.height - i], fill=int(255 * i / 140))
        base = ImageOps.fit(im, (int(W * 1.18), int(H * 1.18)), Image.LANCZOS).filter(ImageFilter.GaussianBlur(28))
        base.paste(fg, (0, int(H * 1.18 * 0.12)), mask); im = base
    im = ImageOps.fit(im, (int(W * 1.18), int(H * 1.18)), Image.LANCZOS)
    return grade(im, warm=rnd.random()) if real else ImageEnhance.Contrast(im).enhance(1.1)

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
def light_leak():
    l = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(l)
    d.ellipse([-300, -200, 700, 900], fill=(255, 140, 40, 120)); d.ellipse([500, 1100, 1500, 2200], fill=(255, 60, 120, 90))
    return l.filter(ImageFilter.GaussianBlur(160))

@lru_cache(None)
def logo():
    """Brand logo: neon ring + cricket ball + wordmark (procedural, no external file)."""
    S = 520; im = Image.new("RGBA", (S, S), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    for r, a in ((250, 60), (240, 255)):
        d.ellipse([S / 2 - r, S / 2 - r, S / 2 + r, S / 2 + r], outline=C_NEON + (a,), width=14 if a == 255 else 40)
    im = im.filter(ImageFilter.GaussianBlur(2)); d = ImageDraw.Draw(im)
    br = 120; cx = cy = S / 2
    d.ellipse([cx - br, cy - br, cx + br, cy + br], fill=(200, 20, 40, 255))
    d.arc([cx - br * 1.6, cy - br, cx + br * 0.4, cy + br], -60, 60, fill=(255, 235, 235, 255), width=6)
    d.arc([cx - br * 0.4, cy - br, cx + br * 1.6, cy + br], 120, 240, fill=(255, 235, 235, 255), width=6)
    d.ellipse([cx - br * 0.55, cy - br * 0.75, cx - br * 0.1, cy - br * 0.35], fill=(255, 255, 255, 90))
    return im

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
    if kind == "cta":
        L["logo"] = logo()
        L["word"] = text_layer(BRAND, "head", 104, glow=C_NEON, glow_r=20, stroke=2)
        L["follow"] = text_layer("FOLLOW करो", "hi_bold", 64, fill=(10, 10, 20), glow=None)
        return L
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
    txt = f"{val}{(' ' + unit) if unit else ''}"
    return text_layer(txt, fk(txt, "head", "hi_bold"), 260, fill=C_WHITE, glow=glow, glow_r=30, stroke=3)

def caption_chunks(text, n=4):
    w = [x for x in text.replace(",", " ").replace(".", " ").replace("!", " ").split() if x]; out = []
    for i in range(0, len(w), n): out.append(" ".join(w[i:i + n]))
    return out

def draw_frame(sc, L, bgim, t, dur, t_abs, idx, total_dur):
    p = t / dur
    if L.get("hero"):  # broadcast player hero card (own background, cutout, lower third)
        fr = hero.frame(L["hero"], kicker_box(L["kicker"]) if "kicker" in L else None, t, dur, t_abs)
        draw_captions(fr, sc, p)
        return finish(fr, sc.get("fx") or ["whip", "flash", "zoom"][idx % 3], t, idx)
    frame = bg_frame(bgim, p, idx).convert("RGBA")
    frame.alpha_composite(overlay())
    st = light_streak(); sx = -st.width + (W + st.width) * ((t_abs * 0.12 + idx * 0.37) % 1.4) / 1.4
    frame.alpha_composite(st, (int(sx), int(H * 0.25)))
    particles(frame, t_abs)
    kind = sc.get("type", "point"); fx = sc.get("fx") or ("glitch" if kind == "hook" else ["flash", "whip", "zoom", "leak"][idx % 4])
    if fx == "leak" or kind in ("hook", "record"):
        ll = light_leak().copy(); ll.putalpha(ll.split()[3].point(lambda v: int(v * (0.55 + 0.45 * math.sin(t_abs * 1.3)))))
        frame.alpha_composite(ll)
    if kind == "cta":
        return outro(frame, L, t, dur, t_abs)
    # punch-in scale at scene start
    punch = 1 + 0.06 * (1 - ease_out(t / 0.35))
    y = H * 0.36
    if "kicker" in L:
        a = ease_out(t / 0.3); paste(frame, kicker_box(L["kicker"]), W / 2 - (1 - a) * 300, y - 170, a)
    if "title" in L:
        a = ease_out((t - 0.08) / 0.35); s = ease_back((t - 0.08) / 0.45) if t < 0.53 else 1
        if kind == "hook": a = ease_out(t / 0.12); s = 1 + 1.4 * (1 - ease_out(t / 0.28))  # SLAM in
        pulse = 1 + 0.012 * math.sin(t_abs * 4)
        paste(frame, L["title"], W / 2, y + (1 - a) * 80, a, max(0.01, s * punch * pulse))
        y += L["title"].height / 2 + 40
    if sc.get("number") is not None:
        num = str(sc["number"]); target = float(num.replace(",", "")) if num.replace(",", "").replace(".", "").isdigit() else None
        k = ease_out((t - 0.2) / 0.9)
        shown = (f"{int(round(target * k)):,}" if target is not None and "." not in num else num) if k < 1 else num
        nl = number_layer(shown, sc.get("unit", ""), C_GOLD)
        sh = 10 * math.sin(t * 90) * max(0, 1 - abs(t - 1.15) / 0.15) if 1.0 < t < 1.3 else 0
        paste(frame, nl, W / 2 + sh, y + nl.height / 2, ease_out((t - 0.15) / 0.25), 1 + 0.08 * (1 - ease_out((t - 1.1) / 0.3)) if t > 1.1 else 1)
        y += nl.height + 10
    if "rows" in L:
        for i, row in enumerate(L["rows"]):
            a = ease_out((t - 0.3 - i * 0.22) / 0.3)
            paste(frame, row, W / 2 + (1 - a) * (W if i % 2 else -W) * 0.5, y + 70 + i * 128, a)
        y += 128 * len(L["rows"]) + 40
    if "sub" in L:
        a = ease_out((t - 0.45) / 0.4); paste(frame, L["sub"], W / 2, max(y + 40, H * 0.60) + (1 - a) * 40, a)
    draw_captions(frame, sc, p)
    return finish(frame, fx, t, idx)

def draw_captions(frame, sc, p):
    """Small karaoke captions low on screen: chunk slides up, the spoken word lights up gold."""
    chunks = sc.get("_chunks") or []
    if not chunks: return
    vt = clamp((p * sc["_dur"] - sc.get("_lead", 0.25)) / max(0.1, sc["_dur"] - 0.6))
    ci = min(len(chunks) - 1, int(vt * len(chunks)))
    cp = vt * len(chunks) - ci
    words = chunks[ci].split(); wi = min(len(words) - 1, int(cp * len(words)))
    cl = caption_layer(chunks[ci], wi)
    a = ease_out(cp / 0.12)
    paste(frame, cl, W / 2, H * 0.835 + (1 - a) * 30, a)

def finish(frame, fx, t, idx):
    if idx > 0 and t < 0.18:
        k = 1 - t / 0.18
        if fx == "flash":
            frame.alpha_composite(Image.new("RGBA", (W, H), (255, 255, 255, int(210 * k))))
        elif fx == "whip":
            off = int(W * 0.35 * k ** 2); frame = ImageChops_offset_rgba(frame, off).filter(ImageFilter.BoxBlur(int(1 + 18 * k)))
        elif fx == "zoom":
            z = 1 + 0.18 * k ** 2; c = frame.resize((int(W * z), int(H * z)), Image.BILINEAR)
            frame = c.crop(((c.width - W) // 2, (c.height - H) // 2, (c.width - W) // 2 + W, (c.height - H) // 2 + H))
        elif fx == "leak":
            frame.alpha_composite(Image.new("RGBA", (W, H), (255, 170, 80, int(150 * k))))
    if (fx == "glitch" and t < 0.5) or (idx > 0 and t < 0.12 and fx == "glitch"):  # RGB split glitch
        r, g, b, a = frame.split(); off = int(14 * (1 - t / 0.5))
        frame = Image.merge("RGBA", (ImageChops_offset(r, off), g, ImageChops_offset(b, -off), a))
    return frame.convert("RGB")

def outro(frame, L, t, dur, t_abs):
    """Animated brand outro: logo spins in, wordmark reveals, FOLLOW pill pulses."""
    a = ease_out(t / 0.5); s = ease_back(t / 0.6) if t < 0.6 else 1 + 0.02 * math.sin(t_abs * 3)
    lg = L["logo"].rotate(-360 * (1 - ease_out(t / 0.8)), resample=Image.BICUBIC)
    paste(frame, lg, W / 2, H * 0.36, a, max(0.01, s))
    wa = ease_out((t - 0.45) / 0.5)
    word = L["word"]
    if wa < 1:  # wipe reveal
        cut = word.crop((0, 0, max(1, int(word.width * wa)), word.height)); pad = Image.new("RGBA", word.size, (0, 0, 0, 0)); pad.alpha_composite(cut); word = pad
    paste(frame, word, W / 2, H * 0.56, wa)
    fa = ease_out((t - 0.9) / 0.4)
    pill = Image.new("RGBA", (L["follow"].width + 90, L["follow"].height + 30), (0, 0, 0, 0))
    ImageDraw.Draw(pill).rounded_rectangle([0, 0, pill.width - 1, pill.height - 1], pill.height // 2, fill=C_GOLD + (255,))
    pill.alpha_composite(L["follow"], (45, 15))
    paste(frame, pill, W / 2, H * 0.66 + (1 - fa) * 60, fa, 1 + 0.05 * math.sin(t_abs * 6) * fa)
    return frame.convert("RGB")

def ImageChops_offset_rgba(im, dx):
    from PIL import ImageChops
    return Image.merge("RGBA", [ImageChops.offset(c, dx, 0) for c in im.split()])

def ImageChops_offset(ch, dx):
    from PIL import ImageChops
    return ImageChops.offset(ch, dx, 0)

@lru_cache(512)
def caption_layer(txt, hi_word=-1):
    """One caption line, 52px, white words with the current word in gold, soft dark backing."""
    words = clean(txt).split(); fn = font(fk(txt, "black", "hi_bold"), 52)
    gap = 16; widths = [fn.getlength(w) for w in words]; tw = int(sum(widths) + gap * (len(words) - 1)) + 60
    th = 92; im = Image.new("RGBA", (max(tw, 2), th), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 6, im.width - 1, th - 6], 22, fill=(0, 0, 0, 120))
    x = 30
    for i, (w, wd) in enumerate(zip(words, widths)):
        d.text((x, th / 2), w, font=fn, fill=C_GOLD if i == hi_word else C_WHITE, anchor="lm", stroke_width=3, stroke_fill=(0, 0, 0))
        x += wd + gap
    return im

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

# ---------- style rotation ----------
def pick_hero(scenes, seed):
    """Hero card on at most 2 photo scenes per reel, alternating by seed so reels differ.
    A scene can force it with look='hero' or block it with look='plain'; SG_HERO=0 turns it off."""
    if os.environ.get("SG_HERO") == "0": return
    ok = [i for i, sc in enumerate(scenes) if sc.get("image_path") and not sc.get("rows")
          and sc.get("type", "point") not in ("cta",) and sc.get("look") != "plain"]
    forced = [i for i in ok if scenes[i].get("look") == "hero"]
    chosen = forced or [i for k, i in enumerate(ok) if (k + seed) % 2 == 0][:2]
    for i in chosen: scenes[i]["_hero"] = True

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
    pick_hero(scenes, hash(job.get("slug", "")) % 2)
    for i, sc in enumerate(scenes):
        L = build_scene(sc)
        if sc.get("_hero"):
            try: L["hero"] = hero.build(sc, sc["image_path"], text_layer, font, fk, clean, is_hindi)
            except Exception as e: print("hero skipped:", e)
        bgim = load_bg(sc.get("image_path"), seed=hash(job.get("slug", "")) % 997 + i)
        nf = int(round(sc["_dur"] * FPS))
        for f in range(nf):
            tt = f / FPS
            ff.stdin.write(draw_frame(sc, L, bgim, tt, sc["_dur"], starts[i] + tt, i, total).tobytes())
    ff.stdin.close(); ff.wait()
    return {"video": str(out), "duration": round(total, 2), "tts": sorted(engines)}
