"""Narrated story Shorts ("faceless series"): AI script -> images -> narration -> soundtrack -> captions -> MP4.

Port of utils/story-short-service.js; behaviour and numbers follow HANDOVER.md §3c.
"""
import base64
import hashlib
import io
import json
import logging
import subprocess
import urllib.parse
from pathlib import Path

import requests
from PIL import Image

from . import ai, audio, captions, config, illustrator, tts

log = logging.getLogger(__name__)

NICHES = {
    "scary": {"label": "Scary stories", "music": "dark", "transition": "fadeblack",
              "brief": "an ORIGINAL short horror story (creepy and suspenseful, not gory) with a chilling twist in the last line",
              "kidsBrief": "a spooky-fun mystery for kids (a little shivery, never frightening) with a funny or sweet twist"},
    "history": {"label": "History", "music": "epic", "transition": "fade",
                "brief": "a surprising TRUE story from history; every fact, name, place and date must be accurate",
                "kidsBrief": "an amazing TRUE story from history told simply for kids; facts must be accurate"},
    "figures": {"label": "Historical figures", "music": "epic", "transition": "fade",
                "brief": "the most dramatic moment in one real historical figure's life; accurate facts only",
                "kidsBrief": "an inspiring moment from a real historical figure's childhood or life, told for kids; accurate facts only"},
    "mythology": {"label": "Greek mythology", "music": "epic", "transition": "fade",
                  "brief": "a Greek myth retold dramatically (stay faithful to the myth)",
                  "kidsBrief": "a Greek myth retold gently for kids (stay faithful to the myth)"},
    "facts": {"label": "Mind-blowing facts", "music": "mystery", "transition": "fade",
              "brief": "a countdown of 5 mind-blowing, TRUE facts on one theme; accurate only",
              "kidsBrief": "a countdown of 5 amazing TRUE facts for kids on one theme"},
    "unsolved": {"label": "Unsolved mysteries", "music": "mystery", "transition": "fadeblack",
                 "brief": "a real unsolved mystery: what happened, the strangest clues, the main theories; accurate facts only, no speculation presented as fact",
                 "kidsBrief": "a real unexplained mystery told for kids, not scary; accurate facts only"},
    "custom": {"label": "Custom", "music": "mystery", "transition": "fade",
               "brief": "a gripping short narrated story on the topic", "kidsBrief": "a gripping short story for kids on the topic"},
}
ART_STYLES = {
    "creepy_comic": "dark horror comic book illustration, heavy ink lines, muted greens and sickly yellows, dramatic shadows",
    "modern_cartoon": "modern 2D cartoon illustration, clean bold outlines, flat vibrant colors, expressive characters",
    "storybook": "classic animated storybook film style, warm painterly colors, soft lighting, charming characters",
    "dark_realism": "cinematic dark realistic digital painting, moody low-key lighting, film grain",
    "watercolor": "soft watercolor illustration, textured paper, gentle washes of color",
    "epic_painting": "epic classical oil painting, dramatic golden light, grand composition, detailed",
}
LANGUAGES = {"en": "English", "hi": "Hindi", "es": "Spanish", "pt": "Portuguese", "fr": "French", "de": "German"}
SETTINGS = ["forest", "house", "village", "castle", "temple", "ruins", "sea", "city", "desert", "mountains", "cave",
            "road", "battlefield", "room"]
FIGURES = ["none", "person", "hooded", "child", "soldier", "king", "creature", "crowd", "wolf"]
TIMES = ["night", "dusk", "day", "dawn", "storm"]
MOODS = ["eerie", "epic", "calm", "tense", "sad", "wonder"]
MOTIONS = ["zoom_in", "zoom_out", "pan_left", "pan_right", "pan_up", "pan_down"]
FADE = 0.35
DEFAULT_SERIES = {"niche": "scary", "style": "creepy_comic", "captions": "bold_stroke", "narrator": "john",
                  "language": "en", "music": None}


def normalize_series(series):
    s = {**DEFAULT_SERIES, **(series or {})}
    if s["niche"] not in NICHES:
        s["niche"] = "custom"
    if s["style"] not in ART_STYLES:
        s["style"] = "storybook"
    if s["captions"] not in captions.STYLES:
        s["captions"] = "bold_stroke"
    if s["narrator"] not in tts.NARRATORS:
        s["narrator"] = "john"
    if s["language"] not in LANGUAGES:
        s["language"] = "en"
    if s.get("music") not in audio.STORY_MUSIC:
        s["music"] = NICHES[s["niche"]]["music"]
    return s


def build_prompt(topic, series=None, avoid_titles=(), recent=(), notes="", target_seconds=50, kids=False,
                 reference=None):
    s = normalize_series(series)
    niche = NICHES[s["niche"]]
    target = min(90, max(25, int(target_seconds or 50)))
    words = round(target * 2.55)
    scenes = f"{max(5, round(target / 7))}-{max(6, round(target / 5))}"
    editor = (notes or "").strip()
    lang = LANGUAGES[s["language"]]
    recent_rule = f"\n- Be clearly different from our recent videos: {json.dumps(list(recent)[:15])}" if recent else ""
    ref = f"\nInspiration channel: niche \"{reference['niche']}\", tone \"{reference.get('tone', '')}\" — match the energy, never copy." \
        if reference and reference.get("niche") else ""
    editor_block = f"\n\nEDITOR NOTES — follow these closely; they override everything above except the JSON format:\n{editor}" \
        if editor else ""
    native = f" Write natural, spoken {lang} (not a literal translation)." if s["language"] != "en" else ""
    return f"""You write viral faceless YouTube Shorts: {niche['kidsBrief'] if kids else niche['brief']}. One narrator tells it over illustrated scenes; captions appear word by word.
Return ONLY valid JSON:
{{
  "title": "curiosity-driven YouTube title, max 60 characters, may end with one emoji",
  "character": "one fixed visual description of the main character (age, build, hair, clothing) reused in every image prompt, or empty if none",
  "scenes": [
    {{ "narration": "what the narrator says during this scene (10-24 words)",
      "image_prompt": "concrete visual description of this scene for an illustrator: subject, action, setting, lighting, camera angle. Include the character description when they appear. No text in the image.",
      "setting": "{'|'.join(SETTINGS)}", "figure": "{'|'.join(FIGURES)}", "time": "{'|'.join(TIMES)}", "mood": "{'|'.join(MOODS)}" }}
  ],
  "tags": ["5-8 lowercase tags"],
  "description": "one or two sentences for the YouTube description"
}}
Rules:
- Narration language: {lang}.{native}
- {scenes} scenes, about {words} words of narration in total (≈{target} seconds spoken).
- Scene 1 narration is the HOOK: one punchy sentence under 14 words that creates instant curiosity or dread (e.g. a shocking claim or a question). No greetings, no "in this video".
- Build tension scene by scene; short sentences; vivid sensory detail; present the story, never describe the video.
- The last scene lands a twist, a chilling line or a satisfying payoff in one sentence. No call to action.
- "setting/figure/time/mood" must use the allowed words; they are a backup illustration if image generation fails.
- Image prompts must stay consistent: same character look, same era and place across scenes.
- {'MADE FOR KIDS: gentle, no gore, no death described graphically, nothing truly frightening; simple words.' if kids else 'No gore or graphic violence; keep it advertiser-friendly.'}
- ORIGINAL: do not retell stories that went viral from other channels. Do NOT reuse or paraphrase: {json.dumps(list(avoid_titles)[:30])}{recent_rule}{ref}
Topic: {topic or f"pick a fresh, gripping {niche['label'].lower()} subject"}{editor_block}"""


def _pick(value, allowed, default):
    v = str(value or "").strip().lower()
    return v if v in allowed else default


def normalize_story(raw):
    scenes = []
    for i, sc in enumerate((raw.get("scenes") or [])[:16]):
        narration = " ".join(str(sc.get("narration", "")).split())
        if not narration and not sc.get("image_prompt"):
            continue
        scenes.append({
            "narration": narration,
            "image_prompt": str(sc.get("image_prompt", "")).strip()[:700],
            "setting": _pick(sc.get("setting"), SETTINGS, "forest"),
            "figure": _pick(sc.get("figure"), FIGURES, "none"),
            "time": _pick(sc.get("time"), TIMES, "night"),
            "mood": _pick(sc.get("mood"), MOODS, "tense"),
            "motion": MOTIONS[i % len(MOTIONS)],
        })
    if sum(1 for s in scenes if s["narration"]) < 3:
        raise ValueError("story needs at least 3 narrated scenes")
    title = str(raw.get("title", "")).strip()[:100]
    if not title:
        raise ValueError("story has no title")
    tags = [str(t).lower().strip()[:30] for t in (raw.get("tags") or []) if str(t).strip()][:8]
    return {"format": "story", "title": title, "character": str(raw.get("character", "")).strip()[:300],
            "scenes": scenes, "tags": tags, "description": str(raw.get("description", "")).strip()[:500]}


def write_story(topic, series=None, **kw):
    prompt = build_prompt(topic, series, **kw)
    story = ai.generate_json(prompt, normalize_story, temperature=0.85)
    story["series"] = normalize_series(series)
    story["topic"] = topic
    return story


# images
def _cover(img):
    """Scale and crop to 2160x3840 so the Ken Burns zooms stay sharp."""
    img = img.convert("RGB")
    k = max(2160 / img.width, 3840 / img.height)
    img = img.resize((max(2160, round(img.width * k)), max(3840, round(img.height * k))), Image.LANCZOS)
    left, top = (img.width - 2160) // 2, (img.height - 3840) // 2
    return img.crop((left, top, left + 2160, top + 3840))


def _pollinations(prompt, seed):
    url = (f"https://image.pollinations.ai/prompt/{urllib.parse.quote(prompt[:900])}"
           f"?width=1080&height=1920&seed={seed}&nologo=true&model={config.POLLINATIONS_MODEL}")
    r = requests.get(url, timeout=config.STORY_IMAGE_TIMEOUT_S)
    r.raise_for_status()
    if not r.headers.get("content-type", "").startswith("image/") or len(r.content) < 20_000:
        raise ValueError("Pollinations returned no usable image")
    return Image.open(io.BytesIO(r.content))


def _gemini_image(prompt):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{config.GEMINI_IMAGE_MODEL}:generateContent"
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": "9:16"}}}
    r = requests.post(url, json=body, timeout=config.STORY_IMAGE_TIMEOUT_S,
                      headers={"x-goog-api-key": config.GEMINI_API_KEY})
    r.raise_for_status()
    for part in r.json()["candidates"][0]["content"]["parts"]:
        if "inlineData" in part:
            return Image.open(io.BytesIO(base64.b64decode(part["inlineData"]["data"])))
    raise ValueError("Gemini returned no image")


def image_prompt(story, scene):
    style = ART_STYLES[story["series"]["style"]]
    char = f" Main character: {story['character']}." if story.get("character") else ""
    return (f"{scene['image_prompt'] or scene['narration']}.{char} Style: {style}. Vertical 9:16 composition, "
            "subject centered, no text, no letters, no watermark, no logo.")


def scene_images(story, source=None):
    """Return (list of 2160x3840 jpg paths, used_ai). Unchanged scenes come from the cache."""
    source = source or config.STORY_IMAGES
    if source == "auto":
        source = "pollinations"
    if source == "gemini" and not config.GEMINI_API_KEY:
        source = "builtin"
    cache = config.DATA / "story" / "images"
    paths, failures, used_ai = [], 0, False
    for i, sc in enumerate(story["scenes"]):
        prompt = image_prompt(story, sc)
        seed = int(hashlib.sha256(f"{story['title']}|{i}".encode()).hexdigest()[:8], 16)
        if source != "builtin" and failures < 2:
            key = hashlib.sha256(f"{source}|{prompt}|{seed}".encode()).hexdigest()[:24]
            path = cache / f"{key}.jpg"
            if path.exists():
                paths.append(path)
                used_ai = True
                continue
            try:
                img = _pollinations(prompt, seed) if source == "pollinations" else _gemini_image(prompt)
                _cover(img).save(path, quality=90)
                paths.append(path)
                used_ai = True
                continue
            except Exception as e:
                failures += 1
                log.warning("AI image failed for scene %d (%s); using the built-in illustrator", i + 1, e)
        bkey = hashlib.sha256(json.dumps([sc["setting"], sc["figure"], sc["time"], sc["mood"],
                                          story["series"]["style"], story["title"], i]).encode()).hexdigest()[:24]
        path = cache / f"builtin_{bkey}.jpg"
        if not path.exists():
            _cover(illustrator.render(sc, story["series"]["style"], seed=f"{story['title']}|{i}")).save(path, quality=90)
        paths.append(path)
    return paths, used_ai


# timing + render
def plan_timing(story, voices):
    """Scene durations from voice length (+0.45 s, first +0.35 s) or reading speed when unvoiced."""
    t, timing = 0.0, []
    for i, (sc, v) in enumerate(zip(story["scenes"], voices)):
        if v is not None and len(v):
            vlen = len(v) / audio.SR
            dur = vlen + (0.35 if i == 0 else 0.45) + 0.15
        else:
            words = len(sc["narration"].split())
            vlen = None
            dur = max(2.2, words / 2.5 + 0.5)
        speak_start = t + 0.15
        speak_end = speak_start + (vlen if vlen else max(0.8, dur - 0.45))
        timing.append({"start": t, "dur": dur, "speak_start": speak_start, "speak_end": speak_end})
        t += dur
    return timing, t


def _zoompan(motion, frames):
    n = max(1, frames)
    centre_x, centre_y = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    return {
        "zoom_in": (f"1+0.14*on/{n}", centre_x, centre_y),
        "zoom_out": (f"1.14-0.14*on/{n}", centre_x, centre_y),
        "pan_left": ("1.12", f"(iw-iw/zoom)*(1-on/{n})", centre_y),
        "pan_right": ("1.12", f"(iw-iw/zoom)*(on/{n})", centre_y),
        "pan_up": ("1.12", centre_x, f"(ih-ih/zoom)*(1-on/{n})"),
        "pan_down": ("1.12", centre_x, f"(ih-ih/zoom)*(on/{n})"),
    }[motion]


def render(story, out_name, made_for_kids=False, image_source=None):
    """Render a story to data/videos/<out_name>.mp4. Returns paths, duration and credit text."""
    series = story["series"] = normalize_series(story.get("series"))
    niche = NICHES[series["niche"]]
    music = series["music"]
    temp = config.DATA / "temp" / out_name
    temp.mkdir(parents=True, exist_ok=True)

    voices, voice_credit = tts.narrate([s["narration"] for s in story["scenes"]], series["narrator"], music,
                                       series["language"], seed=story["title"])
    timing, total = plan_timing(story, voices)
    if total > config.STORY_MAX_SECONDS:
        log.warning("Story is %.1fs, above STORY_MAX_SECONDS=%s", total, config.STORY_MAX_SECONDS)
    images, used_ai = scene_images(story, image_source)

    cues = [("hit", 0.02)] if music in ("dark", "epic") else []
    cues += [("whoosh_soft", max(0, tm["start"] - 0.2)) for tm in timing[1:]]
    if len(timing) > 1:
        cues.append(("riser", max(0, timing[-1]["start"] - 1.6)))
    voice_tracks = [(v, tm["speak_start"]) for v, tm in zip(voices, timing) if v is not None]
    track = audio.render_soundtrack(total, music, cues, voice_tracks, seed=story["title"], music_gain=0.8)
    wav = temp / "soundtrack.wav"
    audio.write_wav(wav, track)

    ass = temp / "captions.ass"
    ass.write_text(captions.build_ass(
        [{"narration": s["narration"], "start": tm["speak_start"], "end": tm["speak_end"]}
         for s, tm in zip(story["scenes"], timing) if s["narration"]],
        series["captions"], series["language"]), encoding="utf-8")

    fps = config.STORY_FPS
    args, filters = ["ffmpeg", "-y", "-loglevel", "error"], []
    for i, (img, tm, sc) in enumerate(zip(images, timing, story["scenes"])):
        args += ["-i", str(img)]
        frames = round((tm["dur"] + (FADE if i < len(timing) - 1 else 0)) * fps)
        z, x, y = _zoompan(sc["motion"], frames)
        filters.append(f"[{i}:v]zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s=1080x1920:fps={fps},"
                       f"setsar=1,format=yuv420p[v{i}]")
    args += ["-i", str(wav)]
    prev = "v0"
    for i in range(1, len(images)):
        filters.append(f"[{prev}][v{i}]xfade=transition={niche['transition']}:duration={FADE}:"
                       f"offset={timing[i]['start']:.3f}[x{i}]")
        prev = f"x{i}"
    fonts = str(config.FONTS).replace(":", r"\:")
    filters.append(f"[{prev}]ass='{str(ass).replace(':', chr(92) + ':')}':fontsdir='{fonts}'[outv]")
    video = config.DATA / "videos" / f"{out_name}.mp4"
    args += ["-filter_complex", ";".join(filters), "-map", "[outv]", "-map", f"{len(images)}:a",
             "-c:v", "libx264", "-preset", config.STORY_X264_PRESET, "-crf", "21", "-pix_fmt", "yuv420p",
             "-r", str(fps), "-c:a", "aac", "-b:a", "160k", "-t", f"{total:.3f}", "-movflags", "+faststart",
             str(video)]
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {r.stderr[-1500:]}")
    thumb = config.DATA / "thumbnails" / f"{out_name}.jpg"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "1.2", "-i", str(video), "-frames:v", "1",
                    str(thumb)], check=False)
    credit = " ".join(c for c in (voice_credit, "Illustrations generated with Pollinations.ai." if used_ai and
                                  (image_source or config.STORY_IMAGES) in ("auto", "pollinations") else "") if c)
    return {"video_path": str(video), "thumb_path": str(thumb), "duration": round(total, 2), "credit": credit,
            "voiced_lines": sum(v is not None for v in voices)}
