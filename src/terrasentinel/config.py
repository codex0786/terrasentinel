"""Configuration loading. Credentials come only from the environment, never from YAML."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = REPO_ROOT / "configs"


def load_yaml(name: str, config_dir: Path = CONFIG_DIR) -> dict[str, Any]:
    path = config_dir / name
    with path.open() as f:
        return yaml.safe_load(f)


def load_dotenv(path: Path = REPO_ROOT / ".env") -> None:
    """Minimal .env reader; does not override variables already set in the environment."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(
            f"Environment variable {name} is not set. Copy .env.example to .env and fill it in."
        )
    return value


def data_dir() -> Path:
    return Path(os.environ.get("TERRASENTINEL_DATA_DIR", REPO_ROOT / "data")).resolve()
