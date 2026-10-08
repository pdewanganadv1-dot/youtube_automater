# YouTube Automater — notes for Claude

Self-running YouTube Shorts factory: Python package `ytauto/` + Streamlit dashboard `app.py`.
Full product spec (from the original Node "Lumen/AgentTube" app): `HANDOVER.md`. User-facing setup: `README.md`.

## Layout
- `ytauto/worker.py` — background loop: scheduler (`SHORTS_SCHEDULE`), uploads due videos, runs dashboard jobs (`jobs` table). All slow work happens here.
- `app.py` — Streamlit UI only; buttons enqueue jobs via `db.enqueue_job`.
- `ytauto/pipeline.py` — topic → `story.write_story` → `story.render` → review/auto-approve → `publish_schedule`.
- `ytauto/story.py` — narrated-story format (prompt is a verbatim port; keep it in sync with HANDOVER.md §3c).
- `ytauto/gags.py` — cartoon + zoo-window prompts (verbatim ports), validation, voice timing, sound cues.
  `animate.py` renders them frame by frame with skia: `cartoon_engine.py`, `window_engine.py`, helpers in `draw.py`.
- `ytauto/audio.py` (numpy synth + ducking mixer), `tts.py` (Piper/Gemini), `captions.py` (ASS styles), `illustrator.py` (fallback art), `youtube.py`, `reference.py`, `db.py` (SQLite in `data/`).

## Run locally (Mac)
```bash
brew install ffmpeg                      # if missing
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp -n .env.example .env                  # user adds GEMINI_API_KEY / YOUTUBE_API_KEY themselves
python scripts/fetch_fonts.py
./scripts/start.sh                       # worker + dashboard → http://localhost:8501
```
Optional: `./scripts/setup_voices.sh` (free Piper voices), `python scripts/connect_youtube.py` (one-time OAuth; needs `config/client_secret.json`).
Keep the Mac awake for 24/7 runs: `caffeinate -i ./scripts/start.sh`.

## Rules
- Never commit or print `.env`, `config/` (OAuth client + tokens) or `data/`.
- Never ask the user to paste API keys into chat; they edit `.env` themselves.
- Tests: `pytest -q`; `RENDER=1 pytest -q` adds a real MP4 render.
- Don't kill processes with `pkill -f` patterns that can match your own shell.

## Not built yet (next work)
- Zoo window's ground line sits at y=1640 (spec said 1830) so glass animals aren't hidden by visitors.
- "Improve from a reference video" flow, per-queue-item format/series, Agents Office.
