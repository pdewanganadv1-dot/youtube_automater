"""Cartoon gags and Zoo window formats: prompts, validation, timing, voices and sound cues.

Ports CartoonShortService (HANDOVER.md §3a, §3b and the prompt appendix). Drawing lives in
cartoon_engine.py and window_engine.py.
"""
import json
import logging

from . import ai, audio

log = logging.getLogger(__name__)

VOCAB = {
    "frame": ["wide", "medium", "closeup", "extreme"],
    "focus": ["hero", "other", "prop", "both"],
    "mood": ["neutral", "smile", "grin", "smug", "angry", "shock", "twitch", "sad", "cry", "dead"],
    "action": ["idle", "walk_in", "walk_out", "run_away", "jump", "shake", "scream", "fall", "faint", "spin",
               "stretch_up", "explode", "wave", "point", "shrink", "grow", "dance", "cry"],
    "prop": ["none", "kiosk", "tv", "computer", "phone", "sign", "door", "fridge", "car", "box", "bed", "table"],
    "item": ["none", "phone", "chips", "cup", "book", "key", "food"],
    "species": ["human", "cat", "dog", "bunny", "bear"],
    "voice": ["kid", "girl", "boy", "man", "woman", "grandpa", "grandma", "robot", "squeaky"],
    "sfx": ["none", "boing", "pop", "slide_up", "slide_down", "wahwah", "honk", "ding", "sparkle", "tada",
            "drumroll", "crash", "thud", "boom", "whoosh", "rumble", "sting", "giggle", "beep", "error", "tick",
            "printer"],
    "music": ["kids", "upbeat", "soothing", "silly", "none"],
}
ENDINGS = ["stretch_up", "explode", "faint", "run_away", "spin", "shrink", "grow", "fall", "dance"]
ACTION_SFX = {"jump": "boing", "explode": "boom", "fall": "slide_down", "faint": "wahwah", "scream": "sting",
              "shake": "rumble", "stretch_up": "slide_up", "run_away": "whoosh", "walk_in": "whoosh",
              "spin": "slide_up", "shrink": "slide_down", "grow": "slide_up", "cry": "wahwah", "dance": "tada"}

# "Zoo window" format: one hand-held shot through enclosure glass, an animal family + visitors reacting.
WINDOW = {
    "species": ["bear", "lion", "panda", "tiger", "polar"],
    "spot": ["glass", "near", "middle", "back", "rock", "offscreen"],
    "side": ["left", "center", "right"],
    "action": ["idle", "sit", "lie", "sleep", "look", "walk", "run", "walk_in", "paws_up", "boop", "wave_paw", "roll",
               "pounce", "nudge", "groom", "yawn", "roar", "tumble", "peek"],
    "visitors": ["calm", "excited", "laugh", "aww", "gasp", "point"],
    "camera": ["wide", "follow", "close"],
    "sfx": ["none", "glass_tap", "thump", "growl", "roar_soft", "cub_squeak", "crowd_laugh", "crowd_aww",
            "crowd_gasp", "camera_click", "pop", "boing", "sparkle"],
}
WINDOW_SPEAKERS = ["visitor", "kid", "dad_visitor"]
WINDOW_VOICE_DEFAULT = {"visitor": "woman", "kid": "kid", "dad_visitor": "man"}
ANIMALS = ["dad", "mom", "cub"]
NEEDS_TARGET = {"nudge", "groom", "pounce"}
CUB_ACTIVE = {"run", "walk_in", "paws_up", "boop", "wave_paw", "roll", "pounce", "tumble", "peek"}
WINDOW_SFX = {"paws_up": [("thump", 0), ("glass_tap", 0.45)], "boop": [("glass_tap", 0)],
              "pounce": [("whoosh", 0), ("thump", 0.3)], "nudge": [("growl", 0)], "roar": [("roar_soft", 0)],
              "yawn": [("yawn", 0)], "tumble": [("whoosh_soft", 0)]}
VISITOR_SFX = {"laugh": "crowd_laugh", "aww": "crowd_aww", "gasp": "crowd_gasp"}


def clamp_target(seconds):
    return max(12, min(60, int(seconds or 22)))


def _pick(v, allowed, default):
    v = str(v or "").strip().lower()
    return v if v in allowed else default


def _editor(notes, json_only=" and allowed values"):
    editor = (notes or "").strip()
    return (f"\n\nEDITOR NOTES — follow these closely; they override everything above except the JSON format"
            f"{json_only}:\n{editor}") if editor else ""


# ---------- cartoon gags ----------
def build_cartoon_prompt(topic, reference=None, avoid_titles=(), market="United States", notes="", target_seconds=22,
                         kids=False, recent=()):
    ref = reference or {}
    target = clamp_target(target_seconds)
    long = target >= 35
    shots = f"{round(target / 2.6)}-{round(target / 2)}" if long else \
        f"{max(6, round(target / 2.4))}-{round(target / 1.6)}"
    ideas = (ref.get("topicGaps") or [])[:6]
    words = 10 if long else 7
    kids_caption = "short fun title for the story (max 45 characters, no emoji)"
    adult_caption = "When you ... (relatable everyday situation, max 45 characters, no emoji)"
    story_rule = ("Tell a tiny story with a beginning (setup), a middle (3 escalating attempts/problems — the rule of "
                  "three) and an end (a surprising, absurd payoff). Use a running gag." if long else
                  "Structure: wide setup, the trigger, 2-4 escalating reactions, things get worse or others react, "
                  "then an ABSURD exaggerated payoff.")
    kids_rule = ('- MADE FOR KIDS (ages 4-10): gentle, positive, silly humor; no insults, no scary or violent moments, '
                 'no romance, no gross-out beyond mild silliness, no brands; simple words; characters are kind in the '
                 'end. Prefer "kids" or "soothing" music and kid/girl/boy/squeaky voices.' if kids else
                 '- Keep it clean (no profanity, no violence against real people, no brands or real people).')
    recent_rule = f"\n- Be clearly different from our recent videos: {json.dumps(list(recent)[:15])}" if recent else ""
    gaps = f", topic ideas they have not covered: {json.dumps(ideas)}" if ideas else ""
    return f"""You write funny {'KIDS ' if kids else ''}cartoon Shorts for YouTube: crude, charming 2D characters on cream paper, one handwritten caption at the top, fast cuts, music, cartoon sound effects and short spoken dialogue (each speech bubble is voiced).
Return ONLY valid JSON:
{{
  "caption": "{kids_caption if kids else adult_caption}",
  "title": "catchy YouTube title, max 60 characters, may end with one emoji",
  "cast": {{ "hero": {{ "species": "human|cat|dog|bunny|bear", "look": "round|tall", "voice": "kid|girl|boy|man|woman|grandpa|grandma|robot|squeaky" }}, "other": {{ "species": "...", "look": "round|tall", "voice": "..." }} }},
  "shots": [
    {{ "dur": 2.0, "frame": "wide|medium|closeup|extreme", "focus": "hero|other|prop|both",
      "hero": {{ "mood": "...", "action": "...", "item": "..." }},
      "other": {{ "present": false, "mood": "...", "action": "..." }},
      "prop": {{ "kind": "...", "text": "TEXT ON ITS SCREEN/SIGN (max 40 chars)", "flash": false }},
      "speech": {{ "who": "hero|other", "text": "spoken line, max {words} words" }},
      "crowd": false, "sfx": "..." }}
  ],
  "music": "kids|upbeat|soothing|silly|none",
  "tags": ["5-8 lowercase tags"],
  "description": "one or two fun sentences"
}}
Allowed values ONLY:
mood: {', '.join(VOCAB['mood'])}
action: {', '.join(VOCAB['action'])}
prop.kind: {', '.join(VOCAB['prop'])}
item (hand-held): {', '.join(VOCAB['item'])}
sfx: {', '.join(VOCAB['sfx'])}
voice: {', '.join(VOCAB['voice'])}
species: {', '.join(VOCAB['species'])} (animal characters are great for kids and for topics about animals)
Rules:
- {shots} shots, each 1.2-3.5 seconds, total about {target} seconds (never more than 60).
- {story_rule}
- The final shot's hero action must be one of: {', '.join(ENDINGS)}.
- Use dialogue: about half of the shots have a short spoken line (max {words} words). Lines must be funny or charming on their own and fit the character's voice. SHOW the story — never narrate it, never label beats ("Attempt one:", "Step two:"), no lecturing or morals spelled out.
- Use the topic exactly as given — same characters and situation.
- Pick sound effects that land the jokes (boing for jumps, slide_up/slide_down for surprises, wahwah for fails, tada/sparkle for wins, drumroll before a reveal, honk/pop for silly beats).
- Keep the same prop through the gag when it is the source of the joke. Close-ups of a prop screen use "focus": "prop".
{kids_rule}
- Make it ORIGINAL: take inspiration from the channel style below but never copy its characters, jokes or titles. Do NOT reuse or paraphrase: {json.dumps(list(avoid_titles)[:30])}{recent_rule}
Inspiration channel style: niche "{ref.get('niche') or 'everyday-life humor'}", audience "{ref.get('audience') or ('kids and families' if kids else 'teens and young adults')}", tone "{ref.get('tone') or 'silly, energetic'}", pacing "{ref.get('pacing') or 'fast'}"{gaps}.
Audience market: {market} (American English).
Topic for this video: {topic or 'pick a fresh, funny everyday situation'}{_editor(notes)}"""


def _scale_durations(durs, target, lo, hi, cap):
    total = sum(durs)
    if total <= 0:
        return durs
    goal = min(cap, max(target * 0.75, min(target * 1.25, total)))
    k = goal / total
    return [max(lo, min(hi, d * k)) for d in durs]


def normalize_cartoon(raw, target_seconds=22):
    target = clamp_target(target_seconds)
    cap_chars = 90 if target >= 35 else 60
    cast = raw.get("cast") or {}
    out_cast = {}
    for role, dv in (("hero", "boy"), ("other", "girl")):
        c = cast.get(role) or {}
        out_cast[role] = {"species": _pick(c.get("species"), VOCAB["species"], "human"),
                          "look": _pick(c.get("look"), ["round", "tall"], "round" if role == "hero" else "tall"),
                          "voice": _pick(c.get("voice"), VOCAB["voice"], dv)}
    shots = []
    for sh in (raw.get("shots") or [])[:30]:
        h, o, p, sp = sh.get("hero") or {}, sh.get("other") or {}, sh.get("prop") or {}, sh.get("speech") or {}
        text = " ".join(str(sp.get("text") or "").split())[:cap_chars]
        shots.append({
            "dur": max(0.9, min(3.5, float(sh.get("dur") or 2))),
            "frame": _pick(sh.get("frame"), VOCAB["frame"], "wide"),
            "focus": _pick(sh.get("focus"), VOCAB["focus"], "hero"),
            "hero": {"mood": _pick(h.get("mood"), VOCAB["mood"], "neutral"),
                     "action": _pick(h.get("action"), VOCAB["action"], "idle"),
                     "item": _pick(h.get("item"), VOCAB["item"], "none")},
            "other": {"present": bool(o.get("present")), "mood": _pick(o.get("mood"), VOCAB["mood"], "neutral"),
                      "action": _pick(o.get("action"), VOCAB["action"], "idle")},
            "prop": {"kind": _pick(p.get("kind"), VOCAB["prop"], "none"),
                     "text": str(p.get("text") or "").upper().strip()[:48], "flash": bool(p.get("flash"))},
            "speech": {"who": _pick(sp.get("who"), ["hero", "other"], "hero"), "text": text} if text else None,
            "crowd": bool(sh.get("crowd")),
            "sfx": _pick(sh.get("sfx"), VOCAB["sfx"], "none"),
        })
    if len(shots) < 5:
        raise ValueError("cartoon needs at least 5 shots")
    for sh in shots:  # a speaker must be on screen-capable: "other" speaking means other is present
        if sh["speech"] and sh["speech"]["who"] == "other":
            sh["other"]["present"] = True
    durs = _scale_durations([s["dur"] for s in shots], target, 0.9, 3.5, 60)
    for sh, d in zip(shots, durs):
        sh["dur"] = round(d, 2)
    shots[-1]["dur"] = max(2.6, shots[-1]["dur"])
    if shots[-1]["hero"]["action"] not in ENDINGS:
        shots[-1]["hero"]["action"] = "stretch_up"
    caption = str(raw.get("caption") or "").strip()[:45]
    title = str(raw.get("title") or caption).strip()[:100]
    if not title:
        raise ValueError("cartoon has no title")
    return {"format": "cartoon", "caption": caption, "title": title, "cast": out_cast, "shots": shots,
            "music": _pick(raw.get("music"), VOCAB["music"], "upbeat"),
            "tags": [str(t).lower().strip()[:30] for t in (raw.get("tags") or [])][:8],
            "description": str(raw.get("description") or "").strip()[:500], "voices": True}


# ---------- zoo window ----------
def build_window_prompt(topic, reference=None, avoid_titles=(), market="United States", notes="", target_seconds=18,
                        kids=False, recent=()):
    ref = reference or {}
    target = min(45, clamp_target(target_seconds))
    beats = f"{max(5, round(target / 2.8))}-{max(6, round(target / 2))}"
    recent_rule = f"\n- Be clearly different from our recent videos: {json.dumps(list(recent)[:15])}" if recent else ""
    return f"""You write {'KIDS ' if kids else ''}YouTube Shorts in the viral "zoo window" style: ONE continuous hand-held phone shot through the glass of an animal enclosure. An animal family — "dad", "mom" and "cub" — acts out a tiny, wholesome drama right at the glass while visitors on our side (a woman = "visitor", a child = "kid", optionally a man = "dad_visitor") react out loud. The humour comes from the animals behaving like a human family (the cub showing off, dad stealing the spotlight, mom restoring order). Visitors' spoken reactions are shown as captions.
Return ONLY valid JSON:
{{
  "caption": "on-screen hook at the top (max 45 characters, no emoji), e.g. what the cub wanted",
  "title": "catchy YouTube title, max 60 characters, may end with one emoji",
  "animal": "{'|'.join(WINDOW['species'])}",
  "cast": {{ "dad": {{"present": true}}, "mom": {{"present": true}}, "cub": {{"present": true}}, "visitor": {{"voice": "woman"}}, "kid": {{"voice": "kid|girl|boy"}} }},
  "shots": [
    {{ "dur": 2.2, "camera": "wide|follow|close", "focus": "dad|mom|cub",
      "dad": {{ "spot": "...", "side": "left|center|right", "action": "...", "target": "mom|cub" }},
      "mom": {{ ... }}, "cub": {{ ... }},
      "visitors": {{ "mood": "..." }},
      "speech": {{ "who": "visitor|kid|dad_visitor", "text": "spoken reaction, max 8 words" }},
      "sfx": "..." }}
  ],
  "tags": ["5-8 lowercase tags"],
  "description": "one or two fun sentences"
}}
Allowed values ONLY:
animal: {', '.join(WINDOW['species'])}
spot: {', '.join(WINDOW['spot'])} ("glass" = pressed right against the window in front of the visitors; "rock" = hiding behind the boulder)
action: {', '.join(WINDOW['action'])} (paws_up = stands up with both paws on the glass; boop = presses its nose on the glass; peek = pops up from behind the rock; nudge/groom/pounce need a "target")
visitors.mood: {', '.join(WINDOW['visitors'])}
camera: {', '.join(WINDOW['camera'])} (follow/close need "focus")
sfx: {', '.join(WINDOW['sfx'])}
Rules:
- {beats} beats, each 1.8-3.2 seconds, total about {target} seconds. It is ONE continuous shot, so animals move between spots; only list an animal in a beat when it does something new (otherwise it keeps doing what it was doing).
- Story: setup (cub at the glass delights the visitors) → a twist (another family member gets involved, e.g. copies or steals the moment) → escalation → a sweet or funny payoff (mom/dad settles it, the family together at the glass).
- About 2 of every 3 beats have one short spoken reaction from a visitor — natural, the way people really talk at a zoo ("Oh my gosh!", "He's waving at you!"). Never narrate what the animals think; never label beats.
- Animals never talk.
- {'MADE FOR KIDS: gentle and wholesome, no fighting or scary moments (a nudge or a playful pounce is fine), simple words.' if kids else 'Wholesome and family friendly.'}
- ORIGINAL: do not copy existing videos' stories or titles. Do NOT reuse: {json.dumps(list(avoid_titles)[:30])}{recent_rule}
Inspiration channel style: niche "{ref.get('niche') or 'funny animal moments'}", tone "{ref.get('tone') or 'wholesome, funny'}".
Audience market: {market} (American English).
Topic for this video: {topic or 'pick a fresh, funny animal-family moment at the zoo glass'}{_editor(notes)}"""


def normalize_window(raw, target_seconds=18):
    target = min(45, clamp_target(target_seconds))
    cast = raw.get("cast") or {}
    present = {a: (cast.get(a) or {}).get("present", True) is not False for a in ANIMALS}
    if not any(present.values()):
        present["cub"] = True
    voices = {"visitor": _pick((cast.get("visitor") or {}).get("voice"), tts_voices(), "woman"),
              "kid": _pick((cast.get("kid") or {}).get("voice"), ["kid", "girl", "boy"], "kid"),
              "dad_visitor": _pick((cast.get("dad_visitor") or {}).get("voice"), tts_voices(), "man")}
    shots = []
    for sh in (raw.get("shots") or [])[:20]:
        beat = {"dur": max(1.2, min(3.5, float(sh.get("dur") or 2.2))),
                "camera": _pick(sh.get("camera"), WINDOW["camera"], "wide"),
                "focus": _pick(sh.get("focus"), ANIMALS, "cub"),
                "visitors": {"mood": _pick((sh.get("visitors") or {}).get("mood"), WINDOW["visitors"], "calm")},
                "sfx": _pick(sh.get("sfx"), WINDOW["sfx"], "none")}
        for a in ANIMALS:
            spec = sh.get(a)
            if not isinstance(spec, dict) or not present[a]:
                continue
            st = {}
            if spec.get("spot"):
                st["spot"] = _pick(spec["spot"], WINDOW["spot"], "middle")
            if spec.get("side"):
                st["side"] = _pick(spec["side"], WINDOW["side"], "center")
            if spec.get("action"):
                st["action"] = _pick(spec["action"], WINDOW["action"], "idle")
            if st.get("action") in NEEDS_TARGET:
                tgt = _pick(spec.get("target"), ANIMALS, "")
                if not tgt or tgt == a or not present.get(tgt):
                    st["action"] = "idle"
                else:
                    st["target"] = tgt
            if st:
                beat[a] = st
        sp = sh.get("speech") or {}
        text = " ".join(str(sp.get("text") or "").split())[:70]
        beat["speech"] = {"who": _pick(sp.get("who"), WINDOW_SPEAKERS, "visitor"), "text": text} if text else None
        shots.append(beat)
    if len(shots) < 4:
        raise ValueError("zoo window needs at least 4 beats")
    durs = _scale_durations([s["dur"] for s in shots], target, 1.2, 3.5, 45)
    for sh, d in zip(shots, durs):
        sh["dur"] = round(d, 2)
    shots[-1]["dur"] = max(2.6, shots[-1]["dur"])
    caption = str(raw.get("caption") or "").strip()[:45]
    title = str(raw.get("title") or caption).strip()[:100]
    if not title:
        raise ValueError("zoo window has no title")
    return {"format": "window", "caption": caption, "title": title,
            "animal": _pick(raw.get("animal"), WINDOW["species"], "bear"), "present": present,
            "visitor_voices": voices, "shots": shots, "music": "soothing",
            "tags": [str(t).lower().strip()[:30] for t in (raw.get("tags") or [])][:8],
            "description": str(raw.get("description") or "").strip()[:500], "voices": True}


def tts_voices():
    return VOCAB["voice"]


def write_gag(fmt, topic, target_seconds=22, **kw):
    builder, norm = (build_window_prompt, normalize_window) if fmt == "window" else \
        (build_cartoon_prompt, normalize_cartoon)
    prompt = builder(topic, target_seconds=target_seconds, **kw)
    gag = ai.generate_json(prompt, lambda raw: norm(raw, target_seconds), temperature=0.9)
    gag["topic"] = topic
    gag["target_seconds"] = target_seconds
    return gag


def normalize(gag):
    """Re-validate an edited gag (dashboard editor)."""
    t = gag.get("target_seconds", 22)
    out = normalize_window(gag, t) if gag.get("format") == "window" else normalize_cartoon(gag, t)
    if gag.get("format") == "window":  # keep the editor's choices that the raw schema stores differently
        out["animal"] = _pick(gag.get("animal"), WINDOW["species"], out["animal"])
        out["present"] = gag.get("present") or out["present"]
        out["visitor_voices"] = {**out["visitor_voices"], **(gag.get("visitor_voices") or {})}
    out["voices"] = gag.get("voices", True)
    out["music"] = gag.get("music", out["music"])
    out["topic"], out["target_seconds"] = gag.get("topic"), t
    return out


# ---------- voices, timing, soundtrack ----------
def speech_lines(gag):
    """[(shot index, text, voice, mood, role)] for every voiced line."""
    lines = []
    for i, sh in enumerate(gag["shots"]):
        sp = sh.get("speech")
        if not sp or not sp.get("text"):
            continue
        if gag["format"] == "window":
            who = sp["who"]
            voice = gag.get("visitor_voices", {}).get(who) or WINDOW_VOICE_DEFAULT[who]
            mood = sh["visitors"]["mood"]
        else:
            who = sp["who"]
            voice = gag["cast"][who]["voice"]
            mood = sh[who]["mood"]
        lines.append((i, sp["text"], voice, mood, who))
    return lines


def fit_shots_to_voices(gag, voices_by_shot, cap=60):
    """Shot duration = max(dur, voice + 0.55 s); total capped by shrinking silent shots."""
    durs = []
    for i, sh in enumerate(gag["shots"]):
        v = voices_by_shot.get(i)
        durs.append(max(sh["dur"], len(v) / audio.SR + 0.55) if v is not None else sh["dur"])
    over = sum(durs) - cap
    if over > 0:
        silent = [i for i in range(len(durs)) if i not in voices_by_shot]
        room = sum(durs[i] - 0.9 for i in silent)
        if room > 0:
            k = min(1.0, over / room)
            for i in silent:
                durs[i] -= (durs[i] - 0.9) * k
    return durs


def cues_for(gag, starts, durs, voiced):
    cues = []
    for i, sh in enumerate(gag["shots"]):
        t0 = starts[i]
        if i > 0:
            cues.append(("whoosh_soft", max(0, t0 - 0.05)))
        if gag["format"] == "window":
            for a in ANIMALS:
                act = (sh.get(a) or {}).get("action")
                for name, off in WINDOW_SFX.get(act, []):
                    cues.append((name, t0 + 0.2 + off))
                if a == "cub" and act in CUB_ACTIVE:
                    cues.append(("cub_squeak", t0 + 0.35))
            vs = VISITOR_SFX.get(sh["visitors"]["mood"])
            if vs:
                cues.append((vs, t0 + 0.4))
        else:
            act = sh["hero"]["action"]
            if act in ACTION_SFX:
                cues.append((ACTION_SFX[act], t0 + (0.5 * durs[i] if act == "explode" else 0.15)))
            if sh["other"]["present"] and sh["other"]["action"] in ACTION_SFX:
                cues.append((ACTION_SFX[sh["other"]["action"]], t0 + 0.25))
            if sh.get("speech") and not voiced:
                cues.append(("pop", t0 + 0.1))
        if sh.get("sfx") and sh["sfx"] != "none":
            cues.append((sh["sfx"], t0 + 0.3))
    return cues
