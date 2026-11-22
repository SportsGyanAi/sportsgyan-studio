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
    band = Image.new("RGBA", (W + 200, t.height + 10), (0, 0, 0, 0))
    ImageDraw.Draw(band).polygon([(80, 0), (W + 200, 0), (W + 120, band.height), (0, band.height)], fill=(8, 10, 22, 190))
    band = band.rotate(4, expand=True, resample=Image.BICUBIC)
    paste(im, band, W / 2, top + 520)
    paste(im, t, W / 2, top + 520)
    if cv.get("big"):
        b = text_layer(cv["big"], fk(cv["big"], "head", "hi_bold"), 300 if not is_hindi(cv["big"]) and len(cv["big"]) <= 6 else 120, fill=C_GOLD, glow=C_NEON, glow_r=30, stroke=3)
        paste(im, b, W / 2, top + 520 + t.height / 2 + b.height / 2 - 20)
    if cv.get("sub"):
        s = text_layer(cv["sub"], fk(cv["sub"], "bold", "hi_bold"), 64, glow=None, stroke=3)
        paste(im, s, W / 2, top + 1250)
    im.convert("RGB").save(out, quality=94); return out
