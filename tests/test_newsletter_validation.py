import json

import pytest
from test_openai_adapter import StubOpenAINewsletterAdapter, _valid_response

from app.schemas import NewsletterAnalysisRequest, NewsletterAnalysisResponse
from app.services.newsletter_prompt import build_prompt_messages
from app.services.newsletter_validation import normalize_analysis_dates


def test_prompt_keeps_application_actions_with_their_deadline():
    # Guard prompt instructions, not live model accuracy.
    prompt = build_prompt_messages(request())[0]["content"]
    assert "해당 deadline에만 연결" in prompt
    assert "종료일 후보가 없으면 신청 deadline을 ambiguous" in prompt
    assert "링크 확인이나 접속은 신청 방법으로 detail" in prompt
    assert "모집 인원과 참가 자격은 조건" in prompt
    assert "서로 다른 제출물은 합치지 않는다" in prompt


def test_prompt_preserves_conditions_as_details_not_tasks():
    prompt = build_prompt_messages(request())[0]["content"]
    assert "관련 조건이 있으면 detail을 null로 두지 않는다" in prompt
    assert "선착순 여부, 참가 대상, 가정당 신청 단위" in prompt
    assert "예시의 조건을 다른 문서에 추가하지 않는다" in prompt
    assert "selectedDateCandidate=null, datetime=null, needsUserConfirmation=true" in prompt


def test_prompt_distinguishes_publication_only_from_real_deadline():
    # Instruction regression only: live cases are tracked in the evaluation guide.
    prompt = build_prompt_messages(request())[0]["content"]
    assert "후보가 존재한다는 이유로 사건을 만들지 않는다" in prompt
    assert "발행일 후보만 남아 있어도 동일하다" in prompt
    assert "동일 날짜가 본문에서 실제 행사/마감으로도 명시되면" in prompt
    assert "9월 7일 후보가 있으면 confirmed, 없으면 ambiguous" in prompt


def test_prompt_preserves_table_ownership_and_grade_caveat():
    prompt = build_prompt_messages(request())[0]["content"]
    assert "열 제목과 구역 제목" in prompt
    assert "'학교에서 지원'하는 물품은 구매/준비/확인 체크리스트에서 제외" in prompt
    assert "가정 구매 구역의 요구는 보존" in prompt
    assert "'학년별/학급별로 다를 수 있음'은 detail에 보존" in prompt


def test_prompt_separates_actions_conditions_and_advice():
    prompt = build_prompt_messages(request())[0]["content"]
    for instruction in (
        "A. 실행 절차",
        "B. 설명 조건",
        "C. 일반 권고/정보",
        "'신청 시 동의한 것으로 간주'는 B",
        "'동의서에 서명해 제출'은 A",
        "지정된 사전 안내문을 학생과 함께 읽기",
        "계좌 잔액 확인",
        "자동이체 안내만으로 별도 송금을 요구하지 않는다",
        "밴드 가입 연령을 행사 참가 연령으로 바꾸지 않는다",
    ):
        assert instruction in prompt


def request():
    return NewsletterAnalysisRequest(
        originalText="2026. 6. 15 수영 실기교육",
        dateCandidates=[
            {
                "candidateId": "dc_1",
                "originalText": "2026. 6. 15",
                "normalizedDate": "2026-06-15",
                "startOffset": 0,
                "endOffset": 11,
            }
        ],
    )


def analyze(raw):
    adapter = StubOpenAINewsletterAdapter([{"output_text": json.dumps(raw)}])
    result = adapter.analyze(request())
    assert len(adapter.payloads) == 1
    return result


@pytest.mark.parametrize("value", ["2026-06-15", "2026-06-15T09:00:00+09:00"])
def test_matching_candidate_preserves_date(value):
    raw = _valid_response()
    raw["items"][0]["datetime"] = value
    result = analyze(raw)
    assert result.items[0].datetime == value
    assert result.items[0].date_status == "confirmed"


@pytest.mark.parametrize("value", [None, "2025-06-15", "2026-06-15garbage", "2026-06-15T99:00"])
def test_invalid_date_downgrades_only_bad_item(value):
    raw = _valid_response()
    raw["items"].append(dict(raw["items"][0], datetime=value))
    result = analyze(raw)
    assert result.items[0].date_status == "confirmed"
    assert result.items[1].date_status == "ambiguous"
    assert result.items[1].datetime is None
    assert result.items[1].checklist_items
    assert result.meta["requiresLLMReview"] is True


@pytest.mark.parametrize(
    "field,value",
    [
        ("index", -1),
        ("index", 1),
        ("candidateId", "invented"),
        ("originalText", "other"),
        ("normalizedDate", "2025-06-15"),
    ],
)
def test_forged_candidate_is_not_confirmed(field, value):
    raw = _valid_response()
    raw["items"][0]["selectedDateCandidate"][field] = value
    result = analyze(raw)
    assert result.items[0].date_status == "ambiguous"
    assert result.items[0].selected_date_candidate is None


def test_missing_preserves_actions_without_calendar_date():
    raw = _valid_response()
    raw["items"][0].update(type="reminder", dateStatus="missing")
    item = analyze(raw).items[0]
    assert item.checklist_items
    assert item.datetime is None
    assert item.selected_date_candidate is None
    assert item.needs_user_confirmation is False


@pytest.mark.parametrize("question", [None, "신청 마감일을 확인해 주세요."])
@pytest.mark.parametrize("has_candidate", [True, False])
def test_ambiguous_clears_candidate_but_preserves_context(question, has_candidate):
    raw = _valid_response()
    original = raw["items"][0]
    original.update(dateStatus="ambiguous", confirmationQuestion=question)
    if not has_candidate:
        original["selectedDateCandidate"] = None
    result = analyze(raw)
    item = result.items[0]
    assert item.selected_date_candidate is None
    assert item.datetime is None
    assert item.needs_user_confirmation is True
    assert item.confirmation_question == (question or "날짜를 확인해 주세요.")
    assert item.evidence_text == original["evidenceText"]
    assert item.checklist_items[0].detail == original["checklistItems"][0]["detail"]
    assert item.checklist_items[0].content == original["checklistItems"][0]["content"]
    assert result.meta["requiresLLMReview"] is True


def test_empty_items_preserve_summary():
    raw = _valid_response()
    raw["items"] = []
    result = analyze(raw)
    assert result.items == []
    assert result.summary == raw["summary"]


@pytest.mark.parametrize("review_flag", [True, False, None])
@pytest.mark.parametrize("status", ["confirmed", "missing", "ambiguous", "empty"])
def test_review_flag_preserves_existing_request_or_ambiguous_dates(review_flag, status):
    raw = _valid_response()
    if review_flag is None:
        raw["meta"].pop("requiresLLMReview")
    else:
        raw["meta"]["requiresLLMReview"] = review_flag
    raw["meta"]["reviewReason"] = "non-date review context"
    if status == "empty":
        raw["items"] = []
    else:
        raw["items"][0]["dateStatus"] = status

    result = analyze(raw)

    assert result.meta["requiresLLMReview"] is (review_flag is True or status == "ambiguous")
    assert result.meta["reviewReason"] == "non-date review context"


def _document_only_response(datetime_value="2026-06-15"):
    raw = _valid_response()
    raw["items"][0]["selectedDateCandidate"] = None
    raw["items"][0]["datetime"] = datetime_value
    return NewsletterAnalysisResponse.model_validate(raw)


def test_document_only_date_is_kept_when_documents_attached():
    result = normalize_analysis_dates(request(), _document_only_response(),
                                      documents_attached=True)
    item = result.items[0]
    assert item.date_status == "confirmed"
    assert item.datetime == "2026-06-15"
    assert {"itemIndex": 0, "code": "DOCUMENT_ONLY_DATE"} in result.meta[
        "dateValidationWarnings"]


def test_document_only_date_is_downgraded_without_documents():
    result = normalize_analysis_dates(request(), _document_only_response())
    item = result.items[0]
    assert item.date_status == "ambiguous"
    assert item.datetime is None
    assert {"itemIndex": 0, "code": "DATE_CANDIDATE_MISMATCH"} in result.meta[
        "dateValidationWarnings"
    ]


@pytest.mark.parametrize("value", [None, "2026-06-15garbage"])
def test_document_only_date_with_invalid_datetime_is_downgraded(value):
    result = normalize_analysis_dates(
        request(), _document_only_response(value), documents_attached=True
    )
    assert result.items[0].date_status == "ambiguous"


def test_forged_candidate_is_downgraded_even_when_documents_attached():
    raw = _valid_response()
    raw["items"][0]["selectedDateCandidate"]["candidateId"] = "invented"
    result = normalize_analysis_dates(
        request(), NewsletterAnalysisResponse.model_validate(raw),
        documents_attached=True
    )
    assert result.items[0].date_status == "ambiguous"


class _Attached:
    file_name = "newsletter-page-1.pdf"
    mime_type = "application/pdf"


def test_text_only_prompt_keeps_candidate_only_date_rule():
    system, user = build_prompt_messages(request())
    assert "원본 문서 사용 원칙" not in system["content"]
    assert "dateCandidates에 없는 날짜를 새로 만들거나 추론해서" in system["content"]
    assert "<attached_documents>" not in user["content"]


def test_document_prompt_adds_principles_and_attachment_order():
    system, user = build_prompt_messages(request(), attached_documents=[_Attached()])
    assert "원본 문서 사용 원칙" in system["content"]
    assert "원본과 original_text의 내용이 다르면 원본을 따른다" in system["content"]
    assert "요일이 날짜와 맞지 않음" in system["content"]
    assert "dateCandidates에 없는 날짜를 새로 만들거나 추론해서" not in system["content"]
    assert "첨부된 원본 문서가 사실 판단의 기준이다" in system["content"]
    assert "1. newsletter-page-1.pdf (application/pdf)" in user["content"]
