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


def _read_int(
    name: str, default: int, *, min_value: int | None = None,
    max_value: int | None = None
) -> int:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    if min_value is not None and parsed < min_value:
        return default
    if max_value is not None and parsed > max_value:
        return default
    return parsed


# OPENAI_DOCUMENT_DETAIL: low / high / auto
def _read_choice(name: str, default: str, choices: tuple[str, ...]) -> str:
    value = _read_str(name)
    if value is None:
        return default
    normalized = value.lower()
    return normalized if normalized in choices else default


DOCUMENT_DETAIL_CHOICES = ("low", "high", "auto")
# OpenAI 요청 1건당 파일 입력 합계 한도(50MB)에 맞춘다.
DEFAULT_DOCUMENT_MAX_BYTES = 50 * 1024 * 1024
# OpenAI Files API의 expires_after 허용 범위: 3600초(1시간) ~ 2592000초(30일)
DEFAULT_DOCUMENT_FILE_TTL_SECONDS = 3600


@dataclass(frozen=True)
class OpenAISettings:
    enabled: bool
    api_key: str | None
    model: str
    base_url: str
    timeout_seconds: float
    # document_detail: OpenAI가 PDF/이미지 페이지를 읽는 해상도. 1차는 high 고정.
    # document_max_bytes: 한 가정통신문의 원본 문서 합계 최대 크기.
    # document_download_timeout_seconds: S3 Presigned URL 다운로드 timeout.
    # document_file_ttl_seconds: 삭제에 실패해도 OpenAI에서 자동 삭제되는 시간(안전장치).
    document_detail: str = "high"
    document_max_bytes: int = DEFAULT_DOCUMENT_MAX_BYTES
    document_download_timeout_seconds: float = 30.0
    document_file_ttl_seconds: int = DEFAULT_DOCUMENT_FILE_TTL_SECONDS

    @classmethod
    def from_env(cls) -> "OpenAISettings":
        return cls(
            enabled=_read_bool("OPENAI_ENABLED", default=False),
            api_key=_read_str("OPENAI_API_KEY"),
            model=_read_str("OPENAI_MODEL", "gpt-4.1-mini") or "gpt-4.1-mini",
            base_url=_read_str("OPENAI_BASE_URL", "https://api.openai.com/v1")
            or "https://api.openai.com/v1",
            timeout_seconds=_read_float("OPENAI_TIMEOUT_SECONDS", 60.0, min_value=0.001),
            document_detail=_read_choice("OPENAI_DOCUMENT_DETAIL", "high",
                                         DOCUMENT_DETAIL_CHOICES),
            document_max_bytes=_read_int(
                "OPENAI_DOCUMENT_MAX_BYTES",
                DEFAULT_DOCUMENT_MAX_BYTES,
                min_value=1,
                max_value=DEFAULT_DOCUMENT_MAX_BYTES,
            ),
            document_download_timeout_seconds=_read_float(
                "OPENAI_DOCUMENT_DOWNLOAD_TIMEOUT_SECONDS", 30.0, min_value=0.001
            ),
            document_file_ttl_seconds=_read_int(
                "OPENAI_DOCUMENT_FILE_TTL_SECONDS",
                DEFAULT_DOCUMENT_FILE_TTL_SECONDS,
                min_value=3600,
                max_value=2592000,
            ),
        )


def get_openai_settings() -> OpenAISettings:
    return OpenAISettings.from_env()
