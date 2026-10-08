"""YouTube Data API v3: OAuth (installed-app flow), uploads, and public channel reads for reference analysis."""
import logging
import re

import requests

from . import config

log = logging.getLogger(__name__)
SCOPES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.readonly"]
API = "https://www.googleapis.com/youtube/v3"


# OAuth + upload
def connect():
    """Run the browser consent flow once and store the refresh token (scripts/connect_youtube.py calls this)."""
    from google_auth_oauthlib.flow import InstalledAppFlow
    if not config.YOUTUBE_CLIENT_SECRETS.exists():
        raise FileNotFoundError(f"Put your OAuth client JSON at {config.YOUTUBE_CLIENT_SECRETS}")
    flow = InstalledAppFlow.from_client_secrets_file(str(config.YOUTUBE_CLIENT_SECRETS), SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")
    config.YOUTUBE_TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.YOUTUBE_TOKEN_FILE.write_text(creds.to_json())
    return creds


def _credentials():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    if not config.YOUTUBE_TOKEN_FILE.exists():
        raise RuntimeError("YouTube is not connected: run `python scripts/connect_youtube.py`")
    creds = Credentials.from_authorized_user_file(str(config.YOUTUBE_TOKEN_FILE), SCOPES)
    if not creds.valid:
        creds.refresh(Request())  # Testing-mode refresh tokens expire after 7 days; reconnect if this fails
        config.YOUTUBE_TOKEN_FILE.write_text(creds.to_json())
    return creds


def connected():
    return config.YOUTUBE_TOKEN_FILE.exists()


def upload(video_path, title, description, tags, made_for_kids=False, thumb_path=None):
    """videos.insert (~1600 quota units). Returns the YouTube video id."""
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    yt = build("youtube", "v3", credentials=_credentials(), cache_discovery=False)
    body = {
        "snippet": {"title": title[:100], "description": description[:4900], "tags": tags[:15], "categoryId": "24"},
        "status": {"privacyStatus": config.YOUTUBE_PRIVACY, "selfDeclaredMadeForKids": bool(made_for_kids)},
    }
    req = yt.videos().insert(part="snippet,status", body=body,
                             media_body=MediaFileUpload(video_path, mimetype="video/mp4", resumable=True))
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    vid = resp["id"]
    if thumb_path:
        try:
            yt.thumbnails().set(videoId=vid, media_body=MediaFileUpload(thumb_path)).execute()
        except Exception as e:  # custom thumbnails need a verified channel; not fatal
            log.info("Thumbnail not set: %s", e)
    return vid


# public reads (API key)
def _get(path, **params):
    if not config.YOUTUBE_API_KEY:
        raise RuntimeError("YOUTUBE_API_KEY is not set")
    r = requests.get(f"{API}/{path}", params={**params, "key": config.YOUTUBE_API_KEY}, timeout=30)
    r.raise_for_status()
    return r.json()


def resolve_channel(ref):
    """Accept @handle, channel id (UC...), or a channel URL."""
    ref = ref.strip()
    m = re.search(r"(UC[\w-]{22})", ref)
    if m:
        params = {"id": m.group(1)}
    else:
        handle = re.search(r"@([\w.-]+)", ref)
        params = {"forHandle": "@" + (handle.group(1) if handle else ref.lstrip("@"))}
    items = _get("channels", part="snippet,statistics,contentDetails", **params).get("items") or []
    if not items:
        raise ValueError(f"Channel not found: {ref}")
    return items[0]


def iso_duration(s):
    m = re.match(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", s or "")
    if not m:
        return 0
    d, h, mi, se = (int(x or 0) for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + se


def recent_videos(channel, n=40):
    uploads = channel["contentDetails"]["relatedPlaylists"]["uploads"]
    items = _get("playlistItems", part="contentDetails", playlistId=uploads, maxResults=min(50, n)).get("items", [])
    ids = [i["contentDetails"]["videoId"] for i in items]
    if not ids:
        return []
    vids = _get("videos", part="snippet,contentDetails,statistics", id=",".join(ids)).get("items", [])
    return [{
        "id": v["id"], "title": v["snippet"]["title"], "description": v["snippet"].get("description", ""),
        "publishedAt": v["snippet"]["publishedAt"], "tags": v["snippet"].get("tags", []),
        "durationSeconds": iso_duration(v["contentDetails"]["duration"]),
        "views": int(v["statistics"].get("viewCount", 0)),
    } for v in vids]
