"""Gemini wrapper: prompt files, Google Search grounding, JSON parsing, caching."""
import json
import re
import sqlite3
import time
from datetime import date


from app import cache, scrape
from app.config import PROMPTS, env

_client = None
_last_call = 0.0


def load_prompt(prompt_name: str, /, **vars) -> str:
    text = (PROMPTS / f"{prompt_name}.md").read_text(encoding="utf-8")
    vars.setdefault("today", date.today().isoformat())
    for k, v in vars.items():
        text = text.replace("{{" + k + "}}", str(v))
    return text


def parse_json(text: str):
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    for open_c, close_c in (("[", "]"), ("{", "}")):
        i, j = text.find(open_c), text.rfind(close_c)
        if i != -1 and j > i:
            try:
                return json.loads(text[i : j + 1])
            except json.JSONDecodeError:
                continue
    raise ValueError(f"model did not return JSON: {text[:200]!r}")


def _call(model: str, prompt: str, grounded: bool, min_interval: float = 1.0):
    global _client, _last_call
    from google import genai  # imported lazily: only needed where research runs
    from google.genai import types
    wait = min_interval - (time.time() - _last_call)
    if wait > 0:
        time.sleep(wait)
    _last_call = time.time()
    if _client is None:
        _client = genai.Client(api_key=env("GEMINI_API_KEY"))
    cfg = types.GenerateContentConfig(temperature=0)
    if grounded:
        cfg.tools = [types.Tool(google_search=types.GoogleSearch())]
    else:
        cfg.response_mime_type = "application/json"
    for attempt in range(4):
        try:
            resp = _client.models.generate_content(model=model, contents=prompt, config=cfg)
            break
        except Exception as e:  # rate limits / transient errors
            transient = any(s in str(e) for s in ("429", "500", "503", "UNAVAILABLE", "disconnected", "timed out"))                 or any(t in type(e).__name__ for t in ("Protocol", "Timeout", "Connect", "Read"))
            if attempt == 3 or not transient:
                raise
            time.sleep(2 ** (attempt + 1))
    uris = []
    cand = resp.candidates[0] if resp.candidates else None
    gm = getattr(cand, "grounding_metadata", None)
    for ch in getattr(gm, "grounding_chunks", None) or []:
        if ch.web and ch.web.uri:
            uris.append(ch.web.uri)
    return {"text": resp.text or "", "grounding_uris": uris}


REDIRECT = "vertexaisearch.cloud.google.com/grounding-api-redirect"


def _unwrap(conn, node, allowed: set):
    """Replace Google grounding-redirect links the model cites with their real targets.
    Only a redirect that really resolves (the search tool issued it) counts as search-sourced."""
    if isinstance(node, dict):
        for k, v in node.items():
            if isinstance(v, str) and REDIRECT in v:
                final = scrape.resolve(conn, v)
                if REDIRECT not in final:
                    node[k] = final
                    allowed.add(final)
            else:
                _unwrap(conn, v, allowed)
    elif isinstance(node, list):
        for x in node:
            _unwrap(conn, x, allowed)


def generate(conn: sqlite3.Connection, cfg: dict, prompt_name: str, grounded: bool = False, **vars):
    """Returns (parsed_json, allowed_urls): URLs that provably came from the search tool."""
    prompt = load_prompt(prompt_name, **vars)
    key = cache.make_key(cfg["model"], str(grounded), prompt)
    res = cache.get_or_set(conn, "gemini", key,
                           lambda: _call(cfg["model"], prompt, grounded, cfg.get("gemini_min_interval_s", 1.0)),
                           ttl_days=cfg.get("cache_ttl_days", 7))
    urls = set(res["grounding_uris"])
    for u in res["grounding_uris"]:
        urls.add(scrape.resolve(conn, u))
    parsed = parse_json(res["text"])
    if grounded:
        _unwrap(conn, parsed, urls)
    return parsed, urls
