"""Streamlit dashboard. Run: streamlit run app.py  (and, in another terminal, python -m ytauto.worker)."""
import json
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

from ytauto import captions, config, db, story, tts, worker, youtube

st.set_page_config(page_title="YouTube Automater", page_icon="🎬", layout="wide")
db.init()

FORMAT_LABEL = {"story": "Narrated story", "cartoon": "Cartoon gags", "window": "Zoo window"}
STATUS_BADGE = {"rendering": "🟡 Rendering", "needs_review": "🟠 Needs review", "scheduled": "🔵 Scheduled",
                "published": "🟢 Published", "failed": "🔴 Failed", "rejected": "⚫ Rejected",
                "needs_attention": "🔴 Needs attention"}


def worker_status():
    state = db.get_json_setting(worker.STATE_KEY, {}) or {}
    beat = state.get("heartbeat")
    alive = bool(beat) and (datetime.now(timezone.utc) - db.utc_iso(beat)).total_seconds() < 120
    return alive, state


def fmt_time(iso):
    if not iso:
        return "—"
    return db.utc_iso(iso).astimezone().strftime("%a %d %b, %H:%M")


def series_controls(series, key):
    s = story.normalize_series(series)
    c = st.columns(5)
    niche = c[0].selectbox("Niche", list(story.NICHES), index=list(story.NICHES).index(s["niche"]),
                           format_func=lambda k: story.NICHES[k]["label"], key=f"{key}_niche")
    style = c[1].selectbox("Art style", list(story.ART_STYLES), index=list(story.ART_STYLES).index(s["style"]),
                           format_func=lambda k: k.replace("_", " ").title(), key=f"{key}_style")
    caps = c[2].selectbox("Captions", list(captions.STYLES), index=list(captions.STYLES).index(s["captions"]),
                          format_func=lambda k: k.replace("_", " ").title(), key=f"{key}_caps")
    narr = c[3].selectbox("Narrator", list(tts.NARRATORS), index=list(tts.NARRATORS).index(s["narrator"]),
                          format_func=str.title, key=f"{key}_narr")
    lang = c[4].selectbox("Language", list(story.LANGUAGES), index=list(story.LANGUAGES).index(s["language"]),
                          format_func=lambda k: story.LANGUAGES[k], key=f"{key}_lang")
    default_music = s["music"] if niche == s["niche"] else story.NICHES[niche]["music"]
    music = st.selectbox("Music", story.audio.STORY_MUSIC, index=story.audio.STORY_MUSIC.index(default_music),
                         key=f"{key}_music")
    return {"niche": niche, "style": style, "captions": caps, "narrator": narr, "language": lang, "music": music}


# sidebar
alive, wstate = worker_status()
with st.sidebar:
    st.title("🎬 YouTube Automater")
    page = st.radio("Page", ["Video library", "Queue", "Series & settings", "Reference channel", "Status"],
                    label_visibility="collapsed")
    st.divider()
    if alive:
        st.success(f"Worker running\n\nNext run: {fmt_time(wstate.get('next_run'))}")
    else:
        st.error("Worker is not running.\n\nStart it with:\n\n`python -m ytauto.worker`")
    if wstate.get("last_result"):
        st.caption(f"Last run {fmt_time(wstate.get('last_run'))}: {wstate['last_result']}")
    paused = db.get_setting("automation_paused") == "true"
    if st.toggle("Pause automatic videos", value=paused) != paused:
        db.set_setting("automation_paused", "false" if paused else "true")
        st.rerun()


def page_library():
    st.header("Video library")
    items = db.list_library()
    c = st.columns(4)
    c[0].metric("Videos", len(items))
    c[1].metric("Waiting for review", sum(i["status"] == "needs_review" for i in items))
    c[2].metric("Scheduled", sum(i["status"] == "scheduled" for i in items))
    c[3].metric("Published", sum(i["status"] == "published" for i in items))
    flt = st.multiselect("Show", list(STATUS_BADGE), default=[k for k in STATUS_BADGE if k != "rejected"],
                         format_func=STATUS_BADGE.get)
    for it in [i for i in items if i["status"] in flt]:
        with st.container(border=True):
            left, right = st.columns([1, 2])
            if it.get("video_path") and Path(it["video_path"]).exists():
                left.video(it["video_path"])
            elif it.get("thumb_path") and Path(it["thumb_path"]).exists():
                left.image(it["thumb_path"])
            right.subheader(it.get("title") or it.get("topic") or f"Video {it['id']}")
            right.write(f"{STATUS_BADGE.get(it['status'], it['status'])} · {FORMAT_LABEL.get(it.get('format'), '')} · "
                        f"{it.get('duration') or '—'} s · "
                        f"made {fmt_time(it['created_at'])}")
            if it.get("publish_at") and it.get("publish_status") == "scheduled":
                right.write(f"Publishes {fmt_time(it['publish_at'])}")
            if it.get("youtube_id"):
                right.markdown(f"[Open on YouTube ↗](https://youtube.com/shorts/{it['youtube_id']})")
            if it.get("error"):
                right.error(it["error"][:600])
            b = right.columns(4)
            if it["status"] == "needs_review" and b[0].button("✅ Approve", key=f"ap{it['id']}"):
                from ytauto import pipeline
                pipeline.approve(it["id"])
                st.rerun()
            if it["status"] in ("needs_review", "scheduled") and b[1].button("🚫 Reject", key=f"rj{it['id']}"):
                from ytauto import pipeline
                pipeline.reject(it["id"])
                st.rerun()
            if it["status"] in ("needs_review", "scheduled", "needs_attention") and it.get("video_path") and \
                    b[2].button("⬆️ Publish now", key=f"pn{it['id']}"):
                db.enqueue_job("publish_now", {"id": it["id"]})
                st.toast("Upload queued for the worker")
            if it.get("video_path"):
                right.caption(f"File: `{it['video_path']}` (or use the player's ⋮ menu to download)")
            with right.expander("Rewrite with AI"):
                notes = st.text_area("What should change?", key=f"nt{it['id']}")
                if st.button("Rewrite", key=f"rw{it['id']}"):
                    db.enqueue_job("regenerate", {"id": it["id"], "notes": notes})
                    st.toast("Rewrite queued")
            script = it.get("script") if isinstance(it.get("script"), dict) else {}
            if script.get("scenes"):
                with right.expander("✎ Edit scenes and re-render"):
                    edit_story(it)
            elif script.get("shots"):
                with right.expander("✎ Edit lines and sounds, then re-render"):
                    edit_gag(it)


def edit_story(it):
    s = json.loads(json.dumps(it["script"]))
    with st.form(f"edit{it['id']}"):
        s["title"] = st.text_input("Title", s["title"])
        s["series"] = series_controls(s.get("series"), f"ed{it['id']}")
        for i, sc in enumerate(s["scenes"]):
            st.markdown(f"**Scene {i + 1}**")
            sc["narration"] = st.text_area("Narration", sc["narration"], key=f"n{it['id']}_{i}", height=70)
            sc["image_prompt"] = st.text_input("Picture description", sc.get("image_prompt", ""), key=f"p{it['id']}_{i}")
            cols = st.columns(4)
            for col, field, opts in zip(cols, ("setting", "figure", "time", "mood"),
                                        (story.SETTINGS, story.FIGURES, story.TIMES, story.MOODS)):
                sc[field] = col.selectbox(field.title(), opts, index=opts.index(sc[field]), key=f"{field}{it['id']}_{i}")
        if st.form_submit_button("Re-render"):
            db.enqueue_job("rerender", {"id": it["id"], "story": s})
            st.toast("Re-render queued for the worker")


def edit_gag(it):
    from ytauto import gags
    g = json.loads(json.dumps(it["script"]))
    window = g["format"] == "window"
    with st.form(f"gag{it['id']}"):
        g["title"] = st.text_input("Title", g["title"])
        g["caption"] = st.text_input("Caption at the top", g.get("caption", ""), max_chars=45)
        cols = st.columns(3)
        g["voices"] = cols[0].toggle("Voices", value=g.get("voices", True), key=f"gv{it['id']}")
        if window:
            g["animal"] = cols[1].selectbox("Animal family", gags.WINDOW["species"],
                                            index=gags.WINDOW["species"].index(g["animal"]), key=f"ga{it['id']}")
            vv = g.setdefault("visitor_voices", {})
            vv["kid"] = cols[2].selectbox("Kid's voice", ["kid", "girl", "boy"],
                                          index=["kid", "girl", "boy"].index(vv.get("kid", "kid")), key=f"gk{it['id']}")
        else:
            g["music"] = cols[1].selectbox("Music", gags.VOCAB["music"], index=gags.VOCAB["music"].index(g["music"]),
                                           key=f"gm{it['id']}")
            for role, col in (("hero", cols[2]), ("other", cols[2])):
                c = g["cast"][role]
                c["species"] = col.selectbox(f"{role.title()} species", gags.VOCAB["species"],
                                             index=gags.VOCAB["species"].index(c["species"]), key=f"gs{role}{it['id']}")
                c["voice"] = col.selectbox(f"{role.title()} voice", gags.VOCAB["voice"],
                                           index=gags.VOCAB["voice"].index(c["voice"]), key=f"gvo{role}{it['id']}")
        speakers = gags.WINDOW_SPEAKERS if window else ["hero", "other"]
        sfx = gags.WINDOW["sfx"] if window else gags.VOCAB["sfx"]
        for i, sh in enumerate(g["shots"]):
            st.markdown(f"**{'Beat' if window else 'Shot'} {i + 1}** · {sh['dur']} s")
            row = st.columns([1, 3, 1, 2] if not window else [1, 4, 1])
            sp = sh.get("speech") or {"who": speakers[0], "text": ""}
            who = row[0].selectbox("Speaker", speakers, index=speakers.index(sp["who"]), key=f"w{it['id']}_{i}")
            line = row[1].text_input("Line", sp["text"], key=f"l{it['id']}_{i}")
            sh["speech"] = {"who": who, "text": line} if line.strip() else None
            sh["sfx"] = row[2].selectbox("Sound", sfx, index=sfx.index(sh.get("sfx", "none")), key=f"x{it['id']}_{i}")
            if not window and sh["prop"]["kind"] != "none":
                sh["prop"]["text"] = row[3].text_input("Sign / screen text", sh["prop"]["text"], key=f"p{it['id']}_{i}")
        if st.form_submit_button("Re-render"):
            db.enqueue_job("rerender", {"id": it["id"], "story": g})
            st.toast("Re-render queued for the worker")


def page_queue():
    st.header("Queue")
    with st.form("add", clear_on_submit=True):
        topic = st.text_input("New topic", placeholder="e.g. The night the lighthouse lamp went out")
        if st.form_submit_button("Add to queue") and topic.strip():
            db.add_queue_item(topic)
            st.rerun()
    c = st.columns(2)
    if c[0].button("▶️ Make next now", help="Ignores the pending-video limit"):
        db.enqueue_job("run_next")
        st.toast("Queued — the worker will start it within 20 seconds")
    st.caption(f"Automatic schedule: `{config.SHORTS_SCHEDULE}` (UTC) · pauses at {config.SHORTS_MAX_PENDING} "
               f"waiting videos · publish gap {config.SHORTS_PUBLISH_GAP_HOURS} h")
    st.subheader("Topic queue")
    queue = db.list_queue()
    if not queue:
        st.info("Queue is empty — the AI will pick topics (from your reference channel's topic gaps when set).")
    for q in queue:
        row = st.columns([6, 1, 1, 1])
        row[0].write(f"{q['topic']}  \n`{q['status']}`")
        if q["status"] == "queued":
            if row[1].button("Top", key=f"t{q['id']}"):
                db.move_queue_item_to_top(q["id"])
                st.rerun()
            if row[2].button("Remove", key=f"r{q['id']}"):
                db.update_queue_item(q["id"], status="removed")
                st.rerun()
    st.subheader("Publishing queue")
    for it in db.list_library():
        if it.get("publish_status") == "scheduled":
            st.write(f"{fmt_time(it['publish_at'])} — {it['title']}")
    st.subheader("Recent jobs")
    jobs = db.list_jobs()
    if jobs:
        st.dataframe([{k: j[k] for k in ("id", "kind", "status", "result", "updated_at")} for j in jobs],
                     hide_index=True, use_container_width=True)


def page_settings():
    st.header("Series & settings")
    fmt = st.selectbox("Video style", ["story", "cartoon", "window"],
                       format_func=FORMAT_LABEL.get,
                       index=["story", "cartoon", "window"].index(db.get_setting("cartoon_format", "story")))
    series = db.get_json_setting("story_series", {})
    if fmt == "story":
        st.subheader("Story series")
        series = series_controls(series, "series")
    elif fmt == "cartoon":
        st.caption("Crude 2D characters on cream paper, fast cuts, voiced speech bubbles, cartoon sound effects. "
                   "Max 60 s.")
    else:
        st.caption("One hand-held shot through zoo glass: an animal family acts out a tiny drama while visitors "
                   "react. Max 45 s.")
    limits = {"story": (25, 90), "cartoon": (12, 60), "window": (12, 45)}[fmt]
    current = min(max(int(db.get_setting("cartoon_target_seconds", "50")), limits[0]), limits[1])
    target = st.slider("Video length (seconds)", limits[0], limits[1], current)
    kids = st.toggle("Made for kids", value=db.get_setting("made_for_kids") == "true")
    auto = st.toggle("Auto-approve (schedule without review)", value=db.get_setting("approval_required") == "false")
    notes = st.text_area("Style notes (added to every prompt as EDITOR NOTES)",
                         db.get_setting("cartoon_style_notes", ""), max_chars=800)
    if st.button("Save settings", type="primary"):
        db.set_setting("cartoon_format", fmt)
        db.set_setting("story_series", series)
        db.set_setting("cartoon_target_seconds", str(target))
        db.set_setting("made_for_kids", "true" if kids else "false")
        db.set_setting("approval_required", "false" if auto else "true")
        db.set_setting("cartoon_style_notes", notes)
        st.success("Saved")
    st.divider()
    with st.expander("Danger zone"):
        confirm = st.text_input("Type DELETE to clear all videos, queue and schedule (settings are kept)")
        if st.button("Clear everything") and confirm == "DELETE":
            db.reset_content()
            for sub in ("videos", "thumbnails", "temp"):
                for f in (config.DATA / sub).rglob("*"):
                    if f.is_file():
                        f.unlink()
            st.success("Cleared")


def page_reference():
    st.header("Reference channel")
    st.write("Give any channel; the app learns its format and topic gaps and makes **original** videos in that "
             "style. It never copies titles, characters or stories.")
    with st.form("ref"):
        ch = st.text_input("Channel (@handle, URL or UC… id)")
        if st.form_submit_button("Analyze & use") and ch.strip():
            db.enqueue_job("analyze", {"channel": ch.strip()})
            st.toast("Analysis queued for the worker")
    prof = db.active_profile()
    if prof:
        p = prof["profile"]
        st.subheader(f"Active: {prof['title']}")
        c = st.columns(3)
        c[0].metric("Shorts share", f"{int(p['stats']['shortsShare'] * 100)}%")
        c[1].metric("Uploads every", f"{p['stats'].get('uploadsEveryDays') or '—'} days")
        c[2].metric("Profile source", p.get("source", "—"))
        st.write(f"**Niche:** {p.get('niche', '—')}  \n**Tone:** {p.get('tone', '—')}  \n**Pacing:** {p.get('pacing', '—')}")
        if p.get("topicGaps"):
            st.write("**Topic gaps** (used when the queue is empty):")
            for g in p["topicGaps"]:
                st.write(f"- {g}")
        if st.button("Stop using this channel"):
            db.deactivate_profiles()
            st.rerun()


def page_status():
    st.header("Status")
    checks = [
        ("Gemini API key (scripts, Gemini voices)", bool(config.GEMINI_API_KEY)),
        ("YouTube API key (reference analysis)", bool(config.YOUTUBE_API_KEY)),
        ("YouTube connected (uploads)", youtube.connected()),
        ("Piper voices installed (free narration)", tts.piper_ready()),
        ("Caption fonts downloaded", any(config.FONTS.glob("*.ttf"))),
        ("Worker running", alive),
    ]
    for label, ok in checks:
        st.write(("✅ " if ok else "❌ ") + label)
    st.caption("See README.md for setup steps.")


{"Video library": page_library, "Queue": page_queue, "Series & settings": page_settings,
 "Reference channel": page_reference, "Status": page_status}[page]()
