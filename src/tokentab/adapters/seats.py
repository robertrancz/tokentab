from __future__ import annotations

from tokentab.db import add_seat, delete_seat, list_seats, update_seat
from tokentab.models import Seat

PRESETS = [
    Seat(name="Cursor Pro", monthly_usd=20.0, notes="Seat only — included quota is not visible"),
    Seat(name="GitHub Copilot", monthly_usd=19.0, notes="Seat only"),
    Seat(name="ChatGPT Plus", monthly_usd=20.0, notes="Seat only"),
    Seat(name="Claude Pro", monthly_usd=20.0, notes="Seat only — not the Anthropic Admin API"),
]


def preset_names() -> list[str]:
    return [s.name for s in PRESETS]


def seat_from_preset(name: str) -> Seat | None:
    for seat in PRESETS:
        if seat.name.lower() == name.lower():
            return Seat(
                name=seat.name,
                monthly_usd=seat.monthly_usd,
                notes=seat.notes,
            )
    return None


__all__ = ["PRESETS", "Seat", "add_seat", "delete_seat", "list_seats", "update_seat", "preset_names", "seat_from_preset"]
