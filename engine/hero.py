"""Broadcast 'player hero card' (edit #1, 2026-11-23).

TV-style depth layering, bottom to top:
  team-colour gradient + slow light rays + halftone dots  ->  giant ghost name  ->
  soft drop shadow  ->  player cutout (rembg) with rim light  ->  slanted lower-third stat panel.
Player scales in with motion blur, then drifts slower than the ghost name (parallax).
Colour comes from the player's own jersey, so every reel gets its own team grade.
All graphics are drawn here; only the match photo comes in.
"""
import math, logging
from functools import lru_cache
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageChops
from .config import W, H, C_GOLD, C_WHITE, C_NEON

log = logging.getLogger("hero")
_SESSION = None


def _session():
    global _SESSION
    if _SESSION is None:
        from rembg import new_session
        _SESSION = new_session("u2net_human_seg")
    return _SESSION


@lru_cache(16)
def cutout(path):
    """Player cutout cropped to its body, or None when no clean single person is found."""
    try:
        from rembg import remove
        im = Image.open(path).convert("RGB")
        if max(im.size) > 1600: im.thumbnail((1600, 1600))
        out = remove(im, session=_session(), post_process_mask=True)
    except Exception as e:
        log.warning("cutout unavailable: %s", e); return None
    a = np.asarray(out)[..., 3]
    fg = a > 128; frac = fg.mean()
    if not 0.025 < frac < 0.6: return None  # nobody, or the whole frame
    ys, xs = np.where(fg)
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    if (y1 - y0) < im.height * 0.35: return None  # too small to look sharp at 9:16
    pad = 6
    return out.crop((max(0, x0 - pad), max(0, y0 - pad), min(im.width, x1 + pad), min(im.height, y1 + pad)))


def jersey_colour(cut):
    """Dominant saturated colour of the cutout (its kit) -> team grade."""
    hsv = np.asarray(cut.convert("RGB").convert("HSV")).reshape(-1, 3).astype(int)
    a = np.asarray(cut)[..., 3].reshape(-1)
    m = (a > 200) & (hsv[:, 1] > 70) & (hsv[:, 2] > 50)
    if m.sum() < 200: return C_NEON
    h = np.bincount(hsv[m, 0] // 8, minlength=32).argmax() * 8 + 4
    rgb = Image.new("HSV", (1, 1), (int(h), 200, 230)).convert("RGB").getpixel((0, 0))
    return tuple(int(v) for v in rgb)


def _halftone(col):
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(im); step = 26
    for y in range(0, H, step):
        for x in range(0, W, step):
            k = max(0.0, 1 - (math.hypot(x - W, y) / (W * 1.3)))  # dots grow toward top-right corner
            r = 1 + 9 * k
            if r > 1.6: d.ellipse([x - r, y - r, x + r, y + r], fill=col + (60,))
    return im


def _rays(col):
    S = 2400; im = Image.new("RGBA", (S, S), (0, 0, 0, 0)); d = ImageDraw.Draw(im); c = S / 2
    for i in range(18):
        a0 = i * 20; a1 = a0 + 7
        pts = [(c, c)] + [(c + S * math.cos(math.radians(a)), c + S * math.sin(math.radians(a))) for a in (a0, a1)]
        d.polygon(pts, fill=col + (38,))
    return im.filter(ImageFilter.GaussianBlur(6))


def _rim(cut, col):
    """Rim light: bright edge on the top-left and right of the silhouette, plus soft spill."""
    a = cut.split()[3]
    inner = a.filter(ImageFilter.MinFilter(9))
    edge = ImageChops.subtract(a, inner).filter(ImageFilter.GaussianBlur(3))
    w, h = cut.size
    # light from the upper left: stronger edge where the alpha shifted toward lower right is empty
    shifted = ImageChops.offset(a, 7, 9)
    side = ImageChops.subtract(a, shifted).filter(ImageFilter.GaussianBlur(2))
    mask = ImageChops.add(edge.point(lambda v: v * 0.55), side)
    rim = Image.new("RGBA", (w, h), col + (0,)); rim.putalpha(mask)
    white = Image.new("RGBA", (w, h), (255, 255, 255, 0)); white.putalpha(side.point(lambda v: int(v * 0.8)))
    out = cut.copy(); out.alpha_composite(rim); out.alpha_composite(white)
    return out


def _glow(cut, col, r=40):
    g = Image.new("RGBA", cut.size, col + (0,)); g.putalpha(cut.split()[3].filter(ImageFilter.GaussianBlur(r)).point(lambda v: int(v * 0.7)))
    return g


def build(sc, img_path, text_layer, font, fk, clean, is_hindi):
    """Pre-render all static hero layers for one scene. Returns dict or None."""
    cut = cutout(str(img_path))
    if cut is None: return None
    col = jersey_colour(cut)
    dark = tuple(int(v * 0.16) for v in col)
    # backdrop: diagonal gradient dark -> team colour
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    k = np.clip((xx / W * 0.45 + (1 - yy / H) * 0.75) - 0.15, 0, 1)[..., None] ** 1.6
    base = np.array((6, 8, 18), np.float32) * (1 - k) + np.array(col, np.float32) * 0.55 * k
    base = base + np.array(dark, np.float32) * 0.6
    bg = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8)).convert("RGBA")
    bg.alpha_composite(_halftone(col))
    # player sized to ~62% of the height, standing behind the lower-third
    th = int(H * 0.62); s = th / cut.height
    tw = int(cut.width * s)
    if tw > W * 0.98: s = W * 0.98 / cut.width; tw, th = int(cut.width * s), int(cut.height * s)
    cut = cut.resize((tw, th), Image.LANCZOS)
    player = _rim(cut, col)
    shadow = Image.new("RGBA", cut.size, (0, 0, 0, 0)); shadow.putalpha(cut.split()[3].filter(ImageFilter.GaussianBlur(22)).point(lambda v: int(v * 0.75)))
    # ghost name: huge outlined word behind the player
    name = clean(sc.get("player") or sc.get("title") or "")
    ws = name.split()
    word = (ws[-1] if sc.get("player") else max(ws, key=len)) if ws else ""  # surname, like TV intros
    word = word if is_hindi(word) else word.upper()
    ghost = None
    if word:
        f = font(fk(word, "head", "hi_bold"), 420)
        gw = int(f.getlength(word)) + 80
        ghost = Image.new("RGBA", (gw, 560), (0, 0, 0, 0)); d = ImageDraw.Draw(ghost)
        d.text((40, 280), word, font=f, anchor="lm", fill=col + (55,), stroke_width=5, stroke_fill=C_WHITE + (120,))
        ghost = ghost.rotate(90, expand=True, resample=Image.BICUBIC)  # vertical, runs up the side like TV intros
        if ghost.height > H * 1.05:
            r = H * 1.05 / ghost.height; ghost = ghost.resize((int(ghost.width * r), int(ghost.height * r)), Image.LANCZOS)
    # lower-third stat panel
    parts = []
    if sc.get("title"):
        t = sc["title"]; parts.append(text_layer(t if is_hindi(t) else t.upper(), fk(t), 86, glow=None, stroke=0, max_w=W - 220))
    if sc.get("number") is not None:
        num = f"{sc['number']}{(' ' + sc['unit']) if sc.get('unit') else ''}"
        parts.append(text_layer(num, fk(num, "head", "hi_bold"), 150, fill=C_GOLD, glow=None, stroke=0, max_w=W - 220))
    if sc.get("sub"):
        parts.append(text_layer(sc["sub"], fk(sc["sub"], "semi", "hi"), 46, glow=None, stroke=0, max_w=W - 220))
    ph = sum(p.height for p in parts) + 40
    pw = W - 80
    panel = Image.new("RGBA", (pw, ph), (0, 0, 0, 0)); d = ImageDraw.Draw(panel); sl = 46
    d.polygon([(sl, 0), (pw, 0), (pw - sl, ph), (0, ph)], fill=(6, 9, 20, 228))
    d.polygon([(sl, 0), (sl + 16, 0), (16, ph), (0, ph)], fill=col + (255,))       # team stripe
    d.line([(sl, 1), (pw, 1)], fill=C_GOLD + (255,), width=5)                       # gold top rule
    y = 20
    for p in parts:
        panel.alpha_composite(p, ((pw - p.width) // 2, y)); y += p.height
    return {"bg": bg, "rays": _rays(col), "player": player, "glow": _glow(cut, col), "shadow": shadow,
            "ghost": ghost, "panel": panel, "col": col}


def _ease(t): t = max(0.0, min(1.0, t)); return 1 - (1 - t) ** 3


def _paste(canvas, layer, cx, cy, alpha=1.0, scale=1.0):
    if alpha <= 0.01: return
    if abs(scale - 1) > 0.002:
        layer = layer.resize((max(1, int(layer.width * scale)), max(1, int(layer.height * scale))), Image.BICUBIC)
    if alpha < 0.999:
        layer = layer.copy(); layer.putalpha(layer.split()[3].point(lambda v: int(v * alpha)))
    canvas.alpha_composite(layer, (int(cx - layer.width / 2), int(cy - layer.height / 2)))


def frame(HL, kicker_layer, t, dur, t_abs):
    """One frame of the hero card. Captions/finish are drawn by the caller."""
    p = t / dur
    fr = HL["bg"].copy()
    rays = HL["rays"].rotate(t_abs * 4, resample=Image.BILINEAR)  # slow, smooth rotation
    fr.alpha_composite(rays, (int(W * 0.5 - rays.width / 2), int(H * 0.34 - rays.height / 2)))
    if HL["ghost"] is not None:  # ghost name drifts up faster than the player -> parallax depth
        g = HL["ghost"]; a = _ease(t / 0.5)
        fr.alpha_composite(g if a > 0.99 else _fade(g, a), (int(W * 0.06 - (1 - a) * 120), int((H - g.height) / 2 + 60 - 140 * p)))
    # player: scale-in 1.3 -> 1.0 with motion blur, then slow push 1.0 -> 1.04
    e = _ease(t / 0.4); sc = 1.3 - 0.3 * e + 0.04 * p
    pcx, pcy = W * 0.54, H * 0.10 + HL["player"].height / 2 - 20 * p
    _paste(fr, HL["glow"], pcx, pcy, 0.9 * e, sc * 1.02)
    _paste(fr, HL["shadow"], pcx + 26, pcy + 22, e, sc)
    if e < 0.97:  # radial motion blur: average a few scales along the move
        for j in (2, 1):  # trailing copies along the zoom path
            _paste(fr, HL["player"], pcx, pcy, 0.28 * (1 - e) + 0.05, sc + (1 - e) * 0.07 * j)
        _paste(fr, HL["player"], pcx, pcy, 0.55 + 0.45 * e, sc)
    else:
        _paste(fr, HL["player"], pcx, pcy, 1.0, sc)
    # lower-third wipes in from the left, bottom edge kept above the captions
    pn = HL["panel"]; a = _ease((t - 0.25) / 0.45)
    if a > 0:
        wv = max(1, int(pn.width * a)); cropped = Image.new("RGBA", pn.size, (0, 0, 0, 0)); cropped.alpha_composite(pn.crop((0, 0, wv, pn.height)))
        py = int(H * 0.79 - pn.height)
        fr.alpha_composite(cropped, (40, py))
        if kicker_layer is not None:
            ka = _ease((t - 0.45) / 0.3)
            if ka > 0: _paste(fr, kicker_layer, 60 + kicker_layer.width / 2 + (1 - ka) * -200, py - kicker_layer.height / 2 - 8, ka)
    return fr


def _fade(layer, a):
    l = layer.copy(); l.putalpha(l.split()[3].point(lambda v: int(v * a))); return l
