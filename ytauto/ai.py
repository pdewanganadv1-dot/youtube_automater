"""Gemini text generation over REST, with model fallback and tolerant JSON parsing."""
import json
import logging
import re

import requests

from . import config

log = logging.getLogger(__name__)
API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class AIUnavailable(RuntimeError):
    pass


def available():
    return bool(config.GEMINI_API_KEY)


def generate_text(prompt, temperature=0.7, max_tokens=6000, json_mode=False, timeout=90):
    if not available():
        raise AIUnavailable("GEMINI_API_KEY is not set")
    gen = {"temperature": temperature, "maxOutputTokens": max_tokens}
    if json_mode:
        gen["responseMimeType"] = "application/json"
    body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}], "generationConfig": gen}
    errors = []
    for model in [config.GEMINI_MODEL, *config.GEMINI_FALLBACK_MODELS]:
        try:
            r = requests.post(API.format(model=model), json=body, timeout=timeout,
                              headers={"x-goog-api-key": config.GEMINI_API_KEY})
            if r.status_code >= 500 or r.status_code == 429:
                errors.append(f"{model}: HTTP {r.status_code}")
                continue
            r.raise_for_status()
            parts = r.json()["candidates"][0]["content"]["parts"]
            return "".join(p.get("text", "") for p in parts)
        except (requests.Timeout, requests.ConnectionError) as e:
            errors.append(f"{model}: {e.__class__.__name__}")
        except (KeyError, IndexError) as e:
            errors.append(f"{model}: empty response ({e})")
    raise RuntimeError("All Gemini models failed: " + "; ".join(errors))


def parse_json(text):
    """Strip ```json fences, keep the outermost {...}, parse."""
    t = re.sub(r"```(?:json)?", "", text or "").strip()
    start, end = t.find("{"), t.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object in reply")
    return json.loads(t[start:end + 1])


def generate_json(prompt, normalize, temperature=0.85, attempts=3, max_tokens=6000):
    """Ask for JSON up to `attempts` times; `normalize` validates and may raise ValueError."""
    last = None
    for i in range(attempts):
        try:
            return normalize(parse_json(generate_text(prompt, temperature, max_tokens, json_mode=True)))
        except (ValueError, json.JSONDecodeError) as e:
            last = e
            log.warning("AI JSON attempt %d failed: %s", i + 1, e)
    raise RuntimeError(f"AI did not return usable JSON after {attempts} attempts: {last}")
