"""Built-in scene illustrator (fallback when AI images fail). Draws layered silhouettes with Pillow.

Inputs use the story vocabulary from HANDOVER.md §3c: setting, figure, time, mood.
"""
import hashlib
import random

from PIL import Image, ImageDraw, ImageFilter

W, H = 1080, 1920
HORIZON = 1240

SKY = {  # top, bottom
    "night": ((8, 12, 34), (38, 44, 82)),
    "dusk": ((52, 30, 82), (232, 120, 70)),
    "day": ((96, 160, 222), (200, 228, 245)),
    "dawn": ((70, 80, 140), (250, 190, 140)),
    "storm": ((28, 32, 38), (82, 90, 98)),
}
MOOD_TINT = {
    "eerie": (40, 90, 60, 60), "epic": (200, 140, 40, 40), "calm": (120, 170, 200, 25),
    "tense": (140, 20, 20, 50), "sad": (60, 80, 120, 60), "wonder": (170, 120, 220, 40),
}
STYLE_INK = {"creepy_comic": (14, 20, 12), "dark_realism": (6, 6, 8), "epic_painting": (30, 18, 8)}


def _gradient(top, bottom):
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = min(1.0, y / HORIZON)
        d.line([(0, y), (W, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)))
    return img


def _shade(c, k):
    return tuple(max(0, min(255, int(v * k))) for v in c)


def _tree(d, x, base, h, col, rng):
    d.rectangle([x - h * 0.04, base - h * 0.35, x + h * 0.04, base], fill=col)
    for i in range(3):
        w = h * (0.32 - i * 0.08)
        top = base - h * (0.3 + i * 0.25)
        d.polygon([(x - w, top + h * 0.3), (x + w, top + h * 0.3), (x + rng.uniform(-8, 8), top - h * 0.12)], fill=col)


def _house(d, x, base, s, col, lit):
    d.rectangle([x - 90 * s, base - 140 * s, x + 90 * s, base], fill=col)
    d.polygon([(x - 110 * s, base - 140 * s), (x + 110 * s, base - 140 * s), (x, base - 240 * s)], fill=col)
    if lit:
        d.rectangle([x - 50 * s, base - 105 * s, x - 15 * s, base - 70 * s], fill=(250, 200, 90))


def _setting(d, setting, ink, rng):
    far, mid, near = _shade(ink, 2.2), _shade(ink, 1.5), ink
    g = HORIZON
    if setting in ("mountains", "desert", "road", "battlefield"):
        pts = [(0, g)] + [(x, g - rng.uniform(150, 420)) for x in range(0, W + 200, 180)] + [(W, g)]
        d.polygon(pts, fill=far)
    if setting == "forest":
        for i in range(14):
            _tree(d, rng.uniform(-40, W + 40), g + rng.uniform(-10, 60), rng.uniform(380, 640), mid, rng)
        for x in (60, W - 80):
            _tree(d, x, H - 300, 1100, near, rng)
    elif setting in ("house", "village"):
        n = 1 if setting == "house" else 5
        for i in range(n):
            x = W / 2 if n == 1 else 120 + i * 210
            _house(d, x, g + 40, 1.9 if n == 1 else 1.0, mid, rng.random() > 0.4)
    elif setting in ("castle", "temple", "ruins"):
        cx = W / 2
        d.rectangle([cx - 300, g - 420, cx + 300, g + 40], fill=mid)
        for tx in (cx - 300, cx + 220):
            d.rectangle([tx, g - 620, tx + 80, g + 40], fill=mid)
        if setting == "temple":
            d.polygon([(cx - 360, g - 420), (cx + 360, g - 420), (cx, g - 640)], fill=mid)
        for bx in range(int(cx - 300), int(cx + 300), 60):
            d.rectangle([bx, g - 460, bx + 34, g - 420], fill=mid)
        if setting == "ruins":  # rubble at the foot of the broken walls
            for _ in range(9):
                rx = rng.uniform(cx - 380, cx + 380)
                d.ellipse([rx - 50, g - 10, rx + 50, g + 50], fill=near)
    elif setting == "sea":
        for i in range(12):
            y = g + i * 55
            d.arc([-100 + (i % 2) * 90, y, W + 100, y + 120], 180, 360, fill=_shade(mid, 1.2), width=6)
    elif setting == "city":
        x = 0
        while x < W:
            w, h = rng.uniform(80, 170), rng.uniform(250, 700)
            d.rectangle([x, g - h, x + w, g + 60], fill=mid)
            for wy in range(int(g - h + 30), int(g), 60):
                for wx in range(int(x + 15), int(x + w - 20), 40):
                    if rng.random() > 0.6:
                        d.rectangle([wx, wy, wx + 16, wy + 24], fill=(240, 210, 120))
            x += w + 8
    elif setting == "cave":
        d.rectangle([0, 0, W, H], fill=near)
        d.ellipse([140, 520, W - 140, H + 400], fill=_shade(ink, 4.5))
    elif setting == "room":
        d.rectangle([0, 0, W, H], fill=_shade(ink, 3.5))
        d.rectangle([300, 420, 780, 900], fill=(30, 40, 70))
        d.line([(540, 420), (540, 900)], fill=near, width=14)
        d.line([(300, 660), (780, 660)], fill=near, width=14)
    if setting == "road":
        d.polygon([(W / 2 - 40, g), (W / 2 + 40, g), (W - 60, H), (60, H)], fill=_shade(mid, 1.4))
    if setting == "battlefield":
        for i in range(5):
            x = rng.uniform(80, W - 80)
            d.line([(x, g + 80), (x, g - 220)], fill=near, width=8)
            d.polygon([(x, g - 220), (x + 110, g - 190), (x, g - 160)], fill=(140, 30, 30))
    if setting not in ("cave", "room", "sea"):
        d.rectangle([0, g + 40, W, H], fill=near)


def _figure(d, figure, ink, rng):
    if figure == "none":
        return
    col = _shade(ink, 0.6)
    x, base = W / 2 + rng.uniform(-120, 120), 1560
    if figure == "crowd":
        for i in range(7):
            _person(d, 110 + i * 145, base + rng.uniform(-20, 20), 0.75, col)
        return
    if figure in ("wolf", "creature"):
        s = 1.4 if figure == "creature" else 1.0
        d.ellipse([x - 200 * s, base - 260 * s, x + 160 * s, base - 80 * s], fill=col)
        d.ellipse([x + 100 * s, base - 340 * s, x + 260 * s, base - 200 * s], fill=col)
        d.polygon([(x + 130 * s, base - 320 * s), (x + 160 * s, base - 420 * s), (x + 190 * s, base - 320 * s)], fill=col)
        for lx in (-150, -60, 40, 110):
            d.rectangle([x + lx * s, base - 120 * s, x + (lx + 30) * s, base], fill=col)
        eye = (230, 40, 30) if figure == "creature" else (240, 220, 90)
        d.ellipse([x + 200 * s, base - 300 * s, x + 222 * s, base - 278 * s], fill=eye)
        return
    scale = {"child": 0.7, "king": 1.1, "soldier": 1.05}.get(figure, 1.0)
    _person(d, x, base, scale, col, hood=figure == "hooded", crown=figure == "king", spear=figure == "soldier")


def _person(d, x, base, s, col, hood=False, crown=False, spear=False):
    h = 520 * s
    d.polygon([(x - 90 * s, base), (x + 90 * s, base), (x + 55 * s, base - h * 0.7), (x - 55 * s, base - h * 0.7)], fill=col)
    d.ellipse([x - 55 * s, base - h, x + 55 * s, base - h * 0.78], fill=col)
    if hood:
        d.polygon([(x - 80 * s, base - h * 0.72), (x + 80 * s, base - h * 0.72), (x, base - h * 1.12)], fill=col)
    if crown:
        d.polygon([(x - 50 * s, base - h * 0.98), (x - 30 * s, base - h * 1.1), (x, base - h * 1.0),
                   (x + 30 * s, base - h * 1.1), (x + 50 * s, base - h * 0.98)], fill=(220, 180, 60))
    if spear:
        d.line([(x + 110 * s, base), (x + 110 * s, base - h * 1.25)], fill=col, width=int(12 * s))


def render(scene, style="storybook", seed="", path=None):
    rng = random.Random(int(hashlib.sha1(f"{seed}|{scene}".encode()).hexdigest()[:8], 16))
    time_ = scene.get("time", "night")
    img = _gradient(*SKY.get(time_, SKY["night"]))
    d = ImageDraw.Draw(img, "RGBA")
    if time_ in ("night", "storm", "dusk"):
        mx, my = rng.uniform(200, 880), rng.uniform(220, 520)
        d.ellipse([mx - 90, my - 90, mx + 90, my + 90], fill=(245, 240, 215, 230 if time_ == "night" else 120))
        if time_ == "night":
            for _ in range(80):
                sx, sy = rng.uniform(0, W), rng.uniform(0, 900)
                d.point((sx, sy), fill=(255, 255, 255, 200))
    else:
        sx, sy = rng.uniform(200, 880), rng.uniform(300, 700)
        d.ellipse([sx - 110, sy - 110, sx + 110, sy + 110], fill=(255, 236, 170, 200))
    ink = STYLE_INK.get(style, (18, 22, 30))
    _setting(d, scene.get("setting", "forest"), ink, rng)
    _figure(d, scene.get("figure", "none"), ink, rng)
    if time_ == "storm":
        x = rng.uniform(150, 900)
        pts = [(x, 0)] + [(x + rng.uniform(-70, 70), y) for y in range(140, 900, 140)]
        d.line(pts, fill=(235, 240, 255, 230), width=7)
        for _ in range(260):
            rx, ry = rng.uniform(0, W), rng.uniform(0, H)
            d.line([(rx, ry), (rx - 12, ry + 46)], fill=(200, 210, 230, 70), width=2)
    r, g, b, a = MOOD_TINT.get(scene.get("mood", "calm"), (0, 0, 0, 0))
    img = Image.alpha_composite(img.convert("RGBA"), Image.new("RGBA", (W, H), (r, g, b, a)))
    # vignette
    vig = Image.new("L", (W, H), 0)
    ImageDraw.Draw(vig).ellipse([-260, -160, W + 260, H + 160], fill=255)
    vig = vig.filter(ImageFilter.GaussianBlur(160))
    dark = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    img = Image.composite(img, dark, vig).convert("RGB")
    if style in ("watercolor", "storybook", "epic_painting"):
        img = img.filter(ImageFilter.SMOOTH_MORE)
    if path:
        img.save(path, quality=92)
    return img
