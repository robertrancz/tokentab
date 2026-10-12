from pathlib import Path

from tokentab.config import AppConfig, SslConfig
from tokentab.http import resolve_verify


def test_resolve_verify_defaults_true():
    assert resolve_verify(AppConfig()) is True


def test_resolve_verify_false_from_config():
    cfg = AppConfig(ssl=SslConfig(verify=False))
    assert resolve_verify(cfg) is False


def test_resolve_verify_ca_bundle_from_config(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("TOKENTAB_CA_BUNDLE", raising=False)
    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    monkeypatch.delenv("REQUESTS_CA_BUNDLE", raising=False)
    monkeypatch.delenv("TOKENTAB_SSL_VERIFY", raising=False)
    ca = tmp_path / "corp.pem"
    ca.write_text("dummy", encoding="utf-8")
    cfg = AppConfig(ssl=SslConfig(verify=True, ca_bundle=str(ca)))
    assert resolve_verify(cfg) == str(ca)


def test_resolve_verify_env_ca_wins(tmp_path: Path, monkeypatch):
    ca = tmp_path / "env.pem"
    ca.write_text("dummy", encoding="utf-8")
    monkeypatch.setenv("TOKENTAB_CA_BUNDLE", str(ca))
    cfg = AppConfig(ssl=SslConfig(verify=False))
    assert resolve_verify(cfg) == str(ca)


def test_resolve_verify_env_disable(monkeypatch):
    monkeypatch.delenv("TOKENTAB_CA_BUNDLE", raising=False)
    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    monkeypatch.delenv("REQUESTS_CA_BUNDLE", raising=False)
    monkeypatch.setenv("TOKENTAB_SSL_VERIFY", "false")
    assert resolve_verify(AppConfig()) is False
