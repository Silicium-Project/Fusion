from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
REFERENCE_LOCALE = REPO_ROOT / "i18n" / "locales" / "en-US.json"


def test_reference_locale_file_structure() -> None:
    data = json.loads(REFERENCE_LOCALE.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    assert isinstance(data.get("meta"), dict)
    assert isinstance(data.get("messages"), dict)

    meta = data["meta"]
    assert meta.get("locale") == "en-US"
    assert isinstance(meta.get("fallback"), str) and meta["fallback"]
    assert meta.get("version") == 1

    messages = data["messages"]
    assert messages, "reference locale must contain at least one key"
    assert all(isinstance(key, str) and key for key in messages.keys())
    assert all(isinstance(value, str) for value in messages.values())
