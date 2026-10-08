"""Reference channel: learn a channel's FORMAT and topic gaps so we make original videos in that style."""
import json
import logging
import statistics
from collections import Counter
from datetime import datetime

from . import ai, config, db, youtube

log = logging.getLogger(__name__)


def channel_stats(videos):
    if not videos:
        return {"shortsShare": 0, "medianLongFormMinutes": 0, "uploadsEveryDays": None, "topTags": [],
                "topPerformers": [], "bestWeekday": None, "bestHourUtc": None}
    shorts = [v for v in videos if v["durationSeconds"] <= 60]
    longs = [v["durationSeconds"] / 60 for v in videos if v["durationSeconds"] > 60]
    dates = sorted(datetime.fromisoformat(v["publishedAt"].replace("Z", "+00:00")) for v in videos)
    gaps = [(b - a).total_seconds() / 86400 for a, b in zip(dates, dates[1:])]
    by_views = sorted(videos, key=lambda v: v["views"], reverse=True)
    top = by_views[: max(3, len(videos) // 5)]
    tops = [datetime.fromisoformat(v["publishedAt"].replace("Z", "+00:00")) for v in top]
    return {
        "shortsShare": round(len(shorts) / len(videos), 2),
        "medianShortSeconds": statistics.median(v["durationSeconds"] for v in shorts) if shorts else None,
        "medianLongFormMinutes": round(statistics.median(longs), 1) if longs else 0,
        "uploadsEveryDays": round(statistics.median(gaps), 1) if gaps else None,
        "topTags": [t for t, _ in Counter(t.lower() for v in videos for t in v["tags"]).most_common(15)],
        "topPerformers": [{"id": v["id"], "title": v["title"], "views": v["views"]} for v in top],
        "bestWeekday": Counter(d.strftime("%A") for d in tops).most_common(1)[0][0] if tops else None,
        "bestHourUtc": Counter(d.hour for d in tops).most_common(1)[0][0] if tops else None,
    }


def heuristic_style(channel, stats):
    return {"niche": channel["snippet"]["title"], "audience": "general", "tone": "energetic", "pacing": "fast",
            "topicGaps": [], "avoid": [], "contentPillars": stats["topTags"][:5]}


def synthesize_style(channel, stats, videos, market):
    if not ai.available():
        return {**heuristic_style(channel, stats), "source": "heuristic"}
    top_ids = {v["id"] for v in stats["topPerformers"]}
    samples = [{"title": v["title"], "minutes": round(v["durationSeconds"] / 60, 1),
                "descriptionStart": v["description"][:300]} for v in videos if v["id"] in top_ids][:6]
    sn = channel["snippet"]
    prompt = f"""You are a YouTube format analyst. Describe this channel's repeatable FORMAT so a different creator could make original videos in the same style. Do not summarize or reuse its specific content.
Return only valid JSON with this exact shape:
{{
  "niche": "one line",
  "audience": "who watches, in one line",
  "promise": "the value every video delivers",
  "format": "e.g. faceless voiceover explainer with stock b-roll",
  "contentType": "Tutorial|Explainer|List|Review|Story|News",
  "hookPattern": "how the first 15 seconds work",
  "structure": ["ordered beat"],
  "tone": "voice and energy",
  "pacing": "pace and edit rhythm",
  "titleFormulas": ["pattern with {{placeholders}}, not a real title"],
  "thumbnailStyle": "visual description",
  "visualStyle": "b-roll / graphics description",
  "recurringElements": ["signature segment or device"],
  "callToAction": "how videos close",
  "contentPillars": ["theme"],
  "topicGaps": ["new topic this channel has not covered but its audience would want"],
  "avoid": ["thing that would make a video feel off-format"]
}}

Channel: {sn['title']} ({channel.get('statistics', {}).get('subscriberCount', '?')} subscribers, country {sn.get('country', 'unknown')})
Channel description: {sn.get('description', '')[:500]}
Measured stats: {json.dumps({k: stats[k] for k in ('shortsShare', 'medianLongFormMinutes', 'uploadsEveryDays')} | {'topTags': stats['topTags'][:10]})}
Top-performing videos: {json.dumps(samples)}
All recent titles: {json.dumps([v['title'] for v in videos][:40])}
Target market for the new videos: {market}."""

    def check(parsed):
        if not parsed.get("niche") or not isinstance(parsed.get("structure"), list):
            raise ValueError("style response missing niche/structure")
        return parsed
    try:
        return {**ai.generate_json(prompt, check, temperature=0.4, max_tokens=1800), "source": "ai"}
    except Exception as e:
        log.warning("Style synthesis failed, using heuristic profile: %s", e)
        return {**heuristic_style(channel, stats), "source": "heuristic", "error": str(e)}


def analyze(ref, activate=True):
    channel = youtube.resolve_channel(ref)
    videos = youtube.recent_videos(channel, 40)
    stats = channel_stats(videos)
    style = synthesize_style(channel, stats, videos, config.TARGET_AUDIENCE)
    profile = {**style, "stats": stats, "titles": [v["title"] for v in videos]}
    db.save_profile(channel["id"], channel["snippet"]["title"], profile, activate)
    return profile


def check_originality(title, profile):
    """Flag titles that share most of their words with a reference title."""
    words = {w for w in title.lower().split() if len(w) > 3}
    for t in (profile or {}).get("titles", []):
        other = {w for w in t.lower().split() if len(w) > 3}
        if words and len(words & other) / len(words) >= 0.6:
            return False, t
    return True, None
