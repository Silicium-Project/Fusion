"""Inputs of an item: texts as JSON, binary inputs (an image, a sound) as
``{"$bytes": "<base64>"}``, decoded here with bounded sizes."""

from __future__ import annotations

import base64
import binascii
import io
from typing import Any

MAX_IMAGE_PIXELS = 40_000_000
MAX_AUDIO_SECONDS = 30 * 60
AUDIO_RATE = 16_000


class InputError(ValueError):
    """An input the task cannot use (message for the user)."""


def raw_bytes(value: Any) -> bytes:
    if not isinstance(value, dict) or not isinstance(value.get("$bytes"), str):
        raise InputError('expected a file as {"$bytes": "<base64>"}')
    try:
        return base64.b64decode(value["$bytes"], validate=True)
    except (binascii.Error, ValueError) as err:
        raise InputError("invalid base64") from err


def image(value: Any):
    """A PIL image in RGB."""
    from PIL import Image

    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
    try:
        picture = Image.open(io.BytesIO(raw_bytes(value)))
        picture.load()
    except InputError:
        raise
    except Exception as err:  # PIL raises many types for a bad file.
        raise InputError(f"unreadable image: {err}") from err
    return picture.convert("RGB")


def audio(value: Any) -> dict:
    """A mono waveform at 16 kHz, as the audio pipelines take it."""
    import numpy as np
    import soundfile
    from scipy.signal import resample_poly

    try:
        samples, rate = soundfile.read(io.BytesIO(raw_bytes(value)), dtype="float32", always_2d=True)
    except InputError:
        raise
    except Exception as err:
        raise InputError(f"unreadable sound (WAV, FLAC or OGG): {err}") from err
    if len(samples) > rate * MAX_AUDIO_SECONDS:
        raise InputError("sound longer than 30 minutes")
    mono = samples.mean(axis=1)
    if rate != AUDIO_RATE:
        from math import gcd

        divisor = gcd(rate, AUDIO_RATE)
        mono = resample_poly(mono, AUDIO_RATE // divisor, rate // divisor).astype(np.float32)
    return {"raw": mono, "sampling_rate": AUDIO_RATE}


def text(value: Any, name: str = "text", max_chars: int = 20_000) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InputError(f"expected a non-empty {name}")
    if len(value) > max_chars:
        raise InputError(f"{name} longer than {max_chars} characters")
    return value


def field(value: Any, key: str) -> Any:
    if not isinstance(value, dict) or key not in value:
        raise InputError(f'expected an object with "{key}"')
    return value[key]


def texts(value: Any, name: str, max_count: int = 256) -> list[str]:
    if not isinstance(value, list) or not value or len(value) > max_count:
        raise InputError(f"expected a list of 1 to {max_count} {name}")
    return [text(item, name) for item in value]
