from __future__ import annotations

from textual.containers import Horizontal, Vertical
from textual.widgets import Static


def _usd(value: float | None) -> str:
    if value is None:
        return "—"
    return f"${value:,.2f}"


def _spark(values: list[float], width: int = 28) -> str:
    if not values:
        return "·" * min(width, 8)
    blocks = "▁▂▃▄▅▆▇█"
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1.0
    chars = []
    for value in values[-width:]:
        idx = int((value - lo) / span * (len(blocks) - 1))
        chars.append(blocks[idx])
    return "".join(chars)


class Overview(Vertical):
    def compose(self):
        with Horizontal(classes="kpi-row"):
            yield Static("Metered MTD\n—", id="kpi-metered", classes="kpi")
            yield Static("Seats (amortized)\n—", id="kpi-seats", classes="kpi")
            yield Static("Forecast (seats committed)\n—", id="kpi-forecast", classes="kpi")
            yield Static("Daily burn\n—", id="kpi-burn", classes="kpi")
        yield Static("", id="spark")
        yield Static("", id="sources-bars")
        yield Static("", id="tokens-line")
        yield Static("", id="basis-line", classes="muted")

    def update_from(self, data: dict) -> None:
        fc = data["forecast"]
        self.query_one("#kpi-metered", Static).update(
            f"Metered MTD\n{_usd(fc.metered_mtd)}"
        )
        self.query_one("#kpi-seats", Static).update(
            f"Seats (amortized)\n{_usd(fc.seats_amortized_mtd)}"
        )
        self.query_one("#kpi-forecast", Static).update(
            f"Forecast (seats committed)\n{_usd(fc.forecast_with_committed_seats)}"
        )
        self.query_one("#kpi-burn", Static).update(
            f"Daily burn\n{_usd(fc.daily_burn)}  ({fc.confidence})"
        )
        daily_vals = [float(v) for _, v in sorted(data["daily"].items())]
        self.query_one("#spark", Static).update(
            f"Daily metered  { _spark(daily_vals) }  cycle {data['cycle_start']} → {data['cycle_end']}"
        )
        bars = []
        items = sorted(data["by_source"].items(), key=lambda kv: kv[1], reverse=True)
        max_v = max((v for _, v in items), default=1) or 1
        for name, value in items:
            width = max(1, int(value / max_v * 24))
            bars.append(f"{name:12} {'█' * width} {_usd(value)}")
        activity = data.get("activity_by_source") or {}
        if activity:
            bars.append("")
            bars.append("Activity (not billed unless aider.counts_as_billing)")
            for name, value in sorted(activity.items(), key=lambda kv: kv[1], reverse=True):
                bars.append(f"{name:12} {_usd(value)}")
        self.query_one("#sources-bars", Static).update("\n".join(bars) or "No billed usage yet.")
        tok = data["tokens"]
        self.query_one("#tokens-line", Static).update(
            f"Tokens  in {tok['input']:,}  out {tok['output']:,}  cache-read {tok['cache_read']:,}  total {tok['total']:,}"
        )
        ev = data["estimated_vs_vendor"]
        self.query_one("#basis-line", Static).update(
            f"Vendor-reported {_usd(ev['vendor'])}  ·  catalog estimate {_usd(ev['estimated'])}  ·  billed sources: {', '.join(data['billing_sources']) or 'none'}"
        )
