"""Zoo window renderer: one hand-held phone shot through enclosure glass (HANDOVER.md §3b).

An animal family (dad, mom, cub) in a flat storybook enclosure with a depth model, visitors in the
foreground reacting, glass tint and reflections, paw prints and nose fog that fade, and a drifting camera.
"""
import math

import skia

from .draw import ease, fill, font, path, rgb, seg, stroke, text, wrap

PALETTE = {  # fur, dark, light, extra
    "bear": ("#8a5a3c", "#6e452c", "#c9a07a", None),
    "lion": ("#d9a352", "#b9843a", "#f2dcae", "#8f4f1e"),
    "panda": ("#f4f3ee", "#1f1f22", "#ffffff", None),
    "tiger": ("#e8913a", "#2a2018", "#fbecd6", None),
    "polar": ("#f1efe6", "#cfcabb", "#ffffff", None),
}
ROLE_SIZE = {"dad": 1.12, "mom": 1.0, "cub": 0.52}
SPOT_D = {"glass": 0.03, "near": 0.22, "middle": 0.45, "back": 0.78, "rock": 0.62, "offscreen": 0.45}
SIDE_X = {"left": 330, "center": 560, "right": 800}
ROCK = (930, 0.55)
LOG = (260, 0.72)
RESTING = {"sit", "lie", "sleep", "look"}
MOVING = {"walk", "run", "walk_in", "pounce", "tumble"}
SPEED = {"run": 950, "pounce": 950, "tumble": 700}
INK = rgb("#111111")
DEFAULT_START = {"dad": ("back", "left", "sit"), "mom": ("middle", "right", "lie"), "cub": ("near", "center", "idle")}


GROUND0 = 1640  # screen y of the glass line; the original used 1830, which hid glass animals behind visitors


def gy(d):
    return GROUND0 - 880 * d ** 0.8


def sc(d):
    return 1 - 0.7 * d


def sx(x, d):
    return 540 + (x - 540) * (1 - 0.45 * d)


def spot_pos(spot, side):
    if spot == "rock":
        return ROCK[0], SPOT_D["rock"]
    if spot == "offscreen":
        return (-420 if side == "left" else 1500), SPOT_D["offscreen"]
    return SIDE_X.get(side, 560), SPOT_D.get(spot, 0.45)


# ---------- timeline ----------
def prepare(gag, starts, durs):
    """Resolve inheritance, movement and glass marks for every beat."""
    animals = [a for a in ("dad", "mom", "cub") if gag["present"].get(a)]
    cur = {}
    for a in animals:
        spot, side, act = DEFAULT_START[a]
        x, d = spot_pos(spot, side)
        cur[a] = {"spot": spot, "side": side, "action": act, "x": x, "d": d, "target": None}
    beats, marks = [], []
    cam_prev = ("wide", gag["shots"][0].get("focus", "cub"))
    for i, sh in enumerate(gag["shots"]):
        beat = {"start": starts[i], "dur": durs[i], "animals": {}, "camera": (sh["camera"], sh["focus"]),
                "cam_prev": cam_prev}
        cam_prev = beat["camera"]
        pushes = {}
        for a in animals:
            spec = sh.get(a) or {}
            st = cur[a]
            prev_action = st["action"]
            spot = spec.get("spot", st["spot"])
            side = spec.get("side", st["side"])
            if "action" in spec:
                action = spec["action"]
            elif "spot" in spec or "side" in spec:
                action = "idle"
            else:
                action = prev_action if prev_action in RESTING else "idle"
            x0, d0 = st["x"], st["d"]
            x1, d1 = spot_pos(spot, side)
            if action == "walk_in" and "spot" in spec and st["spot"] != "offscreen":
                x0, d0 = (-420 if side == "left" else 1500), d1
            target = spec.get("target")
            beat["animals"][a] = {"action": action, "from": (x0, d0), "to": (x1, d1), "target": target}
            if action == "nudge" and target in cur:
                pushes[target] = 190 if cur[target]["x"] >= x1 else -190
            cur[a] = {"spot": spot, "side": side, "action": action, "x": x1, "d": d1, "target": target}
        for a, info in beat["animals"].items():  # pounce / groom move next to their target
            if info["action"] in ("pounce", "groom") and info["target"] in beat["animals"]:
                tx, td = beat["animals"][info["target"]]["to"]
                off = -130 if info["from"][0] < tx else 130
                info["to"] = (tx + off, td)
                cur[a]["x"], cur[a]["d"] = info["to"]
        for a, dx in pushes.items():
            info = beat["animals"][a]
            info["pushed"] = dx
            x, d = info["to"]
            info["to"] = (x + dx, d)
            cur[a]["x"] = x + dx
        for a, info in beat["animals"].items():
            (x0, d0), (x1, d1) = info["from"], info["to"]
            dist = math.hypot(x1 - x0, (d1 - d0) * 900)
            speed = SPEED.get(info["action"], 560)
            limit = 0.75 if info["action"] in MOVING else 0.5
            info["move"] = min(dist / speed, durs[i] * limit) if dist > 2 else 0
            if info["action"] in ("paws_up", "boop") and d1 <= 0.1:
                marks.append({"t": starts[i] + 0.5, "kind": "paws" if info["action"] == "paws_up" else "fog",
                              "x": x1, "role": a})
        beats.append(beat)
    return {"beats": beats, "marks": marks, "animals": animals}


def animal_at(info, lt):
    (x0, d0), (x1, d1) = info["from"], info["to"]
    k = ease(lt / info["move"]) if info["move"] > 0 else 1.0
    if info["action"] in ("run", "pounce"):
        k = min(1.0, lt / info["move"]) if info["move"] > 0 else 1.0
    return x0 + (x1 - x0) * k, d0 + (d1 - d0) * k, (k < 1 and info["move"] > 0), x1 - x0


# ---------- drawing ----------
def draw_background(c, t):
    hz = gy(1.0)
    c.drawRect(skia.Rect(-300, -400, 1380, hz + 60), fill(rgb("#bfe0ef")))
    c.drawCircle(860, hz - 600, 70, fill(rgb("#fff4cf")))
    for i, x in enumerate(range(-260, 1400, 120)):  # back trees
        h = 260 + 60 * math.sin(i * 1.7)
        c.drawCircle(x, hz - 10 - h, 120, fill(rgb("#7fae6a")))
        c.drawRect(skia.Rect(x - 14, hz - 10 - h, x + 14, hz + 20), fill(rgb("#6d4c35")))
    c.drawRect(skia.Rect(-300, hz, 1380, 2400), fill(rgb("#9bc27a")))
    for d in (0.9, 0.7, 0.5, 0.3, 0.1):  # depth bands for grass shading
        c.drawRect(skia.Rect(-300, gy(d), 1380, gy(d) + 30 * sc(d)), fill(rgb("#8fb86f")))
    c.drawPath(path([(-300, hz + 20), (1380, hz + 5)]), stroke(rgb("#6d4c35"), 6))  # back fence rail
    for x in range(-280, 1400, 90):
        c.drawLine(x, hz - 40, x, hz + 25, stroke(rgb("#6d4c35"), 5))


def draw_rock(c):
    x, d = ROCK
    s = sc(d)
    X, Y = sx(x, d), gy(d)
    rock = path([(X - 230 * s, Y + 10), (X - 200 * s, Y - 190 * s), (X - 60 * s, Y - 300 * s), (X + 120 * s, Y - 270 * s),
                 (X + 240 * s, Y - 120 * s), (X + 250 * s, Y + 10)], closed=True)
    c.drawPath(rock, fill(rgb("#9a9a92")))
    c.drawPath(rock, stroke(rgb("#6f6f68"), 6))
    c.drawPath(path([(X - 120 * s, Y - 200 * s), (X + 40 * s, Y - 240 * s)]), stroke(rgb("#b7b7ae"), 10))


def rock_top():
    x, d = ROCK
    return gy(d) - 300 * sc(d)


def draw_log(c):
    x, d = LOG
    s = sc(d)
    X, Y = sx(x, d), gy(d)
    r = skia.Rect(X - 230 * s, Y - 80 * s, X + 230 * s, Y)
    c.drawRoundRect(r, 40 * s, 40 * s, fill(rgb("#8a5a3c")))
    c.drawOval(skia.Rect(X + 190 * s, Y - 80 * s, X + 250 * s, Y), fill(rgb("#c9a07a")))


def draw_animal(c, species, role, action, X, Y, s, lt, t, moving, facing, target_dx, cub_head=1.0, mark_glass=False):
    fur, dark, light, mane = (rgb(v) if v else None for v in PALETTE[species])
    size = ROLE_SIZE[role] * s
    c.save()
    c.translate(X, Y)
    c.scale(size * facing, size)
    bob = 0
    rot = 0
    stand = action == "paws_up"
    if moving or action in ("walk", "run", "walk_in"):
        bob = -abs(math.sin(t * (14 if action == "run" else 9))) * 14
    if action == "idle":
        bob = -3 * math.sin(t * 2.2)
    if action in ("roll", "tumble"):
        rot = 360 * seg(lt, 0, 1.2)
    if action == "pounce":
        bob = -220 * math.sin(math.pi * min(1, lt / 0.8))
    c.translate(0, bob)
    if rot:
        c.translate(0, -90)
        c.rotate(rot)
        c.translate(0, 90)
    st = stroke(rgb("#3a2a1f"), 5)
    lying = action in ("lie", "sleep")
    sitting = action == "sit"
    # legs
    leg = fill(dark if species == "panda" else fur)
    if not stand and not lying:
        for i, lx in enumerate((-110, -50, 50, 110)):
            ph = math.sin(t * (14 if action == "run" else 9) + i * 1.6) * (22 if (moving or action in MOVING) else 0)
            if sitting and abs(lx) > 80:
                continue
            c.drawRoundRect(skia.Rect(lx - 24 + ph, -80, lx + 24 + ph, 0), 18, 18, leg)
    # body
    if stand:
        body = skia.Rect(-95, -330, 95, -10)
    elif lying:
        body = skia.Rect(-170, -95, 170, 0)
    elif sitting:
        body = skia.Rect(-120, -230, 120, -10)
    else:
        body = skia.Rect(-170, -210, 170, -60)
    c.drawOval(body, fill(fur))
    c.drawOval(body, st)
    if species == "tiger":
        for k in range(-2, 3):
            xx = body.centerX() + k * body.width() / 6
            c.drawLine(xx - 10, body.top() + 10, xx + 8, body.top() + body.height() * 0.45, stroke(dark, 9))
    c.drawOval(skia.Rect(body.centerX() - body.width() * 0.25, body.centerY(), body.centerX() + body.width() * 0.25,
                         body.bottom() - 4), fill(light))
    # head position
    if stand:
        hx, hy = 0, -380
    elif lying:
        hx, hy = 150, -70
    elif sitting:
        hx, hy = 0, -280
    else:
        hx, hy = 140, -220
    if action == "look":
        hx += 18 * math.sin(t * 1.3)
    if action == "boop":
        k = math.sin(math.pi * seg(lt, 0.2, 1.4))
        hy += 20 * k
    if action == "nudge":
        hx += 50 * math.sin(math.pi * seg(lt, 0.1, 0.7))
    if action == "groom":
        hy += 12 * math.sin(t * 8)
    hr = 86 * (cub_head if role == "cub" else 1)
    if mane is not None and role == "dad":
        c.drawCircle(hx, hy, hr * 1.55, fill(mane))
        c.drawCircle(hx, hy, hr * 1.55, st)
    for side in (-1, 1):  # ears
        ex, ey = hx + side * hr * 0.7, hy - hr * 0.72
        c.drawCircle(ex, ey, hr * 0.32, fill(dark if species == "panda" else fur))
        c.drawCircle(ex, ey, hr * 0.32, st)
    c.drawCircle(hx, hy, hr, fill(fur))
    c.drawCircle(hx, hy, hr, st)
    eye_closed = action == "sleep" or (int(t * 0.7 + X) % 5 == 0 and (t * 0.7 + X) % 1 < 0.08)
    for side in (-1, 1):
        ex, ey = hx + side * hr * 0.36, hy - hr * 0.1
        if species == "panda":
            c.drawOval(skia.Rect(ex - 24, ey - 18, ex + 24, ey + 22), fill(dark))
        if eye_closed:
            c.drawArc(skia.Rect(ex - 12, ey - 6, ex + 12, ey + 8), 0, 180, False, stroke(INK, 5))
        else:
            c.drawCircle(ex, ey, 11, fill(INK))
            c.drawCircle(ex + 3, ey - 4, 4, fill(rgb("#ffffff")))
    c.drawOval(skia.Rect(hx - hr * 0.42, hy + hr * 0.1, hx + hr * 0.42, hy + hr * 0.6), fill(light))
    c.drawOval(skia.Rect(hx - 14, hy + hr * 0.12, hx + 14, hy + hr * 0.3), fill(INK))
    if action in ("yawn", "roar"):
        k = math.sin(math.pi * seg(lt, 0.2, 1.6))
        c.drawOval(skia.Rect(hx - 26, hy + hr * 0.38, hx + 26, hy + hr * 0.38 + 60 * k), fill(rgb("#7a2b2b")))
        if action == "roar" and k > 0.3:
            for n in range(5):
                a = -0.6 + n * 0.3
                c.drawLine(hx + math.cos(a) * hr * 1.4, hy + math.sin(a) * hr * 1.4,
                           hx + math.cos(a) * hr * 2.0, hy + math.sin(a) * hr * 2.0, stroke(INK, 6))
    # front paws
    if stand:
        for side in (-1, 1):
            c.drawOval(skia.Rect(side * 70 - 34, -330, side * 70 + 34, -250), fill(fur))
            c.drawOval(skia.Rect(side * 70 - 34, -330, side * 70 + 34, -250), st)
    if action == "wave_paw":
        a = -0.9 + 0.5 * math.sin(t * 8)
        px, py = 60 + math.cos(a) * 120, -200 + math.sin(a) * 120
        c.drawLine(40, -160, px, py, stroke(fur, 46))
        c.drawCircle(px, py, 30, fill(fur))
        c.drawCircle(px, py, 30, st)
    if action == "sleep":
        for n in range(3):
            k = (t * 0.6 + n / 3) % 1
            text(c, "z", hx + 60 + k * 60, hy - 90 - k * 140, font("Arial", 40 + 20 * k, bold=True), rgb("#ffffff"),
                 INK, 6)
    if action == "groom":
        k = (t * 0.8) % 1
        c.drawCircle(hx + 90, hy - 80 - k * 80, 10 + 6 * k, fill(rgb("#e86f7a", int(255 * (1 - k)))))
    c.restore()


def draw_visitors(c, gag, beat_shot, t, talking, dx, dy):
    mood = beat_shot["visitors"]["mood"]
    speakers = {beat_shot["speech"]["who"]} if beat_shot.get("speech") else set()
    people = [("visitor", 90, 0.8, rgb("#c0504d"), rgb("#4a2c1d")), ("kid", 900, 0.6, rgb("#3d6fd9"), rgb("#2a1a12"))]
    if "dad_visitor" in speakers or any((s.get("speech") or {}).get("who") == "dad_visitor" for s in gag["shots"]):
        people.append(("dad_visitor", 1060, 0.85, rgb("#4f7a4a"), rgb("#2a2a2a")))
    for role, x, s, shirt, hair in people:
        bob = {"excited": abs(math.sin(t * 8)) * 18, "laugh": abs(math.sin(t * 11)) * 10}.get(mood, 3 * math.sin(t * 1.5))
        if role == "kid":
            bob += abs(math.sin(t * 6)) * 16
        tilt = {"aww": 10, "gasp": -6}.get(mood, 2 * math.sin(t))
        lean = -26 if mood == "gasp" else 0
        X, Y = x + dx * 1.6, 2010 + dy * 1.6 - bob + lean * -0.5
        c.save()
        c.translate(X, Y)
        c.scale(s, s)
        c.rotate(tilt if role != "dad_visitor" else tilt * 0.5)
        c.drawOval(skia.Rect(-210, -300, 210, 260), fill(shirt))
        c.drawCircle(0, -380, 120, fill(rgb("#e9c19b")))
        c.drawOval(skia.Rect(-128, -510, 128, -320), fill(hair))
        if role == "visitor":
            c.drawOval(skia.Rect(-120, -360, 120, -150), fill(hair))  # long hair from behind
        if mood == "point" and (role == "kid" or role in speakers):
            c.drawLine(130, -220, 320, -520, stroke(shirt, 60))
            c.drawCircle(330, -540, 34, fill(rgb("#e9c19b")))
        c.restore()


def camera_target(beat_cam, positions):
    kind, focus = beat_cam
    if kind == "wide" or focus not in positions:
        return 1.08, 540, 1060
    X, Y, s = positions[focus]
    head_y = Y - 260 * s
    if kind == "follow":
        return 1.38, X, Y - 150 * s
    return 1.75, X, head_y


def render_frame(c, gag, state, i, lt, tg, frame_no, talking):
    beat = state["beats"][i]
    sh = gag["shots"][i]
    # animal positions this frame
    positions, draws = {}, []
    for a in state["animals"]:
        info = beat["animals"][a]
        x, d, moving, travel = animal_at(info, lt)
        dy = 0
        if info["action"] == "peek" and abs(x - ROCK[0]) < 40:
            if a == "cub":
                x -= 170 * ease(seg(lt, 0.1, 0.6))
            else:
                dy = -130 * ease(seg(lt, 0.1, 0.6))
        X, Y, s = sx(x, d), gy(d) + dy * sc(d), sc(d)
        facing = -1 if (travel < -5 and moving) else 1
        if info["target"] and info["target"] in beat["animals"]:
            facing = 1 if beat["animals"][info["target"]]["to"][0] >= x else -1
        positions[a] = (X, Y, s * ROLE_SIZE[a])
        draws.append((d, a, info, X, Y, s, moving, facing))
    # camera with easing between beats and hand-held drift
    z1, cx1, cy1 = camera_target(beat["camera"], positions)
    z0, cx0, cy0 = camera_target(beat["cam_prev"], positions)
    k = ease(lt / 0.9)
    z, cx, cy = z0 + (z1 - z0) * k, cx0 + (cx1 - cx0) * k, cy0 + (cy1 - cy0) * k
    jx = 7 * math.sin(1.3 * tg) + 4 * math.sin(2.9 * tg + 1)
    jy = 6 * math.sin(1.1 * tg + 2) + 3 * math.sin(3.3 * tg)
    jr = 0.5 * math.sin(0.9 * tg) + 0.25 * math.sin(2.1 * tg)
    c.save()
    c.translate(540 + jx, 1060 + jy)
    c.rotate(jr)
    c.scale(z, z)
    c.translate(-cx, -cy)
    draw_background(c, tg)
    scene = [(LOG[1], "log", None), (ROCK[1], "rock", None)] + [(dd[0], "animal", dd) for dd in draws]
    scene.sort(key=lambda o: -o[0])
    for d, kind, payload in scene:
        if kind == "log":
            draw_log(c)
        elif kind == "rock":
            draw_rock(c)
        else:
            _, a, info, X, Y, s, moving, facing = payload
            draw_animal(c, gag["animal"], a, info["action"], X, Y, s, lt, tg, moving, facing, 0, cub_head=1.28)
    # glass marks (paw prints / nose fog) fade over 3 s
    for m in state["marks"]:
        age = tg - m["t"]
        if 0 <= age < 3:
            alpha = int(150 * (1 - age / 3))
            X = sx(m["x"], 0.03)
            size = ROLE_SIZE[m["role"]] * sc(0.03)
            if m["kind"] == "fog":
                nx, ny = X + 140 * size, gy(0.03) - 200 * size
                c.drawOval(skia.Rect(nx - 70 * size, ny - 50 * size, nx + 70 * size, ny + 50 * size),
                           fill(rgb("#ffffff", alpha)))
            else:
                for side in (-1, 1):
                    px, py = X + side * 70 * size, gy(0.03) - 300 * size
                    c.drawCircle(px, py, 30, fill(rgb("#ffffff", alpha)))
                    for n in range(4):
                        c.drawCircle(px - 30 + n * 20, py - 40, 10, fill(rgb("#ffffff", alpha)))
    c.restore()
    # glass: tint, moving reflections, window post
    c.drawRect(skia.Rect(0, 0, 1080, 1920), fill(rgb("#9fc6d8", 18)))
    for n, (base, w) in enumerate(((180, 70), (520, 30))):
        off = (tg * 25 + n * 300) % 1400 - 200
        streak = path([(base + off, 0), (base + off + w, 0), (base + off + w - 500, 1920), (base + off - 500, 1920)],
                      closed=True)
        c.drawPath(streak, fill(rgb("#ffffff", 22)))
    c.drawRect(skia.Rect(-10 + jx * 1.6, 0, 46 + jx * 1.6, 1920), fill(rgb("#2b2f33")))
    draw_visitors(c, gag, sh, tg, talking, jx, jy)
    # hook caption
    hook = gag.get("caption") or gag["title"]
    fnt = font("Arial", 70, bold=True)
    for n, ln in enumerate(wrap(hook, 24, 2)):
        text(c, ln, 540, 215 + n * 84, fnt, rgb("#ffffff"), INK, 14)
    # visitor speech subtitle
    sp = sh.get("speech")
    if sp:
        words = len(sp["text"].split())
        show = talking == sp["who"] if talking else 0.2 <= lt <= 0.2 + words * 0.35 + 0.6
        if show:
            sfnt = font("Arial", 56, bold=True)
            for n, ln in enumerate(wrap(sp["text"], 26, 3)):
                text(c, ln, 540, 430 + 74 * n + (84 if len(wrap(hook, 24, 2)) > 1 else 0), sfnt, rgb("#fff6a8"), INK, 12)
