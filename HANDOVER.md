# Lumen YouTube Shorts automater — handover spec for the new repo `youtube_automater`

Source: the `reference-channel` branch of Piyush's fork of github.com/darkzOGx/youtube-automation-agent (the "Lumen/AgentTube" Node app). The latest cloud commit is 137b5da. The Mac copy at ~/Coding/youtube-automation-agent is at 993864a and does not yet have the narrated-story format. Nothing has been pushed anywhere, and no secret values appear in this document.

---

## 1. Purpose and goals (as the user stated them)

- He wants a self-running YouTube **Shorts** factory on his Mac. It runs continuously from a topic queue, auto-approves, and uploads on a schedule. It must also be easy to correct: edit lines and sounds, or regenerate with fine-tuning notes.
- **Reference channel:** he gives any YouTube channel, and the app learns its style and topic gaps and then makes **original** videos. It never copies the channel. The first reference was @ricoanimations0 (Rico Animations, funny animated Shorts). He explicitly rejected direct copying, and he especially wants original sounds.
- **Audience:** US English by default (`TARGET_AUDIENCE`). Kids mode is available; his first target was about 1-minute comic videos for kids.
- **Upload channel:** the connected YouTube channel is "Piyush dDewangan". Uploads are private while the Google OAuth app is unverified.
- **Posting cadence:** the scheduler makes one Short every 4 hours (`SHORTS_SCHEDULE=10 */4 * * *`). Publish slots are spaced at least `SHORTS_PUBLISH_GAP_HOURS=4` apart. Auto-creation pauses when 8 videos are waiting for review or publishing (`SHORTS_MAX_PENDING=8`).
- **Languages:** the narrated-story format supports en, hi, es, pt, fr and de. The cartoon and zoo-window formats are English only.
- **Not part of this project:** "Kadva Sach" (divyam.explains) is a reel he saved about an AI-engineer roadmap. No Kadva Sach channel or niche exists in this codebase. Treat it as a new requirement if he wants one.
- **Free tools preferred:** Gemini free tier for text, free local Piper voices, free Pollinations images, and synthesized music and sound effects (no stock audio). Paid providers may come later.
- He also wanted an "Agents Office" visual control room: agents at desks, a task board and a lead chat. It is built at `/office`.

## 2. Architecture

Node 18+ with Express on port 3456. The database is SQLite (`database/db.js`). Rendering uses Playwright (headless Chromium) and ffmpeg. Python is used only for Piper TTS.

### Pipeline: idea → upload

1. **Topic source.** Either the `shorts_queue` table (topics the user adds in the dashboard) or, when the queue is empty, the AI picks a topic using the reference-channel `topicGaps`.
2. **`schedules/daily-automation.js` → `runContinuousShorts({manual})`.** On the cron `SHORTS_SCHEDULE` (first run about 90 s after boot, `SHORTS_FIRST_RUN_DELAY_MS`) it:
   - skips if a generation job is running;
   - skips automatic (not manual) runs when the review-waiting count reaches `SHORTS_MAX_PENDING` (`COALESCE(content_reviews.status, productions.status) IN ('needs_review','needs_attention')`) or when the publish backlog reaches that maximum;
   - otherwise takes the next queued topic, marks it `started` with the `job_id`, and calls `generateContent({source:'scheduler', length:'shorts', topic})`.
3. **`index.js generateContent` / `startGenerationJob`** builds the strategy context:
   - `editorNotes` = the saved `cartoon_style_notes` setting plus per-job notes;
   - `requestedTopic` = the user's exact words, used verbatim because the strategist used to rewrite them;
   - `cartoonTargetSeconds`, `madeForKids`, `cartoonFormat` (`cartoon` | `window` | `story`) and `storySeries`;
   - `isShort` / `shortForm`;
   - `bestPublishTime = nextShortsPublishSlot()`, a gap-filling slot at least 20 minutes ahead and at least `SHORTS_PUBLISH_GAP_HOURS` from other slots.
4. **`agents/content-strategy-agent.js`** writes the strategy (title angle, audience, reference blueprint).
5. **`agents/script-writer-agent.js` → `generateCartoonScript(strategy)`.** When `strategy.isShort && CartoonShortService.enabled() && AI available`:
   - it calls `CartoonShortService.writeGag(...)`, or `StoryShortService.writeStory(...)` for the story format;
   - `recent` = captions of the last 25 `production_snapshots`, so new videos differ from recent ones.
   - The script becomes `{cartoon: gag, title, hook, sections[]}` with one section per shot or beat.
6. **`agents/seo-optimizer-agent.js`** writes the title, description and tags. **`agents/thumbnail-designer-agent.js`** handles thumbnails; cartoons use a frame grab instead.
7. **`agents/production-management-agent.js → processContent`.** When `script.cartoon` is set it calls `assembleCartoonShort`, which renders through the matching service. It then sets:
   - `assets.video` / `assets.audio` (soundtrack only, `voicedLines`, `voiceCredit`);
   - `assets.thumbnail` and `assets.finalVideo` (1080x1920).
8. **Review.**
   - Auto-approve is on when setting `approval_required='false'`.
   - Auto-approve sends the video straight to the `publish_schedule` table.
   - Otherwise the production waits as `needs_review`.
9. **`agents/publishing-scheduling-agent.js`** uploads at the slot through the YouTube Data API v3 `videos.insert` call. It:
   - sets `selfDeclaredMadeForKids: metadata.madeForKids === true`;
   - appends `voiceCredit` to the description (the CC BY attribution for Piper and the Pollinations credit);
   - forces privacy to private while the app is unverified.
10. **Learning loop.** These existed upstream and were not modified: analytics-optimization-agent, channel-learning-engine, growth-experiment-service, retention, engagement and discoverability services.
11. **Queue status.** Job completion or failure updates the `shorts_queue` status (`started` → `done`/`failed`).

### Modules added or changed in this fork

| Module | Role |
|---|---|
| `utils/reference-channel-service.js` | Analyzes a channel and stores a style profile in `channel_profiles`. Details in §5. |
| `utils/cartoon-short-service.js` | `CartoonShortService`. Formats `cartoon` and `window`: prompt building, normalization, voices (Piper/Gemini), render via Playwright, soundtrack and mux. |
| `utils/cartoon-engine.browser.js` | In-browser SVG engine for cartoon gags: `window.CARTOON = {load(gag)→{duration,cues}, renderFrame(t,fps)}`. |
| `utils/window-engine.browser.js` | In-browser SVG engine for the zoo-window format, same API. |
| `utils/story-short-service.js` | `StoryShortService`, the narrated story format. |
| `utils/story-scene.browser.js` | Built-in SVG illustrator used when AI images fail: `window.STORY_SCENE.render({setting,figure,time,mood,style,seed})`. |
| `utils/cartoon-audio.js` | Pure-JS synth: instruments, music beds, sound effects, zoo ambience, mixer with ducking, WAV writer, and the PCM→voice resampler. |
| `tools/piper_tts.py` | Piper TTS helper (JSON on stdin/stdout). Commands: `synth`, `calibrate`. |
| `utils/office-service.js`, `dashboard/office.html` | The "Agents Office" 3D room (three.js vendored): agents at desks, task board, lead chat, `POST /api/office/command`. |
| `utils/cron-next.js` | `nextCronTime(expr, from)`, used to show the next run. |
| `database/db.js` | Adds `shorts_queue` and its helpers `listShortsQueue`, `addShortsQueueItem`, `updateShortsQueueItem`, `moveShortsQueueItemToTop`, `nextShortsQueueItem`. |
| `schedules/daily-automation.js` | Adds `runContinuousShorts` and `lastShortsRun`. |
| `scripts/reference-channel.js` | CLI that analyzes a channel. |

Mac helper scripts are double-clickable `.command` files:

- `restart-app.command`
- `setup-voices.command`: makes a venv `.voices`, runs `pip install "piper-tts>=1.6"`, downloads `en_US-libritts_r-medium.onnx` and `.onnx.json` from huggingface rhasspy/piper-voices, calibrates, plays a test line, then restarts the app.
- `connect-youtube.command`
- `test-ai.command`
- `push-to-github.command`: pushes to github.com/pdewanganadv1-dot/youtube-automation-agent and refuses to push if secret files are staged.
- `start-office.command`

## 3. Video formats

All three formats produce a "gag" JSON. `normalize*` validates it against fixed vocabularies, because the AI can only use values the engine knows how to draw. The production agent stores it as `script.cartoon`. The `format` field selects the renderer: absent or `cartoon` → cartoon engine, `window` → window engine, `story` → story service.

Each render returns `{videoPath, audioPath(_soundtrack.m4a), thumbnailPath(_thumb.jpg), duration, voicedLines, voiceCredit}`.

### 3a. Cartoon gags (`format: cartoon`, default)

**Look.** A crude meme-style 2D animation:

- cream paper (`#f4efdc`) with ink lines (`#1d1d1b`) and noodle-limb characters;
- one handwritten caption at the top in Patrick Hand, 84 px, centred at y=175 in a 360 px cream band;
- line boil via feTurbulence with seed `floor(frame/3)%7`;
- 1080x1920 at 24 fps (`CARTOON_FPS`).

**Vocabulary (`VOCAB`)**

- frame: wide | medium | closeup | extreme
- focus: hero | other | prop | both
- mood: neutral, smile, grin, smug, angry, shock, twitch, sad, cry, dead
- action: idle, walk_in, walk_out, run_away, jump, shake, scream, fall, faint, spin, stretch_up, explode, wave, point, shrink, grow, dance, cry
- prop: none, kiosk, tv, computer, phone, sign, door, fridge, car, box, bed, table
- item: none, phone, chips, cup, book, key, food
- species: human, cat, dog, bunny, bear
- voice: kid, girl, boy, man, woman, grandpa, grandma, robot, squeaky
- The final shot's hero action must be one of: stretch_up, explode, faint, run_away, spin, shrink, grow, fall, dance.

**Shot fields**

- `{dur 0.9–3.5, frame, focus, hero{mood,action,item}, other{present,mood,action}, prop{kind,text≤48 UPPERCASE,flash}, speech{who,text}, crowd, sfx}`
- At least 5 and at most 30 shots.
- Durations are scaled toward the target length (±25%, never over 60 s).
- The last shot is at least 2.6 s.
- Speech is capped at 60 characters, or 90 when the target is 35 s or more.

**Camera**

- wide: z=1, center (540,1130)
- medium: z=1.75, cy = FLOOR − 440·s
- closeup: z=2.5; extreme: z=3.1, both with cy = FLOOR − 540·s (keeps speech bubbles off faces)
- prop close-ups: z 1.9 / 3.0 / 3.6
- Punch-in: 8% over 0.18 s on every cut.
- Shake on shake, scream or explode.
- Non-wide shots follow the subject vertically.

**Speech bubbles**

- Top of frame at y=420, Patrick Hand 58 px, wrapped at 18 characters, at most 4 lines.
- When the speaker is off-screen the bubble has a dashed outline and no tail.
- Lip-flap animates while the voice line plays (`s.talk`).

**Automatic sound cues (`ACTION_SFX`)**

| Action | Sound |
|---|---|
| jump | boing |
| explode | boom |
| fall | slide_down |
| faint | wahwah |
| scream | sting |
| shake | rumble |
| stretch_up | slide_up |
| run_away | whoosh |
| walk_in | whoosh |
| spin | slide_up |
| shrink | slide_down |
| grow | slide_up |
| cry | wahwah |
| dance | tada |

Every cut also gets `whoosh_soft`, and each bubble gets a `pop` (dropped when voices are present).

### 3b. Zoo window (`format: window`)

Modelled on the viral "AI zoo glass" Shorts (reference: youtube.com/shorts/ba2Y5SARr_8, @SafariBeyond, 13 s, a lion family at the glass). The story and art are original.

- **Shot.** One continuous hand-held phone shot through the enclosure glass, in a flat storybook colour style.
- **Cast.** An animal family plus visitors:
  - family roles: dad (size 1.12), mom (1.0), cub (0.52, head ×1.28);
  - visitors in the foreground: a woman (`visitor`) and a kid (`kid`), optionally `dad_visitor`.
- **Species palettes** (fur / dark / light):

  | Species | Fur | Dark | Light | Notes |
  |---|---|---|---|---|
  | bear | #8a5a3c | #6e452c | #c9a07a | |
  | lion | #d9a352 | #b9843a | #f2dcae | mane #8f4f1e, dad only |
  | panda | #f4f3ee | #1f1f22 | #fff | black limbs and eye patches |
  | tiger | #e8913a | | #fbecd6 | stripes |
  | polar | #f1efe6 | | | |

- **Depth model.** Ground y `gy(d)=1830−880·d^0.8`. Scale `sc(d)=1−0.7d`. Screen x `sx(x,d)=540+(x−540)(1−0.45d)`.
  - Spots (depth d): glass 0.03, near 0.22, middle 0.45, back 0.78, rock 0.62, and offscreen (x −420 or 1500).
  - Sides (x): left 330, center 560, right 800.
  - The rock sits at (930, 0.55) and the log at (260, 0.72).
  - Objects are drawn far to near, so the rock hides animals behind it.
- **Actions:** idle, sit, lie, sleep, look, walk, run, walk_in, paws_up, boop, wave_paw, roll, pounce, nudge, groom, yawn, roar, tumble, peek.
  - nudge, groom and pounce need a `target`. A nudge pushes the target 190 px sideways.
  - peek: the cub slides out from the side of the rock; adults rise over the top.
  - boop and paws_up leave fog or paw prints on the glass that fade over 3 s.
- **Inheritance.** An animal not mentioned in a beat keeps resting (sit, lie, sleep or look). A new `spot` without an action resets it to idle.
- **Movement speed:** run or pounce 950 px/s, tumble 700, walk 560. Movement uses at most 50% of the beat for in-place actions and 75% otherwise.
- **Visitors' moods:** calm, excited, laugh, aww, gasp, point. They bob, lean or tilt; the kid bounces.
- **Camera.**
  - wide: z 1.08, center (540,1060)
  - follow: 1.38; close: 1.75 on the focus animal's head
  - Eases over 0.9 s between beats.
  - Hand-held drift: x = 7·sin(1.3t) + 4·sin(2.9t+1); y = 6·sin(1.1t+2) + 3·sin(3.3t); rotation 0.5·sin(0.9t) + 0.25·sin(2.1t) degrees.
  - Foreground parallax ×1.6.
  - Glass tint `#9fc6d8` at 7% opacity, two moving reflection streaks, and a dark window post at the left edge.
- **Text.**
  - Hook caption: Helvetica Neue / Arial 900, 70 px, white with a 14 px `#111` stroke, at y=215.
  - Visitor speech subtitles: 56 px, weight 800, `#fff6a8` with a 12 px `#111` stroke, at y=430 + 74·line, shown for the length of the line.
- **Automatic sound cues**

  | Trigger | Sound(s) |
  |---|---|
  | paws_up | thump, then glass_tap 0.45 s later |
  | boop | glass_tap |
  | pounce | whoosh + thump |
  | nudge | growl |
  | roar | roar_soft |
  | yawn | yawn |
  | tumble | whoosh_soft |
  | cub active actions | cub_squeak |
  | visitors laugh | crowd_laugh |
  | visitors aww | crowd_aww |
  | visitors gasp | crowd_gasp |

- **Soundtrack.** Uses `ambience:'zoo'` (wind, crowd murmur, bird chirps) and `musicGain: 0.35` (quiet soothing bed).
- **Limits.** 4–20 beats of 1.2–3.5 s each, at most 45 s in total; the last beat is at least 2.6 s.

### 3c. Narrated story (`format: story`, the "faceless series")

One narrator tells an AI-written story over one illustration per scene, with Ken Burns moves, crossfades and word-by-word captions. A **series** is a saved preset of niche, art style, caption style, narrator and language (setting `story_series`), reused for every video.

**Niches** (default music; transition)

| Niche | Music | Transition |
|---|---|---|
| scary | dark | fadeblack |
| history | epic | fade |
| figures | epic | fade |
| mythology | epic | fade |
| facts | mystery | fade |
| unsolved | mystery | fadeblack |
| custom | mystery | fade |

Each niche has an adult brief and a kids brief (verbatim in the prompt appendix).

**Art styles** (prompt suffix)

| Style | Prompt suffix |
|---|---|
| creepy_comic | dark horror comic book illustration, heavy ink lines, muted greens and sickly yellows, dramatic shadows |
| modern_cartoon | modern 2D cartoon illustration, clean bold outlines, flat vibrant colors, expressive characters |
| storybook | classic animated storybook film style, warm painterly colors, soft lighting, charming characters |
| dark_realism | cinematic dark realistic digital painting, moody low-key lighting, film grain |
| watercolor | soft watercolor illustration, textured paper, gentle washes of color |
| epic_painting | epic classical oil painting, dramatic golden light, grand composition, detailed |

**Narrators** (preset → voice key)

| Preset | Voice key | Gemini voice | Piper profile (group, pitch factor, length scale) |
|---|---|---|---|
| adam | narrator_deep | Algenib | low, 0.95, 1.08 |
| john | narrator_story | Charon | low, 1.0, 1.02 |
| bella | narrator_warm | Sulafat | high, 1.0, 1.04 |
| grace | narrator_soft | Enceladus | high, 1.0, 1.10 |
| sage | grandpa | Charon (0.93 pitch) | low, 0.92, 1.15 |

The narration delivery follows the music:

- dark → "as a slow, hushed, suspenseful storyteller" (speed 1.08)
- epic → "as an epic documentary narrator"
- mystery → "as an intrigued documentary narrator" (1.04)
- otherwise → "as a warm, engaging storyteller"

**Scene fields**

- `{narration 10–24 words, image_prompt, setting, figure, time, mood}`. Up to 16 scenes, at least 3 narrated.
- Allowed values (these drive the fallback illustration):
  - setting: forest, house, village, castle, temple, ruins, sea, city, desert, mountains, cave, road, battlefield, room
  - figure: none, person, hooded, child, soldier, king, creature, crowd, wolf
  - time: night, dusk, day, dawn, storm
  - mood: eerie, epic, calm, tense, sad, wonder
- Motion cycles through zoom_in, zoom_out, pan_left, pan_right, pan_up, pan_down.

**Timing**

- Each scene lasts its voice length + 0.45 s (first scene + 0.35 s).
- Without a voice: max(2.2, words/2.5 + 0.5) s.
- Target length 25–90 s at about 2.55 words/s.
- Logs a warning above `STORY_MAX_SECONDS` (default 90).

**Images**

- `STORY_IMAGES` = auto | pollinations | gemini | builtin (auto → Pollinations).
- Pollinations request: `https://image.pollinations.ai/prompt/<prompt≤900>?width=1080&height=1920&seed=<sha(title|i)>&nologo=true&model=$POLLINATIONS_MODEL(flux)`
  - Timeout `STORY_IMAGE_TIMEOUT_MS` (90 s).
  - Rejected if the response is not an image or is under 20 KB.
- Gemini image model: `GEMINI_IMAGE_MODEL` (gemini-2.5-flash-image), aspect 9:16. The free-tier quota is 0, so it effectively needs billing.
- After 2 AI failures the remaining scenes use the built-in SVG illustrator (Playwright at 2× scale).
- Every scene is scaled and cropped to 2160x3840 so the zooms stay sharp.
- Images are cached in `data/story/images/<sha>.jpg`.
- Image prompt template: `<scene prompt>. Main character: <character>. Style: <art style>. Vertical 9:16 composition, subject centered, no text, no letters, no watermark, no logo.`

**ffmpeg render (one pass)**

```
per scene i:  -i scene_i.jpg
  [i:v]scale=2160:3840:force_original_aspect_ratio=increase,crop=2160:3840,
       zoompan=z='<z>':x='<x>':y='<y>':d=<frames>:s=1080x1920:fps=30,setsar=1,format=yuv420p[vi]
  zoom_in  z=1+0.14*(on/n), x=iw/2-(iw/zoom/2), y=ih/2-(ih/zoom/2)
  zoom_out z=1.14-0.14*(on/n)
  pan_left z=1.12, x=(iw-iw/zoom)*(1-on/n)   pan_right x=(iw-iw/zoom)*(on/n)
  pan_up/pan_down same on y
chain: [prev][vi]xfade=transition=<fade|fadeblack>:duration=0.35:offset=<scene start>
final: [last]ass='captions.ass':fontsdir='assets/fonts'[outv]
-map [outv] -map <audio> -c:v libx264 -preset $STORY_X264_PRESET(veryfast) -crf 21 -pix_fmt yuv420p -r 30 -c:a copy -t <dur> -movflags +faststart
```

- fps = `STORY_FPS` (30).
- Scenes are extended by the 0.35 s fade length so the crossfades overlap.
- Thumbnail = the frame at 1.2 s.

**Soundtrack**

- Narration starts at each scene start + 0.15 s.
- Cues:
  - a `hit` at 0.02 s for dark or epic music;
  - `whoosh_soft` 0.2 s before every cut;
  - a `riser` 1.6 s before the last scene.
- Music bed: dark | epic | mystery are minor-key progressions (`STORY_MUSIC`), with `musicGain: 0.8`.

**Captions (ASS)**

- PlayRes 1080x1920, centered at `\an5\pos(540,1290)`, BorderStyle 1, outline colour `&H00000000`, back colour `&H96000000`, Spacing 1.
- Per-word timing is weighted by letter count + 2, plus 4 after sentence ends or 2 after commas.
- Groups never straddle a sentence end.
- Fonts in `assets/fonts`: Poppins, Anton, Bangers, Bebas Neue, Lora (Latin languages only; Hindi falls back to Poppins). Patrick Hand is the cartoon font.

| Style | Font, size | Primary | Highlight | Outline / Shadow | Case | Words per group | Effect |
|---|---|---|---|---|---|---|---|
| bold_stroke | Poppins 112, bold | `&H00FFFFFF` | – | 10 / 3 | upper | 2 | pop-in `\fscx90→100` over 80 ms |
| red_highlight | Poppins 100, bold | `&H00FFFFFF` | `&H003C3CF0&` (red) | 8 / 3 | upper | 3 | current word coloured + 108% |
| karaoke | Poppins 92, bold | `&H00FFFFFF` | `&H0000E5FF&` (yellow) | 8 / 2 | as written | 4 | `\kf` sweep |
| beast | Anton 150 | `&H00FFFFFF` | `&H0000F0FF&` (yellow), every 3rd group | 11 / 6 | upper | 1 | 120→100% pop over 90 ms |
| sleek | Poppins 70, bold | `&H00FFFFFF` | – | 0 / 4 | lower | 4 | – |
| majestic | Lora 88, bold | `&H0066D4F5` (gold) | – | 6 / 4 | as written | 3 | words reveal cumulatively, 120 ms fade-in |
| comic | Bangers 118 | `&H00FFFFFF` | `&H0000D7FF&` (yellow) | 10 / 5 | upper | 2 | current word coloured, ±2° tilt |

Credits are added to the description: the Piper credit, plus "Illustrations generated with Pollinations.ai." when Pollinations images were used.

### Shared soundtrack engine (`utils/cartoon-audio.js`)

- Mono, 44.1 kHz, 16-bit WAV.
- **Instruments:** pluck (Karplus-Strong), bell, marimba, bass, tuba, pad, kick, hat, shaker (gain 0.045), clap, woodblock, sweep (sine, brass or square).
- **Music styles:**
  - `MUSIC_STYLES`: kids (C G Am F, 108 bpm), upbeat (Am F C G, 120), soothing (C Am F G, 76, pad + bells), silly (C F G C, 140, tuba + marimba), none.
  - `STORY_MUSIC`: dark, epic, mystery, soothing, none.
  - The melody is an 8-note motif seeded from the caption.
- **SFX:** beep, error, tick, pop, boing, slide_up, slide_down, wahwah, honk, ding, sparkle, tada, drumroll, crash, thud, boom, whoosh, whoosh_soft, rumble, printer, sting, giggle, glass_tap, thump, growl, roar_soft, yawn, cub_squeak, crowd_laugh, crowd_aww, crowd_gasp, camera_click, hit, riser.
- **`renderSoundtrack({duration, musicStyle, cues:[[name,sec]], voices:[{samples,at}], seed, ambience, musicGain})`:**
  - ducking envelope: attack 0.08 s, release 0.25 s, ducks to 35% when |voice| > 0.02;
  - mix = music·0.55·musicGain·duck + ambience·(0.75+0.25·duck) + sfx·(0.6+0.4·duck) + voice·1.1;
  - then `tanh(1.2x)` soft-clip, normalized to a 0.92 peak.
- **`pcm16ToVoice(buf, inRate, factor)`:** trims silence (threshold 0.01) and resamples to 44.1 kHz with a pitch/speed factor (the cartoon chipmunk effect).

### Voices

- **Provider choice:** `voiceProvider()`, set by `CARTOON_TTS` (auto | piper | gemini). Auto uses Piper if it is installed and calibrated, otherwise Gemini if a key exists. `CARTOON_VOICES=off` disables voices.
- **Piper (free, local).**
  - Model `data/voices/en_US-libritts_r-medium.onnx`: 904 speakers, CC BY 4.0 dataset (the voice was fine-tuned from lessac; licence caveat disclosed to the user).
  - `calibrate` synthesizes 60 sample speakers, measures median pitch by autocorrelation, and writes `data/voices/speakers.json` as `{groups:{low,mid,high}, pitches}`.
  - Per character voice: `PIPER_PROFILE = kid [high,1.12,1.0], girl [high,1.08], boy [mid,1.18], woman [high,1.0], man [low,1.0], grandpa [low,0.92,1.15], grandma [mid,0.95,1.12], robot [mid,1.0,1.05] (+55 Hz AM), squeaky [high,1.38,0.95]`.
  - The speaker id inside a group is `hash(caption|role)`, so each role gets a distinct voice.
  - Synthesis uses noise_scale 0.667 and noise_w 0.8. Length scale is multiplied by `MOOD_SPEED` (angry 0.9, shock 0.88, sad 1.15, cry 1.18, …).
  - Batch requests go to `.voices/bin/python tools/piper_tts.py` (or `PIPER_PYTHON`) with a 180 s timeout.
  - Cache: `data/cartoon/voices/<sha1>.wav`.
  - Credit: "Character voices: Piper TTS with LibriTTS-R voices (CC BY 4.0)."
- **Gemini TTS.**
  - Model `GEMINI_TTS_MODEL` (gemini-3.1-flash-tts-preview).
  - Prompt: `Say <delivery>: <text>`, where delivery comes from mood (angry → "angrily, in a funny cartoon voice", shock → "in total shock", …).
  - Prebuilt voices: kid Leda 1.18, girl Leda 1.26, boy Puck 1.2, man Fenrir 1.02, woman Kore 1.06, grandpa Charon 0.93, grandma Gacrux 0.97, robot Iapetus, squeaky Puck 1.42.
  - On a 429 "retry in Ns" (N ≤ 75 s) it waits and retries, up to 4 attempts. Voicing stops after 2 failed lines.
  - Cache: `.pcm` files.
- **`fitShotsToVoices`:** shot duration = max(dur, voice + 0.55 s), and the total is capped at 60 s by shrinking silent shots.
- **Speaker roles:** `speakerOf(gag, shot)` maps roles to voices: hero/other (cartoon), visitor/kid/dad_visitor (window), narrator (story).

## 4. Dashboard (`dashboard/index.html`, `app.js`, `styles.css`, `enhance.js`; served at `/`)

**Pages** (left nav, plus g-chord keyboard shortcuts from enhance.js):

- the original upstream pages: Overview, Generate, Content review, Scenes editor, Analytics, Experiments, Engagement, Ideas, Settings, Readiness, Notifications;
- **Queue** (added);
- **Video library** (added);
- **Office** (`/office`).

**Queue page**

- Status cards.
- "Making now" with progress.
- Topic queue: add, move to top, remove, and "Make next now" (`POST /api/queue/run-next`, a manual run that ignores the pending limit).
- Publishing queue (the scheduled slots).
- Recent runs. The next cron time comes from `nextCronTime`.

**Video library**

- Stats: number of videos, waiting for review, continuous-Shorts status (Running / Paused / Off with the cron), style.
- Filters, plus a card per video with an inline player and the links Open ↗, YouTube ↗, Download, ✎ Edit, Details, and a Regenerate-with-notes form.
- **Controls row 1:**
  - Inspiration channel (input + "Analyze & use" → `POST /api/reference-channel {channel, activate:true}`);
  - **Video style** select: Cartoon gags / Zoo window / Narrated story → setting `cartoon_format`;
  - **Story series** controls, shown when the style is story: niche, art style, caption style, narrator, language → setting `story_series`;
  - Video length: 20 / 35 / 60 s → `cartoon_target_seconds`, range 12–60;
  - "Made for kids" toggle → `made_for_kids`.
- **Controls row 2:**
  - Auto-approve toggle (`approval_required` false/true);
  - Style notes textarea (≤ 800 characters) → `cartoon_style_notes`, injected as EDITOR NOTES into every prompt;
  - "Clear everything" — the user must type DELETE → `POST /api/reset {confirm:'DELETE'}`. It clears content tables and the videos, audio, assets, temp, scripts, captions, shorts, thumbnails and uploads folders, but keeps settings, keys and reference profiles.
- **✎ Edit dialog.**
  - Cartoon: title, caption, music, species and voice per character, voices on/off, kids, and per shot the speaker, line, sign text and sfx.
  - Window: animal family, music, visitor voices, and per beat the speaker, line and sfx.
  - Buttons: **Re-render** (`POST /api/content/:id/rerender {gag}`, async, in place) or **Rewrite with AI** (`POST /api/content/:id/regenerate {notes, madeForKids, format?, series?}`). Rewrite keeps the requested topic, adds "previous version was rejected — make a clearly different joke", and marks the old video rejected.
- The global `api()` helper sends the stored dashboard API key header to `protect`-ed routes.

**API endpoints** (Express in `index.js`)

- Pages and health:
  - `GET /`, `GET /health`, `GET /office`, `GET /api/office/state`, `POST /api/office/command`
- Reference channel:
  - `POST /api/reference-channel {channel, activate}`, `GET /api/reference-channel`
  - `POST /api/reference-channel/:channelId/activate`, `DELETE /api/reference-channel/active`
- Generation and schedule:
  - `POST /generate`, `GET /analytics`, `GET /api/outcomes`, `GET /schedule`, `POST /publish/:contentId`
  - `GET /api/dashboard`
  - `GET /api/jobs/:jobId`, `POST /api/jobs/:jobId/resume`, `POST /api/jobs/:jobId/cancel`
  - `GET /api/readiness`, `POST /api/readiness/run`
- Content:
  - `GET /api/content/:id`
  - scenes: `…/scenes/:sceneId/estimate`, `…/scenes/reorder`, `…/scenes/:sceneId/regenerate`, `…/scenes/:sceneId/narration`, `…/narration/silence`, `…/scenes/rebuild`, `…/scenes/:sceneId/asset`
  - shorts clips: `…/shorts/propose`, `…/shorts/:clipId/render|approve|asset/:kind`
  - review: `…/approve`, `…/rerender`, `…/regenerate`, `…/reject`, `…/retry`, `…/asset/:kind`
  - provenance and publishing: `PUT …/provenance`, `POST …/discoverability/run`, `POST …/publish-now`, `DELETE …/schedule`
- Reset and queue:
  - `POST /api/reset`
  - `GET /api/queue`, `POST /api/queue {topic}`, `DELETE /api/queue/:itemId`, `POST /api/queue/:itemId/top`, `POST /api/queue/run-next`
- Library:
  - `GET /api/library` → items (joined with the latest `publish_schedule` row; status: rendering, needs_review, scheduled, published, …; `youtubeUrl`) plus `automation{continuousShorts, schedule, maxPending, enabled, cartoon, autoApprove, styleNotes, targetSeconds, madeForKids, videoFormat, story, storyOptions}`
  - `GET /api/library/file/:name`
- Profile and operator:
  - `PUT /api/profile`, `PUT /api/operator/strategy`
  - `POST /api/operator/start|pause`, `POST /api/operator/runs/:runId/cancel|resume`
- Learning and growth:
  - `POST /api/learning/recommendations/:id/:action`
  - `GET|POST /api/experiments`, `POST /api/experiments/:id/:action`
  - `GET /api/retention/:videoId`, `POST …/refresh`
  - `GET /api/engagement/:videoId`, `POST …/sync`, `POST …/draft-replies`, `POST /api/engagement/replies/:draftId/approve`
  - `POST /api/ideas`, `POST /api/ideas/:ideaId/generate`
- Automation, settings and notifications:
  - `POST /api/automation/:action`
  - `PUT /api/settings` (keys below)
  - `POST /api/notifications/:id/read`

**Settings table keys:** `approval_required`, `notification_enabled`, `channel_timezone`, `max_daily_posts`, `content_buffer_days`, `cartoon_target_seconds`, `made_for_kids`, `cartoon_style_notes`, `cartoon_format` (cartoon | window | story), `story_series` (JSON), `automation_paused`.

## 5. Integrations

- **YouTube OAuth and upload.**
  - Google Cloud project with the YouTube Data API v3 enabled and an OAuth client of type Desktop/Web. `oauth-server.js` / `connect-youtube.command` runs the consent flow on localhost and stores the refresh token locally.
  - The user's Gmail was added as a test user, because the app is in Testing mode.
  - Limits:
    - unverified-app uploads are forced to **private**;
    - refresh tokens in Testing mode **expire after 7 days**;
    - `videos.insert` costs about 1600 quota units, so roughly 6 uploads a day on the default 10k quota.
- **AI text** (`utils/ai-text-service.js`).
  - Gemini via @google/genai: `GEMINI_MODEL=gemini-flash-lite-latest`, `GEMINI_FALLBACK_MODELS=gemini-3.7-flash,gemini-flash-latest`.
  - Has a timeout and falls back to the next model on 5xx errors or hangs.
  - The upstream fix retries without unsupported temperature values.
  - The OpenAI and Anthropic upstream providers still exist but are unused.
- **Free tiers.**
  - Gemini TTS is limited to 3 requests/min and 10/day.
  - Gemini image generation has a quota of 0 on the free tier.
  - Stock visuals for the old slideshow path: Pexels (keys were paused) → Openverse (no key needed).
- **Reference-channel analysis** (`utils/reference-channel-service.js`).
  - Uses the YouTube Data API: `channels` (by handle, id or URL) → uploads playlist → `playlistItems` for the last 40 videos → `videos` (duration, stats, tags).
  - Stats: shorts share, median long-form minutes, upload interval (`uploadsEveryDays`), best weekday and hour slots, top tags.
  - Transcripts are fetched best-effort through `fetchTranscript`.
  - The AI synthesizes a style profile: niche, audience, tone, pacing, hook patterns, content pillars, **topicGaps**, avoid. There is a heuristic fallback without AI.
  - Stored in `channel_profiles`; one profile is active at a time.
  - `blueprint(profile)` feeds strategy and prompts. Mostly-Shorts channels are copied as Shorts.
  - `checkOriginality` compares titles and scripts against the channel's titles.
  - Example: the Rico profile UCOicc9kd58k_XR3D7bTx8oA is 85% Shorts with a median of about 34 s.
- **YouTube-link frame extraction** (manual, done in-session, not an app feature).
  - Read the storyboard spec from the watch-page HTML (`"spec"`), fetch the level-3 sprite sheets `https://i.ytimg.com/sb/<ID>/storyboard3_L3/M<n>.jpg?sqp=…&sigh=…`, or draw `<video>` frames onto a canvas in a browser tab.
  - Get video data via oEmbed (`https://www.youtube.com/oembed?url=…&format=json`).
  - Captions: `captionTracks` (en:asr) from the page.
  - Worth building as a `POST /api/reference-video {url}` endpoint that turns one Short into a format brief.
- **Pollinations** — see §3c. Free, no key, and it can be slow or rate-limited.
- **Scheduling.**
  - node-cron for `SHORTS_SCHEDULE`, plus the upstream daily automation crons.
  - Queue items move queued → started (with job_id) → done/failed/removed.
  - `position` is a REAL, so "move to top" sets min − 1.

## 6. Configuration (names only — no values)

**.env names**

- AI and voices: `GEMINI_API_KEY`, `GEMINI_MODEL`, `GEMINI_FALLBACK_MODELS`, `GEMINI_TTS_MODEL`, `GEMINI_IMAGE_MODEL`, `OPENAI_API_KEY` (optional), `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`, `ELEVENLABS_TTS_MODEL` (optional)
- Stock media: `PEXELS_API_KEY`
- YouTube: `YOUTUBE_API_KEY` (for reference analysis), `YOUTUBE_API_BASE`, `YOUTUBE_WEB_BASE`, `YOUTUBE_REDIRECT_URI`, `YOUTUBE_REGION`
- App: `PORT` (3456), `API_KEY` (the dashboard/API key checked by `protect`), `TARGET_AUDIENCE`
- Cartoon formats: `CARTOON_SHORTS` (on/off), `CARTOON_FPS`, `CARTOON_TTS` (auto/piper/gemini), `CARTOON_VOICES` (on/off), `PIPER_PYTHON`
- Scheduler: `SHORTS_CONTINUOUS` (on/off), `SHORTS_SCHEDULE`, `SHORTS_MAX_PENDING`, `SHORTS_PUBLISH_GAP_HOURS`, `SHORTS_FIRST_RUN_DELAY_MS`
- Story format: `STORY_IMAGES`, `POLLINATIONS_MODEL`, `STORY_IMAGE_TIMEOUT_MS`, `STORY_FPS`, `STORY_MAX_SECONDS`, `STORY_X264_PRESET`

The OAuth client id/secret and tokens are **not** env variables. They live in `config/credentials.json` (`credentials.youtube.client_id / client_secret`, plus stored tokens), written by `utils/credential-manager.js` and `oauth-server.js`/`modern-auth.js`. That file is git-ignored and must never be copied into the new repo.

**Data layout**

- `data/lumen.db` (SQLite)
- `data/videos`, `data/audio`, `data/thumbnails`, `data/temp`
- `data/cartoon/voices` (voice cache), `data/story/images` (image cache)
- `data/voices/*.onnx|.onnx.json|speakers.json`
- `.voices/` (Python venv; excluded from git)

**Tables added:** `shorts_queue (id, topic, position REAL, status, job_id, note, created_at, updated_at)` and `channel_profiles`. The upstream tables are listed in `database/db.js`, including productions, content_reviews, publish_schedule, production_snapshots and generation_jobs.

**Gag JSON:** stored inside `scripts.script` → `cartoon`. Its shape is described in §3, and the fixtures are `tests/fixtures/window-gag.json` and `tests/fixtures/story.json`.

**Tests**

- `npm test` (upstream, 47 checks)
- `test:cartoon` (11, covering cartoon, window and story)
- `test:queue` (3)
- `test:reference` (7)
- `test:office` (5)
- `CARTOON_RENDER=1` performs a real MP4 render test.

## 7. Known bugs, limitations and next steps

- **YouTube restrictions:** private-only uploads, 7-day token expiry and about 6 uploads a day. Fix by verifying the OAuth app, or by publishing it to production with a privacy policy.
- **Piper is not installed on the Mac yet.** The user must run `setup-voices.command`. Until then voices fall back to Gemini, which allows only 10 a day; the kids test "Puppy and Kitty Bake a Cake" rendered with 0 voices.
- **The Mac is behind the cloud copy.** It is at 993864a, which has the zoo-window format but not the narrated story (137b5da). `.git/HEAD.lock` and `.git/objects/maintenance.lock` were left behind on the Mac because the bridge can't delete files, and the user must delete them before the next commit there.
- **Zoo-window rendering is cartoon-style**, not the photoreal "AI footage" look of the reference. Photoreal would need a video model such as Veo or Kling, which is paid.
- The window format sometimes crowds animals at the glass in the final beat.
- Subtitles are not word-timed in the cartoon and window formats; they cover the whole line.
- **Gemini image generation does not work on the free tier**, so story images rely on Pollinations, which is sometimes slow or rate-limited (the illustrator fallback covers this).
- **Mutating the dashboard by typing can trigger enhance.js g-chord shortcuts.** Guard key handlers when focus is in an input.
- **A restart during a render kills the job** ("browser closed"). It is harmless but needs a re-queue.
- **Fixed bugs worth not reintroducing:**
  - SQLite timestamps were parsed as local time → use the `utcIso()` helper.
  - The review count used `p.status='ready'` → use `COALESCE(cr.status, p.status)`.
  - Publish slots jumped days ahead → use the gap-filling slot algorithm.
  - The strategist rewrote the user's topic → keep `requestedTopic` verbatim.
  - Bubbles covered faces → frame faces in the lower middle.
  - `pkill -f` killed its own shell → use a script file for kills.
- **Planned next:**
  1. An "improve from a reference video" flow: upload or link a Short → extract its format (beats, captions, sound design) → produce a format brief that feeds the prompts. The user asked for this last, with an uploaded MP4, and it was not started.
  2. Per-queue-item format and series, instead of a single global setting.
  3. Word-timed captions for the cartoon and window formats.
  4. A Hindi or other-language channel setup if he wants one.
  5. Analytics-driven topic picking.
  6. Moving uploads to a verified OAuth app.
  7. A git push workflow to his own GitHub.

---

## Appendix: prompt builders (verbatim source)


### Cartoon gags — `CartoonShortService.buildPrompt` (utils/cartoon-short-service.js)

```js
  buildPrompt({ topic, reference, avoidTitles = [], market, notes = '', targetSeconds = 22, kids = false, recent = [] }) {
    const ref = reference || {};
    const editor = String(notes || '').trim();
    const target = CartoonShortService.clampTarget(targetSeconds);
    const long = target >= 35;
    const shots = long ? `${Math.round(target / 2.6)}-${Math.round(target / 2)}` : `${Math.max(6, Math.round(target / 2.4))}-${Math.round(target / 1.6)}`;
    const ideas = (ref.topicGaps || []).slice(0, 6);
    return `You write funny ${kids ? 'KIDS ' : ''}cartoon Shorts for YouTube: crude, charming 2D characters on cream paper, one handwritten caption at the top, fast cuts, music, cartoon sound effects and short spoken dialogue (each speech bubble is voiced).
Return ONLY valid JSON:
{
  "caption": "${kids ? 'short fun title for the story (max 45 characters, no emoji)' : 'When you ... (relatable everyday situation, max 45 characters, no emoji)'}",
  "title": "catchy YouTube title, max 60 characters, may end with one emoji",
  "cast": { "hero": { "species": "human|cat|dog|bunny|bear", "look": "round|tall", "voice": "kid|girl|boy|man|woman|grandpa|grandma|robot|squeaky" }, "other": { "species": "...", "look": "round|tall", "voice": "..." } },
  "shots": [
    { "dur": 2.0, "frame": "wide|medium|closeup|extreme", "focus": "hero|other|prop|both",
      "hero": { "mood": "...", "action": "...", "item": "..." },
      "other": { "present": false, "mood": "...", "action": "..." },
      "prop": { "kind": "...", "text": "TEXT ON ITS SCREEN/SIGN (max 40 chars)", "flash": false },
      "speech": { "who": "hero|other", "text": "spoken line, max ${long ? 10 : 7} words" },
      "crowd": false, "sfx": "..." }
  ],
  "music": "kids|upbeat|soothing|silly|none",
  "tags": ["5-8 lowercase tags"],
  "description": "one or two fun sentences"
}
Allowed values ONLY:
mood: ${VOCAB.mood.join(', ')}
action: ${VOCAB.action.join(', ')}
prop.kind: ${VOCAB.prop.join(', ')}
item (hand-held): ${VOCAB.item.join(', ')}
sfx: ${VOCAB.sfx.join(', ')}
voice: ${VOCAB.voice.join(', ')}
species: ${VOCAB.species.join(', ')} (animal characters are great for kids and for topics about animals)
Rules:
- ${shots} shots, each 1.2-3.5 seconds, total about ${target} seconds (never more than 60).
- ${long ? 'Tell a tiny story with a beginning (setup), a middle (3 escalating attempts/problems — the rule of three) and an end (a surprising, absurd payoff). Use a running gag.' : 'Structure: wide setup, the trigger, 2-4 escalating reactions, things get worse or others react, then an ABSURD exaggerated payoff.'}
- The final shot's hero action must be one of: ${ENDINGS.join(', ')}.
- Use dialogue: about half of the shots have a short spoken line (max ${long ? 10 : 7} words). Lines must be funny or charming on their own and fit the character's voice. SHOW the story — never narrate it, never label beats ("Attempt one:", "Step two:"), no lecturing or morals spelled out.
- Use the topic exactly as given — same characters and situation.
- Pick sound effects that land the jokes (boing for jumps, slide_up/slide_down for surprises, wahwah for fails, tada/sparkle for wins, drumroll before a reveal, honk/pop for silly beats).
- Keep the same prop through the gag when it is the source of the joke. Close-ups of a prop screen use "focus": "prop".
${kids ? `- MADE FOR KIDS (ages 4-10): gentle, positive, silly humor; no insults, no scary or violent moments, no romance, no gross-out beyond mild silliness, no brands; simple words; characters are kind in the end. Prefer "kids" or "soothing" music and kid/girl/boy/squeaky voices.` : '- Keep it clean (no profanity, no violence against real people, no brands or real people).'}
- Make it ORIGINAL: take inspiration from the channel style below but never copy its characters, jokes or titles. Do NOT reuse or paraphrase: ${JSON.stringify(avoidTitles.slice(0, 30))}
${recent.length ? `- Be clearly different from our recent videos: ${JSON.stringify(recent.slice(0, 15))}` : ''}
Inspiration channel style: niche "${ref.niche || 'everyday-life humor'}", audience "${ref.audience || (kids ? 'kids and families' : 'teens and young adults')}", tone "${ref.tone || 'silly, energetic'}", pacing "${ref.pacing || 'fast'}"${ideas.length ? `, topic ideas they have not covered: ${JSON.stringify(ideas)}` : ''}.
Audience market: ${market?.label || 'United States'} (American English).
Topic for this video: ${topic || 'pick a fresh, funny everyday situation'}${editor ? `

EDITOR NOTES — follow these closely; they override everything above except the JSON format and allowed values:
${editor}` : ''}`;
  }
```

### Zoo window — `buildWindowPrompt` + `WINDOW` vocabulary

```js
// "Zoo window" format: one hand-held shot through enclosure glass, an animal family + visitors reacting.
const WINDOW = {
  species: ['bear', 'lion', 'panda', 'tiger', 'polar'],
  spot: ['glass', 'near', 'middle', 'back', 'rock', 'offscreen'],
  side: ['left', 'center', 'right'],
  action: ['idle', 'sit', 'lie', 'sleep', 'look', 'walk', 'run', 'walk_in', 'paws_up', 'boop', 'wave_paw', 'roll', 'pounce', 'nudge', 'groom', 'yawn', 'roar', 'tumble', 'peek'],
  visitors: ['calm', 'excited', 'laugh', 'aww', 'gasp', 'point'],
  camera: ['wide', 'follow', 'close'],
  sfx: ['none', 'glass_tap', 'thump', 'growl', 'roar_soft', 'cub_squeak', 'crowd_laugh', 'crowd_aww', 'crowd_gasp', 'camera_click', 'pop', 'boing', 'sparkle']
};
const WINDOW_SPEAKERS = ['visitor', 'kid', 'dad_visitor'];
const WINDOW_VOICE_DEFAULT = { visitor: 'woman', kid: 'kid', dad_visitor: 'man' };

  buildWindowPrompt({ topic, reference, avoidTitles = [], market, notes = '', targetSeconds = 18, kids = false, recent = [] }) {
    const ref = reference || {};
    const editor = String(notes || '').trim();
    const target = Math.min(45, CartoonShortService.clampTarget(targetSeconds));
    const beats = `${Math.max(5, Math.round(target / 2.8))}-${Math.max(6, Math.round(target / 2))}`;
    return `You write ${kids ? 'KIDS ' : ''}YouTube Shorts in the viral "zoo window" style: ONE continuous hand-held phone shot through the glass of an animal enclosure. An animal family — "dad", "mom" and "cub" — acts out a tiny, wholesome drama right at the glass while visitors on our side (a woman = "visitor", a child = "kid", optionally a man = "dad_visitor") react out loud. The humour comes from the animals behaving like a human family (the cub showing off, dad stealing the spotlight, mom restoring order). Visitors' spoken reactions are shown as captions.
Return ONLY valid JSON:
{
  "caption": "on-screen hook at the top (max 45 characters, no emoji), e.g. what the cub wanted",
  "title": "catchy YouTube title, max 60 characters, may end with one emoji",
  "animal": "${WINDOW.species.join('|')}",
  "cast": { "dad": {"present": true}, "mom": {"present": true}, "cub": {"present": true}, "visitor": {"voice": "woman"}, "kid": {"voice": "kid|girl|boy"} },
  "shots": [
    { "dur": 2.2, "camera": "wide|follow|close", "focus": "dad|mom|cub",
      "dad": { "spot": "...", "side": "left|center|right", "action": "...", "target": "mom|cub" },
      "mom": { ... }, "cub": { ... },
      "visitors": { "mood": "..." },
      "speech": { "who": "visitor|kid|dad_visitor", "text": "spoken reaction, max 8 words" },
      "sfx": "..." }
  ],
  "tags": ["5-8 lowercase tags"],
  "description": "one or two fun sentences"
}
Allowed values ONLY:
animal: ${WINDOW.species.join(', ')}
spot: ${WINDOW.spot.join(', ')} ("glass" = pressed right against the window in front of the visitors; "rock" = hiding behind the boulder)
action: ${WINDOW.action.join(', ')} (paws_up = stands up with both paws on the glass; boop = presses its nose on the glass; peek = pops up from behind the rock; nudge/groom/pounce need a "target")
visitors.mood: ${WINDOW.visitors.join(', ')}
camera: ${WINDOW.camera.join(', ')} (follow/close need "focus")
sfx: ${WINDOW.sfx.join(', ')}
Rules:
- ${beats} beats, each 1.8-3.2 seconds, total about ${target} seconds. It is ONE continuous shot, so animals move between spots; only list an animal in a beat when it does something new (otherwise it keeps doing what it was doing).
- Story: setup (cub at the glass delights the visitors) → a twist (another family member gets involved, e.g. copies or steals the moment) → escalation → a sweet or funny payoff (mom/dad settles it, the family together at the glass).
- About 2 of every 3 beats have one short spoken reaction from a visitor — natural, the way people really talk at a zoo ("Oh my gosh!", "He's waving at you!"). Never narrate what the animals think; never label beats.
- Animals never talk.
- ${kids ? 'MADE FOR KIDS: gentle and wholesome, no fighting or scary moments (a nudge or a playful pounce is fine), simple words.' : 'Wholesome and family friendly.'}
- ORIGINAL: do not copy existing videos' stories or titles. Do NOT reuse: ${JSON.stringify(avoidTitles.slice(0, 30))}
${recent.length ? `- Be clearly different from our recent videos: ${JSON.stringify(recent.slice(0, 15))}` : ''}
Inspiration channel style: niche "${ref.niche || 'funny animal moments'}", tone "${ref.tone || 'wholesome, funny'}".
Audience market: ${market?.label || 'United States'} (American English).
Topic for this video: ${topic || 'pick a fresh, funny animal-family moment at the zoo glass'}${editor ? `

EDITOR NOTES — follow these closely; they override everything above except the JSON format and allowed values:
${editor}` : ''}`;
  }
```

### Narrated story — `NICHES` + `StoryShortService.buildPrompt` (utils/story-short-service.js)

```js
const NICHES = {
  scary: { label: 'Scary stories', music: 'dark', transition: 'fadeblack', brief: 'an ORIGINAL short horror story (creepy and suspenseful, not gory) with a chilling twist in the last line', kidsBrief: 'a spooky-fun mystery for kids (a little shivery, never frightening) with a funny or sweet twist' },
  history: { label: 'History', music: 'epic', transition: 'fade', brief: 'a surprising TRUE story from history; every fact, name, place and date must be accurate', kidsBrief: 'an amazing TRUE story from history told simply for kids; facts must be accurate' },
  figures: { label: 'Historical figures', music: 'epic', transition: 'fade', brief: "the most dramatic moment in one real historical figure's life; accurate facts only", kidsBrief: "an inspiring moment from a real historical figure's childhood or life, told for kids; accurate facts only" },
  mythology: { label: 'Greek mythology', music: 'epic', transition: 'fade', brief: 'a Greek myth retold dramatically (stay faithful to the myth)', kidsBrief: 'a Greek myth retold gently for kids (stay faithful to the myth)' },
  facts: { label: 'Mind-blowing facts', music: 'mystery', transition: 'fade', brief: 'a countdown of 5 mind-blowing, TRUE facts on one theme; accurate only', kidsBrief: 'a countdown of 5 amazing TRUE facts for kids on one theme' },
  unsolved: { label: 'Unsolved mysteries', music: 'mystery', transition: 'fadeblack', brief: 'a real unsolved mystery: what happened, the strangest clues, the main theories; accurate facts only, no speculation presented as fact', kidsBrief: 'a real unexplained mystery told for kids, not scary; accurate facts only' },
  custom: { label: 'Custom', music: 'mystery', transition: 'fade', brief: 'a gripping short narrated story on the topic', kidsBrief: 'a gripping short story for kids on the topic' }
};

  buildPrompt({ topic, series = {}, avoidTitles = [], recent = [], notes = '', targetSeconds = 50, kids = false, reference = null }) {
    const s = StoryShortService.normalizeSeries(series);
    const niche = NICHES[s.niche];
    const target = Math.min(90, Math.max(25, Number(targetSeconds) || 50));
    const words = Math.round(target * 2.55);
    const scenes = `${Math.max(5, Math.round(target / 7))}-${Math.max(6, Math.round(target / 5))}`;
    const editor = String(notes || '').trim();
    const lang = LANGUAGES[s.language];
    return `You write viral faceless YouTube Shorts: ${kids ? niche.kidsBrief : niche.brief}. One narrator tells it over illustrated scenes; captions appear word by word.
Return ONLY valid JSON:
{
  "title": "curiosity-driven YouTube title, max 60 characters, may end with one emoji",
  "character": "one fixed visual description of the main character (age, build, hair, clothing) reused in every image prompt, or empty if none",
  "scenes": [
    { "narration": "what the narrator says during this scene (${s.language === 'en' ? '10-24 words' : '10-24 words'})",
      "image_prompt": "concrete visual description of this scene for an illustrator: subject, action, setting, lighting, camera angle. Include the character description when they appear. No text in the image.",
      "setting": "${SETTINGS.join('|')}", "figure": "${FIGURES.join('|')}", "time": "${TIMES.join('|')}", "mood": "${MOODS.join('|')}" }
  ],
  "tags": ["5-8 lowercase tags"],
  "description": "one or two sentences for the YouTube description"
}
Rules:
- Narration language: ${lang}.${s.language !== 'en' ? ' Write natural, spoken ' + lang + ' (not a literal translation).' : ''}
- ${scenes} scenes, about ${words} words of narration in total (≈${target} seconds spoken).
- Scene 1 narration is the HOOK: one punchy sentence under 14 words that creates instant curiosity or dread (e.g. a shocking claim or a question). No greetings, no "in this video".
- Build tension scene by scene; short sentences; vivid sensory detail; present the story, never describe the video.
- The last scene lands a twist, a chilling line or a satisfying payoff in one sentence. No call to action.
- "setting/figure/time/mood" must use the allowed words; they are a backup illustration if image generation fails.
- Image prompts must stay consistent: same character look, same era and place across scenes.
- ${kids ? 'MADE FOR KIDS: gentle, no gore, no death described graphically, nothing truly frightening; simple words.' : 'No gore or graphic violence; keep it advertiser-friendly.'}
- ORIGINAL: do not retell stories that went viral from other channels. Do NOT reuse or paraphrase: ${JSON.stringify(avoidTitles.slice(0, 30))}
${recent.length ? `- Be clearly different from our recent videos: ${JSON.stringify(recent.slice(0, 15))}` : ''}
${reference?.niche ? `Inspiration channel: niche "${reference.niche}", tone "${reference.tone || ''}" — match the energy, never copy.` : ''}
Topic: ${topic || `pick a fresh, gripping ${niche.label.toLowerCase()} subject`}${editor ? `

EDITOR NOTES — follow these closely; they override everything above except the JSON format:
${editor}` : ''}`;
  }
```

### Reference-channel style synthesis prompt (utils/reference-channel-service.js)

```js
  async synthesizeStyle(channel, stats, videos, transcripts, market) {
    if (!this.ai?.isAvailable?.()) return { ...this.heuristicStyle(channel, stats), source: 'heuristic' };
    const topIds = new Set(stats.topPerformers.map(v => v.id));
    const samples = videos.filter(v => topIds.has(v.id)).slice(0, 6).map(v => ({
      title: v.title,
      minutes: round1(v.durationSeconds / 60),
      descriptionStart: v.description.slice(0, 300),
      transcriptOpening: (transcripts[v.id] || '').slice(0, 1200)
    }));
    const prompt = `You are a YouTube format analyst. Describe this channel's repeatable FORMAT so a different creator could make original videos in the same style. Do not summarize or reuse its specific content.
Return only valid JSON with this exact shape:
{
  "niche": "one line",
  "audience": "who watches, in one line",
  "promise": "the value every video delivers",
  "format": "e.g. faceless voiceover explainer with stock b-roll",
  "contentType": "Tutorial|Explainer|List|Review|Story|News",
  "hookPattern": "how the first 15 seconds work",
  "structure": ["ordered beat"],
  "tone": "voice and energy",
  "pacing": "pace and edit rhythm",
  "titleFormulas": ["pattern with {placeholders}, not a real title"],
  "thumbnailStyle": "visual description",
  "palette": { "background": "#rrggbb", "backgroundAlt": "#rrggbb", "accent": "#rrggbb", "text": "#rrggbb" },
  "visualStyle": "b-roll / graphics description",
  "recurringElements": ["signature segment or device"],
  "callToAction": "how videos close",
  "contentPillars": ["theme"],
  "topicGaps": ["new topic this channel has not covered but its audience would want"],
  "avoid": ["thing that would make a video feel off-format"]
}

Channel: ${channel.title} (${channel.subscribers} subscribers, country ${channel.country || 'unknown'})
Channel description: ${channel.description.slice(0, 500)}
Measured stats: ${JSON.stringify({ shortsShare: stats.shortsShare, medianLongFormMinutes: stats.medianLongFormMinutes, uploadsEveryDays: stats.uploadsEveryDays, title: stats.title, topTags: stats.topTags.slice(0, 10) })}
Top-performing videos: ${JSON.stringify(samples)}
All recent titles: ${JSON.stringify(videos.map(v => v.title).slice(0, 40))}
Target market for the new videos: ${market.label}.`;
    try {
      const text = await this.ai.generateText(prompt, { maxTokens: 1800, temperature: 0.4 });
      const parsed = parseJson(text);
      if (!parsed.niche || !Array.isArray(parsed.structure)) throw new Error('style response missing niche/structure');
      return { ...parsed, source: 'ai' };
    } catch (error) {
      this.logger.warn(`Style synthesis failed, using heuristic profile: ${error.message}`);
      return { ...this.heuristicStyle(channel, stats), source: 'heuristic', error: error.message };
    }
  }
```

All three AI writers parse the reply with: strip ```json fences → drop text before the first `{` and after the last `}` → `JSON.parse` → normalize. They try up to 3 times (temperature 0.9 for cartoon/window, 0.85 for story; maxTokens 6000).
