"""Cartoon gags renderer: crude meme-style 2D animation on cream paper (HANDOVER.md §3a).

Noodle-limb characters (human, cat, dog, bunny, bear) with 10 moods and 18 actions, 11 props, hand-held items,
speech bubbles with lip-flap, punch-in cuts, camera shake and line boil. 1080x1920.
"""
import math
import random

import skia

from .draw import INK, PAPER, ease, fill, font, path, rgb, seg, stroke, text, wrap

FLOOR = 1500
CAPTION_BAND = 360
WHITE = skia.Color(255, 255, 255)
SPECIES_FILL = {"human": rgb("#ffffff"), "cat": rgb("#f6c78e"), "dog": rgb("#e9d3b0"), "bunny": rgb("#f4f1ee"),
                "bear": rgb("#c9a07a")}
ACCENT = {"cat": rgb("#d98a3d"), "dog": rgb("#8a5a3c"), "bunny": rgb("#f3a6b8"), "bear": rgb("#6e452c")}


def char_home(shot, role):
    has_prop = shot["prop"]["kind"] != "none"
    has_other = shot["other"]["present"]
    if role == "hero":
        return 300 if (has_prop and has_other) else 380 if (has_other or has_prop) else 540
    return 580 if has_prop else 720


class Pose:
    def __init__(self):
        self.dx = self.dy = self.rot = 0.0
        self.sx = self.sy = 1.0
        self.arm_l, self.arm_r = 110.0, 70.0  # degrees from +x, clockwise on screen: 90 = straight down
        self.walk = None  # leg phase in radians
        self.mouth = None  # "o" for scream
        self.charred = False
        self.hidden = False
        self.fx = []  # ("stars"|"tears"|"lines"|"burst"|"speed"|"smoke"|"sweat", strength)
        self.pivot = "feet"


def action_pose(action, u, t, dur, home_x, other_x):
    p = Pose()
    p.dy = -4 * math.sin(2 * math.pi * 1.2 * t)
    if action == "walk_in":
        k = ease(seg(u, 0, 0.6))
        p.dx = -700 * (1 - k) * (1 if home_x < 700 else -1)
        if k < 1:
            p.walk = t * 12
    elif action == "walk_out":
        k = ease(seg(u, 0.3, 1))
        p.dx = 1000 * k * (1 if home_x >= 540 else -1)
        if k > 0:
            p.walk = t * 12
    elif action == "run_away":
        k = seg(u, 0.15, 0.6) ** 2
        p.dx = 1500 * k * (1 if home_x >= 400 else -1)
        p.walk = t * 30
        p.rot = 12 * (1 if home_x >= 400 else -1) if u > 0.1 else 0
        if 0.1 < u < 0.65:
            p.fx.append(("speed", 1))
        p.arm_l, p.arm_r = 160, 20
    elif action == "jump":
        k = seg(u, 0.05, 0.65)
        p.dy = -280 * math.sin(math.pi * k)
        p.arm_l, p.arm_r = 220, -40
        p.sy = 0.9 if k == 0 or k == 1 else 1.05
    elif action == "shake":
        p.dx = 11 * math.sin(2 * math.pi * 28 * t)
        p.fx.append(("sweat", 1))
    elif action == "scream":
        p.dx = 6 * math.sin(2 * math.pi * 31 * t)
        p.arm_l, p.arm_r = 230, -50
        p.mouth = "o"
        p.fx.append(("lines", 1))
    elif action == "fall":
        k = ease(seg(u, 0.1, 0.4))
        p.rot = 88 * k * (1 if home_x < 700 else -1)
        p.arm_l, p.arm_r = 160, 20
    elif action == "faint":
        k = ease(seg(u, 0.2, 0.5))
        p.rot = -88 * k * (1 if home_x < 700 else -1)
        if k > 0.9:
            p.fx.append(("stars", 1))
    elif action == "spin":
        p.rot = 720 * ease(seg(u, 0.1, 0.8))
        p.pivot = "center"
        p.arm_l, p.arm_r = 180, 0
    elif action == "stretch_up":
        k = ease(seg(u, 0.1, 0.6))
        p.sy, p.sx = 1 + 0.9 * k, 1 - 0.25 * k
        p.arm_l, p.arm_r = 250, -70
    elif action == "explode":
        if u < 0.45:
            p.dx = 14 * seg(u, 0, 0.45) * math.sin(2 * math.pi * 30 * t)
            p.sx = p.sy = 1 + 0.12 * seg(u, 0, 0.45)
        else:
            p.charred = True
            p.fx.append(("burst", seg(u, 0.45, 0.75)))
            p.fx.append(("smoke", seg(u, 0.55, 1)))
            p.arm_l, p.arm_r = 150, 30
    elif action == "wave":
        p.arm_r = -60 + 25 * math.sin(2 * math.pi * 3 * t)
    elif action == "point":
        p.arm_r = 0 if other_x is None or other_x > home_x else 180
        if other_x is not None and other_x < home_x:
            p.arm_l = 180
            p.arm_r = 70
    elif action == "shrink":
        k = ease(seg(u, 0.1, 0.7))
        p.sx = p.sy = 1 - 0.7 * k
    elif action == "grow":
        k = ease(seg(u, 0.1, 0.7))
        p.sx = p.sy = 1 + 0.9 * k
    elif action == "dance":
        p.dx = 30 * math.sin(2 * math.pi * 1.8 * t)
        p.rot = 7 * math.sin(2 * math.pi * 1.8 * t)
        p.arm_l = 200 + 50 * math.sin(2 * math.pi * 3.6 * t)
        p.arm_r = -20 - 50 * math.sin(2 * math.pi * 3.6 * t + 1)
        p.walk = t * 10
        p.dy = -abs(18 * math.sin(2 * math.pi * 1.8 * t))
    elif action == "cry":
        p.dx = 3 * math.sin(2 * math.pi * 9 * t)
        p.fx.append(("tears", 1))
    return p


def draw_face(c, hx, hy, r, mood, talking, t, boil, mouth=None, dead=False):
    ink = fill(INK)
    st = stroke(width=6, boil=boil)
    ex = r * 0.36
    ey = hy - r * 0.1
    if dead or mood == "dead":
        for sx in (-1, 1):
            x = hx + sx * ex
            c.drawLine(x - 12, ey - 12, x + 12, ey + 12, st)
            c.drawLine(x - 12, ey + 12, x + 12, ey - 12, st)
    elif mood == "shock":
        for sx in (-1, 1):
            c.drawCircle(hx + sx * ex, ey, 22, fill(WHITE))
            c.drawCircle(hx + sx * ex, ey, 22, st)
            c.drawCircle(hx + sx * ex, ey, 6, ink)
    elif mood == "twitch":
        c.drawCircle(hx - ex, ey, 20, fill(WHITE))
        c.drawCircle(hx - ex, ey, 20, st)
        c.drawCircle(hx - ex, ey, 6, ink)
        k = 1 + 0.5 * (int(t * 14) % 2)
        c.drawCircle(hx + ex, ey, 8 * k, ink)
    elif mood == "cry":
        for sx in (-1, 1):
            c.drawArc(skia.Rect(hx + sx * ex - 14, ey - 8, hx + sx * ex + 14, ey + 12), 180, 180, False, st)
    elif mood == "smug":
        for sx in (-1, 1):
            c.drawCircle(hx + sx * ex, ey + 3, 8, ink)
            c.drawLine(hx + sx * ex - 14, ey - 4, hx + sx * ex + 14, ey - 4, st)
    else:
        for sx in (-1, 1):
            c.drawCircle(hx + sx * ex, ey, 9, ink)
    # brows
    if mood == "angry":
        c.drawLine(hx - ex - 18, ey - 30, hx - ex + 14, ey - 18, st)
        c.drawLine(hx + ex + 18, ey - 30, hx + ex - 14, ey - 18, st)
    elif mood in ("sad", "cry"):
        c.drawLine(hx - ex - 16, ey - 20, hx - ex + 14, ey - 30, st)
        c.drawLine(hx + ex + 16, ey - 20, hx + ex - 14, ey - 30, st)
    # mouth
    my = hy + r * 0.42
    if mouth == "o" or (talking and int(t / 0.09) % 2 == 0):
        size = 26 if mouth == "o" else 15
        c.drawOval(skia.Rect(hx - size * 0.8, my - size, hx + size * 0.8, my + size), ink)
    elif dead or mood == "dead":
        c.drawLine(hx - 20, my, hx + 20, my, st)
        c.drawOval(skia.Rect(hx + 2, my, hx + 20, my + 22), fill(rgb("#e86f7a")))
    elif mood in ("smile",):
        c.drawArc(skia.Rect(hx - 26, my - 22, hx + 26, my + 12), 20, 140, False, st)
    elif mood == "grin":
        pth = skia.Path()
        pth.moveTo(hx - 34, my - 8)
        pth.lineTo(hx + 34, my - 8)
        pth.quadTo(hx, my + 44, hx - 34, my - 8)
        c.drawPath(pth, fill(WHITE))
        c.drawPath(pth, st)
    elif mood == "smug":
        c.drawPath(path([(hx - 16, my + 4), (hx + 10, my + 6), (hx + 26, my - 8)], curve=True), st)
    elif mood in ("angry", "sad", "cry"):
        c.drawArc(skia.Rect(hx - 24, my - 4, hx + 24, my + 26), 200, 140, False, st)
    elif mood == "twitch":
        pth = skia.Path()
        pth.moveTo(hx - 24, my)
        for i in range(1, 7):
            pth.lineTo(hx - 24 + i * 8, my + (6 if i % 2 else -6))
        c.drawPath(pth, st)
    elif mood == "shock":
        c.drawOval(skia.Rect(hx - 12, my - 14, hx + 12, my + 14), ink)
    else:
        c.drawLine(hx - 18, my + 4, hx + 18, my + 4, st)


def draw_character(c, x, cast, pose, mood, item, talking, t, boil, flip=False):
    if pose.hidden:
        return
    species, look, voice = cast["species"], cast["look"], cast["voice"]
    body_fill = fill(rgb("#2b2b2b")) if pose.charred else fill(SPECIES_FILL[species])
    st = stroke(width=8, boil=boil)
    tall = look == "tall"
    head_r = 78 if tall else 92
    neck = -360 if tall else -330
    hip = -170
    c.save()
    c.translate(x + pose.dx, FLOOR + pose.dy)
    pivot_y = -260 if pose.pivot == "center" else 0
    c.translate(0, pivot_y)
    c.rotate(pose.rot)
    c.translate(0, -pivot_y)
    c.scale(pose.sx * (-1 if flip else 1), pose.sy)
    # tail
    if species in ("cat", "dog"):
        c.drawPath(path([(0, hip), (-90, hip - 30), (-110, hip - 120)], curve=True), st)
    elif species in ("bunny", "bear"):
        c.drawCircle(-28, hip - 10, 18, body_fill)
        c.drawCircle(-28, hip - 10, 18, st)
    # legs
    for side in (-1, 1):
        ph = 0 if pose.walk is None else math.sin(pose.walk + (0 if side < 0 else math.pi))
        foot_x = side * 42 + ph * 55
        foot_y = -max(0, ph) * 18
        knee = (side * 30 + ph * 40, (hip + foot_y) / 2)
        c.drawPath(path([(side * 14, hip), knee, (foot_x, foot_y)], curve=True), st)
        c.drawLine(foot_x, foot_y, foot_x + 26 * (1 if side > 0 else -1) * 0.8, foot_y, st)
    # torso: a soft bean so animals and humans read the same
    torso = skia.Path()
    torso.moveTo(-34, neck + 10)
    torso.cubicTo(-58, neck + 80, -54, hip, -22, hip + 8)
    torso.lineTo(22, hip + 8)
    torso.cubicTo(54, hip, 58, neck + 80, 34, neck + 10)
    torso.close()
    c.drawPath(torso, body_fill)
    c.drawPath(torso, st)
    # arms
    shoulder = (0, neck + 30)
    hands = []
    for side, ang in ((-1, pose.arm_l), (1, pose.arm_r)):
        a = math.radians(ang)
        hx_, hy_ = shoulder[0] + side * 10 + math.cos(a) * 150, shoulder[1] + math.sin(a) * 150
        elbow = ((shoulder[0] + hx_) / 2 + side * 20, (shoulder[1] + hy_) / 2 + 10)
        c.drawPath(path([(shoulder[0] + side * 22, shoulder[1]), elbow, (hx_, hy_)], curve=True), st)
        c.drawCircle(hx_, hy_, 11, body_fill)
        c.drawCircle(hx_, hy_, 11, st)
        hands.append((hx_, hy_))
    if item != "none":
        draw_item(c, item, *hands[1], boil)
    # head
    hx, hy = 0, neck - head_r + 14
    if species == "bunny":
        for side in (-1, 1):
            r = skia.Rect(side * 34 - 20, hy - head_r - 120, side * 34 + 20, hy - head_r + 20)
            c.drawOval(r, body_fill)
            c.drawOval(r, st)
            c.drawOval(skia.Rect(side * 34 - 9, hy - head_r - 100, side * 34 + 9, hy - head_r), fill(ACCENT["bunny"]))
    if species == "bear":
        for side in (-1, 1):
            c.drawCircle(side * head_r * 0.72, hy - head_r * 0.72, 30, body_fill)
            c.drawCircle(side * head_r * 0.72, hy - head_r * 0.72, 30, st)
            c.drawCircle(side * head_r * 0.72, hy - head_r * 0.72, 13, fill(ACCENT["bear"]))
    if species == "cat":
        for side in (-1, 1):
            ear = path([(side * head_r * 0.25, hy - head_r * 0.85), (side * head_r * 0.85, hy - head_r * 1.35),
                        (side * head_r * 0.92, hy - head_r * 0.35)], closed=True)
            c.drawPath(ear, body_fill)
            c.drawPath(ear, st)
    head_rect = skia.Rect(hx - head_r, hy - head_r * (1.15 if tall else 1), hx + head_r, hy + head_r * (1.15 if tall else 1))
    if voice == "robot" and species == "human":
        c.drawRect(head_rect, body_fill)
        c.drawRect(head_rect, st)
        c.drawLine(0, head_rect.top(), 0, head_rect.top() - 45, st)
        c.drawCircle(0, head_rect.top() - 52, 10, fill(rgb("#e04a3b")))
    else:
        c.drawOval(head_rect, body_fill)
        c.drawOval(head_rect, st)
    if species == "dog":
        for side in (-1, 1):
            ear = skia.Rect(side * head_r * 0.95 - 26, hy - head_r * 0.7, side * head_r * 0.95 + 26, hy + head_r * 0.5)
            c.drawOval(ear, fill(ACCENT["dog"]))
            c.drawOval(ear, st)
    if species in ("dog", "bear"):
        c.drawOval(skia.Rect(-34, hy + 6, 34, hy + 56), fill(rgb("#f4e6cf")))
        c.drawOval(skia.Rect(-34, hy + 6, 34, hy + 56), stroke(width=5, boil=boil))
        c.drawOval(skia.Rect(-12, hy + 8, 12, hy + 24), fill(INK))
    if species == "cat":
        for side in (-1, 1):
            for k in (-1, 1):
                c.drawLine(side * 30, hy + 22, side * 88, hy + 14 + k * 12, stroke(width=3, boil=boil))
        c.drawPath(path([(-8, hy + 12), (8, hy + 12), (0, hy + 22)], closed=True), fill(rgb("#e86f7a")))
    if species == "human" and voice != "robot":
        if voice in ("girl", "woman", "grandma"):
            bow_y = hy - head_r * 0.95
            c.drawPath(path([(0, bow_y), (-36, bow_y - 22), (-36, bow_y + 22)], closed=True), fill(rgb("#e0517a")))
            c.drawPath(path([(0, bow_y), (36, bow_y - 22), (36, bow_y + 22)], closed=True), fill(rgb("#e0517a")))
        else:
            for k in (-1, 0, 1):
                c.drawPath(path([(k * 22, hy - head_r * 0.92), (k * 26 + 10, hy - head_r * 1.25),
                                 (k * 18 + 18, hy - head_r * 1.18)], curve=True), stroke(width=6, boil=boil))
        if voice == "grandpa":
            c.drawCircle(-30, hy - 8, 20, stroke(width=5))
            c.drawCircle(30, hy - 8, 20, stroke(width=5))
            c.drawOval(skia.Rect(-34, hy + 18, 34, hy + 34), fill(rgb("#bbbbbb")))
    if voice == "robot" and species == "human":
        c.drawRect(skia.Rect(-46, hy - 24, -14, hy + 6), fill(rgb("#7fd3ff")))
        c.drawRect(skia.Rect(14, hy - 24, 46, hy + 6), fill(rgb("#7fd3ff")))
        if talking and int(t / 0.09) % 2 == 0:
            c.drawRect(skia.Rect(-26, hy + 30, 26, hy + 46), fill(INK))
        else:
            c.drawLine(-26, hy + 38, 26, hy + 38, st)
    else:
        draw_face(c, hx, hy, head_r, mood, talking, t, boil, pose.mouth, dead=pose.charred)
    # effects attached to the body
    for kind, k in pose.fx:
        if kind == "tears":
            for side in (-1, 1):
                for n in range(3):
                    yy = hy + ((t * 220 + n * 40) % 120)
                    c.drawCircle(side * head_r * 0.45, yy, 8, fill(rgb("#5aaee8")))
        elif kind == "sweat":
            c.drawOval(skia.Rect(head_r * 0.7, hy - head_r * 0.6, head_r * 0.7 + 18, hy - head_r * 0.6 + 30),
                       fill(rgb("#5aaee8")))
        elif kind == "stars":
            for n in range(3):
                a = t * 4 + n * 2.1
                sx_, sy_ = math.cos(a) * head_r * 1.2, hy - head_r * 1.2 + math.sin(a) * 18
                star(c, sx_, sy_, 16, fill(rgb("#f2c230")))
        elif kind == "lines":
            for n in range(8):
                a = n / 8 * 2 * math.pi
                r1, r2 = head_r * 1.3, head_r * 1.7 + 10 * math.sin(t * 30 + n)
                c.drawLine(hx + math.cos(a) * r1, hy + math.sin(a) * r1, hx + math.cos(a) * r2, hy + math.sin(a) * r2,
                           stroke(width=6, boil=boil))
        elif kind == "speed":
            for n in range(5):
                yy = -80 - n * 70
                c.drawLine(-120, yy, -300, yy, stroke(width=5, boil=boil))
        elif kind == "smoke" and k > 0:
            for n in range(4):
                yy = hy - head_r - 40 - k * 160 - n * 50
                c.drawCircle(math.sin(n + t * 3) * 30, yy, 26 + n * 6, fill(rgb("#9a9a9a", int(160 * (1 - k)))))
    c.restore()
    for kind, k in pose.fx:
        if kind == "burst" and 0 < k < 1:
            cx_, cy_ = x + pose.dx, FLOOR - 280
            r = 120 + 700 * k
            c.drawCircle(cx_, cy_, r, fill(rgb("#ffe27a", int(255 * (1 - k)))))
            c.drawCircle(cx_, cy_, r * 0.6, fill(rgb("#ff8a3d", int(255 * (1 - k)))))
            rnd = random.Random(7)
            for _ in range(14):
                a = rnd.uniform(0, 2 * math.pi)
                d = r * rnd.uniform(0.6, 1.1)
                c.drawRect(skia.Rect.MakeXYWH(cx_ + math.cos(a) * d, cy_ + math.sin(a) * d, 18, 18), fill(INK))


def star(c, x, y, r, paint):
    pts = []
    for i in range(10):
        a = -math.pi / 2 + i * math.pi / 5
        rr = r if i % 2 == 0 else r * 0.45
        pts.append((x + math.cos(a) * rr, y + math.sin(a) * rr))
    c.drawPath(path(pts, closed=True), paint)


def draw_item(c, item, x, y, boil):
    st = stroke(width=5, boil=boil)
    if item == "phone":
        r = skia.Rect(x - 18, y - 52, x + 18, y + 10)
        c.drawRoundRect(r, 6, 6, fill(rgb("#333")))
        c.drawRect(skia.Rect(x - 13, y - 46, x + 13, y), fill(rgb("#7fd3ff")))
    elif item == "chips":
        bag = path([(x - 30, y - 60), (x + 30, y - 60), (x + 26, y + 20), (x - 26, y + 20)], closed=True)
        c.drawPath(bag, fill(rgb("#e04a3b")))
        c.drawPath(bag, st)
    elif item == "cup":
        cup = path([(x - 22, y - 50), (x + 22, y - 50), (x + 16, y + 10), (x - 16, y + 10)], closed=True)
        c.drawPath(cup, fill(WHITE))
        c.drawPath(cup, st)
        c.drawPath(path([(x - 6, y - 60), (x + 4, y - 80), (x - 4, y - 100)], curve=True), stroke(width=3))
    elif item == "book":
        c.drawRect(skia.Rect(x - 36, y - 50, x + 36, y + 6), fill(rgb("#3d6fd9")))
        c.drawRect(skia.Rect(x - 36, y - 50, x + 36, y + 6), st)
    elif item == "key":
        c.drawCircle(x, y - 30, 14, st)
        c.drawLine(x, y - 16, x, y + 20, st)
        c.drawLine(x, y + 10, x + 12, y + 10, st)
    elif item == "food":
        c.drawOval(skia.Rect(x - 32, y - 56, x + 18, y - 6), fill(rgb("#c9793a")))
        c.drawLine(x + 10, y - 16, x + 30, y + 10, stroke(width=10, color=WHITE))


PROP_SIZE = {"kiosk": (240, 560), "tv": (360, 300), "computer": (340, 280), "phone": (230, 420), "sign": (300, 200),
             "door": (260, 560), "fridge": (280, 560), "car": (520, 260), "box": (280, 240), "bed": (480, 200),
             "table": (380, 220)}


def prop_screen_center(kind, x):
    w, h = PROP_SIZE.get(kind, (300, 300))
    if kind in ("tv", "computer"):
        return x, FLOOR - h - 60
    if kind == "sign":
        return x, FLOOR - 330
    return x, FLOOR - h * 0.6


def draw_prop(c, prop, x, t, boil):
    kind = prop["kind"]
    if kind == "none":
        return
    st = stroke(width=8, boil=boil)
    w, h = PROP_SIZE[kind]
    flash_on = prop.get("flash") and int(t * 6) % 2 == 0
    screen_col = rgb("#ffe27a") if flash_on else rgb("#cfe9f7")
    label = prop.get("text") or ""
    left, top = x - w / 2, FLOOR - h

    def screen(rect):
        c.drawRect(rect, fill(screen_col))
        c.drawRect(rect, stroke(width=6, boil=boil))
        if label:
            fit_text(c, label, rect)

    if kind in ("kiosk", "fridge", "door"):
        body = skia.Rect(left, top, left + w, FLOOR)
        c.drawRect(body, fill(rgb("#e7e2d0") if kind != "door" else rgb("#c08a58")))
        c.drawRect(body, st)
        if kind == "kiosk":
            screen(skia.Rect(left + 30, top + 50, left + w - 30, top + 260))
            c.drawRect(skia.Rect(left + 60, top + 320, left + w - 60, top + 360), fill(INK))
        elif kind == "fridge":
            c.drawLine(left, top + h * 0.38, left + w, top + h * 0.38, st)
            c.drawLine(left + w - 40, top + 40, left + w - 40, top + 160, st)
            if label:
                screen(skia.Rect(left + 30, top + h * 0.45, left + w - 60, top + h * 0.7))
        else:
            c.drawCircle(left + w - 40, top + h * 0.55, 14, fill(INK))
            if label:
                screen(skia.Rect(left + 40, top + 50, left + w - 40, top + 190))
    elif kind in ("tv", "computer"):
        if kind == "computer":
            c.drawRect(skia.Rect(x - 260, FLOOR - 200, x + 260, FLOOR - 180), fill(rgb("#c08a58")))
            c.drawLine(x - 230, FLOOR - 180, x - 230, FLOOR, st)
            c.drawLine(x + 230, FLOOR - 180, x + 230, FLOOR, st)
            base = FLOOR - 200
        else:
            c.drawLine(x - 80, FLOOR, x, FLOOR - 120, st)
            c.drawLine(x + 80, FLOOR, x, FLOOR - 120, st)
            base = FLOOR - 120
        body = skia.Rect(x - w / 2, base - h, x + w / 2, base - 20)
        c.drawRoundRect(body, 18, 18, fill(rgb("#3a3a3a")))
        c.drawRoundRect(body, 18, 18, st)
        screen(skia.Rect(body.left() + 22, body.top() + 22, body.right() - 22, body.bottom() - 22))
    elif kind == "phone":
        body = skia.Rect(left, top, left + w, FLOOR)
        c.drawRoundRect(body, 36, 36, fill(rgb("#2f2f2f")))
        c.drawRoundRect(body, 36, 36, st)
        screen(skia.Rect(left + 20, top + 50, left + w - 20, FLOOR - 50))
    elif kind == "sign":
        c.drawLine(x, FLOOR, x, FLOOR - 230, stroke(width=16, boil=boil))
        screen(skia.Rect(x - w / 2, FLOOR - 430, x + w / 2, FLOOR - 230))
    elif kind == "car":
        body = path([(left, FLOOR - 70), (left + 40, FLOOR - 160), (left + 150, FLOOR - 170), (left + 220, FLOOR - h),
                     (left + 380, FLOOR - h), (left + 440, FLOOR - 170), (left + w, FLOOR - 150), (left + w, FLOOR - 70)],
                    closed=True)
        c.drawPath(body, fill(rgb("#e04a3b")))
        c.drawPath(body, st)
        for wx in (left + 110, left + w - 110):
            c.drawCircle(wx, FLOOR - 60, 56, fill(INK))
            c.drawCircle(wx, FLOOR - 60, 22, fill(rgb("#bbbbbb")))
        if label:
            fit_text(c, label, skia.Rect(left + 60, FLOOR - 160, left + w - 60, FLOOR - 90), WHITE)
    elif kind == "box":
        body = skia.Rect(left, top, left + w, FLOOR)
        c.drawRect(body, fill(rgb("#d9a86c")))
        c.drawRect(body, st)
        c.drawLine(left, top + 50, left + w, top + 50, stroke(width=5, boil=boil))
        if label:
            fit_text(c, label, skia.Rect(left + 20, top + 60, left + w - 20, FLOOR - 20))
    elif kind == "bed":
        c.drawRect(skia.Rect(left, FLOOR - 130, left + w, FLOOR - 60), fill(rgb("#7fa8e0")))
        c.drawRect(skia.Rect(left, FLOOR - 130, left + w, FLOOR - 60), st)
        c.drawRect(skia.Rect(left, FLOOR - h, left + 40, FLOOR), fill(rgb("#c08a58")))
        c.drawRoundRect(skia.Rect(left + 50, FLOOR - 170, left + 170, FLOOR - 120), 20, 20, fill(WHITE))
        c.drawLine(left + w, FLOOR - 140, left + w, FLOOR, st)
    elif kind == "table":
        c.drawRect(skia.Rect(left, FLOOR - h, left + w, FLOOR - h + 30), fill(rgb("#c08a58")))
        c.drawRect(skia.Rect(left, FLOOR - h, left + w, FLOOR - h + 30), st)
        c.drawLine(left + 30, FLOOR - h + 30, left + 30, FLOOR, st)
        c.drawLine(left + w - 30, FLOOR - h + 30, left + w - 30, FLOOR, st)
        if label:
            fit_text(c, label, skia.Rect(left, FLOOR - h - 110, left + w, FLOOR - h - 10))


def fit_text(c, label, rect, color=INK):
    """Largest Patrick Hand size (<= 60 px) whose wrapped lines fit inside rect."""
    best = None
    for chars in (8, 10, 12, 16, 20):
        lines = wrap(label, chars, 3)
        size = 60
        while size > 14:
            f = font("Patrick Hand", size)
            if max(f.measureText(ln) for ln in lines) <= rect.width() * 0.88 and len(lines) * size * 1.1 <= rect.height() * 0.9:
                break
            size -= 2
        if not best or size > best[0]:
            best = (size, lines)
    size, lines = best
    f = font("Patrick Hand", size)
    for i, ln in enumerate(lines):
        text(c, ln, rect.centerX(), rect.centerY() + (i - (len(lines) - 1) / 2) * size * 1.1, f, color)


def draw_crowd(c, t, boil):
    for i in range(7):
        x = 60 + i * 160
        bob = abs(math.sin(t * 7 + i)) * 26
        y = 1900 - bob
        c.drawCircle(x, y - 150, 70, fill(rgb("#3a3a3a")))
        c.drawOval(skia.Rect(x - 110, y - 90, x + 110, y + 160), fill(rgb("#3a3a3a")))


def draw_bubble(c, speech_text, speaker_screen, on_screen, boil):
    fnt = font("Patrick Hand", 58)
    lines = wrap(speech_text, 18, 4)
    lw = max(fnt.measureText(ln) for ln in lines)
    bw, bh = lw + 90, len(lines) * 66 + 50
    sx_, sy_ = speaker_screen
    cx = min(max(sx_, bw / 2 + 40), 1080 - bw / 2 - 40) if on_screen else 540
    top = 420
    rect = skia.Rect(cx - bw / 2, top, cx + bw / 2, top + bh)
    c.drawRoundRect(rect, 40, 40, fill(WHITE))
    if on_screen:
        tip_y = max(top + bh + 40, sy_ - 120)
        tail = path([(cx - 30, top + bh - 4), (cx + 30, top + bh - 4), (sx_ * 0.4 + cx * 0.6, tip_y)], closed=True)
        c.drawPath(tail, fill(WHITE))
        c.drawPath(path([(cx - 30, top + bh - 2), (sx_ * 0.4 + cx * 0.6, tip_y), (cx + 30, top + bh - 2)]),
                   stroke(width=7, boil=boil))
        c.drawRoundRect(rect, 40, 40, stroke(width=7, boil=boil))
        c.drawLine(cx - 28, top + bh, cx + 28, top + bh, stroke(WHITE, 9))
    else:
        c.drawRoundRect(rect, 40, 40, stroke(width=7, dash=[22, 14]))
    for i, ln in enumerate(lines):
        text(c, ln, cx, top + 52 + i * 66, fnt)


def camera_for(shot, hero_x, other_x, prop_x, hero_pose, t):
    frame, focus = shot["frame"], shot["focus"]
    if frame == "wide":
        z, cx, cy = 1.0, 540, 1130
    elif focus == "prop" and shot["prop"]["kind"] != "none":
        z = {"medium": 1.9, "closeup": 3.0, "extreme": 3.6}[frame]
        cx, cy = prop_screen_center(shot["prop"]["kind"], prop_x)
    else:
        s = 1.0
        z = {"medium": 1.75, "closeup": 2.5, "extreme": 3.1}[frame]
        cy = FLOOR - (440 if frame == "medium" else 540) * s
        if focus == "both" and shot["other"]["present"]:
            cx = (hero_x + other_x) / 2
            z = min(z, 1.45)
            cy = FLOOR - 400
        elif focus == "other" and shot["other"]["present"]:
            cx = other_x
        else:
            cx = hero_x + hero_pose.dx * 0.6
            cy += hero_pose.dy * 0.7
    z *= 1 + 0.08 * (1 - min(1.0, t / 0.18))  # punch-in on every cut
    return z, cx, cy


def render_frame(c, gag, shot, t, dur, frame_no, paper, talking_role):
    boil = (frame_no // 3) % 7
    u = t / dur if dur else 0
    hero_x = char_home(shot, "hero")
    other_x = char_home(shot, "other") if shot["other"]["present"] else None
    prop_x = 850 if shot["prop"]["kind"] != "none" else None
    hp = action_pose(shot["hero"]["action"], u, t, dur, hero_x, other_x if other_x else prop_x)
    op = action_pose(shot["other"]["action"], u, t + 0.37, dur, other_x, hero_x) if other_x else None
    z, cx, cy = camera_for(shot, hero_x, other_x, prop_x, hp, t)
    shaking = any(a in ("shake", "scream", "explode") for a in (shot["hero"]["action"],
                                                                 shot["other"]["action"] if op else ""))
    jx = jy = 0
    if shaking:
        rnd = random.Random(frame_no)
        jx, jy = rnd.uniform(-8, 8), rnd.uniform(-8, 8)
    c.drawImage(paper, 0, 0)
    c.save()
    c.translate(540 + jx, 1130 + jy)
    c.scale(z, z)
    c.translate(-cx, -cy)
    st = stroke(width=6, boil=boil)
    c.drawLine(-400, FLOOR, 1480, FLOOR, st)
    c.drawLine(-400, FLOOR - 820, 1480, FLOOR - 820, stroke(rgb("#d8d1b8"), 4))
    if prop_x:
        draw_prop(c, shot["prop"], prop_x, t, boil)
    if op:
        draw_character(c, other_x, gag["cast"]["other"], op, shot["other"]["mood"], "none", talking_role == "other",
                       t, boil, flip=True)
    draw_character(c, hero_x, gag["cast"]["hero"], hp, shot["hero"]["mood"], shot["hero"]["item"],
                   talking_role == "hero", t, boil)
    c.restore()
    if shot.get("crowd"):
        draw_crowd(c, t, boil)
    sp = shot.get("speech")
    if sp and t >= 0.1:
        who = sp["who"]
        sx_ = (hero_x + hp.dx) if who == "hero" else (other_x or 2000)
        pose = hp if who == "hero" else op
        head_y = FLOOR - 470 + (pose.dy if pose else 0)
        scr = ((sx_ - cx) * z + 540, (head_y - cy) * z + 1130)
        visible = pose is not None and -40 < scr[0] < 1120 and 500 < scr[1] < 1980 and not pose.hidden
        draw_bubble(c, sp["text"], scr, visible, boil)
    # caption band
    c.drawRect(skia.Rect(0, 0, 1080, CAPTION_BAND), fill(PAPER))
    lines = wrap(gag.get("caption") or gag["title"], 22, 3)
    fnt = font("Patrick Hand", 84)
    for i, ln in enumerate(lines):
        text(c, ln, 540, 175 + (i - (len(lines) - 1) / 2) * 90, fnt)
