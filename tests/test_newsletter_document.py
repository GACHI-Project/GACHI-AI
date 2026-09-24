import io
import urllib.error

import pytest

from app.schemas import NewsletterDocument
from app.services import newsletter_document
from app.services.newsletter_document import DocumentLoadError, load_documents

S3_URL = (
    "https://gachi-bucket.s3.ap-northeast-2.amazonaws.com/newsletters/page1.pdf?X-Amz-Signature=x"
)


def document(url: str = S3_URL, mime_type: str = "application/pdf", name: str = "page-1.pdf"):
    return NewsletterDocument(fileUrl=url, fileName=name, mimeType=mime_type)


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class FakeOpener:
    """실제 네트워크 없이 다운로드 결과를 순서대로 돌려준다. 예외를 넣으면 그 예외를 던진다."""

    def __init__(self, results):
        self.results = list(results)
        self.calls = 0

    def open(self, request, timeout):
        self.calls += 1
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return FakeResponse(result)


def load(documents, opener, monkeypatch, max_total_bytes=1024):
    monkeypatch.setattr(newsletter_document, "_opener", opener)
    return load_documents(documents, max_total_bytes=max_total_bytes, timeout_seconds=1)


@pytest.mark.parametrize(
    "url",
    [
        "http://gachi-bucket.s3.amazonaws.com/page1.pdf",
        "file:///etc/passwd",
        "https://169.254.169.254/latest/meta-data",
        "https://evil.example.com/page1.pdf",
        "https://amazonaws.com.evil.example.com/page1.pdf",
    ],
)
def test_rejects_url_outside_https_s3_before_download(url, monkeypatch):
    opener = FakeOpener([b"never"])
    with pytest.raises(DocumentLoadError):
        load([document(url=url)], opener, monkeypatch)
    assert opener.calls == 0


def test_rejects_unsupported_mime_type_before_download(monkeypatch):
    opener = FakeOpener([b"never"])
    with pytest.raises(DocumentLoadError):
        load([document(mime_type="application/x-hwp")], opener, monkeypatch)
    assert opener.calls == 0


def test_loads_documents_in_page_order(monkeypatch):
    opener = FakeOpener([b"pdf-bytes", b"png-bytes"])
    loaded = load(
        [document(), document(mime_type="image/png", name="page-2.png")],
        opener,
        monkeypatch,
    )
    assert [item.file_name for item in loaded] == ["page-1.pdf", "page-2.png"]
    assert [item.content for item in loaded] == [b"pdf-bytes", b"png-bytes"]


def test_retries_once_on_temporary_network_error(monkeypatch):
    opener = FakeOpener([urllib.error.URLError("temporary"), b"pdf-bytes"])
    loaded = load([document()], opener, monkeypatch)
    assert loaded[0].content == b"pdf-bytes"
    assert opener.calls == 2


def test_does_not_retry_client_error_such_as_expired_url(monkeypatch):
    expired = urllib.error.HTTPError(S3_URL, 403, "Forbidden", None, None)
    opener = FakeOpener([expired, b"never"])
    with pytest.raises(DocumentLoadError):
        load([document()], opener, monkeypatch)
    assert opener.calls == 1


def test_fails_when_total_size_exceeds_limit(monkeypatch):
    opener = FakeOpener([b"a" * 600, b"b" * 600])
    with pytest.raises(DocumentLoadError):
        load(
            [document(), document(mime_type="image/png", name="page-2.png")],
            opener,
            monkeypatch,
            max_total_bytes=1000,
        )
