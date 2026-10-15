# 학습용 사본 — 실행/테스트에서 참조하는 구현 기준이 아닙니다.
# 주제: 비동기 HTTP·timeout·자원 정리
# 원본 경로: src/client/json_request.py
# 원본 브랜치: feat/phase2-client
# 원본 commit SHA: 1174da04027e1757e66965f44f15e045efd0e668
# 복사 날짜: 2026-10-15 (Asia/Seoul)
# 원본과 다른 점: 한국어 설명 주석만 추가. 코드·문자열·기존 docstring은 보존.
# 읽는 방법: 번호가 붙은 주석을 따라가고 같은 폴더의 explanation.md를 함께 읽습니다.
# import는 실제 프로젝트 패키지를 가리킵니다. 이 사본은 독립 실행용 앱/테스트가 아닙니다.

"""두 상태 API에서 함께 사용하는 비동기 HTTP 요청과 취소 처리."""

# [1단계: Qt의 비동기 통신 도구]
# QObject는 신호와 부모/자식 수명 관리, QTimer는 시간 이벤트, QUrl은 URL 표현을 제공한다.
# QNetworkAccessManager가 요청을 시작하고 QNetworkReply가 응답 상태와 본문을 제공한다.
# 이 파일은 asyncio나 직접 만든 작업 스레드를 사용하지 않는다. Qt 이벤트 루프를 이용한다.
from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkProxy, QNetworkReply, QNetworkRequest

from shared.protocol import DEFAULT_PORT


# [2단계: 전송 계층의 책임]
# 주소로 GET을 보내고 '본문 바이트' 또는 '실패 종류'를 알리는 공통 객체다.
# 이름에 Json이 있지만 이 파일은 json.loads를 호출하지 않는다.
# JSON 매체 유형을 확인한 다음, 실제 JSON 구조 검증은 BackendClient 등의 상위 계층에 맡긴다.
class JsonRequest(QObject):
    """요청 하나만 유지하며 UI를 멈추지 않고 결과 또는 오류 종류를 알린다."""

    # 클래스 수준에서 신호의 인자 타입을 선언한다.
    # received는 받은 본문, failed는 실패 이유(str)와 HTTP 상태 코드(int)를 전달한다.
    # 전송 상태를 화면 문구로 바꾸는 책임은 이 객체에 넣지 않는다.
    received = Signal(bytes)
    failed = Signal(str, int)

    # [3단계: 요청 전의 준비 상태]
    # port와 Qt 부모를 받고, 부모 QObject 초기화 후 네트워크 관리자/타이머를 만든다.
    # 이때 요청은 아직 전송하지 않는다. 최초 상태는 reply=None, timed_out=False다.
    def __init__(self, port: int = DEFAULT_PORT, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.port = port
        # 관리자 객체를 self의 Qt 자식으로 둔다. 같은 객체를 여러 요청에 재사용할 수 있다.
        # 바로 아래 NoProxy 설정은 loopback 요청을 시스템 프록시로 보내지 않기 위한 것이다.
        self.manager = QNetworkAccessManager(self)
        # 로컬 작업 정보를 시스템 프록시로 전달하지 않는다.
        self.manager.setProxy(QNetworkProxy(QNetworkProxy.ProxyType.NoProxy))
        # QTimer도 self의 자식이다. SingleShot은 한 번 만료되면 자동 반복하지 않는다는 뜻이다.
        # 간격 단위는 밀리초이므로 3000은 3초다. timeout 신호를 _timeout과 연결한다.
        # 타이머 콜백은 이벤트 루프가 처리하므로 UI 스레드를 막으면 정확히 제때 호출되지 않을 수 있다.
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(3000)
        self.timer.timeout.connect(self._timeout)
        # reply는 '현재 진행 중인 요청 객체' 또는 None이다. 동시에 하나의 요청만 유지하는 표식이다.
        # timed_out은 취소 원인이 시간 초과였는지 구분한다. abort 자체의 오류와 구별할 때 쓴다.
        self.reply: QNetworkReply | None = None
        self.timed_out = False

    # [4단계: 요청 시작]
    # 입력 path는 /health 같은 API 경로다. 서버 주소는 127.0.0.1로 고정한다.
    # 진행 중이면 새 요청을 만들지 않고 돌아간다. 새 요청을 시작할 때 timeout 표식을 초기화한다.
    # 이 메서드는 결과 바이트를 return하지 않는다. 결과는 나중에 신호로 전달한다.
    def get(self, path: str) -> None:
        """고정된 loopback 주소에 요청하며 진행 중인 요청을 중복 생성하지 않는다."""
        if self.reply is not None:
            return
        self.timed_out = False
        request = QNetworkRequest(QUrl(f"http://127.0.0.1:{self.port}{path}"))
        # b 접두사는 문자열이 아닌 bytes 리터럴이다. Qt의 원시 헤더 API에 맞춰 사용한다.
        # Accept는 원하는 응답 형식을 알리는 헤더이며 서버의 준수를 강제하지는 않는다.
        # 따라서 수신 시 실제 Content-Type을 다시 확인한다.
        request.setRawHeader(b"Accept", b"application/json")
        # 다른 주소로의 이동을 따르지 않고 API 오류로 처리한다.
        # [4-1: 리다이렉트 자동 추적 금지]
        # 3xx 응답의 다른 주소를 자동으로 따라가지 않는다. 이 앱은 고정된 로컬 API를 기대한다.
        # 따라서 이동 응답은 _finished에서 200이 아닌 HTTP 응답으로 분류한다.
        request.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,
                             QNetworkRequest.RedirectPolicy.ManualRedirectPolicy)
        # [4-2: 비동기 요청 등록]
        # get은 전체 응답을 기다리지 않고 QNetworkReply를 돌려준다.
        # finished 신호에 콜백을 연결하고 타이머를 시작한 뒤 호출자에게 제어가 돌아간다.
        # 사용자가 클릭/창 이동을 계속 할 수 있는 이유는 기다리는 동안 이벤트 루프를 막지 않기 때문이다.
        self.reply = self.manager.get(request)
        self.reply.finished.connect(self._finished)
        self.timer.start()

    # [5단계: 제한 시간이 먼저 지난 경우]
    # 현재 요청이 남아 있으면 원인 표식을 먼저 세우고 abort로 취소한다.
    # Qt의 abort는 finished도 발생시킨다. 이후 _finished가 timeout을 우선 분류한다.
    # 순서가 반대이면 취소 콜백이 원인을 읽을 때 아직 timed_out=False일 수 있다.
    def _timeout(self) -> None:
        """수신 도중에도 전체 요청 제한 시간이 지나면 중단한다."""
        if self.reply is not None:
            self.timed_out = True
            self.reply.abort()

    # [6단계: 성공·실패·취소 후 공통 마무리]
    # finished가 '성공'을 뜻하지는 않는다. timeout/HTTP/네트워크/본문 형식을 순서대로 검사한다.
    # 현재 reply를 지역 변수에 보관한 뒤 self.reply를 먼저 비워 완료 상태로 전환한다.
    # 신호 수신자가 다음 요청을 시작해도 이전 요청 객체는 지역 변수 reply로 정리할 수 있다.
    def _finished(self) -> None:
        """HTTP/전송 오류를 먼저 확인하고 JSON 형식의 본문을 상위 계층에 전달한다."""
        reply = self.reply
        if reply is None:
            return
        self.reply = None
        self.timer.stop()
        try:
            # HTTP 응답을 못 받았다면 상태 코드가 없을 수 있다.
            # 먼저 timed_out을 보고, 다음으로 받은 HTTP 상태, 다음으로 전송 오류를 본다.
            # HTTP 500 응답은 Qt의 오류 상태도 동반할 수 있으므로 HTTP 분류를 앞에 둔다.
            # 이 코드에서 정상으로 인정하는 HTTP 코드는 정확히 200이다.
            status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
            if self.timed_out:
                self.failed.emit("timeout", 0)
            elif status is not None and status != 200:
                self.failed.emit("http", status)
            elif reply.error() != QNetworkReply.NetworkError.NoError:
                self.failed.emit("network", 0)
            else:
                # [6-1: 성공 HTTP 응답의 매체 유형 확인]
                # 'application/json; charset=utf-8'에서 ';' 뒤 매개변수를 떼고 공백/대소문자를 정규화한다.
                # 정확히 application/json만 허용한다. JSON 문법이나 필드가 맞다는 보장은 아직 없다.
                content_type = str(reply.header(QNetworkRequest.KnownHeaders.ContentTypeHeader))
                if content_type.split(";")[0].strip().lower() != "application/json":
                    self.failed.emit("content_type", 0)
                else:
                    # 수신 버퍼 전체를 읽고 Qt의 바이트 배열을 Python bytes로 바꿔 신호로 전달한다.
                    # 상위 객체의 JSON 파서가 다음 단계에서 내용을 검증한다.
                    self.received.emit(bytes(reply.readAll()))
        # [6-2: 분기에 관계없이 응답 객체 정리]
        # try 안에서 어느 분기를 탔든 finally를 수행한다.
        # finished 콜백 안에서 응답을 즉시 파괴하지 않고 deleteLater로 삭제를 예약한다.
        # 실제 삭제는 Qt의 이벤트 처리에 맡긴다. Python의 del과 동일한 동작이 아니다.
        finally:
            # Qt 콜백 실행 중 즉시 삭제하지 않고 이벤트 루프에서 정리한다.
            reply.deleteLater()

    # [7단계: 화면 종료/재확인에 따른 취소]
    # timeout을 멈추고, 진행 중 reply를 지역 변수에 옮기면서 self.reply를 비운다.
    # finished 연결을 먼저 끊어 abort 후의 콜백이 닫힌 화면을 갱신하지 못하게 한다.
    # 시간 초과 취소는 결과를 안내해야 하므로 연결을 유지하고, 여기의 종료 취소는 알리지 않는다.
    def close(self) -> None:
        """종료/재확인 시 늦은 응답이 화면을 갱신하지 못하도록 연결부터 해제한다."""
        self.timer.stop()
        if self.reply is not None:
            # Python의 다중 대입은 오른쪽 값을 먼저 평가한 뒤 왼쪽에 배정한다.
            # 그래서 이전 요청을 reply에 보관하면서 self.reply=None으로 만들 수 있다.
            # 이후 disconnect → abort → deleteLater 순서로 처리한다.
            reply, self.reply = self.reply, None
            reply.finished.disconnect(self._finished)
            reply.abort()
            reply.deleteLater()
