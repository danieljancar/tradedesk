import tomllib

import pytest
from pydantic import ValidationError

from tradedesk import config, settings_io
from tradedesk.config import RiskLimits, Settings
from tradedesk.profiles import PROFILES


def test_every_profile_has_a_drawdown_pause_and_balanced_is_the_default():
    assert all("max_drawdown_pct" in p for p in PROFILES.values())
    defaults = RiskLimits().model_dump()
    assert all(defaults[k] == v for k, v in PROFILES["balanced"].items())


def test_profile_fills_and_explicit_keys_win():
    s = Settings.model_validate({"risk": {"profile": "aggressive", "max_open_positions": 5}})
    assert s.risk.risk_per_trade_pct == 2.0
    assert s.risk.max_drawdown_pct == 25.0
    assert s.risk.max_open_positions == 5
    assert s.risk.min_stop_atr == 0.5
    with pytest.raises(ValidationError):
        Settings.model_validate({"risk": {"profile": "yolo"}})


def test_settings_and_settings_io_agree(tmp_path, monkeypatch):
    cfg = tmp_path / "desk.toml"
    cfg.write_text('[risk]\nprofile = "conservative"\nmin_confidence = 70\n')
    monkeypatch.setenv("DESK_CONFIG", str(cfg))
    config.settings.cache_clear()
    try:
        loaded = config.settings().risk
    finally:
        config.settings.cache_clear()
    shown = settings_io.read()["settings"]["risk"]
    assert loaded.risk_per_trade_pct == shown["risk_per_trade_pct"] == 0.5
    assert loaded.min_confidence == shown["min_confidence"] == 70


def test_round_trip_writes_only_what_differs_from_the_profile(tmp_path, monkeypatch):
    cfg = tmp_path / "desk.toml"
    cfg.write_text('mode = "paper"\n[risk]\nprofile = "conservative"\nmin_confidence = 70\n')
    monkeypatch.setenv("DESK_CONFIG", str(cfg))
    echoed = settings_io.read()["settings"]["risk"] | {"profile": "aggressive"}
    new = settings_io.update({"risk": echoed})
    assert new.risk.profile == "aggressive"
    assert new.risk.risk_per_trade_pct == 2.0
    assert new.risk.min_confidence == 70
    risk = tomllib.loads(cfg.read_text())["risk"]
    assert risk == {"profile": "aggressive", "min_confidence": 70}

    new = settings_io.update({"risk": {"risk_per_trade_pct": 2.0, "max_leverage": 4}})
    assert tomllib.loads(cfg.read_text())["risk"] == {
        "profile": "aggressive",
        "min_confidence": 70,
        "max_leverage": 4,
    }
    assert new.risk.max_leverage == 4


def test_portfolio_table_round_trips(tmp_path, monkeypatch):
    cfg = tmp_path / "desk.toml"
    cfg.write_text("")
    monkeypatch.setenv("DESK_CONFIG", str(cfg))
    new = settings_io.update(
        {"portfolio": {"core_pct": 30, "core_targets": {"btc": 60, "PAXG": 40}}}
    )
    assert new.portfolio.core_targets == {"BTC": 60, "PAXG": 40}
    again = Settings.model_validate(tomllib.loads(cfg.read_text()))
    assert again.portfolio == new.portfolio
    with pytest.raises(ValidationError):
        settings_io.update({"portfolio": {"core_targets": {"BTC": 50}}})
