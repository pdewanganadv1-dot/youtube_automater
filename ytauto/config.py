"""Environment-driven configuration. Names match HANDOVER.md §6 where they carry over."""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:  # python-dotenv is optional
    pass

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.getenv("DATA_DIR", ROOT / "data"))
FONTS = ROOT / "assets" / "fonts"


def env(name, default=""):
    return os.getenv(name, default)


def env_int(name, default):
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def env_on(name, default="on"):
    return os.getenv(name, default).strip().lower() in ("1", "on", "true", "yes")


# AI
GEMINI_API_KEY = env("GEMINI_API_KEY")
GEMINI_MODEL = env("GEMINI_MODEL", "gemini-flash-lite-latest")
GEMINI_FALLBACK_MODELS = [m.strip() for m in env("GEMINI_FALLBACK_MODELS", "gemini-flash-latest").split(",") if m.strip()]
GEMINI_TTS_MODEL = env("GEMINI_TTS_MODEL", "gemini-2.5-flash-preview-tts")
GEMINI_IMAGE_MODEL = env("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image")

# YouTube
YOUTUBE_API_KEY = env("YOUTUBE_API_KEY")
YOUTUBE_CLIENT_SECRETS = Path(env("YOUTUBE_CLIENT_SECRETS", ROOT / "config" / "client_secret.json"))
YOUTUBE_TOKEN_FILE = Path(env("YOUTUBE_TOKEN_FILE", ROOT / "config" / "youtube_token.json"))
YOUTUBE_PRIVACY = env("YOUTUBE_PRIVACY", "private")  # unverified OAuth apps can only upload private
TARGET_AUDIENCE = env("TARGET_AUDIENCE", "United States")

# Voices
CARTOON_TTS = env("CARTOON_TTS", "auto")  # auto | piper | gemini
CARTOON_VOICES = env_on("CARTOON_VOICES", "on")
PIPER_PYTHON = env("PIPER_PYTHON", str(ROOT / ".voices" / "bin" / "python"))
PIPER_MODEL = Path(env("PIPER_MODEL", DATA / "voices" / "en_US-libritts_r-medium.onnx"))

# Scheduler
SHORTS_CONTINUOUS = env_on("SHORTS_CONTINUOUS", "on")
SHORTS_SCHEDULE = env("SHORTS_SCHEDULE", "10 */4 * * *")
SHORTS_MAX_PENDING = env_int("SHORTS_MAX_PENDING", 8)
SHORTS_PUBLISH_GAP_HOURS = env_int("SHORTS_PUBLISH_GAP_HOURS", 4)
SHORTS_FIRST_RUN_DELAY_S = env_int("SHORTS_FIRST_RUN_DELAY_S", 90)

# Story format
STORY_IMAGES = env("STORY_IMAGES", "auto")  # auto | pollinations | gemini | builtin
POLLINATIONS_MODEL = env("POLLINATIONS_MODEL", "flux")
STORY_IMAGE_TIMEOUT_S = env_int("STORY_IMAGE_TIMEOUT_S", 90)
STORY_FPS = env_int("STORY_FPS", 30)
STORY_MAX_SECONDS = env_int("STORY_MAX_SECONDS", 90)
STORY_X264_PRESET = env("STORY_X264_PRESET", "veryfast")

for sub in ("videos", "audio", "thumbnails", "temp", "story/images", "voices", "tts"):
    (DATA / sub).mkdir(parents=True, exist_ok=True)
