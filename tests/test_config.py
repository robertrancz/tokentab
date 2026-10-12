from tokentab.config import config_from_dict, config_to_dict, load_config, save_config


def test_config_roundtrip(tmp_path):
    path = tmp_path / "config.toml"
    cfg = load_config(path)
    cfg.aider.counts_as_billing = True
    cfg.sources.openai = False
    cfg.forecast_days = 14
    cfg.ssl.verify = False
    cfg.ssl.ca_bundle = "C:/certs/corp-root.pem"
    save_config(cfg, path)
    loaded = load_config(path)
    assert loaded.aider.counts_as_billing is True
    assert loaded.sources.openai is False
    assert loaded.forecast_days == 14
    assert loaded.ssl.verify is False
    assert loaded.ssl.ca_bundle == "C:/certs/corp-root.pem"
    assert config_from_dict(config_to_dict(loaded)).forecast_days == 14
