"""Pure-numpy soundtrack engine: synthesized music beds, sound effects and a ducking mixer.

Port of utils/cartoon-audio.js (HANDOVER.md, "Shared soundtrack engine"). Everything is generated,
so there is no stock audio to license.
"""
import hashlib
import wave

import numpy as np

SR = 44100

# chord = (root midi, quality); qualities: "M" major, "m" minor
_Q = {"M": (0, 4, 7), "m": (0, 3, 7)}
MUSIC_STYLES = {
    # name: (bpm, progression, voices)
    "dark": (68, [(57, "m"), (53, "M"), (50, "m"), (52, "M")], {"pad": 0.5, "drone": 0.35, "bell": 0.12}),
    "epic": (92, [(50, "m"), (46, "M"), (53, "M"), (48, "M")], {"pad": 0.45, "bass": 0.35, "kick": 0.4, "pluck": 0.18}),
    "mystery": (84, [(52, "m"), (48, "M"), (57, "m"), (59, "M")], {"pad": 0.35, "pluck": 0.25, "bass": 0.25, "hat": 0.05}),
    "soothing": (76, [(60, "M"), (57, "m"), (53, "M"), (55, "M")], {"pad": 0.45, "bell": 0.2}),
    "kids": (108, [(60, "M"), (55, "M"), (57, "m"), (53, "M")], {"pluck": 0.3, "bass": 0.3, "kick": 0.25, "hat": 0.06}),
    "upbeat": (120, [(57, "m"), (53, "M"), (60, "M"), (55, "M")], {"pluck": 0.28, "bass": 0.32, "kick": 0.35, "hat": 0.08}),
    "silly": (140, [(60, "M"), (53, "M"), (55, "M"), (60, "M")], {"pluck": 0.3, "bass": 0.4, "hat": 0.06}),
    "none": (0, [], {}),
}
STORY_MUSIC = ("dark", "epic", "mystery", "soothing", "none")


def midi_hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def _t(dur):
    return np.arange(int(dur * SR)) / SR


def _env(n, attack=0.01, release=0.2):
    e = np.ones(n)
    a, r = max(1, int(attack * SR)), max(1, int(release * SR))
    e[:a] = np.linspace(0, 1, min(a, n))[:n] if a < n else np.linspace(0, 1, n)
    if r < n:
        e[-r:] *= np.linspace(1, 0, r)
    return e


def _add(buf, sig, at):
    i = int(at * SR)
    if i >= len(buf) or i + len(sig) <= 0:
        return
    if i < 0:
        sig, i = sig[-i:], 0
    j = min(len(buf), i + len(sig))
    buf[i:j] += sig[: j - i]


# instruments
def pad(freqs, dur):
    t = _t(dur)
    s = sum(np.sin(2 * np.pi * f * t) + 0.5 * np.sin(2 * np.pi * f * 1.003 * t) for f in freqs)
    return s / (len(freqs) * 1.5) * _env(len(t), 0.4, 0.6)


def pluck(f, dur, rng):
    """Karplus-Strong string."""
    n, period = int(dur * SR), max(2, int(SR / f))
    out = np.zeros(n)
    ring = rng.uniform(-1, 1, period)
    for k in range(0, n, period):
        chunk = ring[: min(period, n - k)]
        out[k:k + len(chunk)] = chunk
        ring = 0.996 * 0.5 * (ring + np.roll(ring, -1))
    return out * _env(n, 0.002, 0.1)


def bell(f, dur):
    t = _t(dur)
    s = np.sin(2 * np.pi * f * t) + 0.4 * np.sin(2 * np.pi * f * 2.76 * t) + 0.2 * np.sin(2 * np.pi * f * 5.4 * t)
    return s * np.exp(-3 * t) * 0.6


def bass(f, dur):
    t = _t(dur)
    return (np.sin(2 * np.pi * f * t) + 0.3 * np.sin(4 * np.pi * f * t)) * _env(len(t), 0.01, 0.08) * 0.8


def kick(dur=0.35):
    t = _t(dur)
    f = 50 + 90 * np.exp(-25 * t)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-9 * t)


def noise_burst(dur, decay, rng, hp=True):
    n = rng.uniform(-1, 1, int(dur * SR))
    if hp:
        n = np.diff(n, prepend=0)
    return n * np.exp(-decay * _t(dur))


def music_bed(style, duration, seed="x"):
    bpm, prog, voices = MUSIC_STYLES.get(style, MUSIC_STYLES["mystery"])
    out = np.zeros(int(duration * SR) + SR)
    if not bpm:
        return out[: int(duration * SR)]
    rng = np.random.default_rng(int(hashlib.sha1(seed.encode()).hexdigest()[:8], 16))
    beat = 60 / bpm
    bar = 4 * beat
    motif = rng.integers(0, 3, 8)  # chord-tone index per eighth note, seeded from the caption/title
    t, b = 0.0, 0
    while t < duration:
        root, q = prog[b % len(prog)]
        tones = [root + i for i in _Q[q]]
        if "pad" in voices:
            _add(out, voices["pad"] * pad([midi_hz(m) for m in tones], bar + 0.5), t)
        if "drone" in voices:
            _add(out, voices["drone"] * pad([midi_hz(root - 24)], bar + 0.5), t)
        for k in range(4):
            bt = t + k * beat
            if "bass" in voices and k in (0, 2):
                _add(out, voices["bass"] * bass(midi_hz(root - 12), beat * 0.9), bt)
            if "kick" in voices and k in (0, 2):
                _add(out, voices["kick"] * kick(), bt)
            if "hat" in voices:
                _add(out, voices["hat"] * noise_burst(0.05, 60, rng), bt + beat / 2)
        if "pluck" in voices:
            for e in range(8):
                note = tones[motif[e]] + 12
                _add(out, voices["pluck"] * pluck(midi_hz(note), beat * 0.6, rng), t + e * beat / 2)
        if "bell" in voices and b % 2 == 0:
            _add(out, voices["bell"] * bell(midi_hz(tones[motif[b % 8]] + 12), 2.5), t)
        t += bar
        b += 1
    return out[: int(duration * SR)]


def sfx(name, rng=None):
    rng = rng or np.random.default_rng(7)
    if name in ("whoosh", "whoosh_soft"):
        d = 0.45 if name == "whoosh" else 0.35
        n = rng.uniform(-1, 1, int(d * SR))
        n = np.convolve(n, np.ones(12) / 12, mode="same")
        env = np.sin(np.linspace(0, np.pi, len(n))) ** 2
        return n * env * (0.9 if name == "whoosh" else 0.45)
    if name == "hit":
        return 0.9 * kick(0.8) + 0.4 * noise_burst(0.8, 6, rng, hp=False)
    if name == "riser":
        t = _t(1.6)
        f = 200 + 1400 * (t / 1.6) ** 2
        tone = np.sin(2 * np.pi * np.cumsum(f) / SR) * 0.25
        return (tone + 0.25 * rng.uniform(-1, 1, len(t))) * (t / 1.6) ** 2
    if name == "pop":
        t = _t(0.08)
        return np.sin(2 * np.pi * 900 * t) * np.exp(-50 * t)
    if name == "boing":
        t = _t(0.5)
        f = 220 + 120 * np.sin(2 * np.pi * 9 * t)
        return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-5 * t) * 0.7
    if name in ("ding", "sparkle", "tada"):
        return bell(1046.5, 1.2) + (bell(1318.5, 1.2) if name != "ding" else 0)
    if name in ("thump", "thud", "boom"):
        return kick(0.6) * (1.3 if name == "boom" else 0.9)
    if name in ("slide_up", "slide_down", "wahwah"):
        t = _t(0.6)
        f = np.linspace(300, 900, len(t)) if name == "slide_up" else np.linspace(700, 200, len(t))
        return np.sin(2 * np.pi * np.cumsum(f) / SR) * _env(len(t), 0.01, 0.1) * 0.5
    if name == "glass_tap":
        return bell(2200, 0.25) * 0.5
    if name == "rumble":
        n = np.convolve(rng.uniform(-1, 1, int(0.9 * SR)), np.ones(200) / 200, mode="same")
        return n * 6 * _env(len(n), 0.05, 0.3)
    if name == "sting":
        return sum(bell(midi_hz(m), 0.9) for m in (72, 75, 78)) * 0.5
    if name == "honk":
        t = _t(0.35)
        return np.sign(np.sin(2 * np.pi * 330 * t)) * 0.3 * _env(len(t), 0.01, 0.05)
    if name in ("beep", "error"):
        t = _t(0.18 if name == "beep" else 0.4)
        f = 1000 if name == "beep" else 180
        return np.sign(np.sin(2 * np.pi * f * t)) * 0.25 * _env(len(t), 0.005, 0.03)
    if name == "tick":
        return noise_burst(0.03, 120, rng) * 0.6
    if name == "drumroll":
        out = np.zeros(int(1.2 * SR))
        for k in range(36):
            _add(out, noise_burst(0.05, 50, rng) * (0.3 + 0.5 * k / 36), k / 30)
        return out
    if name == "crash":
        return noise_burst(1.2, 3.5, rng) * 0.8
    if name == "giggle":
        out = np.zeros(int(0.8 * SR))
        for k in range(5):
            t = _t(0.1)
            _add(out, np.sin(2 * np.pi * (700 + 60 * k) * t) * np.sin(np.pi * t / 0.1) * 0.4, k * 0.14)
        return out
    if name == "printer":
        out = np.zeros(int(1.0 * SR))
        for k in range(12):
            _add(out, noise_burst(0.06, 40, rng) * 0.35, k * 0.08)
        return out
    if name == "camera_click":
        return noise_burst(0.05, 90, rng) * 0.7
    if name in ("growl", "roar_soft"):
        d = 0.8 if name == "growl" else 1.3
        t = _t(d)
        base = np.sin(2 * np.pi * (85 if name == "growl" else 120) * t) * (0.6 + 0.4 * np.sin(2 * np.pi * 23 * t))
        return (base + 0.3 * rng.uniform(-1, 1, len(t))) * _env(len(t), 0.1, 0.3) * 0.6
    if name == "yawn":
        t = _t(1.1)
        f = 380 - 180 * t / 1.1
        return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.sin(np.pi * t / 1.1) * 0.3
    if name == "cub_squeak":
        t = _t(0.22)
        f = 900 + 500 * np.sin(np.pi * t / 0.22)
        return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.sin(np.pi * t / 0.22) * 0.35
    if name in ("crowd_laugh", "crowd_aww", "crowd_gasp"):
        d = {"crowd_laugh": 1.4, "crowd_aww": 1.2, "crowd_gasp": 0.6}[name]
        out = np.zeros(int(d * SR))
        for k in range(7):
            f0 = rng.uniform(180, 320)
            t = _t(d * 0.9)
            if name == "crowd_aww":
                f = f0 * (1.3 - 0.3 * t / t[-1])
                v = np.sin(np.pi * t / t[-1])
            elif name == "crowd_laugh":
                f = np.full(len(t), f0 * 1.2)
                v = np.clip(np.sin(2 * np.pi * rng.uniform(5, 7) * t), 0, 1) * np.exp(-t)
            else:
                f = f0 * (1 + 0.4 * t / t[-1])
                v = np.exp(-6 * t)
            _add(out, np.sin(2 * np.pi * np.cumsum(f) / SR) * v * 0.08, rng.uniform(0, d * 0.1))
        return out + 0.05 * noise_burst(d, 2, rng)
    return np.zeros(1)


def ambience(kind, duration, rng):
    """Zoo ambience: wind, crowd murmur and bird chirps."""
    n = int(duration * SR)
    if kind != "zoo":
        return np.zeros(n)
    wind = np.convolve(rng.uniform(-1, 1, n), np.ones(400) / 400, mode="same") * 2.5
    murmur = np.zeros(n)
    t = np.arange(n) / SR
    for _ in range(6):
        f = rng.uniform(150, 260)
        murmur += np.sin(2 * np.pi * f * t + rng.uniform(0, 6)) * (0.5 + 0.5 * np.sin(2 * np.pi * rng.uniform(0.3, 1.2) * t)) * 0.02
    birds = np.zeros(n)
    for _ in range(int(duration / 2.5)):
        tt = _t(0.12)
        chirp = np.sin(2 * np.pi * np.cumsum(np.linspace(2600, 3800, len(tt))) / SR) * np.sin(np.pi * tt / 0.12) * 0.08
        for k in range(rng.integers(1, 4)):
            _add(birds, chirp, rng.uniform(0, duration) + k * 0.16)
    return wind * 0.25 + murmur + birds


def duck_envelope(voice, attack=0.08, release=0.25, floor=0.35, threshold=0.02):
    """1.0 when silent, `floor` while a voice is speaking, with attack/release smoothing."""
    block = int(0.01 * SR)
    nb = len(voice) // block + 1
    active = np.array([np.abs(voice[i * block:(i + 1) * block]).max(initial=0) > threshold for i in range(nb)])
    env = np.ones(nb)
    level = 1.0
    a, r = 0.01 / attack, 0.01 / release
    for i, on in enumerate(active):
        target = floor if on else 1.0
        step = a if target < level else r
        level += np.clip(target - level, -step, step)
        env[i] = level
    return np.repeat(env, block)[: len(voice)]


def render_soundtrack(duration, music_style="mystery", cues=(), voices=(), seed="x", music_gain=0.8, amb=None):
    """cues: [(sfx_name, seconds)], voices: [(samples, at_seconds)], amb: None | "zoo"."""
    n = int(duration * SR)
    rng = np.random.default_rng(int(hashlib.sha1(seed.encode()).hexdigest()[:8], 16))
    music = music_bed(music_style, duration, seed) if music_style != "none" else np.zeros(n)
    fx = np.zeros(n)
    for name, at in cues:
        _add(fx, sfx(name, rng), at)
    vox = np.zeros(n)
    for samples, at in voices:
        _add(vox, samples, at)
    duck = duck_envelope(vox)
    amb_track = ambience(amb, duration, rng) if amb else 0
    mix = music * 0.55 * music_gain * duck + amb_track * (0.75 + 0.25 * duck) + fx * (0.6 + 0.4 * duck) + vox * 1.1
    mix = np.tanh(1.2 * mix)
    peak = np.abs(mix).max(initial=0)
    return mix / peak * 0.92 if peak > 0 else mix


def write_wav(path, samples, sr=SR):
    pcm = (np.clip(samples, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


def read_wav(path):
    """Return mono float samples resampled to SR."""
    with wave.open(str(path), "rb") as w:
        sr, ch, width = w.getframerate(), w.getnchannels(), w.getsampwidth()
        raw = w.readframes(w.getnframes())
    data = np.frombuffer(raw, dtype="<i2" if width == 2 else np.uint8).astype(float)
    data = data / 32768 if width == 2 else (data - 128) / 128
    if ch > 1:
        data = data.reshape(-1, ch).mean(axis=1)
    return pcm_to_voice(data, sr)


def pcm_to_voice(samples, in_rate, factor=1.0, threshold=0.01):
    """Trim leading/trailing silence, resample to SR; factor > 1 raises pitch and speed."""
    idx = np.nonzero(np.abs(samples) > threshold)[0]
    if len(idx):
        samples = samples[idx[0]: idx[-1] + 1]
    n_out = int(len(samples) * SR / in_rate / factor)
    if n_out <= 0:
        return np.zeros(0)
    return np.interp(np.linspace(0, len(samples) - 1, n_out), np.arange(len(samples)), samples)
