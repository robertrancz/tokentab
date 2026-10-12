from __future__ import annotations

import json
from functools import lru_cache
from importlib.resources import files

from tokentab.models import PriceRate

DEFAULT_RATES: dict[str, dict[str, float]] = {
    "gpt-4o": {"input": 2.5, "output": 10.0, "cache_read": 1.25},
    "gpt-4o-mini": {"input": 0.15, "output": 0.6, "cache_read": 0.075},
    "gpt-4.1": {"input": 2.0, "output": 8.0, "cache_read": 0.5},
    "gpt-4.1-mini": {"input": 0.4, "output": 1.6, "cache_read": 0.1},
    "gpt-4.1-nano": {"input": 0.1, "output": 0.4, "cache_read": 0.025},
    "gpt-5": {"input": 1.25, "output": 10.0, "cache_read": 0.125},
    "gpt-5-mini": {"input": 0.25, "output": 2.0, "cache_read": 0.025},
    "o3": {"input": 2.0, "output": 8.0, "cache_read": 0.5},
    "o4-mini": {"input": 1.1, "output": 4.4, "cache_read": 0.275},
    "claude-sonnet-4-5": {"input": 3.0, "output": 15.0, "cache_read": 0.3, "cache_write": 3.75},
    "claude-sonnet-4": {"input": 3.0, "output": 15.0, "cache_read": 0.3, "cache_write": 3.75},
    "claude-3-5-sonnet": {"input": 3.0, "output": 15.0, "cache_read": 0.3, "cache_write": 3.75},
    "claude-3-7-sonnet": {"input": 3.0, "output": 15.0, "cache_read": 0.3, "cache_write": 3.75},
    "claude-opus-4": {"input": 15.0, "output": 75.0, "cache_read": 1.5, "cache_write": 18.75},
    "claude-opus-4-1": {"input": 15.0, "output": 75.0, "cache_read": 1.5, "cache_write": 18.75},
    "claude-3-5-haiku": {"input": 0.8, "output": 4.0, "cache_read": 0.08, "cache_write": 1.0},
    "claude-haiku-4-5": {"input": 1.0, "output": 5.0, "cache_read": 0.1, "cache_write": 1.25},
    "gemini-2.5-pro": {"input": 1.25, "output": 10.0, "cache_read": 0.315},
    "gemini-2.5-flash": {"input": 0.3, "output": 2.5, "cache_read": 0.075},
    "gemini-2.0-flash": {"input": 0.1, "output": 0.4, "cache_read": 0.025},
}


def _normalize_name(model: str) -> str:
    name = model.strip().lower()
    for prefix in (
        "openai/",
        "anthropic/",
        "google/",
        "openrouter/",
        "claude/",
        "models/",
    ):
        if name.startswith(prefix):
            name = name[len(prefix) :]
    if name.startswith("claude") and "claude-" not in name[:8]:
        pass
    return name


@lru_cache(maxsize=1)
def load_catalog() -> dict[str, PriceRate]:
    catalog: dict[str, PriceRate] = {}
    for name, raw in DEFAULT_RATES.items():
        catalog[_normalize_name(name)] = _rate_from_dict(raw, "bundled")
    try:
        payload = files("tokentab.data").joinpath("prices.json").read_text(encoding="utf-8")
        overlay = json.loads(payload)
        for name, raw in overlay.items():
            catalog[_normalize_name(name)] = _rate_from_dict(raw, "prices.json")
    except (FileNotFoundError, ModuleNotFoundError, OSError, json.JSONDecodeError):
        pass
    return catalog


def _rate_from_dict(raw: dict[str, float], origin: str) -> PriceRate:
    return PriceRate(
        input_per_m=float(raw.get("input", 0)),
        output_per_m=float(raw.get("output", 0)),
        cache_read_per_m=float(raw.get("cache_read", raw.get("input", 0) * 0.1)),
        cache_write_per_m=float(raw.get("cache_write", raw.get("input", 0) * 1.25)),
        origin=origin,
    )


def lookup_rate(model: str) -> PriceRate | None:
    catalog = load_catalog()
    key = _normalize_name(model)
    if key in catalog:
        return catalog[key]
    for name, rate in catalog.items():
        if key.endswith(name) or name.endswith(key) or name in key:
            return rate
    return None


def list_models() -> list[str]:
    return sorted(load_catalog().keys())
