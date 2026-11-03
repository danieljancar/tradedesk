"""Read and write the active config file from the dashboard. Only the trading knobs are editable;
mode, market and file paths stay file-only, so going live is always a deliberate edit by hand."""

import os
import tomllib
from pathlib import Path

from tradedesk.config import ROOT, Settings

READ_ONLY = {"mode", "market", "quote", "db_path", "runs_dir"}
EDITABLE_TABLES = {"risk", "execution", "hold_days"}


def config_path() -> Path:
    return Path(os.environ.get("DESK_CONFIG", ROOT / "desk.toml"))


def read() -> dict:
    path = config_path()
    data = tomllib.loads(path.read_text()) if path.exists() else {}
    full = Settings.model_validate(data).model_dump(mode="json")
    return {"path": str(path), "settings": full, "read_only": sorted(READ_ONLY)}


def _value(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, list):
        return "[" + ", ".join(_value(x) for x in v) + "]"
    return '"' + str(v).replace("\\", "\\\\").replace('"', '\\"') + '"'


def to_toml(data: dict) -> str:
    top = [
        f"{k} = {_value(v)}" for k, v in data.items() if not isinstance(v, dict) and v is not None
    ]
    out = ["# Written by the tradedesk dashboard.", *top]
    for k, v in data.items():
        if isinstance(v, dict):
            out += [
                "",
                f"[{k}]",
                *[f"{kk} = {_value(vv)}" for kk, vv in v.items() if vv is not None],
            ]
    return "\n".join(out) + "\n"


def update(changes: dict) -> Settings:
    """Merge editable changes into the config file, validate, write. Returns the new settings."""
    path = config_path()
    current = tomllib.loads(path.read_text()) if path.exists() else {}
    merged = dict(current)
    for key, value in changes.items():
        if key in READ_ONLY:
            raise ValueError(f"{key} can only be changed in {path.name} by hand")
        if key in EDITABLE_TABLES and isinstance(value, dict):
            merged[key] = {**current.get(key, {}), **value}
        elif key in ("watchlist", "paper_equity"):
            merged[key] = value
        else:
            raise ValueError(f"{key} is not an editable setting")
    if "watchlist" in merged:
        merged["watchlist"] = [
            str(a).upper().strip() for a in merged["watchlist"] if str(a).strip()
        ]
    new = Settings.model_validate(merged)
    path.write_text(to_toml(merged))
    return new
