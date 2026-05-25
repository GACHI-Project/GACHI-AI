import os
from dataclasses import dataclass


def _read_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _read_str(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip()
    return normalized or default


def _read_float(name: str, default: float, *, min_value: float | None = None) -> float:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    try:
        parsed = float(value)
        if min_value is not None and parsed < min_value:
            return default
        return parsed
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
            api_key=_read_str("OPENAI_API_KEY"),
            model=_read_str("OPENAI_MODEL", "gpt-4.1-mini") or "gpt-4.1-mini",
            base_url=_read_str("OPENAI_BASE_URL", "https://api.openai.com/v1")
            or "https://api.openai.com/v1",
            timeout_seconds=_read_float("OPENAI_TIMEOUT_SECONDS", 60.0, min_value=0.001),
        )


def get_openai_settings() -> OpenAISettings:
    return OpenAISettings.from_env()
