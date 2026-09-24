"""가정통신문 원본 문서를 S3 Presigned URL에서 내려받는다.

- 한 문서라도 실패하면 전체를 실패로 본다. (페이지가 빠진 원본은 AI가 맥락을 잘못 잡을 수 있음)
  실패 시 호출부(OpenAINewsletterAdapter)가 원본 없이 텍스트만으로 분석을 계속한다.
- Presigned URL은 누구나 열 수 있는 링크이므로 로그에 절대 남기지 않는다.
"""

import logging
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import urlparse

from app.schemas import NewsletterDocument

logger = logging.getLogger(__name__)

# 내부 서버나 로컬 파일을 읽게 만드는 요청을 막기 위해 https + S3 도메인만 허용한다.
ALLOWED_URL_SCHEME = "https"
ALLOWED_HOST_SUFFIX = ".amazonaws.com"
# BE가 보내는 형식: PDF 원본, EXIF 보정한 PNG. JPEG는 원본 이미지 확장 대비.
SUPPORTED_MIME_TYPES = frozenset({"application/pdf", "image/png", "image/jpeg"})
# 일시적 네트워크 오류는 한 번만 다시 시도한다.
MAX_DOWNLOAD_ATTEMPTS = 2
READ_CHUNK_BYTES = 1024 * 1024


class DocumentLoadError(RuntimeError):
    """원본 문서를 준비하지 못함. 호출부는 텍스트만으로 분석을 계속한다."""


@dataclass(frozen=True)
class LoadedDocument:
    """다운로드가 끝난 원본 문서 1건. 평가 스크립트/테스트에서는 로컬 파일로 직접 만들 수 있다."""

    file_name: str
    mime_type: str
    content: bytes


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """리다이렉트로 허용 도메인 밖의 주소를 읽지 않도록 리다이렉트를 따라가지 않는다."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_opener = urllib.request.build_opener(_NoRedirectHandler)


def load_documents(
    documents: list[NewsletterDocument],
    *,
    max_total_bytes: int,
    timeout_seconds: float,
) -> list[LoadedDocument]:
    """문서를 페이지 순서대로 모두 내려받는다. 하나라도 실패하면 DocumentLoadError."""
    loaded: list[LoadedDocument] = []
    total_bytes = 0
    for page, document in enumerate(documents, start=1):
        _validate_document(document, page)
        content = _download_with_retry(
            document,
            page,
            remaining_bytes=max_total_bytes - total_bytes,
            timeout_seconds=timeout_seconds,
        )
        total_bytes += len(content)
        loaded.append(
            LoadedDocument(
                file_name=document.file_name,
                mime_type=document.mime_type,
                content=content,
            )
        )
    logger.info(
        "[NewsletterDocument] 원본 문서 다운로드 완료. documentCount=%s, totalBytes=%s",
        len(loaded),
        total_bytes,
    )
    return loaded


def _validate_document(document: NewsletterDocument, page: int) -> None:
    if document.mime_type not in SUPPORTED_MIME_TYPES:
        raise DocumentLoadError(
            f"지원하지 않는 문서 형식입니다. page={page}, mimeType={document.mime_type}"
        )

    parsed = urlparse(document.file_url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != ALLOWED_URL_SCHEME or not host.endswith(ALLOWED_HOST_SUFFIX):
        # URL 전체는 서명이 포함되어 있으므로 scheme/host만 남긴다.
        raise DocumentLoadError(
            f"허용되지 않은 문서 주소입니다. page={page}, scheme={parsed.scheme}, host={host}"
        )


def _download_with_retry(
    document: NewsletterDocument,
    page: int,
    *,
    remaining_bytes: int,
    timeout_seconds: float,
) -> bytes:
    for attempt in range(1, MAX_DOWNLOAD_ATTEMPTS + 1):
        try:
            return _download(document.file_url, remaining_bytes, timeout_seconds)
        except urllib.error.HTTPError as exc:
            # 4xx(만료된 URL, 권한 없음 등)는 다시 시도해도 같으므로 바로 실패 처리한다.
            if exc.code < 500 or attempt == MAX_DOWNLOAD_ATTEMPTS:
                raise DocumentLoadError(
                    f"원본 문서 다운로드 실패. page={page}, status={exc.code}"
                ) from exc
            _log_retry(page, attempt, f"status={exc.code}")
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            if attempt == MAX_DOWNLOAD_ATTEMPTS:
                raise DocumentLoadError(
                    f"원본 문서 다운로드 실패. page={page}, reason={type(exc).__name__}"
                ) from exc
            _log_retry(page, attempt, type(exc).__name__)
    # for문 안에서 반드시 return 또는 raise 된다.
    raise DocumentLoadError(f"원본 문서 다운로드 실패. page={page}")


def _download(url: str, max_bytes: int, timeout_seconds: float) -> bytes:
    if max_bytes <= 0:
        raise DocumentLoadError("원본 문서 합계 크기가 제한을 초과했습니다.")

    request = urllib.request.Request(url, method="GET")
    chunks: list[bytes] = []
    size = 0
    with _opener.open(request, timeout=timeout_seconds) as response:
        while True:
            chunk = response.read(READ_CHUNK_BYTES)
            if not chunk:
                break
            size += len(chunk)
            # 전체를 메모리에 올리기 전에 크기 제한을 넘으면 바로 중단한다.
            if size > max_bytes:
                raise DocumentLoadError("원본 문서 합계 크기가 제한을 초과했습니다.")
            chunks.append(chunk)
    return b"".join(chunks)


def _log_retry(page: int, attempt: int, reason: str) -> None:
    logger.warning(
        "[NewsletterDocument] 원본 문서 다운로드 재시도. page=%s, attempt=%s/%s, reason=%s",
        page,
        attempt,
        MAX_DOWNLOAD_ATTEMPTS,
        reason,
    )
