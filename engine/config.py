from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
FONTS = ROOT / "assets" / "fonts"
BG = ROOT / "assets" / "bg"
W, H, FPS = 1080, 1920, 30
SR = 48000
BRAND = "THE SPORTS GYAN AI"
# palette: neon cricket night
C_BG = (8, 10, 22)
C_NEON = (0, 229, 255)      # cyan neon
C_HOT = (255, 46, 99)       # hot pink / impact
C_GOLD = (255, 200, 40)
C_WHITE = (245, 247, 255)
FONT = {
    "head": FONTS / "Anton-Regular.ttf",
    "black": FONTS / "Poppins-Black.ttf",
    "bold": FONTS / "Poppins-Bold.ttf",
    "semi": FONTS / "Poppins-SemiBold.ttf",
    "hi_bold": FONTS / "Mukta-ExtraBold.ttf",
    "hi": FONTS / "Mukta-Bold.ttf",
}
