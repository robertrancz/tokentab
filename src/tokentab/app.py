from __future__ import annotations

from datetime import datetime
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Header, Static, TabbedContent, TabPane

from tokentab.config import AppConfig, load_config, save_config
from tokentab.db import connect, list_sources, set_source_enabled
from tokentab.demo import seed_demo
from tokentab.ledger import current_cycle_report
from tokentab.sync import sync_all, sync_message
from tokentab.ui.forecast_view import ForecastView
from tokentab.ui.models_view import ModelsView
from tokentab.ui.overview import Overview
from tokentab.ui.seats_view import SeatsView
from tokentab.ui.sources import SourcesView


def _css_path() -> Path:
    """Resolve app CSS for both source installs and PyInstaller frozen builds."""
    return Path(__file__).resolve().parent / "ui" / "app.tcss"


class TokenTabApp(App):
    TITLE = "TokenTab"
    SUB_TITLE = "local token/cost dashboard — no editor MITM"
    CSS_PATH = _css_path()
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("s", "sync_now", "Sync"),
        Binding("r", "refresh", "Refresh"),
    ]

    def __init__(
        self,
        *,
        db_path=None,
        config_path=None,
        demo: bool = False,
    ) -> None:
        super().__init__()
        self._db_path = db_path
        self._config_path = config_path
        self.demo = demo
        self.conn = connect(db_path)
        self.cfg: AppConfig = load_config(config_path)
        for source_id, enabled in (
            ("openai", self.cfg.sources.openai),
            ("anthropic", self.cfg.sources.anthropic),
            ("openrouter", self.cfg.sources.openrouter),
            ("aider", self.cfg.sources.aider),
        ):
            set_source_enabled(self.conn, source_id, enabled)
        self.status_text = "Ready"
        self.last_sync: str | None = None
        if demo:
            seed_demo(self.conn)

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent(id="tabs"):
            with TabPane("Overview", id="tab-overview"):
                yield Overview(id="overview")
            with TabPane("Models", id="tab-models"):
                yield ModelsView(id="models")
            with TabPane("Sources", id="tab-sources"):
                yield SourcesView(id="sources")
            with TabPane("Seats", id="tab-seats"):
                yield SeatsView(id="seats")
            with TabPane("Forecast", id="tab-forecast"):
                yield ForecastView(id="forecast")
        yield Static(id="status", classes="status")
        yield Footer()

    def on_mount(self) -> None:
        minutes = max(1, self.cfg.sync_interval_minutes)
        self.set_interval(minutes * 60, self._background_sync)
        self.refresh_dashboard()
        if not self.demo:
            self.run_worker(self._sync_worker, exclusive=True, thread=True)

    def report(self) -> dict:
        what_model = None
        what_tokens = None
        forecast = self.query_one("#forecast", ForecastView)
        if forecast.what_if_model and forecast.what_if_tokens:
            what_model = forecast.what_if_model
            what_tokens = forecast.what_if_tokens
        return current_cycle_report(
            self.conn,
            self.cfg,
            what_if_model=what_model,
            what_if_tokens_per_day=what_tokens,
        )

    def refresh_dashboard(self) -> None:
        data = self.report()
        self.query_one("#overview", Overview).update_from(data)
        self.query_one("#models", ModelsView).update_from(data)
        self.query_one("#sources", SourcesView).update_from(
            list_sources(self.conn), self.cfg, self.status_text
        )
        self.query_one("#seats", SeatsView).update_from(data)
        self.query_one("#forecast", ForecastView).update_from(data)
        stamp = self.last_sync or "never"
        self.query_one("#status", Static).update(
            f"{self.status_text}  ·  last sync {stamp}  ·  does not proxy Cursor, Copilot, or Claude Desktop"
        )

    def action_refresh(self) -> None:
        self.refresh_dashboard()

    def action_sync_now(self) -> None:
        self.run_worker(self._sync_worker, exclusive=True, thread=True)

    def _background_sync(self) -> None:
        self.run_worker(self._sync_worker, exclusive=True, thread=True)

    def _sync_worker(self) -> None:
        if self.demo:
            self.call_from_thread(self._after_sync, "demo data (no network)")
            return
        # Fresh connection for this worker thread — do not share self.conn.
        conn = connect(self._db_path)
        try:
            results = sync_all(conn, self.cfg)
            message = sync_message(results)
        finally:
            conn.close()
        self.call_from_thread(self._after_sync, message)

    def _after_sync(self, message: str) -> None:
        self.status_text = message
        self.last_sync = datetime.now().strftime("%H:%M:%S")
        self.refresh_dashboard()

    def persist_config(self) -> None:
        save_config(self.cfg, self._config_path)

    def toggle_source(self, source_id: str, enabled: bool) -> None:
        set_source_enabled(self.conn, source_id, enabled)
        if source_id == "openai":
            self.cfg.sources.openai = enabled
        elif source_id == "anthropic":
            self.cfg.sources.anthropic = enabled
        elif source_id == "openrouter":
            self.cfg.sources.openrouter = enabled
        elif source_id == "aider":
            self.cfg.sources.aider = enabled
        self.persist_config()
        self.refresh_dashboard()

    def set_aider_billing(self, value: bool) -> None:
        self.cfg.aider.counts_as_billing = value
        self.persist_config()
        self.refresh_dashboard()
