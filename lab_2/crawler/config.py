from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_config(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Конфиг не найден: {path}")

    with path.open(encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    if not isinstance(cfg, dict):
        raise ValueError("Конфиг должен быть YAML-словарём")

    for section in ("db", "logic", "sources"):
        if section not in cfg:
            raise ValueError(f"В конфиге нет секции '{section}'")

    logic = cfg["logic"]
    if "delay" not in logic:
        raise ValueError("В logic обязательно поле delay")

    logic.setdefault("timeout", 20)
    logic.setdefault("user_agent", "MAI-IR-Crawler/1.0")
    logic.setdefault("max_pages", 1_000_000)
    logic.setdefault("recrawl_after_days", 7)
    logic.setdefault("max_errors_per_url", 3)

    db = cfg["db"]
    db.setdefault("documents", "documents")
    db.setdefault("frontier", "frontier")

    return cfg