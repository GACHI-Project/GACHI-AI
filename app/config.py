import os
from dataclasses import dataclass


def _read_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _read_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    try:
        return float(value)
    except ValueError:
        return default


@dataclass(frozen=True)
class OpenAISettings:
    enabled: bool
    api_key: str | None
    model: str
    base_url: str
    timeout_seconds: float

    @classmethod
    def from_env(cls) -> "OpenAISettings":
        return cls(
            enabled=_read_bool("OPENAI_ENABLED", default=False),
            api_key=os.getenv("OPENAI_API_KEY") or None,
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            timeout_seconds=_read_float("OPENAI_TIMEOUT_SECONDS", 60.0),
        )


def get_openai_settings() -> OpenAISettings:
    return OpenAISettings.from_env()
