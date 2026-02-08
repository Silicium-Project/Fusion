from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
LOCALE_DIR = REPO_ROOT / "i18n" / "locales"

DEFAULT_LOCALE = "en-US"

_runtime_locale: str | None = None


def set_runtime_locale(locale: str | None) -> None:
    global _runtime_locale
    _runtime_locale = (locale or "").strip() or None


def _normalize_locale(raw: str | None) -> str:
    value = (raw or "").strip()
    if not value:
        return DEFAULT_LOCALE
    value = value.split(".", 1)[0].split("@", 1)[0].strip()
    if value in {"C", "POSIX"}:
        return DEFAULT_LOCALE
    return value.replace("_", "-")


def _env_locale() -> str:
    for name in ("SILICIUM_LOCALE", "LC_ALL", "LC_MESSAGES", "LANG"):
        val = os.environ.get(name)
        if val:
            return val
    return DEFAULT_LOCALE


def get_runtime_locale() -> str:
    return _normalize_locale(_runtime_locale or _env_locale())


def _locale_candidates(locale: str) -> list[str]:
    norm = _normalize_locale(locale)
    lang = norm.split("-", 1)[0]
    out: list[str] = []
    for cand in (norm, lang, DEFAULT_LOCALE):
        if cand and cand not in out:
            out.append(cand)
    return out


@lru_cache(maxsize=32)
def _load_messages(locale: str) -> dict[str, str]:
    path = LOCALE_DIR / f"{locale}.json"
    if not path.exists():
        return {}
    payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    messages = payload.get("messages", {})
    if isinstance(messages, dict):
        return {str(k): str(v) for k, v in messages.items() if isinstance(v, str)}
    return {}


def tr(key: str, *args: Any, locale: str | None = None, **kwargs: Any) -> str:
    loc = _normalize_locale(locale) if locale is not None else get_runtime_locale()
    for cand in _locale_candidates(loc):
        msg = _load_messages(cand).get(key)
        if not msg:
            continue
        if not args and not kwargs:
            return msg
        if kwargs:
            try:
                return msg.format(**kwargs)
            except Exception:
                return msg
        if "{" in msg:
            try:
                return msg.format(*args)
            except Exception:
                return msg
        if "%" in msg:
            try:
                return msg % (args[0] if len(args) == 1 else args)
            except Exception:
                return msg
        return msg
    return f"[missing:{key}]"

