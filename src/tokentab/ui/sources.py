from __future__ import annotations

from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Checkbox, Input, Static

from tokentab.config import AppConfig
from tokentab.models import SourceState
from tokentab.secrets import (
    ANTHROPIC_ADMIN,
    OPENAI_ADMIN,
    OPENROUTER,
    OPENROUTER_MGMT,
    has_secret,
    set_secret,
)

HINTS = {
    "openai": "Needs an org admin / usage-capable key, not a project inference key.",
    "anthropic": "Needs an Admin API key (sk-ant-admin01-…), not a normal API key. Claude Desktop Pro is a seat.",
    "openrouter": "Regular key for GET /api/v1/key; optional management key for credits.",
    "aider": "Reads ~/.aider/analytics.jsonl (or config path). Not billed if OpenAI/Anthropic/OpenRouter are on.",
    "seats": "User-entered subscriptions. No API.",
}


class SourcesView(Vertical):
    _suppress = False

    def compose(self):
        yield Static("Sources", classes="section-title")
        yield Static(id="source-list")
        yield Checkbox("Count aider as billing (only if it does not flow through the APIs above)", id="aider-billing")
        yield Static("Store a key (written to OS keyring; env vars still win):")
        with Horizontal(classes="key-row"):
            yield Input(placeholder="openai | anthropic | openrouter | openrouter-mgmt", id="key-name")
            yield Input(placeholder="secret", password=True, id="key-value")
            yield Button("Save key", id="save-key", variant="primary")
        yield Static(id="key-status", classes="muted")
        yield Button("Enable/disable selected source ids in the checkboxes below", disabled=True, variant="default")
        with Horizontal(id="toggles"):
            yield Checkbox("openai", id="en-openai")
            yield Checkbox("anthropic", id="en-anthropic")
            yield Checkbox("openrouter", id="en-openrouter")
            yield Checkbox("aider", id="en-aider")

    def update_from(self, sources: list[SourceState], cfg: AppConfig, status: str) -> None:
        lines = []
        for source in sources:
            flag = "on " if source.enabled else "off"
            key_ok = "—"
            if source.id == "openai":
                key_ok = "key" if has_secret(OPENAI_ADMIN) else "no key"
            elif source.id == "anthropic":
                key_ok = "key" if has_secret(ANTHROPIC_ADMIN) else "no key"
            elif source.id == "openrouter":
                key_ok = "key" if has_secret(OPENROUTER) or has_secret(OPENROUTER_MGMT) else "no key"
            elif source.id == "aider":
                key_ok = "logs"
            last = source.last_sync.isoformat(sep=" ", timespec="minutes") if source.last_sync else "never"
            err = f"  err: {source.last_error}" if source.last_error else ""
            hint = HINTS.get(source.id, "")
            lines.append(
                f"[{flag}] {source.id:12} role={source.role:8} {key_ok:6} last={last}{err}\n    {hint}"
            )
        self.query_one("#source-list", Static).update("\n".join(lines))
        self._suppress = True
        try:
            self.query_one("#aider-billing", Checkbox).value = cfg.aider.counts_as_billing
            self.query_one("#en-openai", Checkbox).value = cfg.sources.openai
            self.query_one("#en-anthropic", Checkbox).value = cfg.sources.anthropic
            self.query_one("#en-openrouter", Checkbox).value = cfg.sources.openrouter
            self.query_one("#en-aider", Checkbox).value = cfg.sources.aider
        finally:
            self._suppress = False

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        if self._suppress:
            return
        app = self.app
        if event.checkbox.id == "aider-billing":
            app.set_aider_billing(event.value)
            return
        mapping = {
            "en-openai": "openai",
            "en-anthropic": "anthropic",
            "en-openrouter": "openrouter",
            "en-aider": "aider",
        }
        source_id = mapping.get(event.checkbox.id or "")
        if source_id:
            app.toggle_source(source_id, event.value)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "save-key":
            return
        name = self.query_one("#key-name", Input).value.strip().lower()
        value = self.query_one("#key-value", Input).value.strip()
        keys = {
            "openai": OPENAI_ADMIN,
            "anthropic": ANTHROPIC_ADMIN,
            "openrouter": OPENROUTER,
            "openrouter-mgmt": OPENROUTER_MGMT,
        }
        if name not in keys or not value:
            self.query_one("#key-status", Static).update("Need a known name and a non-empty secret.")
            return
        set_secret(keys[name], value)
        self.query_one("#key-value", Input).value = ""
        self.query_one("#key-status", Static).update(f"Saved {name} to keyring.")
        self.app.refresh_dashboard()
