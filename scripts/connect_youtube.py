"""One-time YouTube sign-in. Needs config/client_secret.json (OAuth client, type Desktop) from Google Cloud."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ytauto import config, youtube  # noqa: E402

if __name__ == "__main__":
    youtube.connect()
    print(f"Connected. Token saved to {config.YOUTUBE_TOKEN_FILE} (keep it private; it is git-ignored).")
