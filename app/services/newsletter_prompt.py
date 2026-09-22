from app.constants import LANGUAGE_NAMES, SUPPORTED_LANGUAGE_CODES
from app.schemas import NewsletterAnalysisRequest

I18N_TEXT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": list(SUPPORTED_LANGUAGE_CODES),
    "properties": {
        code: {"type": "string", "minLength": 1, "maxLength": 500}
        for code in SUPPORTED_LANGUAGE_CODES
    },
}

NULLABLE_I18N_TEXT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": list(SUPPORTED_LANGUAGE_CODES),
    "properties": {code: {"type": "string", "maxLength": 500} for code in SUPPORTED_LANGUAGE_CODES},
}

SELECTED_DATE_CANDIDATE_SCHEMA = {
    "type": ["object", "null"],
    "additionalProperties": False,
    "required": ["index", "candidateId", "originalText", "normalizedDate"],
    "properties": {
        "index": {"type": "integer", "minimum": 0},
        "candidateId": {"type": ["string", "null"]},
        "originalText": {"type": "string"},
        "normalizedDate": {"type": "string", "format": "date"},
    },
}

CHECKLIST_ITEM_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["content", "contentI18n", "detail", "detailI18n"],
    "properties": {
        "content": {"type": "string", "minLength": 1, "maxLength": 500},
        "contentI18n": I18N_TEXT_SCHEMA,
        "detail": {"type": ["string", "null"], "maxLength": 500},
        "detailI18n": NULLABLE_I18N_TEXT_SCHEMA,
    },
}

ITEM_RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "type",
        "title",
        "titleI18n",
        "selectedDateCandidate",
        "dateStatus",
        "datetime",
        "timezone",
        "evidenceText",
        "confidence",
        "needsUserConfirmation",
        "confirmationQuestion",
        "checklistItems",
    ],
    "properties": {
        "type": {
            "type": "string",
            "enum": ["schedule", "deadline", "reminder"],
        },
        "title": {"type": "string"},
        "titleI18n": I18N_TEXT_SCHEMA,
        "selectedDateCandidate": SELECTED_DATE_CANDIDATE_SCHEMA,
        "dateStatus": {
            "type": "string",
            "enum": ["confirmed", "ambiguous", "missing"],
        },
        "datetime": {"type": ["string", "null"]},
        "timezone": {"type": "string"},
        "evidenceText": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "needsUserConfirmation": {"type": "boolean"},
        "confirmationQuestion": {"type": ["string", "null"]},
        "checklistItems": {
            "type": "array",
            "items": CHECKLIST_ITEM_SCHEMA,
        },
    },
}

EXTRACTION_RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["items"],
    "properties": {
        "items": {"type": "array", "items": ITEM_RESPONSE_SCHEMA},
        "meta": {"type": "object"},
    },
}

CONVERSATION_TOPIC_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["topic"],
    "properties": {
        "topic": {"type": "string", "minLength": 1, "maxLength": 200},
    },
}

ANALYSIS_RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["title", "titleI18n", "summary", "items", "conversationTopics", "meta"],
    "properties": {
        "title": {"type": "string"},
        "titleI18n": I18N_TEXT_SCHEMA,
        "summary": {"type": "string"},
        "items": {"type": "array", "items": ITEM_RESPONSE_SCHEMA},
        "conversationTopics": {
            "type": "array",
            "items": CONVERSATION_TOPIC_SCHEMA,
            "minItems": 0,
            "maxItems": 3,
        },
        "meta": {
            "type": "object",
            "additionalProperties": True,
            "properties": {
                "mode": {"type": "string"},
                "dateCandidateCount": {"type": "integer", "minimum": 0},
                "requiresLLMReview": {"type": "boolean"},
                "outputLanguage": {"type": "string"},
                "localizedOutput": {"type": "boolean"},
            },
        },
    },
}


def build_prompt_messages(request: NewsletterAnalysisRequest) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": _build_system_prompt(request.language)},
        {"role": "user", "content": _build_user_prompt(request)},
    ]


def _build_system_prompt(language: str) -> str:
    language_name = _language_name(language)
    return f"""
역할: 학교 가정통신문 원문을 분석해서 저장 가능한 제목, 요약,
주요 일정/마감/체크리스트 항목을 JSON으로 반환한다.

- response schema에 맞는 JSON만 반환한다.
- AI 서버는 DB 저장을 직접 알지 않는다. 저장 판단은 BE가 하며, AI 서버는 분석 결과만 반환한다.
- items 배열의 모든 원소는 반드시 JSON object여야 하며, 문자열 조각(예: "}},{{")이나
  JSON을 흉내 낸 문자열을 배열 원소로 넣지 않는다.
- checklistItems 배열의 모든 원소도 반드시 JSON object여야 한다.
- title, summary, items[].title, checklistItems[].content, checklistItems[].detail,
  conversationTopics[].topic은 사용자 언어({language_name})와 무관하게 항상 한국어로 작성한다.
  (이 값들은 이후 단계에서 번역 및 검수를 거쳐 사용자 언어로 변환된다.)
- 단, titleI18n과 checklistItems[].contentI18n,
  checklistItems[].detailI18n은 기존과 동일하게 KO/US/ZH/VI
  네 언어 값을 모두 채운다. 이 값들은 사용자의 현재 언어({language_name})와
  무관하게 알림(notification)에서 사용된다.
- title은 문서 제목으로 사용할 수 있는 짧은 문자열로 작성한다.
- titleI18n은 알림에서 사용할 문서 제목이며 KO/US/ZH/VI 네 언어 값을 모두 채운다.
- summary는 보호자나 학생이 빠르게 확인할 수 있는 1~2문장으로 작성한다.
- items의 구조는 /ai/newsletters/extract-items 응답 형식을 유지한다.
- 구체적인 날짜는 제공된 dateCandidates 중 하나만 선택한다.
- dateCandidates에 없는 날짜를 새로 만들거나 추론해서 confirmed로 반환하지 않는다.
- 실제 행사/마감과 날짜의 연결 근거가 명확할 때만 dateStatus를 confirmed로 설정한다.
- 날짜 정보가 없거나 근거가 약하면 ambiguous 또는 missing을 사용한다.
- evidenceText는 사용자가 볼 수 있는 근거/상세 설명 문구로 작성하되, 원문 의미를 벗어나지 않는다.

항목 분류 기준 (items[]는 일정 후보 또는 날짜 없는 실행 항목 그룹이다):
- deadline: 제출, 신청, 납부, 등록, 동의, 회신 등의 기한이 있는 행동
- schedule: 행사, 수업, 상담, 체험학습, 설명회, 운영일
- reminder: 날짜가 없지만 원문에서 요구하는 구체적이고 완료 가능한 행동의 그룹
- 날짜 없는 행동은 reminder, selectedDateCandidate=null, datetime=null,
  dateStatus=missing, needsUserConfirmation=false, confirmationQuestion=null로 반환한다.
  날짜 입력은 필수가 아니다. 실행 항목도 실제 일정도 없으면 items=[]로 반환한다.

날짜 판단 원칙:
1. 먼저 원문에서 실제 행사/운영 또는 행동의 기한이 있는지 판단한다.
   '안내문 발행', '안내일', '공지일' 자체는 캘린더에 등록할 사건이 아니다.
2. 실제 사건이나 행동 기한이 있으면 해당 사건에 연결된 날짜만 후보에서 찾는다.
   후보가 존재한다는 이유로 사건을 만들지 않는다. 후보 목록은 정답이 아니다.
3. 행동은 있지만 해당 행동의 날짜/기한이 원문에 없으면 reminder/missing으로 반환한다.
   발행일 후보만 남아 있어도 동일하다. 날짜를 묻거나 안내일 일정에 행동을 붙이지 않는다.
4. 실제 사건의 날짜/기한이 원문에는 있으나 대응 후보가 없으면 ambiguous로 보존한다.
   '날짜 없는 행동'과 '원문 날짜의 후보 누락'을 구분한다.
- 발행일, 작성일, 공문 시행일자, 설명용 날짜, 예시 화면의 날짜는 일정에서 제외한다.
  단, 프로그램 시행일이나 운영 시작일은 실제 일정으로 판단한다.
- 문서 하단의 YYYY년 M월 D일 또는 YYYY. M. D.와 학교장/기관장 서명이 함께
  나타나고 실제 행사/행동 기한과 연결된 근거가 없으면 발행일로 제외한다.
  서명 옆 날짜가 명확하다는 사실만으로 confirmed 처리하지 않는다.
  동일 날짜가 본문에서 실제 행사/마감으로도 명시되면 그 사건은 보존한다.
- 본문과 안내 이미지의 날짜가 충돌하면 실제 안내 대상과 연결된 근거를 우선한다.
  해결할 수 없는 충돌은 ambiguous로 반환한다.
- 문맥상 이미 종료된 과거 사례는 제외하되, referenceDate보다 과거라는 이유만으로
  행사나 마감을 제외하지 않는다. referenceDate는 업로드 기준일이며 문서 작성일이 아니다.
- 음력 8월 15일 같은 설명을 양력 일정으로 바꾸지 않는다. 첫 접종일 없는 6개월 간격
  같은 상대 정보로 특정 날짜를 만들지 않는다.
- confirmed는 입력 후보의 index, candidateId, originalText, normalizedDate를 그대로
  선택하고 datetime의 날짜 부분도 normalizedDate와 같아야 한다.
- 연도 없는 후보에 붙은 기준 연도를 무조건 신뢰하지 않는다. 문서 연도와 충돌하면
  날짜를 임의 수정하지 말고 ambiguous로 반환한다.
- 실제 일정의 날짜 근거가 있지만 후보가 없거나 불확실하면 ambiguous,
  selectedDateCandidate=null, datetime=null, needsUserConfirmation=true로 반환한다.
  확인 질문을 작성한다.
  이때 시작일이나 발행일 후보를 대신 선택하지 않는다. 확인할 날짜 근거는 evidenceText에 보존한다.
- evidenceText에는 날짜와 행동의 연결을 확인할 수 있는 원문 근거를 보존한다.
- 현행 단일 datetime 계약을 유지한다. 접수 기간은 마감 후보가 명확하면 deadline으로
  마감일 하나를 선택하고 전체 기간과 시간을 evidenceText/detail에 보존한다.
  종료일 후보가 없으면 시작일을 마감일로 사용하지 않고 ambiguous로 반환한다.
  운영 기간은 시작일 후보를 사용하되 전체 기간을 근거에 보존한다.
  기간의 양 끝을 의미 없는 별도 일정으로 만들지 않는다.

일정 제목 원칙:
- top-level title은 문서 제목이고 items[].title은 개별 사건이나 행동의 제목이다.
- 문서 제목을 각 항목에 일괄 복사하지 않는다. 신청, 제출, 교육 등 목적을 구분한다.
  예: 가족발명교실 신청 / 가족발명교실 교육 / 공연 참여 동의서 제출
- items[].titleI18n도 같은 의미로 작성한다. 제목을 다르게 만들기 위해 사실을 추가하지 않는다.

체크리스트(checklistItems) 추출 원칙:
- 먼저 원문의 문장을 아래 세 범주로 분류하고, A만 체크리스트 content로 만든다.
  A. 실행 절차: 원문에서 보호자/학생에게 요구하고 완료 여부를 확인할 수 있는 행동.
     신청서 작성/제출, 실제 동의서 서명, 계좌 잔액 확인, 개인 준비물 준비,
     지정된 사전 안내문을 학생과 함께 읽기 등이 해당한다.
  B. 설명 조건: 간주 동의, 참가 자격, 인원 제한, 신청 방법, 금액, 변동 가능성.
     관련 A 행동의 detail에 보존한다. 조건 자체를 '동의하기/확인하기'로 바꾸지 않는다.
  C. 일반 권고/정보: 안전에 유의, 보호자 책임, 자녀와 평소 대화, 필요시 상담 이용,
     기관 연락처, 학교의 제공 혜택. 요약/원문에서 확인할 정보이며 할 일로 만들지 않는다.
- 명령형 문장이라고 모두 A는 아니다. '안전에 유의하세요'는 C이고,
  '첨부된 안전교육 안내장을 자녀와 함께 읽어 주세요'는 완료 가능한 A이다.
  '신청 시 동의한 것으로 간주'는 B이고, '동의서에 서명해 제출'은 A이다.
  A나 실제 일정이 전혀 없는 일반 안내는 items=[]이며 요약은 유지한다.
- 체크리스트는 더 이상 독립적인 최상위 항목이 아니다. 반드시 items[] 중
  하나의 일정 후보 또는 날짜 없는 reminder 그룹의 checklistItems[]로 추출한다.
- 체크리스트에 날짜 필드를 추가하지 않는다. 실제 관련 일정이 있으면 그 항목에 연결하고,
  없으면 날짜 없는 그룹에 보존한다. 기한, 방법, 제출처, 금액, 조건은 detail에 보존한다.
- 신청, 제출, 납부, 작성, 서명과 준비물 중 원문에 명시된 A 행동만 추출한다.
  실제 첨부 동의서 작성과 보호자 서명, 계좌 잔액 확인, 사전 가입 요구를 누락하지 않는다.
  동의서가 없는데 동의서를 만들거나, 자동이체 안내만으로 별도 송금을 요구하지 않는다.
- 조건부 행동은 원문에 명시된 참여나 납부의 필요 조건일 때 조건을 포함해 추출한다.
  예: 봉사시간 인정을 받으려면 VMS 가입하기 / 이체 전 계좌 잔액 확인하기
- 표는 행의 물품명뿐 아니라 열 제목과 구역 제목을 함께 읽고 제공/준비 주체를 구분한다.
  '학교에서 지원'하는 물품은 구매/준비/확인 체크리스트에서 제외한다.
  '가정에서 직접 구매'하는 물품만 가정의 구매/준비 행동으로 추출한다.
  같은 물품이 학교 지원과 가정 구매 양쪽에 있으면 가정 구매 구역의 요구는 보존한다.
  '학년별/학급별로 다를 수 있음'은 detail에 보존하고 별도 확인 행동으로 만들지 않는다.
- 모든 일정에 체크리스트가 있어야 하는 것은 아니다. 해당 일정과 관련해
  학부모나 자녀가 실제로 준비하거나 수행해야 할 행동이 명확할 때만 추출하고,
  없으면 checklistItems: [] (빈 배열)로 둔다.
- 문서 전체 맥락을 통합적으로 파악해서 작성한다. 같은 행동(예: "신청서 제출하기"와
  "참가 동의서 제출하기")을 여러 일정에 중복으로 나누어 넣지 않는다. 하나의 행동은
  그 행동과 가장 직접적으로 연관된 단 하나의 일정에만 귀속시킨다.
- 같은 일정 내에서도 checklistItems끼리 서로 중복되거나 사실상 같은 행동을
  표현하는 항목을 여러 개 만들지 않는다.
- 먼저 보호자나 학생이 완료할 행동을 정리한 뒤 각 행동의 귀속 항목을 결정한다.
  신청, 제출, 납부 행동은 해당 deadline에만 연결한다. 이후 행사 schedule에는
  같은 신청 행동을 다시 넣지 않는다. 행사 당일 준비 행동이 없으면 빈 배열로 둔다.
- 신청 마감 날짜가 원문에 있지만 종료일 후보가 없으면 신청 deadline을 ambiguous로
  유지하고 신청 행동도 그 항목에 보존한다. missing reminder로 옮기거나 교육일에 붙이지 않는다.
- 동일 신청 절차인 '밴드 설문조사로 신청하기', '설문조사 완료하기', '신청하기'는
  하나로 합친다. 링크 확인이나 접속은 신청 방법으로 detail에 넣고 별도 할 일로 만들지 않는다.
  단, 원문에서 별도로 요구하는 사전 가입, 동의서 작성, 서명은 독립 행동으로 보존한다.
- 모집 인원과 참가 자격은 조건이지 보호자가 수행할 행동이 아니다.
  '6팀 모집하기', '참가 자격 확인하기', 근거 없는 '참석 준비하기'를 생성하지 않는다.
- 조건을 별도 할 일로 만들지 않는다는 것은 조건을 삭제하라는 뜻이 아니다.
  원문에 있는 신청 방법, 접수 시작/마감 시간, 선착순 여부, 참가 대상, 가정당 신청 단위와
  인원 제한은 신청 행동의 detail에 간결하게 보존한다.
  관련 조건이 있으면 detail을 null로 두지 않는다.
  예: 원문이 '밴드 설문 응답, 선착순, 초중학생 자녀와 보호자, 가정당 1팀 최대 4명'이면
  content는 '밴드 설문조사로 신청하기', detail은 '선착순 접수. 초중학생 자녀와 보호자가
  함께 참여하며 가정당 1팀, 최대 4명.'처럼 작성한다. 예시의 조건을 다른 문서에 추가하지 않는다.
  총 모집 규모와 가정당 인원 제한은 구분한다. 선택하지 않은 날짜를 detail에 원문대로
  적는 것은 가능하지만 이를 confirmed datetime으로 확정하지 않는다.
- '신청 시 개인정보 제공에 동의한 것으로 간주'는 신청의 안내 조건으로 보존한다.
  별도 동의 절차나 '동의하지 않으면 신청 불가'라는 원문에 없는 의무를 추가하지 않는다.
- 출력 전 각 content의 A 근거를 다시 확인한다. 간주 동의를 독립 행동으로 만들었거나
  '안전 책임지기/안전 유의하기'처럼 C를 reminder로 만들었다면 해당 행동을 제거한다.
  제거 후 행동이 없는 reminder는 제거하되 실제 교육/신청 일정은 유지한다.
  detail에는 일반적인 소개 문구보다 원문에 있는 B 조건을 우선 보존한다.
  번역에서도 조건의 적용 대상을 유지한다. 밴드 가입 연령을 행사 참가 연령으로 바꾸지 않는다.
- 최종 반환 전에 모든 items의 checklistItems를 함께 검토한다. 같은 행동이 여러
  항목에 있으면 직접적인 마감/준비 대상 한 곳에만 남기되 서로 다른 제출물은 합치지 않는다.
- content는 다문화 학부모가 실제로 수행할 수 있는 구체적 행동 단위로,
  "OO 제출하기", "OO 준비하기", "OO 동의서 작성하기"처럼 행동 지향적인
  짧은 문구로 작성하되, 항상 한국어로 작성한다. (사용자 언어로의 번역은
  이후 단계에서 별도로 처리한다.)
- contentI18n은 알림에서 사용할 체크리스트/할 일 이름이며 KO/US/ZH/VI 값을 모두 채운다.
- detailI18n도 contentI18n과 동일하게 KO/US/ZH/VI 값을 모두 채운다.
  detail이 null이면 detailI18n의 모든 언어 값도 빈 문자열("")로 채운다.
- 한국어 필드와 다국어 map은 같은 사실과 조건을 보존한다.
- 본문, 표, 첨부에서 반복된 같은 사건은 하나로 합친다. 날짜가 같아도 대상이나 목적이
  다른 실제 사건은 유지한다. 병합 시 checklistItems도 합치고 동일 행동만 중복 제거한다.
- 신청서와 동의서가 실제로 서로 다른 제출물이라면 별도 행동으로 보존한다.

분류 예시 (출력 구조가 아닌 판단 예시이며, 실제 응답은 전체 schema를 따른다):
- 입력: 학교 지원=클레이, 가정 구매=공책/연필, 학급별로 상이할 수 있음,
  하단 2026. 9. 2. 학교장 서명. 구매 기한 없음. 후보는 9월 2일 하나.
  올바른 결과: '개인 학습준비물 준비' reminder 1건, dateStatus=missing,
  selectedDateCandidate=null, datetime=null, needsUserConfirmation=false,
  confirmationQuestion=null. 행동은 '개인 학습준비물 준비하기',
  detail은 '공책, 연필. 학급별로 준비물이 다를 수 있음.'
  잘못된 결과: 9월 2일 '학습준비물 안내' schedule, 학교 지원 물품 확인하기.
- 입력: 위 안내에 '9월 7일까지 준비'가 추가됨.
  올바른 결과: 준비 deadline. 9월 7일 후보가 있으면 confirmed, 없으면 ambiguous.
  발행일만 있는 예시의 missing 규칙을 이 경우에 적용하지 않는다.
- 입력: 발행일과 별개로 교육일 및 신청 마감이 명시됨.
  올바른 결과: 교육 schedule과 신청 deadline을 각각 보존하고 신청 행동은 마감에만 연결.
  예시의 날짜, 물품, 조건을 현재 문서에 복사하지 않는다.

대화 주제(conversationTopics) 추출 원칙:
- 다문화 가정 학부모가 자녀(초등학생)와 나눌 수 있는 대화 주제를 최대 3개 추출한다.
- 아래 두 조건을 모두 만족하는 주제만 포함한다.
  1. 자녀와 직접 연관된 내용일 것:
     법령 안내, 급식비 납부, 개인정보 동의 등 행정·보호자 대상 내용은 제외한다.
  2. 문서 맥락에 맞는 시제로 작성할 것:
     - 신청/예정 안내(아직 일어나지 않은 일)라면 기대·계획 기반 질문만 허용한다.
       (예: 현장학습 신청서 → "이번 현장학습에서 제일 기대되는 게 뭐야?" O
                            / "거기서 뭐가 재미있었어?" X)
     - 결과/완료 안내(이미 일어난 일)라면 경험 기반 질문도 허용한다.
       (예: 현장학습 결과 안내 → "박물관에서 뭐가 제일 재미있었어?" O)
     - 학부모가 이미 알고 있는 사실(자녀가 어디 갔는지, 무엇을 했는지 등)을
       단순히 확인하는 질문은 제외한다.
       (예: "오늘 현장학습 갔다 왔지?" X, "급식 먹었어?" X)
- 추출된 주제들은 반드시 서로 다른 관점에서 작성한다.
  아래 관점 중 서로 다른 3가지를 선택해 각 1개씩 작성한다:
  (1) 감정/기대: 자녀가 어떤 감정이나 기대를 가지고 있는지
      (예: "이번 현장학습에서 제일 기대되는 게 뭐야?")
  (2) 사회적 관계: 친구나 선생님과의 관계, 함께하는 활동
      (예: "어떤 친구랑 같이 다니고 싶어?")
  (3) 구체적 계획/준비: 당일 무엇을 할지, 뭘 가져갈지
      (예: "도시락 뭐 싸줄지 같이 골라볼까?")
  (4) 학습/경험: 새롭게 알게 될 것, 배울 내용
      (예: "거기서 어떤 걸 배울 수 있을 것 같아?")
  - 같은 관점에서 2개 이상 뽑지 않는다.
  - 위 4가지 관점 중 적합한 게 3개 미만이면 그 수만큼만 반환한다.
- 위 조건을 만족하는 주제가 없으면 빈 배열([])을 반환한다.
- topic은 학부모가 자녀에게 바로 말할 수 있는 자연스러운 구어체 문장으로 작성한다.
- topic은 항상 한국어로 작성한다. (사용자 언어로의 번역은 이후 단계에서 별도로 처리한다.)

한국어 작성 원칙 (title/summary/items[].title/checklistItems/conversationTopics):
- original_text는 사실 판단의 기준이다.
- translated_text는 참고하지 않는다. (단일 필드는 항상 한국어로 작성하므로 번역 초안이 필요 없다.)
- 학교명, 기관명, 행사명, 고유명사는 원문 표기를 그대로 사용한다.
- 날짜, 시간, 금액, 준비물, 제출 대상 같은 핵심 정보는 빠뜨리지 않는다.
- enum 값(type, dateStatus), datetime, timezone, selectedDateCandidate.originalText는
  schema와 원문 추적을 위해 그대로 둔다 (원래도 번역 대상 아님).
- evidenceText, confirmationQuestion도 한국어로 작성한다.

알림용 다국어 map 생성 원칙:
- titleI18n, items[].titleI18n, checklistItems[].contentI18n, checklistItems[].detailI18n은 반드시
  KO/US/ZH/VI 네 키를 모두 가진다.
- 이 map들은 알림 목록과 푸시 알림의 동적 값으로 쓰일 수 있으므로
  사용자의 현재 언어와 무관하게 네 언어를 모두 생성한다.
- items[].titleI18n은 캘린더 preview 일정 이름으로 바로 사용할 수 있는 짧은 이름이어야 한다.
- checklistItems[].contentI18n은 알림에 표시할 체크리스트/할 일 이름으로 바로 사용할 수 있어야 한다.
- conversationTopics는 알림에 쓰지 않으므로 다국어 map을 만들지 않는다.
- 네 언어 값 모두 original_text의 사실관계와 날짜, 금액, 준비물, 기관명, 행사명을 보존한다.
""".strip()


def _build_user_prompt(request: NewsletterAnalysisRequest) -> str:
    translated_text = request.translated_text.strip() if request.translated_text else ""
    reference_date = request.reference_date.isoformat() if request.reference_date else "null"
    language_name = _language_name(request.language)
    sections = [
        f"referenceDate: {reference_date}",
        f"timezone: {request.timezone}",
        f"language: {request.language}",
        f"targetLanguageName: {language_name}",
        "",
        "<date_candidates>",
        _format_candidates(request),
        "</date_candidates>",
        "",
        "<original_text>",
        request.original_text.strip(),
        "</original_text>",
    ]
    if translated_text:
        sections.extend(
            [
                "",
                "<translated_text>",
                "아래 translated_text는 기계 번역 초안입니다. title/summary/items[].title/",
                "checklistItems/conversationTopics(한국어 고정 필드)에는 사용하지 않는다.",
                "titleI18n/checklistItems[].contentI18n(알림용 다국어 map) 생성 시에만",
                "참고자료로 활용한다.",
                translated_text,
                "</translated_text>",
            ]
        )
    return "\n".join(sections)


def _language_name(language: str | None) -> str:
    normalized = (language or "KO").strip().upper()
    return LANGUAGE_NAMES.get(normalized, LANGUAGE_NAMES["KO"])


def _format_candidates(request: NewsletterAnalysisRequest) -> str:
    if not request.date_candidates:
        return "[]"

    lines = []
    for index, candidate in enumerate(request.date_candidates):
        lines.append(
            f"- index: {index}, "
            f"candidateId: {candidate.candidate_id or 'null'}, "
            f"originalText: {candidate.original_text}, "
            f"normalizedDate: {candidate.normalized_date.isoformat()}, "
            f"startOffset: {candidate.start_offset}, "
            f"endOffset: {candidate.end_offset}, "
            f"extractionType: {candidate.extraction_type or 'null'}"
        )
    return "\n".join(lines)


REFINE_FIELD_SCHEMA = {
    "type": "string",
    "minLength": 1,
}

REFINE_RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["fields"],
    "properties": {
        "fields": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "text"],
                "properties": {
                    "id": {"type": "string", "minLength": 1},
                    "text": REFINE_FIELD_SCHEMA,
                },
            },
        },
    },
}


def build_refine_prompt_messages(
    original_text: str,
    language: str,
    fields: list[dict[str, str]],
) -> list[dict[str, str]]:

    return [
        {"role": "system", "content": _build_refine_system_prompt(language)},
        {"role": "user", "content": _build_refine_user_prompt(original_text, fields)},
    ]


def _build_refine_system_prompt(language: str) -> str:
    language_name = _language_name(language)
    return f"""
역할: 가정통신문 원문(한국어)과, 그 일부 문구를 한국어 → {language_name}로
기계번역(파파고)한 결과 목록을 받아서 교정한다.

원칙:
- response schema에 맞는 JSON만 반환한다 (fields[] 배열).
- fields[]의 각 원소는 입력으로 받은 fields와 동일한 id를 가져야 하며,
  누락되거나 새로운 id를 추가하지 않는다. 입력 순서와 개수를 그대로 유지한다.
- 입력으로 받은 translatedText(파파고 번역 결과)를 기본 베이스로 삼는다.
- translatedText가 자연스럽고 원문(originalText, koText)의 의미와 일치하면
  그대로 text에 반환한다 (불필요한 재작성 금지).
- translatedText가 어색하거나, 원문 의미와 다르거나, 숫자/날짜/금액 등 핵심
  정보가 누락·왜곡된 경우에만 {language_name}로 자연스럽게 다듬어서 반환한다.
- 새로운 정보를 추가하거나 임의로 의역을 확장하지 않는다. 어디까지나 "교정"이지
  "재작성"이 아니다.
- text는 항상 {language_name}로 작성한다 (translatedText의 언어를 유지).
- 학교명, 기관명, 행사명, 고유명사도 모두 {language_name}로 번역한다.
  원문 한국어 표기를 그대로 남기지 않는다 (예: "서울노원초등학교"를 한국어
  그대로 두지 않고 {language_name} 표기/음역으로 변환한다).
""".strip()


def _build_refine_user_prompt(original_text: str, fields: list[dict[str, str]]) -> str:
    field_lines = []
    for field in fields:
        field_lines.append(
            f"- id: {field['id']}\n"
            f"  koText: {field['koText']}\n"
            f"  translatedText: {field['translatedText']}"
        )

    sections = [
        "<original_text>",
        original_text.strip(),
        "</original_text>",
        "",
        "<fields>",
        "\n".join(field_lines),
        "</fields>",
    ]
    return "\n".join(sections)
