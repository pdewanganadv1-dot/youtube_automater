import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    from ytauto import db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init()
    yield db


def test_parse_json_strips_fences():
    from ytauto import ai
    assert ai.parse_json('Sure!\n```json\n{"a": 1}\n```\nbye') == {"a": 1}
    with pytest.raises(ValueError):
        ai.parse_json("no json here")


def test_normalize_story_clamps_vocabulary():
    from ytauto import story
    raw = json.loads((FIX / "story.json").read_text())
    raw["scenes"][0]["setting"] = "spaceship"
    s = story.normalize_story(raw)
    assert s["scenes"][0]["setting"] == "forest"
    assert [sc["motion"] for sc in s["scenes"][:2]] == ["zoom_in", "zoom_out"]
    with pytest.raises(ValueError):
        story.normalize_story({"title": "x", "scenes": [{"narration": "only one"}]})


def test_build_prompt_contains_rules():
    from ytauto import story
    p = story.build_prompt("A haunted lighthouse", {"niche": "history", "language": "hi"}, notes="slower pace",
                           target_seconds=40, kids=True)
    assert "amazing TRUE story from history told simply for kids" in p
    assert "Narration language: Hindi" in p
    assert "EDITOR NOTES" in p and "slower pace" in p
    assert "102 words" in p


def test_word_times_and_groups():
    from ytauto import captions
    t = captions.word_times("Hello there. The end", 0.0, 4.0)
    assert t[0][1] == 0.0 and abs(t[-1][2] - 4.0) < 1e-9
    groups = captions.groups(t, 3)
    assert [len(g) for g in groups] == [2, 2]  # never straddles the sentence end
    ass = captions.build_ass([{"narration": "One two three.", "start": 0, "end": 2}], "karaoke")
    assert r"\kf" in ass and "PlayResY: 1920" in ass


def test_publish_slots_fill_gaps(tmp_db):
    from ytauto import pipeline
    now = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    taken = [(now + timedelta(hours=1)).isoformat(), (now + timedelta(hours=10)).isoformat()]
    slot = pipeline.next_publish_slot(now, gap_hours=4, existing=taken)
    assert slot == now + timedelta(hours=5)  # first gap that is 4h from both
    assert pipeline.next_publish_slot(now, gap_hours=4, existing=[]) == now + timedelta(minutes=20)


def test_queue_order(tmp_db):
    db = tmp_db
    a, b = db.add_queue_item("first"), db.add_queue_item("second")
    assert db.next_queue_item()["id"] == a
    db.move_queue_item_to_top(b)
    assert db.next_queue_item()["id"] == b


def test_soundtrack_ducks_under_voice():
    import numpy as np
    from ytauto import audio
    voice = np.zeros(audio.SR * 3)
    voice[audio.SR:2 * audio.SR] = 0.5
    env = audio.duck_envelope(voice)
    assert env[audio.SR // 2] == pytest.approx(1.0)
    assert env[int(1.5 * audio.SR)] == pytest.approx(0.35, abs=0.01)
    mix = audio.render_soundtrack(3, "dark", [("hit", 0.0)], [], seed="t")
    assert len(mix) == 3 * audio.SR and np.abs(mix).max() <= 0.921


def test_run_continuous_respects_backlog(tmp_db, monkeypatch):
    from ytauto import config, pipeline
    monkeypatch.setattr(config, "SHORTS_MAX_PENDING", 1)
    monkeypatch.setattr(pipeline.ai, "available", lambda: True)
    tmp_db.create_production(topic="x", status="needs_review")
    assert pipeline.run_continuous() == "skipped: backlog full"


@pytest.mark.skipif(not __import__("os").getenv("RENDER"), reason="set RENDER=1 for a real MP4 render (~30 s)")
def test_real_render():
    from ytauto import story
    s = story.normalize_story(json.loads((FIX / "story.json").read_text()))
    s["series"] = {"niche": "scary", "style": "storybook", "captions": "comic"}
    out = story.render(s, "pytest_render", image_source="builtin")
    assert Path(out["video_path"]).stat().st_size > 100_000 and out["duration"] > 20
