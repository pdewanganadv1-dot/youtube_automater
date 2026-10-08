"""Narrator voices: free local Piper (preferred) or Gemini TTS, with an on-disk cache."""
import base64
import hashlib
import json
import logging
import re
import subprocess
import time
from pathlib import Path

import numpy as np
import requests

from . import audio, config

log = logging.getLogger(__name__)
CACHE = config.DATA / "tts"
SPEAKERS_FILE = config.DATA / "voices" / "speakers.json"
PIPER_SCRIPT = config.ROOT / "tools" / "piper_tts.py"

# preset -> (gemini voice, gemini pitch factor, piper group, piper pitch factor, piper length scale)
NARRATORS = {
    "adam": ("Algenib", 1.0, "low", 0.95, 1.08),
    "john": ("Charon", 1.0, "low", 1.0, 1.02),
    "bella": ("Sulafat", 1.0, "high", 1.0, 1.04),
    "grace": ("Enceladus", 1.0, "high", 1.0, 1.10),
    "sage": ("Charon", 0.93, "low", 0.92, 1.15),
}
DELIVERY = {
    "dark": ("as a slow, hushed, suspenseful storyteller", 1.08),
    "epic": ("as an epic documentary narrator", 1.0),
    "mystery": ("as an intrigued documentary narrator", 1.04),
}
PIPER_CREDIT = "Narration: Piper TTS with LibriTTS-R voices (CC BY 4.0)."


def piper_ready():
    return Path(config.PIPER_PYTHON).exists() and config.PIPER_MODEL.exists() and SPEAKERS_FILE.exists()


def provider(language="en"):
    if not config.CARTOON_VOICES:
        return None
    choice = config.CARTOON_TTS
    if choice in ("auto", "piper") and language == "en" and piper_ready():
        return "piper"
    if choice in ("auto", "gemini") and config.GEMINI_API_KEY:
        return "gemini"
    return None


def _speaker_id(group, key):
    groups = json.loads(SPEAKERS_FILE.read_text())["groups"]
    ids = groups.get(group) or groups.get("mid") or [0]
    return ids[int(hashlib.sha1(key.encode()).hexdigest()[:8], 16) % len(ids)]


def _piper_batch(lines):
    """lines: [{text, speaker, length_scale, out}] -> runs tools/piper_tts.py once for all of them."""
    req = {"cmd": "synth", "model": str(config.PIPER_MODEL), "items": lines}
    r = subprocess.run([config.PIPER_PYTHON, str(PIPER_SCRIPT)], input=json.dumps(req), capture_output=True,
                       text=True, timeout=180)
    if r.returncode != 0:
        raise RuntimeError(f"piper failed: {r.stderr[-400:]}")


def _gemini(text, voice, delivery):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{config.GEMINI_TTS_MODEL}:generateContent"
    body = {"contents": [{"parts": [{"text": f"Say {delivery}: {text}"}]}],
            "generationConfig": {"responseModalities": ["AUDIO"],
                                 "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}}}}
    for attempt in range(4):
        r = requests.post(url, json=body, timeout=120, headers={"x-goog-api-key": config.GEMINI_API_KEY})
        if r.status_code == 429:
            m = re.search(r"retry in (\d+(?:\.\d+)?)s", r.text)
            wait = float(m.group(1)) if m else 30
            if wait > 75 or attempt == 3:
                raise RuntimeError("Gemini TTS rate limit")
            time.sleep(wait + 1)
            continue
        r.raise_for_status()
        data = r.json()["candidates"][0]["content"]["parts"][0]["inlineData"]["data"]
        return np.frombuffer(base64.b64decode(data), dtype="<i2").astype(float) / 32768
    raise RuntimeError("Gemini TTS failed")


# character voices for cartoon/window formats: voice -> (piper group, piper pitch, piper length,
#                                                       gemini voice, gemini pitch)
CHARACTER_VOICES = {
    "kid": ("high", 1.12, 1.0, "Leda", 1.18), "girl": ("high", 1.08, 1.0, "Leda", 1.26),
    "boy": ("mid", 1.18, 1.0, "Puck", 1.2), "woman": ("high", 1.0, 1.0, "Kore", 1.06),
    "man": ("low", 1.0, 1.0, "Fenrir", 1.02), "grandpa": ("low", 0.92, 1.15, "Charon", 0.93),
    "grandma": ("mid", 0.95, 1.12, "Gacrux", 0.97), "robot": ("mid", 1.0, 1.05, "Iapetus", 1.0),
    "squeaky": ("high", 1.38, 0.95, "Puck", 1.42),
}
MOOD_SPEED = {"angry": 0.9, "shock": 0.88, "scream": 0.88, "sad": 1.15, "cry": 1.18, "excited": 0.92,
              "laugh": 0.95, "gasp": 0.9}
MOOD_DELIVERY = {"angry": "angrily, in a funny cartoon voice", "shock": "in total shock", "sad": "sadly",
                 "cry": "while sobbing", "smug": "smugly", "grin": "cheekily", "smile": "cheerfully",
                 "scream": "screaming", "excited": "excitedly", "laugh": "while laughing", "aww": "adoringly",
                 "gasp": "with a surprised gasp"}
CHARACTER_CREDIT = "Character voices: Piper TTS with LibriTTS-R voices (CC BY 4.0)."


def speak(items, language="en"):
    """items: [{text, key, piper: (group, pitch, length), gemini: (voice, pitch, delivery), robot}].
    Returns (samples or None per item, provider name or None). Never raises."""
    prov = provider(language)
    if not prov or not items:
        return [None] * len(items), None
    out = []
    if prov == "piper":
        todo, paths = [], []
        for it in items:
            group, pitch, length = it["piper"]
            speaker = _speaker_id(group, it["key"])
            h = hashlib.sha1(f"piper|{speaker}|{length}|{it['text']}".encode()).hexdigest()
            path = CACHE / f"{h}.wav"
            if not path.exists():
                todo.append({"text": it["text"], "speaker": speaker, "length_scale": length, "out": str(path)})
            paths.append(path)
        if todo:
            try:
                _piper_batch(todo)
            except Exception as e:  # fall back to silence rather than failing the video
                log.warning("Piper synthesis failed: %s", e)
                return [None] * len(items), None
        for it, path in zip(items, paths):
            out.append(audio.pcm_to_voice(audio.read_wav(path), audio.SR, it["piper"][1]) if path.exists() else None)
    else:
        failures = 0
        for it in items:
            voice, pitch, delivery = it["gemini"]
            h = hashlib.sha1(f"gemini|{voice}|{delivery}|{it['text']}".encode()).hexdigest()
            path = CACHE / f"{h}.npy"
            if path.exists():
                out.append(audio.pcm_to_voice(np.load(path), 24000, pitch))
                continue
            if failures >= 2:  # stop voicing after 2 failed lines (free tier is ~10 a day)
                out.append(None)
                continue
            try:
                pcm = _gemini(it["text"], voice, delivery)
                np.save(path, pcm)
                out.append(audio.pcm_to_voice(pcm, 24000, pitch))
            except Exception as e:
                failures += 1
                log.warning("Gemini TTS failed for a line: %s", e)
                out.append(None)
    for i, it in enumerate(items):
        if it.get("robot") and out[i] is not None:  # +55 Hz amplitude modulation
            t = np.arange(len(out[i])) / audio.SR
            out[i] = out[i] * (0.6 + 0.4 * np.sin(2 * np.pi * 55 * t))
    return out, prov


def narrate(lines, narrator="john", music="mystery", language="en", seed=""):
    """Narrator voice for every line. Returns (samples or None per line, credit text)."""
    gem_voice, gem_pitch, group, pitch, length = NARRATORS.get(narrator, NARRATORS["john"])
    delivery, speed = DELIVERY.get(music, ("as a warm, engaging storyteller", 1.0))
    items = [{"text": t, "key": f"{seed}|{narrator}", "piper": (group, pitch, length * speed),
              "gemini": (gem_voice, gem_pitch * speed, delivery)} for t in lines]
    out, prov = speak(items, language)
    if not any(v is not None for v in out):
        return out, ""
    return out, PIPER_CREDIT if prov == "piper" else "Narration: Gemini TTS."


def character_lines(lines, seed=""):
    """lines: [(text, voice, mood, role)]. Each role gets a distinct, stable speaker. Returns (samples, credit)."""
    items = []
    for text, voice, mood, role in lines:
        group, pitch, length, gem, gem_pitch = CHARACTER_VOICES.get(voice, CHARACTER_VOICES["man"])
        sp = MOOD_SPEED.get(mood, 1.0)
        items.append({"text": text, "key": f"{seed}|{role}", "piper": (group, pitch, length * sp),
                      "gemini": (gem, gem_pitch, MOOD_DELIVERY.get(mood, "in a funny cartoon voice")),
                      "robot": voice == "robot"})
    out, prov = speak(items)
    if not any(v is not None for v in out):
        return out, ""
    return out, CHARACTER_CREDIT if prov == "piper" else "Character voices: Gemini TTS."
