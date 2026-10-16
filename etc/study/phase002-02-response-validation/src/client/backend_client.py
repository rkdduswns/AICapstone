# 학습용 사본 — 실행/테스트에서 참조하는 구현 기준이 아닙니다.
# 주제: 응답 검증과 오류 분류
# 원본 경로: src/client/backend_client.py
# 원본 브랜치: feat/phase2-client
# 원본 commit SHA: 1174da04027e1757e66965f44f15e045efd0e668
# 복사 날짜: 2026-10-15 (Asia/Seoul)
# 원본과 다른 점: 한국어 설명 주석만 추가. 코드·문자열·기존 docstring은 보존.
# 읽는 방법: 번호가 붙은 주석을 따라가고 같은 폴더의 explanation.md를 함께 읽습니다.
# import는 실제 프로젝트 패키지를 가리킵니다. 이 사본은 독립 실행용 앱/테스트가 아닙니다.

"""Backend 연결 응답을 검증하고 화면에 표시할 연결 상태로 바꾼다."""

import json

from PySide6.QtCore import QObject, Signal

# [1단계: 전송과 의미 검증을 분리]
# JsonRequest는 HTTP·timeout·응답 바이트를 담당한다.
# 이 파일은 그 바이트가 '우리 Backend의 호환 가능한 health 응답'인지 검사한다.
# SERVICE_NAME/API_VERSION으로 같은 포트의 다른 프로그램을 정상 서버로 오인하지 않게 한다.
from client.json_request import JsonRequest
from shared.protocol import API_VERSION, DEFAULT_PORT, SERVICE_NAME


# [2단계: 바이트를 검증하고 버전 문자열만 반환]
# 네트워크/GUI 객체를 만들지 않는 함수라 입력 바이트만으로 단위 테스트할 수 있다.
# 성공하면 str을 반환하고 계약이 틀리면 ValueError 등의 예외로 알린다.
# 함수의 '-> str'은 반환 의도를 표시하며 실행 시 반환 타입을 자동 검사하지는 않는다.
def read_version(payload: bytes) -> str:
    """다른 서비스나 호환되지 않는 API를 정상 연결로 오인하지 않도록 검사한다."""
    # JSON 바이트를 Python 값으로 해석한다. 객체는 dict, 배열은 list, null은 None이 된다.
    # 파싱에 성공해도 결과가 dict라는 보장은 없다. b'[]'나 b'null'도 유효한 JSON이다.
    # 잘못된 JSON은 JSONDecodeError(ValueError의 하위 타입), 잘못된 인코딩은 별도 오류가 날 수 있다.
    body = json.loads(payload)
    # [2-1: 바깥 응답 껍데기 검사]
    # or는 앞 조건이 True면 뒤를 평가하지 않으므로 dict가 아닌 값에 .get을 호출하지 않는다.
    # 'is True'는 숫자 1 같은 값을 성공 플래그로 인정하지 않고 bool True만 받는다.
    # error는 None이어야 한다. 다만 .get은 키가 없어도 None이므로 다음 존재 검사도 필요하다.
    if not isinstance(body, dict) or body.get("ok") is not True or body.get("error") is not None:
        raise ValueError("Invalid response envelope")
    # error:null과 error 필드 자체가 없는 응답을 구분한다.
    # 앞의 .get 검사만으로는 둘을 구분할 수 없어 명시적으로 키 존재를 확인한다.
    if "error" not in body:
        raise ValueError("Missing error field")
    # [2-2: 실제 데이터 객체 검사]
    # data가 없거나 null/list이면 실패다. 바깥 형식이 맞아도 내부 객체를 별도로 검증한다.
    status = body.get("data")
    if not isinstance(status, dict):
        raise ValueError("Missing health status")
    # [2-3: 서버 식별과 통신 규격 검사]
    # service는 우리 Backend, status는 running, api_version은 정확한 정수 버전이어야 한다.
    # Python에서 bool은 int의 하위 타입이어서 isinstance(True, int)는 True다.
    # 그래서 type(value) is int로 bool을 거부한 다음 버전 값을 비교한다.
    # 앞의 or 조건이 잘못된 타입/누락을 잡으면 뒤의 status['api_version']은 평가하지 않는다.
    if (status.get("service") != SERVICE_NAME or status.get("status") != "running"
            or type(status.get("api_version")) is not int
            or status["api_version"] != API_VERSION):
        raise ValueError("Incompatible service")
    # [2-4: 표시할 앱 버전 검사]
    # 통신 버전(api_version)과 앱 버전(version)은 목적이 다르다.
    # 문자열이며 공백만으로 이루어지지 않았는지 확인한다.
    # .strip()은 유효성 판단에만 쓰며 반환값 자체를 strip해 바꾸지는 않는다.
    version = status.get("version")
    if not isinstance(version, str) or not version.strip():
        raise ValueError("Missing version")
    return version


# [3단계: 공통 전송 객체를 health 전용으로 확장]
# C# 상속처럼 기반 클래스의 get/close와 전송 상태를 재사용한다.
# 이 클래스는 경로 선택·응답 검증·연결 결과 신호에 집중한다.
class BackendClient(JsonRequest):
    """Phase 1의 수동 연결 확인을 유지하고 성공 여부를 별도 신호로 전달한다."""

    # result는 사람이 읽는 문구, connection_changed는 다른 로직이 쓸 bool 결과다.
    # 번역/문구가 바뀌어도 자동 조회 시작 여부가 바뀌지 않도록 역할을 나눈다.
    result = Signal(str)
    connection_changed = Signal(bool)

    # [4단계: 기반 클래스의 신호를 자신의 처리기로 연결]
    # super().__init__이 네트워크 관리자와 타이머를 만든다.
    # received는 _received로, failed는 _failed로 연결된다. 여기서는 아직 요청하지 않는다.
    def __init__(self, port: int = DEFAULT_PORT, parent: QObject | None = None) -> None:
        super().__init__(port, parent)
        self.received.connect(self._received)
        self.failed.connect(self._failed)

    # [5단계: 호출자가 연결 확인을 요청]
    # 상속한 get('/health')를 실행한 뒤 돌아간다.
    # 실제 성공/실패 안내는 응답 도착 또는 timeout 이후의 신호 경로에서 발생한다.
    def check(self) -> None:
        """UI 이벤트 루프를 막지 않고 서비스 상태를 요청한다."""
        self.get("/health")

    # [6단계: 전송상 성공한 본문을 의미상 검증]
    # HTTP 200과 JSON Content-Type 검사를 통과한 bytes가 들어온다.
    # read_version이 실패하면 전송 실패 때와 같은 안내 경로로 보낸다.
    # catch 대상에 JSONDecodeError를 따로 적지 않은 이유는 ValueError의 하위 타입이기 때문이다.
    def _received(self, payload: bytes) -> None:
        """검증된 응답일 때만 현재 창 정보 조회를 시작할 수 있게 한다."""
        try:
            version = read_version(payload)
        # content_type이라는 내부 분류에는 잘못된 매체 유형뿐 아니라 내용 규격 위반도 포함한다.
        # 실패 후 return하므로 아래의 '연결됨'/True 신호가 잘못 발생하지 않는다.
        except (ValueError, UnicodeDecodeError):
            self._failed("content_type", 0)
            return
        # 모든 검증이 끝난 경우에만 표시 문구와 성공 상태를 차례로 알린다.
        # MainWindow는 result를 받아 문구/버튼을, connection_changed를 받아 후속 조회를 처리한다.
        self.result.emit(f"연결됨 — Backend {version}")
        self.connection_changed.emit(True)

    # [7단계: 전송 실패 또는 내용 검증 실패를 사용자 상태로 변환]
    # 실패 원인별 고정 문구를 선택한다. 서버의 원시 본문이나 예외 문자열을 그대로 표시하지 않는다.
    # status는 공통 failed 신호와 맞춘 인자다. 현재 안내 문구에는 HTTP 숫자를 넣지 않는다.
    # 아래 사전은 알려진 네 가지 reason을 전제로 []로 조회하므로 임의 원인을 보내면 KeyError다.
    def _failed(self, reason: str, status: int) -> None:
        """서버 원문이나 내부 예외를 노출하지 않는 기존 연결 안내를 유지한다."""
        message = {
            "timeout": "시간 초과 — 다시 확인해 주세요.",
            "http": "상태 확인 실패 — HTTP 오류",
            "network": "연결 안 됨 — Backend 실행 후 다시 확인해 주세요.",
            "content_type": "호환되지 않는 응답",
        }[reason]
        self.result.emit(message)
        # 실패도 화면 문구와 bool 상태를 함께 알린다. 이전 성공 상태가 남지 않게 하는 마지막 단계다.
        self.connection_changed.emit(False)
