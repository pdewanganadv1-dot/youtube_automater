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


def narrate(lines, narrator="john", music="mystery", language="en", seed=""):
    """Return (list of sample arrays or None per line, credit text). Never raises: missing voices -> None."""
    prov = provider(language)
    if not prov:
        return [None] * len(lines), ""
    gem_voice, gem_pitch, group, pitch, length = NARRATORS.get(narrator, NARRATORS["john"])
    delivery, speed = DELIVERY.get(music, ("as a warm, engaging storyteller", 1.0))
    out, failures = [], 0
    if prov == "piper":
        speaker = _speaker_id(group, f"{seed}|{narrator}")
        todo = []
        for text in lines:
            key = hashlib.sha1(f"piper|{speaker}|{length * speed}|{text}".encode()).hexdigest()
            path = CACHE / f"{key}.wav"
            if not path.exists():
                todo.append({"text": text, "speaker": speaker, "length_scale": length * speed, "out": str(path)})
            out.append(path)
        if todo:
            try:
                _piper_batch(todo)
            except Exception as e:  # fall back to silence rather than failing the video
                log.warning("Piper synthesis failed: %s", e)
                return [None] * len(lines), ""
        return [audio.pcm_to_voice(audio.read_wav(p), audio.SR, pitch) if p.exists() else None for p in out], \
            PIPER_CREDIT
    for text in lines:
        key = hashlib.sha1(f"gemini|{gem_voice}|{delivery}|{text}".encode()).hexdigest()
        path = CACHE / f"{key}.npy"
        if path.exists():
            out.append(audio.pcm_to_voice(np.load(path), 24000, gem_pitch * speed))
            continue
        if failures >= 2:
            out.append(None)
            continue
        try:
            pcm = _gemini(text, gem_voice, delivery)
            np.save(path, pcm)
            out.append(audio.pcm_to_voice(pcm, 24000, gem_pitch * speed))
        except Exception as e:
            failures += 1
            log.warning("Gemini TTS failed for a line: %s", e)
            out.append(None)
    return out, ("Narration: Gemini TTS." if any(v is not None for v in out) else "")
