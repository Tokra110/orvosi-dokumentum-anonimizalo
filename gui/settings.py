"""App settings persistence and log sanitization. No Qt imports here."""

import json
import re
from pathlib import Path

CONFIG_PATH = Path.home() / ".config" / "medical-redactor" / "settings.json"


def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def update_config(**changes) -> dict:
    cfg = load_config()
    cfg.update(changes)
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))
    return cfg


def sanitize_log(msg: str) -> str:
    msg = re.sub(r"['\"]?/[^\s'\",:\]]+", lambda m: "/***/" + Path(m.group().strip("'\"")).name, msg)
    msg = re.sub(r"[^\s/\\]+\.pdf\b", "XYZ.pdf", msg, flags=re.IGNORECASE)
    msg = re.sub(r"[^\s/\\]+\.md\b", "XYZ.md", msg, flags=re.IGNORECASE)
    return msg


def get_last_dir() -> str:
    d = load_config().get("last_dir", "")
    return d if d and Path(d).is_dir() else str(Path.home())


def remember_dir(path: str):
    update_config(last_dir=path)
