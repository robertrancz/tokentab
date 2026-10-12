from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]

from tokentab.paths import config_path


@dataclass
class AiderConfig:
    counts_as_billing: bool = False
    analytics_log: str = ""
    history_dirs: list[str] = field(default_factory=list)


@dataclass
class SourcesConfig:
    openai: bool = True
    anthropic: bool = True
    openrouter: bool = True
    aider: bool = True


@dataclass
class SslConfig:
    """TLS settings for vendor HTTPS calls (corporate SSL inspection)."""

    verify: bool = True
    ca_bundle: str = ""


@dataclass
class AppConfig:
    forecast_days: int = 7
    sync_interval_minutes: int = 15
    billing_cycle_day: int = 1
    aider: AiderConfig = field(default_factory=AiderConfig)
    sources: SourcesConfig = field(default_factory=SourcesConfig)
    ssl: SslConfig = field(default_factory=SslConfig)


def _toml_dumps(data: dict[str, Any]) -> str:
    lines: list[str] = []

    def emit_table(name: str, table: dict[str, Any]) -> None:
        lines.append(f"[{name}]")
        for key, value in table.items():
            lines.append(f"{key} = {_format_value(value)}")
        lines.append("")

    general = {
        "forecast_days": data["forecast_days"],
        "sync_interval_minutes": data["sync_interval_minutes"],
        "billing_cycle_day": data["billing_cycle_day"],
    }
    emit_table("general", general)
    emit_table("aider", data["aider"])
    emit_table("sources", data["sources"])
    emit_table("ssl", data["ssl"])
    return "\n".join(lines).rstrip() + "\n"


def _format_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        inner = ", ".join(_format_value(v) for v in value)
        return f"[{inner}]"
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def default_config() -> AppConfig:
    return AppConfig()


def config_to_dict(cfg: AppConfig) -> dict[str, Any]:
    return {
        "forecast_days": cfg.forecast_days,
        "sync_interval_minutes": cfg.sync_interval_minutes,
        "billing_cycle_day": cfg.billing_cycle_day,
        "aider": {
            "counts_as_billing": cfg.aider.counts_as_billing,
            "analytics_log": cfg.aider.analytics_log,
            "history_dirs": list(cfg.aider.history_dirs),
        },
        "sources": {
            "openai": cfg.sources.openai,
            "anthropic": cfg.sources.anthropic,
            "openrouter": cfg.sources.openrouter,
            "aider": cfg.sources.aider,
        },
        "ssl": {
            "verify": cfg.ssl.verify,
            "ca_bundle": cfg.ssl.ca_bundle,
        },
    }


def config_from_dict(raw: dict[str, Any]) -> AppConfig:
    general = raw.get("general", raw)
    aider_raw = raw.get("aider", {})
    sources_raw = raw.get("sources", {})
    ssl_raw = raw.get("ssl", {})
    return AppConfig(
        forecast_days=int(general.get("forecast_days", 7)),
        sync_interval_minutes=int(general.get("sync_interval_minutes", 15)),
        billing_cycle_day=int(general.get("billing_cycle_day", 1)),
        aider=AiderConfig(
            counts_as_billing=bool(aider_raw.get("counts_as_billing", False)),
            analytics_log=str(aider_raw.get("analytics_log", "")),
            history_dirs=list(aider_raw.get("history_dirs", [])),
        ),
        sources=SourcesConfig(
            openai=bool(sources_raw.get("openai", True)),
            anthropic=bool(sources_raw.get("anthropic", True)),
            openrouter=bool(sources_raw.get("openrouter", True)),
            aider=bool(sources_raw.get("aider", True)),
        ),
        ssl=SslConfig(
            verify=bool(ssl_raw.get("verify", True)),
            ca_bundle=str(ssl_raw.get("ca_bundle", "")),
        ),
    )


def save_config(cfg: AppConfig, path: Path | None = None) -> Path:
    target = path or config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_toml_dumps(config_to_dict(cfg)), encoding="utf-8")
    return target


def load_config(path: Path | None = None) -> AppConfig:
    target = path or config_path()
    if not target.exists():
        cfg = default_config()
        save_config(cfg, target)
        return cfg
    raw = tomllib.loads(target.read_text(encoding="utf-8"))
    return config_from_dict(raw)
