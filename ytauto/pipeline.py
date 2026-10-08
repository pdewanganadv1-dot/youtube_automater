"""Idea -> script -> render -> review/auto-approve -> scheduled upload."""
import logging
import random
import threading
from datetime import datetime, timedelta, timezone

from . import ai, animate, config, db, gags, reference, story, youtube

log = logging.getLogger(__name__)
_running = threading.Lock()


def settings_snapshot():
    return {
        "format": db.get_setting("cartoon_format", "story"),
        "series": db.get_json_setting("story_series", {}),
        "target": int(db.get_setting("cartoon_target_seconds", "50") or 50),
        "kids": db.get_setting("made_for_kids") == "true",
        "notes": db.get_setting("cartoon_style_notes", ""),
        "auto_approve": db.get_setting("approval_required") == "false",
    }


def next_publish_slot(now=None, gap_hours=None, existing=None):
    """Earliest time >= now+20min that is at least `gap_hours` from every scheduled slot (fills gaps)."""
    now = now or datetime.now(timezone.utc)
    gap = timedelta(hours=config.SHORTS_PUBLISH_GAP_HOURS if gap_hours is None else gap_hours)
    slots = sorted(db.utc_iso(s) for s in (db.scheduled_slots() if existing is None else existing))
    cand = now + timedelta(minutes=20)
    moved = True
    while moved:
        moved = False
        for s in slots:
            if abs((s - cand).total_seconds()) < gap.total_seconds():
                cand = s + gap
                moved = True
    return cand.replace(microsecond=0)


def pick_topic():
    profile = db.active_profile()
    gaps = (profile or {}).get("profile", {}).get("topicGaps") or []
    recent = " ".join(db.recent_titles(25)).lower()
    fresh = [g for g in gaps if g.lower()[:25] not in recent]
    return random.choice(fresh) if fresh else ""


def busy():
    return _running.locked()


def generate(topic=None, source="manual", notes_extra="", queue_item=None, series_override=None, format_override=None):
    """Make one video. Returns the production id. Only one generation runs at a time."""
    if not _running.acquire(blocking=False):
        raise RuntimeError("A video is already being made")
    pid = None
    try:
        s = settings_snapshot()
        fmt = format_override or s["format"]
        if fmt not in ("story", "cartoon", "window"):
            fmt = "story"
        series = series_override or s["series"]
        topic = (topic or "").strip() or pick_topic()
        notes = "\n".join(n for n in (s["notes"], notes_extra) if n)
        pid = db.create_production(topic=topic, format=fmt, status="rendering", source=source,
                                   made_for_kids=int(s["kids"]))
        if queue_item:
            db.update_queue_item(queue_item, status="started", job_id=pid)
        profile = (db.active_profile() or {}).get("profile")
        common = dict(avoid_titles=(profile or {}).get("titles", []), recent=db.recent_titles(25), notes=notes,
                      kids=s["kids"], reference=profile)
        if fmt == "story":
            st = story.write_story(topic, series, target_seconds=s["target"], **common)
        else:
            st = gags.write_gag(fmt, topic, target_seconds=min(s["target"], 60 if fmt == "cartoon" else 45),
                                market=config.TARGET_AUDIENCE, **common)
        ok, clash = reference.check_originality(st["title"], profile)
        if not ok:
            log.warning("Title %r is close to reference title %r", st["title"], clash)
        db.update_production(pid, title=st["title"], script=st, tags=st["tags"])
        _render_and_review(pid, st, s["kids"], s["auto_approve"])
        if queue_item:
            db.update_queue_item(queue_item, status="done")
        return pid
    except Exception as e:
        log.exception("Generation failed")
        if pid:
            db.update_production(pid, status="failed", error=str(e)[:2000])
        if queue_item:
            db.update_queue_item(queue_item, status="failed", note=str(e)[:500])
        raise
    finally:
        _running.release()


def _render_and_review(pid, st, kids, auto_approve):
    db.update_production(pid, status="rendering")
    if st.get("format") in ("cartoon", "window"):
        out = animate.render(st, f"short_{pid}")
    else:
        out = story.render(st, f"short_{pid}", made_for_kids=kids)
    desc = st.get("description", "")
    if out["credit"]:
        desc = f"{desc}\n\n{out['credit']}".strip()
    tags = st.get("tags") or []
    if "#shorts" not in desc.lower():
        desc += "\n\n#shorts"
    db.update_production(pid, video_path=out["video_path"], thumb_path=out["thumb_path"], duration=out["duration"],
                         credit=out["credit"], description=desc, tags=tags, status="needs_review", error=None)
    if auto_approve:
        approve(pid)


def approve(pid):
    db.schedule_publish(pid, next_publish_slot().isoformat())


def rerender(pid, edited_story):
    """Re-render in place after edits; unchanged scene images come from the cache."""
    if not _running.acquire(blocking=False):
        raise RuntimeError("A video is already being made")
    try:
        p = db.get_production(pid)
        if edited_story.get("format") in ("cartoon", "window"):
            st = gags.normalize({**edited_story, "topic": p["topic"]})
        else:
            st = story.normalize_story(edited_story) | {"series": story.normalize_series(edited_story.get("series")),
                                                         "topic": p["topic"]}
        db.cancel_schedule(pid)
        db.update_production(pid, title=st["title"], script=st)
        _render_and_review(pid, st, bool(p["made_for_kids"]), auto_approve=False)
    except Exception as e:
        db.update_production(pid, status="failed", error=str(e)[:2000])
        raise
    finally:
        _running.release()


def regenerate(pid, notes):
    """Rewrite with AI: same topic, clearly different take; the old video is rejected."""
    p = db.get_production(pid)
    db.cancel_schedule(pid)
    db.update_production(pid, status="rejected")
    script = p.get("script") if isinstance(p.get("script"), dict) else {}
    fmt = script.get("format") or p.get("format") or None
    kind = "story" if fmt in (None, "story") else "joke"
    extra = (notes or "") + f"\nThe previous version was rejected — make a clearly different {kind}."
    return generate(p["topic"], source="regenerate", notes_extra=extra.strip(), series_override=script.get("series"),
                    format_override=fmt)


def reject(pid):
    db.cancel_schedule(pid)
    db.update_production(pid, status="rejected")


def publish_due(now=None):
    """Upload every scheduled video whose slot has passed."""
    now = (now or datetime.now(timezone.utc)).replace(microsecond=0)
    done = []
    if not youtube.connected():
        return done  # keep videos scheduled until YouTube is connected
    for row in db.due_publications(now.isoformat()):
        p = db.get_production(row["production_id"])
        try:
            vid = youtube.upload(p["video_path"], p["title"], p["description"] or "", p.get("tags") or [],
                                 bool(p["made_for_kids"]), p["thumb_path"])
            db.update_publication(row["id"], status="published", youtube_id=vid, error=None)
            db.update_production(p["id"], status="published")
            done.append(vid)
        except Exception as e:
            log.exception("Upload failed for production %s", p["id"])
            db.update_publication(row["id"], status="failed", error=str(e)[:1000])
            db.update_production(p["id"], status="needs_attention", error=f"Upload failed: {e}"[:2000])
    return done


def run_continuous(manual=False):
    """One scheduler tick: take the next queued topic (or an AI-picked one) and make a video."""
    if busy():
        return "skipped: busy"
    if not ai.available():
        return "skipped: GEMINI_API_KEY is not set"
    if not manual:
        if db.get_setting("automation_paused") == "true":
            return "skipped: paused"
        if db.pending_review_count() >= config.SHORTS_MAX_PENDING or \
                len(db.scheduled_slots()) >= config.SHORTS_MAX_PENDING:
            return "skipped: backlog full"
    item = db.next_queue_item()
    pid = generate(item["topic"] if item else None, source="manual" if manual else "scheduler",
                   queue_item=item["id"] if item else None)
    return f"made production {pid}"
