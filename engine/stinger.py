"""Broadcast stinger: logo-free diagonal slab wipe (3 staggered colour slabs + white edge line + glow)
that covers the screen, then reveals the new scene. Plays over first STING seconds of a scene."""
import numpy as np
from PIL import Image
STING = 0.5
COLS = [(255, 196, 0), (20, 24, 40), (230, 40, 60)]
_cache = {}
def _grid(W, H):
    k = (W, H)
    if k not in _cache:
        y, x = np.mgrid[0:H, 0:W].astype(np.float32)
        _cache[k] = (x + 0.45 * y) / (W + 0.45 * H)  # 0..1 diagonal coordinate
    return _cache[k]
def apply(fr, t, flip=False):
    if t >= STING: return fr
    W, H = fr.size; d = _grid(W, H)
    if flip: d = 1 - d
    p = t / STING; a = np.asarray(fr).astype(np.float32)
    # each slab: covered where d < edge(p); slabs staggered; cover phase 0..0.5, reveal 0.5..1
    out = a
    for n, c in enumerate(COLS):
        q = np.clip((p - n * 0.07) / 0.5, 0, 1.6)
        lead = q * 1.3 - 0.15          # front edge sweeping across
        trail = (q - 1.0) * 1.3 - 0.15 if q > 1.0 else -1
        m = ((d < lead) & (d >= trail)).astype(np.float32)[..., None]
        out = out * (1 - m) + np.array(c, np.float32) * m
        edge = np.exp(-((d - lead) ** 2) / 0.00015)[..., None] * (0.9 if q < 1.4 else 0)
        out = out + 255 * edge * 0.5
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))
