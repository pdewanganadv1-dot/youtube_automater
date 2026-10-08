"""Render a cartoon or zoo-window gag to MP4: voices -> timing -> soundtrack -> frames -> ffmpeg."""
import logging

from . import audio, config, draw, gags, tts

log = logging.getLogger(__name__)
FPS = config.env_int("CARTOON_FPS", 24)


def render(gag, out_name):
    fmt = gag["format"]
    if fmt == "window":
        from . import window_engine as engine
    else:
        from . import cartoon_engine as engine
    temp = config.DATA / "temp" / out_name
    temp.mkdir(parents=True, exist_ok=True)

    lines = gags.speech_lines(gag) if gag.get("voices", True) else []
    samples, credit = tts.character_lines([(text, voice, mood, role) for _, text, voice, mood, role in lines],
                                          seed=gag.get("caption") or gag["title"])
    by_shot = {i: s for (i, *_), s in zip(lines, samples) if s is not None}
    durs = gags.fit_shots_to_voices(gag, by_shot, cap=45 if fmt == "window" else 60)
    starts, t = [], 0.0
    for d in durs:
        starts.append(t)
        t += d
    total = t
    cues = gags.cues_for(gag, starts, durs, voiced=bool(by_shot))
    voice_tracks = [(s, starts[i] + 0.25) for i, s in by_shot.items()]
    talk = {i: (starts[i] + 0.25, starts[i] + 0.25 + len(s) / audio.SR) for i, s in by_shot.items()}
    music = gag.get("music", "upbeat") if fmt == "cartoon" else "soothing"
    track = audio.render_soundtrack(total, music, cues, voice_tracks, seed=gag["title"],
                                    music_gain=0.35 if fmt == "window" else 0.8,
                                    amb="zoo" if fmt == "window" else None)
    wav = temp / "soundtrack.wav"
    audio.write_wav(wav, track)

    video = config.DATA / "videos" / f"{out_name}.mp4"
    frame = draw.Frame()
    state = engine.prepare(gag, starts, durs) if hasattr(engine, "prepare") else None
    paper = draw.paper_texture()
    enc = draw.Encoder(video, FPS, wav, total)
    n_frames = int(total * FPS)
    i = 0
    thumb_frame = int(n_frames * 0.4)
    try:
        for f in range(n_frames):
            tg = f / FPS
            while i + 1 < len(starts) and tg >= starts[i + 1]:
                i += 1
            lt = tg - starts[i]
            sp = gag["shots"][i].get("speech")
            talking = None
            if sp and i in talk and talk[i][0] <= tg <= talk[i][1]:
                talking = sp["who"]
            if fmt == "window":
                engine.render_frame(frame.canvas, gag, state, i, lt, tg, f, talking)
            else:
                engine.render_frame(frame.canvas, gag, gag["shots"][i], lt, durs[i], f, paper, talking)
            enc.write(frame.bytes())
            if f == thumb_frame:
                thumb = config.DATA / "thumbnails" / f"{out_name}.jpg"
                from PIL import Image
                Image.fromarray(frame.array[..., :3]).save(thumb, quality=90)
    finally:
        enc.close()
    return {"video_path": str(video), "thumb_path": str(config.DATA / "thumbnails" / f"{out_name}.jpg"),
            "duration": round(total, 2), "credit": credit, "voiced_lines": len(by_shot)}
