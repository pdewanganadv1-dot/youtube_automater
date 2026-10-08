import json
import os
from pathlib import Path

import numpy as np
import pytest

from ytauto import audio, gags

FIX = Path(__file__).parent / "fixtures"


def cartoon():
    return gags.normalize_cartoon(json.loads((FIX / "cartoon-gag.json").read_text()), 22)


def window():
    return gags.normalize_window(json.loads((FIX / "window-gag.json").read_text()), 18)


def test_cartoon_normalize_enforces_vocab_and_ending():
    raw = json.loads((FIX / "cartoon-gag.json").read_text())
    raw["shots"][0]["hero"]["action"] = "teleport"
    raw["shots"][-1]["hero"]["action"] = "idle"
    raw["shots"][1]["prop"]["text"] = "x" * 80
    g = gags.normalize_cartoon(raw, 22)
    assert g["shots"][0]["hero"]["action"] == "idle"
    assert g["shots"][-1]["hero"]["action"] in gags.ENDINGS
    assert g["shots"][-1]["dur"] >= 2.6
    assert len(g["shots"][1]["prop"]["text"]) == 48 and g["shots"][1]["prop"]["text"].isupper()
    assert sum(s["dur"] for s in g["shots"]) <= 60
    with pytest.raises(ValueError):
        gags.normalize_cartoon({"title": "x", "shots": raw["shots"][:3]}, 22)


def test_cartoon_prompt_is_verbatim_port():
    p = gags.build_cartoon_prompt("A cat vs a vacuum", kids=True, target_seconds=40, notes="more honks")
    assert "You write funny KIDS cartoon Shorts" in p
    assert "rule of three" in p and "max 10 words" in p
    assert "MADE FOR KIDS (ages 4-10)" in p
    assert "EDITOR NOTES" in p and "more honks" in p
    assert "Topic for this video: A cat vs a vacuum" in p


def test_window_prompt_and_targets():
    p = gags.build_window_prompt("cub steals the show", target_seconds=60)
    assert '"zoo window" style' in p and "Animals never talk." in p
    assert "total about 45 seconds" in p  # window is capped at 45 s


def test_window_normalize_targets_and_speakers():
    raw = json.loads((FIX / "window-gag.json").read_text())
    raw["shots"][0]["cub"]["action"] = "nudge"  # nudge without target -> idle
    raw["shots"][1]["speech"]["who"] = "lion"
    g = gags.normalize_window(raw, 18)
    assert g["shots"][0]["cub"]["action"] == "idle"
    assert g["shots"][1]["speech"]["who"] == "visitor"
    assert g["shots"][5]["mom"]["target"] == "dad"
    assert sum(s["dur"] for s in g["shots"]) <= 45


def test_window_inheritance_and_nudge():
    from ytauto import window_engine as we
    g = window()
    starts, t = [], 0
    for s in g["shots"]:
        starts.append(t)
        t += s["dur"]
    state = we.prepare(g, starts, [s["dur"] for s in g["shots"]])
    b = state["beats"]
    assert b[0]["animals"]["cub"]["action"] == "walk_in"
    assert b[1]["animals"]["dad"]["action"] == "sit"  # not mentioned + resting -> keeps resting
    assert b[2]["animals"]["cub"]["action"] == "idle"  # not mentioned + was active -> idle
    assert b[5]["animals"]["dad"].get("pushed") in (190, -190)
    assert any(m["kind"] == "paws" for m in state["marks"]) and any(m["kind"] == "fog" for m in state["marks"])


def test_voices_stretch_shots_and_cap_total():
    g = cartoon()
    voices = {0: np.zeros(int(4.0 * audio.SR))}
    durs = gags.fit_shots_to_voices(g, voices, cap=60)
    assert durs[0] == pytest.approx(4.55)
    many = {i: np.zeros(int(9 * audio.SR)) for i in range(len(g["shots"]) - 1)}
    fitted = gags.fit_shots_to_voices(g, many, cap=60)
    assert all(d == pytest.approx(9.55) for d in fitted[:-1])  # voiced shots are never cut
    assert fitted[-1] < g["shots"][-1]["dur"] + 1e-9  # only the silent shot shrinks
    capped = gags.fit_shots_to_voices(g, {0: np.zeros(int(50 * audio.SR))}, cap=60)
    assert sum(capped) <= 60 + 1e-6


def test_speech_lines_and_cues():
    g = cartoon()
    lines = gags.speech_lines(g)
    assert lines[0][1] == "Finally, snack time!" and lines[0][2] == "boy"
    assert any(role == "other" and voice == "squeaky" for *_, voice, _m, role in lines)
    durs = [s["dur"] for s in g["shots"]]
    starts = list(np.cumsum([0] + durs[:-1]))
    names = [c[0] for c in gags.cues_for(g, starts, durs, voiced=False)]
    assert "whoosh" in names and "wahwah" in names and "pop" in names and "error" in names
    w = window()
    wn = [c[0] for c in gags.cues_for(w, starts[:len(w["shots"])], [s["dur"] for s in w["shots"]], voiced=True)]
    assert "crowd_laugh" in wn and "crowd_aww" in wn and "glass_tap" in wn and "growl" in wn


def test_edited_gag_renormalizes():
    g = window()
    g["animal"] = "panda"
    g["visitor_voices"]["kid"] = "boy"
    out = gags.normalize(g)
    assert out["animal"] == "panda" and out["visitor_voices"]["kid"] == "boy"


@pytest.mark.skipif(not os.getenv("RENDER"), reason="set RENDER=1 for real MP4 renders (~25 s)")
@pytest.mark.parametrize("make", [cartoon, window])
def test_real_gag_render(make):
    from ytauto import animate
    out = animate.render(make(), f"pytest_{make.__name__}")
    assert Path(out["video_path"]).stat().st_size > 100_000 and out["duration"] > 10
