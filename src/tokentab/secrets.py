from __future__ import annotations

import os

import keyring

SERVICE = "tokentab"

OPENAI_ADMIN = "openai_admin_key"
ANTHROPIC_ADMIN = "anthropic_admin_key"
OPENROUTER = "openrouter_api_key"
OPENROUTER_MGMT = "openrouter_management_key"

ENV_MAP = {
    OPENAI_ADMIN: ("TOKENTAB_OPENAI_ADMIN_KEY", "OPENAI_ADMIN_KEY"),
    ANTHROPIC_ADMIN: ("TOKENTAB_ANTHROPIC_ADMIN_KEY", "ANTHROPIC_ADMIN_KEY"),
    OPENROUTER: ("TOKENTAB_OPENROUTER_API_KEY", "OPENROUTER_API_KEY"),
    OPENROUTER_MGMT: ("TOKENTAB_OPENROUTER_MANAGEMENT_KEY", "OPENROUTER_MANAGEMENT_KEY"),
}


def get_secret(name: str) -> str | None:
    for env_name in ENV_MAP.get(name, ()):
        value = os.environ.get(env_name)
        if value:
            return value
    try:
        value = keyring.get_password(SERVICE, name)
    except Exception:
        return None
    return value or None


def set_secret(name: str, value: str) -> None:
    keyring.set_password(SERVICE, name, value)


def delete_secret(name: str) -> None:
    try:
        keyring.delete_password(SERVICE, name)
    except keyring.errors.PasswordDeleteError:
        pass


def has_secret(name: str) -> bool:
    return bool(get_secret(name))
