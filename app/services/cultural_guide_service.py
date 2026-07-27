import logging

from app.config import get_openai_settings
from app.schemas import CulturalGuideRequest, CulturalGuideResponse, SelectedCulturalGuide
from app.services.cultural_guide_prompt import MAX_SELECTED_FAQ_COUNT
from app.services.openai_adapter import OpenAIConfigurationError, OpenAINewsletterAdapter

logger = logging.getLogger(__name__)


def select_cultural_guides(request: CulturalGuideRequest) -> CulturalGuideResponse:
    # 후보가 없으면 OpenAI를 호출하지 않고 빈 배열 반환 (불필요한 비용/지연 방지)
    if not request.faq_candidates:
        logger.info("[CulturalGuide] FAQ 후보가 없어 빈 배열을 반환합니다.")
        return CulturalGuideResponse(selectedFaqs=[])

    settings = get_openai_settings()

    if not settings.enabled:
        raise OpenAIConfigurationError("OpenAI 기능이 비활성화되어 있습니다.")

    if not settings.api_key:
        raise OpenAIConfigurationError("OPENAI_API_KEY가 설정되어 있지 않습니다.")

    logger.info(
        "[CulturalGuide] OpenAI 선정 호출. model=%s, candidate_count=%d",
        settings.model,
        len(request.faq_candidates),
    )

    response = OpenAINewsletterAdapter(settings).select_cultural_guides(request)
    sanitized = _sanitize(request, response)

    logger.info(
        "[CulturalGuide] 선정 완료. selected_count=%d, faq_ids=%s",
        len(sanitized.selected_faqs),
        [item.faq_id for item in sanitized.selected_faqs],
    )
    return sanitized


def _sanitize(
    request: CulturalGuideRequest, response: CulturalGuideResponse
) -> CulturalGuideResponse:
    """모델이 후보에 없는 faqId를 만들어내거나 중복/초과 선택하는 경우를 방어한다."""
    allowed_faq_ids = {candidate.faq_id for candidate in request.faq_candidates}

    seen: set[int] = set()
    result: list[SelectedCulturalGuide] = []

    for item in response.selected_faqs:
        if item.faq_id not in allowed_faq_ids:
            logger.warning(
                "[CulturalGuide] 후보에 없는 faqId가 반환되어 제외합니다. faq_id=%s",
                item.faq_id,
            )
            continue
        if item.faq_id in seen:
            continue

        seen.add(item.faq_id)
        result.append(item)

        if len(result) >= MAX_SELECTED_FAQ_COUNT:
            break

    return CulturalGuideResponse(selectedFaqs=result)
