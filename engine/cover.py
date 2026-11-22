"""Thumbnail/cover 1080x1920; all text inside the centre 1080x1350 safe area (grid crop)."""
from PIL import Image, ImageDraw
from .render import load_bg, bg_frame, overlay, text_layer, paste, is_hindi, fk, light_streak
from .config import W, H, C_HOT, C_GOLD, C_NEON, C_WHITE

def make_cover(cv, out):
    im = bg_frame(load_bg(cv.get("image_path")), 0.6, 3).convert("RGBA")
    im.alpha_composite(overlay()); im.alpha_composite(light_streak(), (-300, int(H * 0.3)))
    top = (H - 1350) // 2
    if cv.get("tag"):
        tg = text_layer(cv["tag"], fk(cv["tag"], "black", "hi_bold"), 54, fill=(10, 10, 20), glow=None)
        box = Image.new("RGBA", (tg.width + 30, tg.height), C_HOT + (255,)); box.alpha_composite(tg, (15, 0))
        paste(im, box, W / 2, top + 150)
    t = text_layer(cv["title"] if is_hindi(cv["title"]) else cv["title"].upper(), fk(cv["title"]), 150, glow=C_HOT, glow_r=26, stroke=3)
    paste(im, t, W / 2, top + 520)
    if cv.get("big"):
        b = text_layer(cv["big"], "head", 300, fill=C_GOLD, glow=C_NEON, glow_r=30, stroke=3)
        paste(im, b, W / 2, top + 520 + t.height / 2 + b.height / 2 - 20)
    if cv.get("sub"):
        s = text_layer(cv["sub"], fk(cv["sub"], "bold", "hi_bold"), 64, glow=None, stroke=3)
        paste(im, s, W / 2, top + 1250)
    im.convert("RGB").save(out, quality=94); return out
