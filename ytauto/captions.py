"""Word-by-word ASS captions for narrated stories (HANDOVER.md §3c "Captions (ASS)")."""
import re

from . import config

# style: font, size, bold, primary, highlight, outline, shadow, case, words per group, effect
STYLES = {
    "bold_stroke": dict(font="Poppins", size=112, bold=1, primary="&H00FFFFFF", hi=None, outline=10, shadow=3,
                        case="upper", group=2, effect="pop"),
    "red_highlight": dict(font="Poppins", size=100, bold=1, primary="&H00FFFFFF", hi="&H003C3CF0&", outline=8,
                          shadow=3, case="upper", group=3, effect="word"),
    "karaoke": dict(font="Poppins", size=92, bold=1, primary="&H00FFFFFF", hi="&H0000E5FF&", outline=8, shadow=2,
                    case="as_is", group=4, effect="karaoke"),
    "beast": dict(font="Anton", size=150, bold=0, primary="&H00FFFFFF", hi="&H0000F0FF&", outline=11, shadow=6,
                  case="upper", group=1, effect="beast"),
    "sleek": dict(font="Poppins", size=70, bold=1, primary="&H00FFFFFF", hi=None, outline=0, shadow=4,
                  case="lower", group=4, effect=None),
    "majestic": dict(font="Lora", size=88, bold=1, primary="&H0066D4F5", hi=None, outline=6, shadow=4,
                     case="as_is", group=3, effect="reveal"),
    "comic": dict(font="Bangers", size=118, bold=0, primary="&H00FFFFFF", hi="&H0000D7FF&", outline=10, shadow=5,
                  case="upper", group=2, effect="comic"),
}
FALLBACK_FONT = "DejaVu Sans"


def available_font(name, language="en"):
    """Use the bundled font when present (run scripts/fetch_fonts.py), otherwise a system font."""
    if language == "hi":
        name = "Poppins"
    if any(p.stem.lower().startswith(name.lower().replace(" ", "")) for p in config.FONTS.glob("*.ttf")):
        return name
    return FALLBACK_FONT


def _ts(sec):
    cs = int(round(max(0.0, sec) * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def word_times(text, start, end):
    """Split [start, end] across words, weighted by letters + 2 (+4 after sentence ends, +2 after commas)."""
    words = text.split()
    if not words:
        return []
    weights = []
    for w in words:
        k = len(re.sub(r"\W", "", w)) + 2
        if re.search(r"[.!?…]$", w):
            k += 4
        elif re.search(r"[,;:]$", w):
            k += 2
        weights.append(k)
    total, t, out = sum(weights), start, []
    for w, k in zip(words, weights):
        d = (end - start) * k / total
        out.append((w, t, t + d))
        t += d
    return out


def groups(timed, size):
    """Chunk words into groups of `size` that never straddle a sentence end."""
    out, cur = [], []
    for item in timed:
        cur.append(item)
        if len(cur) >= size or re.search(r"[.!?…]$", item[0]):
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


def _case(word, case):
    return word.upper() if case == "upper" else word.lower() if case == "lower" else word


def build_ass(scenes, style_name="bold_stroke", language="en"):
    """scenes: [{"narration", "start", "end"}] (voice timing). Returns ASS file text."""
    st = STYLES.get(style_name, STYLES["bold_stroke"])
    font = available_font(st["font"], language)
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{font},{st['size']},{st['primary']},{(st['hi'] or st['primary']).rstrip('&')},&H00000000,&H96000000,{-1 if st['bold'] else 0},0,0,0,100,100,1,0,1,{st['outline']},{st['shadow']},5,60,60,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    pos = r"\an5\pos(540,1290)"
    gi = 0
    for sc in scenes:
        for grp in groups(word_times(sc["narration"], sc["start"], sc["end"]), st["group"]):
            g0, g1 = grp[0][1], grp[-1][2]
            words = [_case(w, st["case"]) for w, _, _ in grp]
            eff = st["effect"]
            if eff == "karaoke":
                body = " ".join(rf"{{\kf{int((e - s) * 100)}}}{w}" for w, (_, s, e) in zip(words, grp))
                lines.append((g0, g1, f"{{{pos}}}{body}"))
            elif eff in ("word", "comic"):
                for i, (_, s, e) in enumerate(grp):
                    parts = []
                    for j, w in enumerate(words):
                        if i == j:
                            extra = r"\fscx108\fscy108" if eff == "word" else rf"\frz{2 if i % 2 else -2}"
                            parts.append(rf"{{\1c{st['hi']}{extra}}}{w}{{\r}}")
                        else:
                            parts.append(w)
                    end = grp[i + 1][1] if i + 1 < len(grp) else g1
                    lines.append((s, end, f"{{{pos}}}" + " ".join(parts)))
            elif eff == "reveal":
                for i, (_, s, _e) in enumerate(grp):
                    end = grp[i + 1][1] if i + 1 < len(grp) else g1
                    shown = " ".join(words[: i + 1])
                    lines.append((s, end, rf"{{{pos}\fad(120,0)}}{shown}"))
            elif eff == "beast":
                colour = rf"\1c{st['hi']}" if gi % 3 == 2 else ""
                lines.append((g0, g1, rf"{{{pos}{colour}\fscx120\fscy120\t(0,90,\fscx100\fscy100)}}" + " ".join(words)))
            elif eff == "pop":
                lines.append((g0, g1, rf"{{{pos}\fscx90\fscy90\t(0,80,\fscx100\fscy100)}}" + " ".join(words)))
            else:
                lines.append((g0, g1, f"{{{pos}}}" + " ".join(words)))
            gi += 1
    return head + "".join(f"Dialogue: 0,{_ts(a)},{_ts(b)},Cap,,0,0,0,,{t}\n" for a, b, t in lines)
