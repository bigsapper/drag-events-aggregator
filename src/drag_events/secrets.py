"""Secret resolution helpers for external service clients."""

from functools import lru_cache
from pathlib import Path
import os

import anthropic

BASE_DIR = Path(__file__).resolve().parents[2]
PROJECT_SECRET_FILE = BASE_DIR / ".env"


class SecretConfigurationError(RuntimeError):
    """Raised when required secret configuration is missing or invalid."""


def _read_secret_file(path: Path) -> str:
    try:
        value = path.read_text().strip()
    except FileNotFoundError as exc:
        raise SecretConfigurationError(f"Secret file does not exist: {path}") from exc

    if not value:
        raise SecretConfigurationError(f"Secret file is empty: {path}")
    return value


def _read_project_dotenv_key(path: Path, key_name: str) -> str:
    try:
        lines = path.read_text().splitlines()
    except FileNotFoundError as exc:
        raise SecretConfigurationError(f"Project .env file does not exist: {path}") from exc

    prefix = f"{key_name}="
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or not stripped.startswith(prefix):
            continue
        value = stripped[len(prefix):].strip()
        if value[:1] == value[-1:] and value[:1] in {'"', "'"}:
            value = value[1:-1]
        if not value:
            raise SecretConfigurationError(f"Project .env value for {key_name} is empty: {path}")
        return value

    raise SecretConfigurationError(f"Project .env file does not define {key_name}: {path}")


def get_anthropic_api_key(env: dict[str, str] | None = None) -> str:
    """Resolve the Anthropic API key from environment, explicit secret files, or project-local .env."""
    environment = os.environ if env is None else env

    api_key = environment.get("ANTHROPIC_API_KEY", "").strip()
    if api_key:
        return api_key

    secret_file = environment.get("ANTHROPIC_API_KEY_FILE", "").strip()
    if secret_file:
        return _read_secret_file(Path(secret_file))

    if PROJECT_SECRET_FILE.exists():
        return _read_project_dotenv_key(PROJECT_SECRET_FILE, "ANTHROPIC_API_KEY")

    raise SecretConfigurationError(
        "Missing Anthropic API key. Set ANTHROPIC_API_KEY, set ANTHROPIC_API_KEY_FILE, "
        f"or define ANTHROPIC_API_KEY in {PROJECT_SECRET_FILE}."
    )


@lru_cache(maxsize=1)
def get_anthropic_client():
    """Build and cache the Anthropic client."""
    return anthropic.Anthropic(api_key=get_anthropic_api_key())
