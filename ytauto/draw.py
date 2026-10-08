"""Shared skia drawing helpers and the raw-frame → ffmpeg encoder used by the cartoon and zoo-window engines."""
import math
import subprocess
from functools import lru_cache

import numpy as np
import skia

from . import config

W, H = 1080, 1920
INK = skia.Color(29, 29, 27)
PAPER = skia.Color(244, 239, 220)
FALLBACK_FONTS = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
                  "/Library/Fonts/Arial Bold.ttf"]


def rgb(hexstr, alpha=255):
    h = hexstr.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return skia.Color(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), alpha)


@lru_cache(maxsize=None)
def typeface(family, bold=False):
    """Bundled font from assets/fonts (scripts/fetch_fonts.py) or a system fallback."""
    key = family.lower().replace(" ", "")
    for p in sorted(config.FONTS.glob("*.ttf")):
        if p.stem.lower().replace("-", "").startswith(key):
            tf = skia.Typeface.MakeFromFile(str(p))
            if tf:
                return tf
    tf = skia.Typeface(family, skia.FontStyle.Bold() if bold else skia.FontStyle.Normal())
    if tf and tf.getFamilyName().lower().replace(" ", "") == key:
        return tf
    for path in FALLBACK_FONTS:
        tf = skia.Typeface.MakeFromFile(path)
        if tf:
            return tf
    return skia.Typeface.MakeDefault()


def font(family, size, bold=False):
    return skia.Font(typeface(family, bold), size)


class Frame:
    """An RGBA numpy buffer with a skia canvas drawing straight into it."""

    def __init__(self, w=W, h=H):
        self.array = np.zeros((h, w, 4), dtype=np.uint8)
        self.surface = skia.Surface(self.array, colorType=skia.kRGBA_8888_ColorType)
        self.canvas = self.surface.getCanvas()

    def bytes(self):
        self.surface.flushAndSubmit() if hasattr(self.surface, "flushAndSubmit") else None
        return self.array.tobytes()


def stroke(color=INK, width=8, boil=None, dash=None):
    p = skia.Paint(AntiAlias=True, Color=color, Style=skia.Paint.kStroke_Style, StrokeWidth=width,
                   StrokeCap=skia.Paint.kRound_Cap, StrokeJoin=skia.Paint.kRound_Join)
    if dash:
        p.setPathEffect(skia.DashPathEffect.Make(dash, 0))
    elif boil is not None:
        p.setPathEffect(skia.DiscretePathEffect.Make(16, 1.7, boil))
    return p


def fill(color):
    return skia.Paint(AntiAlias=True, Color=color, Style=skia.Paint.kFill_Style)


def path(points, closed=False, curve=False):
    p = skia.Path()
    p.moveTo(*points[0])
    if curve and len(points) == 3:
        p.quadTo(*points[1], *points[2])
    else:
        for pt in points[1:]:
            p.lineTo(*pt)
    if closed:
        p.close()
    return p


def text(canvas, s, x, y, fnt, color=INK, outline=None, outline_w=0, align="center"):
    """Draw text with its baseline centred vertically on y (cap height approximation)."""
    w = fnt.measureText(s)
    x0 = x - w / 2 if align == "center" else x
    y0 = y + fnt.getSize() * 0.35
    blob = skia.TextBlob.MakeFromString(s, fnt)
    if outline:
        canvas.drawTextBlob(blob, x0, y0, stroke(outline, outline_w))
    canvas.drawTextBlob(blob, x0, y0, fill(color))
    return w


def wrap(s, max_chars, max_lines=4):
    words, lines, cur = s.split(), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > max_chars:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip(".,!?") + "…"
    return lines


def ease(u):
    u = max(0.0, min(1.0, u))
    return u * u * (3 - 2 * u)


def seg(u, a, b):
    """Progress of u through [a, b], clamped to 0..1."""
    return max(0.0, min(1.0, (u - a) / (b - a))) if b > a else float(u >= b)


def paper_texture(seed=3):
    rng = np.random.default_rng(seed)
    noise = rng.normal(0, 1, (H // 4, W // 4))
    noise = np.kron(noise, np.ones((4, 4)))
    base = np.array([244, 239, 220], dtype=float)
    arr = np.clip(base[None, None, :] + noise[..., None] * 3.0, 0, 255).astype(np.uint8)
    rgba = np.dstack([arr, np.full((H, W), 255, np.uint8)])
    return skia.Image.fromarray(rgba, colorType=skia.kRGBA_8888_ColorType)


class Encoder:
    """Pipe raw RGBA frames into ffmpeg and mux the soundtrack."""

    def __init__(self, out_path, fps, audio_path, duration, preset=None):
        self.proc = subprocess.Popen(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W}x{H}",
             "-r", str(fps), "-i", "-", "-i", str(audio_path), "-map", "0:v", "-map", "1:a",
             "-c:v", "libx264", "-preset", preset or config.STORY_X264_PRESET, "-crf", "21", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "160k", "-t", f"{duration:.3f}", "-movflags", "+faststart", str(out_path)],
            stdin=subprocess.PIPE, stderr=subprocess.PIPE)

    def write(self, frame_bytes):
        self.proc.stdin.write(frame_bytes)

    def close(self):
        self.proc.stdin.close()
        err = self.proc.stderr.read().decode(errors="ignore")
        if self.proc.wait() != 0:
            raise RuntimeError(f"ffmpeg failed: {err[-1500:]}")


def rot_point(x, y, cx, cy, deg):
    r = math.radians(deg)
    dx, dy = x - cx, y - cy
    return cx + dx * math.cos(r) - dy * math.sin(r), cy + dx * math.sin(r) + dy * math.cos(r)
