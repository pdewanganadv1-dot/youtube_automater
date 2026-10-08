"""Download the caption fonts (SIL Open Font License) into assets/fonts."""
import sys
from pathlib import Path

import requests

FONTS = {
    "Poppins-Bold.ttf": "ofl/poppins/Poppins-Bold.ttf",
    "Anton-Regular.ttf": "ofl/anton/Anton-Regular.ttf",
    "Bangers-Regular.ttf": "ofl/bangers/Bangers-Regular.ttf",
    "BebasNeue-Regular.ttf": "ofl/bebasneue/BebasNeue-Regular.ttf",
    "Lora[wght].ttf": "ofl/lora/Lora%5Bwght%5D.ttf",
    "PatrickHand-Regular.ttf": "ofl/patrickhand/PatrickHand-Regular.ttf",
}
BASE = "https://raw.githubusercontent.com/google/fonts/main/"
OUT = Path(__file__).resolve().parent.parent / "assets" / "fonts"

if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    failed = 0
    for name, path in FONTS.items():
        dest = OUT / name
        if dest.exists():
            continue
        try:
            r = requests.get(BASE + path, timeout=60)
            r.raise_for_status()
            dest.write_bytes(r.content)
            print("downloaded", name)
        except Exception as e:
            failed += 1
            print("failed", name, e)
    sys.exit(1 if failed else 0)
