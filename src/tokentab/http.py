from __future__ import annotations

import os
from pathlib import Path

import httpx

from tokentab.config import AppConfig


def resolve_verify(cfg: AppConfig | None = None) -> bool | str:
    """Return httpx ``verify`` value from env / config.

    Corporate SSL inspection often injects a self-signed root. Prefer pointing
    at that CA bundle; ``verify=false`` is a last resort.
    """
    for env_name in ("TOKENTAB_CA_BUNDLE", "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE"):
        path = os.environ.get(env_name, "").strip()
        if path and Path(path).is_file():
            return path

    if cfg is not None:
        if cfg.ssl.ca_bundle:
            path = Path(cfg.ssl.ca_bundle).expanduser()
            if path.is_file():
                return str(path)
        if not cfg.ssl.verify:
            return False

    insecure = os.environ.get("TOKENTAB_SSL_VERIFY", "").strip().lower()
    if insecure in {"0", "false", "no", "off"}:
        return False

    return True


def make_client(
    cfg: AppConfig | None = None,
    *,
    timeout: float = 30.0,
) -> httpx.Client:
    return httpx.Client(timeout=timeout, verify=resolve_verify(cfg))
