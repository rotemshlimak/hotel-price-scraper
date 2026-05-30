import os
from pathlib import Path


def load_dotenv(path: str | None = None):
    """Load KEY=VALUE lines from .env into os.environ (does not override existing)."""
    env_file = Path(path) if path else Path(__file__).resolve().parent / ".env"
    if not env_file.is_file():
        return
    for line in env_file.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip("'\"")
        if value:
            os.environ.setdefault(key, value)
