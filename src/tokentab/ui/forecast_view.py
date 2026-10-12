from __future__ import annotations

from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Input, Select, Static

from tokentab.catalog import list_models


def _usd(value: float | None) -> str:
    if value is None:
        return "—"
    return f"${value:,.2f}"


class ForecastView(Vertical):
    what_if_model: str | None = None
    what_if_tokens: int | None = None

    def compose(self):
        yield Static(id="forecast-body")
        yield Static("What-if: catalog cost if you spend N tokens/day (80% input / 20% output). Estimate only.")
        with Horizontal(classes="form-row"):
            yield Select(
                options=[(m, m) for m in list_models()],
                prompt="Model",
                id="what-model",
            )
            yield Input(placeholder="Tokens per day", id="what-tokens", type="integer")
            yield Button("Apply", id="what-apply", variant="primary")
            yield Button("Clear", id="what-clear")
        yield Static(id="what-result", classes="muted")

    def update_from(self, data: dict) -> None:
        fc = data["forecast"]
        band = ""
        if fc.p25 is not None and fc.p75 is not None:
            band = f"\nBand (p25–p75 of daily burn, ≥7 days): {_usd(fc.p25)} – {_usd(fc.p75)}"
        body = (
            f"Metered MTD              {_usd(fc.metered_mtd)}\n"
            f"Seats amortized MTD      {_usd(fc.seats_amortized_mtd)}\n"
            f"Seats committed / cycle  {_usd(fc.seats_committed)}\n"
            f"Median daily burn        {_usd(fc.daily_burn)}  (confidence: {fc.confidence})\n"
            f"Remaining days           {fc.remaining_days}\n"
            f"Forecast metered         {_usd(fc.forecast_metered)}\n"
            f"Forecast + seats         {_usd(fc.forecast_with_committed_seats)}\n"
            f"{band}"
        )
        self.query_one("#forecast-body", Static).update(body.strip())
        if fc.what_if_daily_usd is not None:
            self.query_one("#what-result", Static).update(
                f"What-if {self.what_if_tokens:,} tok/day on {self.what_if_model}: "
                f"{_usd(fc.what_if_daily_usd)}/day · {_usd(fc.what_if_month_usd)}/cycle  (catalog estimate)"
            )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "what-clear":
            self.what_if_model = None
            self.what_if_tokens = None
            self.query_one("#what-result", Static).update("")
            self.app.refresh_dashboard()
            return
        if event.button.id != "what-apply":
            return
        model = self.query_one("#what-model", Select).value
        tokens = self.query_one("#what-tokens", Input).value.strip()
        if model in (Select.BLANK, None) or not tokens:
            self.query_one("#what-result", Static).update("Pick a model and tokens/day.")
            return
        self.what_if_model = str(model)
        self.what_if_tokens = int(tokens)
        self.app.refresh_dashboard()
