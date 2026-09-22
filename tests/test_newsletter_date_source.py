import json
from datetime import date

import pytest
from test_openai_adapter import StubOpenAINewsletterAdapter, _valid_response

from app.schemas import DateCandidate, NewsletterAnalysisRequest
from app.services.newsletter_date_source import source_date_warning, source_span
from app.services.newsletter_prompt import ANALYSIS_RESPONSE_SCHEMA, build_prompt_messages


def candidate(text, value, day):
    start = text.index(value)
    return DateCandidate(
        candidateId="source",
        originalText=value,
        normalizedDate=day,
        startOffset=start,
        endOffset=start + len(value),
    )


@pytest.mark.parametrize(
    "text,value,day,kind,expected",
    [
        (
            "신청 2025년 12월 17일",
            "2025년 12월 17일",
            "2026-12-17",
            "deadline",
            "SOURCE_DATE_CONFLICT",
        ),
        (
            "신청 2025년 12월 17일(수) ~ 19일(금)",
            "19일",
            "2026-12-19",
            "deadline",
            "SOURCE_DATE_CONFLICT",
        ),
        ("신청 2025년 12월 17일(수) ~ 19일(금)", "19일", "2025-12-19", "deadline", None),
        ("신청 9월 4일 ~ 9월 8일", "9월 4일", "2026-09-04", "deadline", "DEADLINE_RANGE_START"),
        ("운영 9월 4일 ~ 9월 8일", "9월 4일", "2026-09-04", "schedule", None),
        ("제출 9월 8일", "9월 8일", "2026-09-04", "deadline", "SOURCE_DATE_CONFLICT"),
        ("2025학년도 안내\n행사 2026년 1월 8일", "2026년 1월 8일", "2026-01-08", "schedule", None),
        ("기간 2025년 12월 29일 ~ 1월 2일", "1월 2일", "2026-01-02", "deadline", None),
        (
            "기간 2025년 12월 29일 ~ 2026년 1월 2일",
            "2026년 1월 2일",
            "2026-01-02",
            "deadline",
            None,
        ),
        ("발행 2025년 12월 17일\n행사 1월 8일", "1월 8일", "2026-01-08", "schedule", None),
    ],
)
def test_source_date_guards(text, value, day, kind, expected):
    assert source_date_warning(text, candidate(text, value, day), kind) == expected


@pytest.mark.parametrize(
    "kind,expected", [("deadline", "DEADLINE_RANGE_START"), ("schedule", None)]
)
def test_range_start_with_weekday_and_parenthesized_opening_time(kind, expected):
    text = "신청기간: 2026.9.14.(월) (11:00부터 접수가능) ~ 9.18.(금) 15:00"
    value = candidate(text, "2026.9.14", "2026-09-14")
    assert source_date_warning(text, value, kind) == expected


def test_parentheses_without_range_do_not_reject_deadline():
    text = "마감: 2026.9.14.(월) (11:00까지 접수가능)"
    value = candidate(text, "2026.9.14", "2026-09-14")
    assert source_date_warning(text, value, "deadline") is None


def test_prompt_covers_observed_live_failures():
    prompt = build_prompt_messages(NewsletterAnalysisRequest(originalText="안내"))[0]["content"]
    for rule in (
        "온라인 조사/설문 참여 기간은 응답 제출 deadline 하나",
        "읽기 행동을 누락하는 것은 다르다",
        "보호자가 '이체하기'로 작성하지 않는다",
        "이상/이하와 초과/미만은 서로 바꾸지 않는다",
        "신청과 납부는 각각 연도를 검증한다",
    ):
        assert rule in prompt


def test_utf16_offsets_and_repeated_dates():
    text = "😀 신청 9월 4일\n발행 9월 4일"
    value = candidate(text, "9월 4일", "2026-09-04")
    value.start_offset += 1
    value.end_offset += 1
    assert source_span(text, value) == (5, 10)
    value.start_offset = 0
    value.end_offset = 0
    assert source_span(text, value) is None


def test_source_conflict_preserves_actions_and_summary_without_extra_call():
    text = "신청 기간: 2025년 12월 17일(수) ~ 19일(금)"
    value = candidate(text, "19일", "2026-12-19")
    raw = _valid_response()
    raw["items"][0].update(
        type="deadline",
        datetime="2026-12-19",
        selectedDateCandidate={
            "index": 0,
            "candidateId": "source",
            "originalText": "19일",
            "normalizedDate": "2026-12-19",
        },
    )
    adapter = StubOpenAINewsletterAdapter([{"output_text": json.dumps(raw)}])
    result = adapter.analyze(NewsletterAnalysisRequest(originalText=text, dateCandidates=[value]))
    assert len(adapter.payloads) == 1
    assert result.items[0].date_status == "ambiguous"
    assert result.items[0].datetime is None
    assert (
        result.items[0].checklist_items[0].content
        == raw["items"][0]["checklistItems"][0]["content"]
    )
    assert result.summary == raw["summary"]
    assert result.meta["dateValidationWarnings"][0]["code"] == "SOURCE_DATE_CONFLICT"
    assert value.normalized_date == date(2026, 12, 19)


def test_analysis_schema_is_strict_compatible_at_every_object():
    def check(node):
        if not isinstance(node, dict):
            return
        if node.get("type") == "object" or "object" in node.get("type", []):
            assert node["additionalProperties"] is False
            assert set(node["required"]) == set(node["properties"])
        for child in node.values():
            if isinstance(child, dict):
                check(child)
            elif isinstance(child, list):
                for nested in child:
                    check(nested)

    check(ANALYSIS_RESPONSE_SCHEMA)
    payload = StubOpenAINewsletterAdapter([])._analysis_payload([])
    assert payload["text"]["format"]["strict"] is True


def test_prompt_includes_time_coverage_and_verified_source_context():
    text = "교육일시: 2026.10.3.(토) 9:00~12:00"
    request = NewsletterAnalysisRequest(
        originalText=text, dateCandidates=[candidate(text, "2026.10.3", "2026-10-03")]
    )
    system, user = build_prompt_messages(request)
    assert "YYYY-MM-DDTHH:MM:SS" in system["content"]
    assert "첫 번째 신청 마감을 찾았다고 멈추지 않는다" in system["content"]
    assert "자료 목록이나 영상 링크 소개만으로 시청 과제를 만들지 않는다" in system["content"]
    assert "sourceContext:" in user["content"]
    assert text in user["content"]
