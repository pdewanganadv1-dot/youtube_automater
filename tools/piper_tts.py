"""Piper TTS helper. Run with the .voices venv python; reads one JSON request on stdin.

  {"cmd": "synth", "model": "...onnx", "items": [{"text", "speaker", "length_scale", "out"}]}
  {"cmd": "calibrate", "model": "...onnx", "out": "data/voices/speakers.json", "samples": 60}
"""
import json
import sys
import wave

import numpy as np
from piper import PiperVoice

try:
    from piper import SynthesisConfig
except ImportError:  # older piper-tts
    SynthesisConfig = None


def synth(voice, text, speaker, length_scale, out):
    with wave.open(out, "wb") as wav:
        if SynthesisConfig:
            cfg = SynthesisConfig(speaker_id=speaker, length_scale=length_scale, noise_scale=0.667, noise_w_scale=0.8)
            voice.synthesize_wav(text, wav, syn_config=cfg)
        else:
            voice.synthesize(text, wav, speaker_id=speaker, length_scale=length_scale, noise_scale=0.667, noise_w=0.8)


def pitch_of(path):
    with wave.open(path, "rb") as w:
        sr = w.getframerate()
        x = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(float)
    pitches = []
    frame = int(0.04 * sr)
    for i in range(0, len(x) - frame, frame):
        seg = x[i:i + frame] - x[i:i + frame].mean()
        if np.abs(seg).max() < 1500:
            continue
        ac = np.correlate(seg, seg, "full")[frame - 1:]
        lo, hi = int(sr / 400), int(sr / 70)
        lag = lo + int(np.argmax(ac[lo:hi]))
        pitches.append(sr / lag)
    return float(np.median(pitches)) if pitches else 0.0


def main():
    req = json.load(sys.stdin)
    voice = PiperVoice.load(req["model"])
    if req["cmd"] == "synth":
        for it in req["items"]:
            synth(voice, it["text"], it.get("speaker", 0), it.get("length_scale", 1.0), it["out"])
        print(json.dumps({"ok": True}))
    elif req["cmd"] == "calibrate":
        n_speakers = voice.config.num_speakers or 1
        step = max(1, n_speakers // req.get("samples", 60))
        pitches = {}
        for sid in range(0, n_speakers, step):
            tmp = f"/tmp/piper_cal_{sid}.wav"
            synth(voice, "The old lighthouse keeper heard a knock at midnight.", sid, 1.0, tmp)
            pitches[sid] = pitch_of(tmp)
        ordered = sorted((p, s) for s, p in pitches.items() if p > 0)
        third = max(1, len(ordered) // 3)
        groups = {"low": [s for _, s in ordered[:third]], "mid": [s for _, s in ordered[third:2 * third]],
                  "high": [s for _, s in ordered[2 * third:]]}
        with open(req["out"], "w") as f:
            json.dump({"groups": groups, "pitches": pitches}, f)
        print(json.dumps({"ok": True, "speakers": len(pitches)}))


if __name__ == "__main__":
    main()
