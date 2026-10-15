# 학습용 사본 — 실행/테스트에서 참조하는 구현 기준이 아닙니다.
# 주제: Python 데이터 구조
# 원본 경로: src/shared/activity.py
# 원본 브랜치: feat/phase3-client
# 원본 commit SHA: e698b9af7cd37f963fd94092b170e85e8d80e1d3
# 복사 날짜: 2026-10-15 (Asia/Seoul)
# 원본과 다른 점: 한국어 설명 주석만 추가. 코드·문자열·기존 docstring은 보존.
# 읽는 방법: 번호가 붙은 주석을 따라가고 같은 폴더의 explanation.md를 함께 읽습니다.
# import는 실제 프로젝트 패키지를 가리킵니다. 이 사본은 독립 실행용 앱/테스트가 아닙니다.

"""Phase 2 현재 창 응답 규격. OS 감지나 UI 처리에 의존하지 않는다."""

# [1단계: 사용할 도구를 가져오기]
# dataclass는 필드 선언을 읽고 __init__, __repr__, __eq__ 등을 만들어 주는 장식자다.
# C#의 데이터 전달용 클래스/record와 목적을 비교해 보면 이해하기 쉽다.
# 다만 동일한 언어 기능은 아니다. Python의 필드 타입 표기는 기본적으로 강제되지 않는다.
# Literal은 정해진 값만 사용한다는 타입 계약을 표현한다. 아래에서 실제 사용 예를 본다.
from dataclasses import dataclass
from typing import Literal

# 서비스명과 통신 규격 버전을 공통 모듈에서 가져온다.
# 화면/서버 중 한쪽이 별도의 문자열을 관리하면 값이 어긋날 수 있기 때문이다.
# shared는 UI와 서버 구현을 import하지 않는 공통 데이터 경계다.
from shared.protocol import API_VERSION, SERVICE_NAME

# [2단계: 주소와 상태 종류 정의]
# 이 상수는 주소를 정의할 뿐 API를 만들거나 HTTP 요청을 보내지 않는다.
# CollectionStatus는 클래스나 검사 함수가 아닌 타입 별칭이다.
# 예를 들어 collection_status='collecting'은 계약에 맞고 'busy'는 맞지 않는다.
# 그러나 Literal 자체가 런타임 입력을 거부하지는 않는다. 응답 파서의 검증이 따로 필요하다.
ACTIVITY_PATH = "/activity/current"
CollectionStatus = Literal["collecting", "no_active_window", "unsupported", "error"]


# [3단계: 창 정보 하나를 표현하기]
# @장식자는 바로 다음 클래스 정의에 적용된다.
# frozen=True는 생성한 객체의 필드를 일반 대입으로 바꾸지 못하게 한다.
# 새로운 감지 결과는 기존 객체를 수정하기보다 새 스냅샷 객체로 표현한다.
# 이것이 모든 내부 객체를 재귀적으로 불변으로 만들거나 입력 타입을 검사한다는 뜻은 아니다.
@dataclass(frozen=True)
class ActiveWindow:
    """Backend가 감지·정규화한 현재 창 정보이며 저장 기록이나 작업 시간은 아니다."""

    # application은 화면에서 읽기 좋은 프로그램명, process_name은 실행 프로세스명이다.
    # process_id는 특정 프로세스를 구분하는 정수이며 창 제목과 역할이 다르다.
    # ':' 뒤는 타입 힌트다. 이 선언들로 생성자 인자와 저장할 필드를 정한다.
    # 예: ActiveWindow('Chrome', 'chrome.exe', 1234, '예시 문서').
    application: str
    process_name: str
    process_id: int
    window_title: str


# [4단계: 시각과 지속 시간을 분리하기]
# started_at은 '언제 시작했는가'이고 active_duration_ms는 '얼마나 활성 상태였는가'다.
# 문자열에는 시간대가 포함된 ISO 8601 시각을 전달하고, 누적 시간의 단위는 밀리초다.
# 예: 65_000은 65초다. 이 클래스는 시간을 계산하거나 현재 시각을 읽지 않는다.
@dataclass(frozen=True)
class ActivityTiming:
    """Backend 작업 시작 시각(시간대 포함 ISO 8601)과 누적 활성 밀리초."""

    started_at: str
    active_duration_ms: int


# [5단계: 창·수집 상태·시간을 하나의 스냅샷으로 묶기]
# 창 객체만으로는 '활성 창 없음'과 '감지 오류'를 구분하기 어렵다.
# collection_status로 원인을 나타내고, 창이 없을 때 window=None으로 표현한다.
# 감지 성공 여부와 window 유무의 일관성은 생산자와 응답 파서에서 지켜야 한다.
# dataclass 생성자가 이 관계를 자동 검사하는 것은 아니다.
@dataclass(frozen=True)
class CurrentActivity:
    """감지 성공일 때만 window를 제공하고 나머지 상태에서는 None으로 비운다."""

    collection_status: CollectionStatus
    # A | None은 'A 객체 또는 값이 없음'이라는 뜻이다. C# nullable 개념과 비교할 수 있다.
    # 이 줄에는 기본값이 없으므로 생성자에서 window 인자를 반드시 전달해야 한다.
    # 값으로 None을 허용한다는 사실과 인자 생략을 허용한다는 사실은 서로 다르다.
    window: ActiveWindow | None
    # '=' 뒤는 생성자 인자를 생략했을 때 사용할 기본값이다.
    # 필수 필드를 먼저, 기본값이 있는 필드를 나중에 둔다. dataclass 생성자 순서에 영향을 준다.
    # 기본값은 덮어쓸 수도 있으므로 외부 응답의 서비스명/버전 검증을 대신하지 않는다.
    service: str = SERVICE_NAME
    api_version: int = API_VERSION
    # timing은 None을 허용하면서 기본값도 None이다. 따라서 이전 호출자는 생략할 수 있다.
    # 시간 미제공은 0ms와 다르다. 화면은 None이면 '시간 정보 없음'으로 표시한다.
    # 창 감지 모델에 시간 필드를 선택적으로 추가해 이전 응답과의 호환을 유지한 부분이다.
    timing: ActivityTiming | None = None


# [6단계: 공통 응답 껍데기에 담기]
# data에는 실제 수집 상태, 바깥의 ok/error에는 API 처리 결과를 담는다.
# ok=True여도 collection_status='no_active_window'일 수 있다.
# 즉 '정상 응답을 받음'과 '창이 감지됨'을 따로 다룬다.
# 여기에는 실패 응답 클래스나 JSON 직렬화 코드가 없다. 성공 응답 형태만 정의한다.
@dataclass(frozen=True)
class CurrentActivityResponse:
    """통신 성공과 실제 창 감지 상태를 구분하는 공통 응답 구조."""

    data: CurrentActivity
    # Literal[True]는 일반 bool보다 좁은 타입 계약이다. 성공 응답에는 True만 사용한다.
    # error: None은 성공 응답의 error 필드가 비어 있다는 계약이다.
    # Python의 None은 JSON으로 변환할 때 null로 표현된다.
    ok: Literal[True] = True
    error: None = None
