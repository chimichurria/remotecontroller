from __future__ import annotations

import os
import secrets
import sys
from dataclasses import dataclass, field
from pathlib import Path

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # Python 3.9 / 3.10
    import tomli as tomllib


def config_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home()))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "remotehub"


def load_token(create: bool = True) -> str:
    """Token de pairing persistente (128 bits). Se crea la primera vez."""
    d = config_dir()
    f = d / "token"
    if f.exists():
        return f.read_text().strip()
    if not create:
        raise FileNotFoundError("Todavía no hay token: corré el receptor una vez.")
    d.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(16)
    f.write_text(token)
    try:
        f.chmod(0o600)
    except OSError:
        pass
    return token


@dataclass
class ClaudeConfig:
    bin: str = "claude"
    cwd: str = str(Path.home())
    # "default" = en modo headless NO puede aprobar herramientas fuera de allowed_tools.
    permission_mode: str = "default"
    allowed_tools: list[str] = field(default_factory=lambda: ["Read", "Grep", "Glob"])
    max_turns: int = 8
    timeout: int = 600
    presets: dict[str, str] = field(
        default_factory=lambda: {
            "tests": "Corré los tests del proyecto y resumime en 5 líneas qué falla.",
            "status": "Resumime en 5 líneas el estado del repo (git status y últimos commits).",
            "review": "Revisá los cambios sin commitear y decime los 3 riesgos más importantes.",
        }
    )


@dataclass
class Config:
    host: str = "0.0.0.0"
    port: int = 8765
    sensitivity: float = 1.6
    accel: float = 1.0          # 0 = sin aceleración
    scroll_sensitivity: float = 1.0
    allow_keys: bool = True     # key.tap / key.combo / text.type
    allow_claude: bool = True
    allow_web: bool = True      # control web en / y página de pairing en /pair
    slides_start: list[str] = field(default_factory=list)  # vacío = default por plataforma
    claude: ClaudeConfig = field(default_factory=ClaudeConfig)


def load_config(path: Path | None = None) -> Config:
    path = path or (config_dir() / "config.toml")
    cfg = Config()
    if not path.exists():
        return cfg
    data = tomllib.loads(path.read_text())
    claude = data.pop("claude", {})
    for k, v in data.items():
        if hasattr(cfg, k):
            setattr(cfg, k, v)
    for k, v in claude.items():
        if hasattr(cfg.claude, k):
            setattr(cfg.claude, k, v)
    return cfg
