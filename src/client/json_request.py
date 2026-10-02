"""두 상태 API에서 함께 사용하는 비동기 HTTP 요청과 취소 처리."""

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkProxy, QNetworkReply, QNetworkRequest

from shared.protocol import DEFAULT_PORT


class JsonRequest(QObject):
    """요청 하나만 유지하며 UI를 멈추지 않고 결과 또는 오류 종류를 알린다."""

    received = Signal(bytes)
    failed = Signal(str, int)

    def __init__(self, port: int = DEFAULT_PORT, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.port = port
        self.manager = QNetworkAccessManager(self)
        # 로컬 작업 정보를 시스템 프록시로 전달하지 않는다.
        self.manager.setProxy(QNetworkProxy(QNetworkProxy.ProxyType.NoProxy))
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(3000)
        self.timer.timeout.connect(self._timeout)
        self.reply: QNetworkReply | None = None
        self.timed_out = False

    def get(self, path: str) -> None:
        """고정된 loopback 주소에 요청하며 진행 중인 요청을 중복 생성하지 않는다."""
        if self.reply is not None:
            return
        self.timed_out = False
        request = QNetworkRequest(QUrl(f"http://127.0.0.1:{self.port}{path}"))
        request.setRawHeader(b"Accept", b"application/json")
        # 다른 주소로의 이동을 따르지 않고 API 오류로 처리한다.
        request.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,
                             QNetworkRequest.RedirectPolicy.ManualRedirectPolicy)
        self.reply = self.manager.get(request)
        self.reply.finished.connect(self._finished)
        self.timer.start()

    def _timeout(self) -> None:
        """수신 도중에도 전체 요청 제한 시간이 지나면 중단한다."""
        if self.reply is not None:
            self.timed_out = True
            self.reply.abort()

    def _finished(self) -> None:
        """HTTP/전송 오류를 먼저 확인하고 JSON 형식의 본문을 상위 계층에 전달한다."""
        reply = self.reply
        if reply is None:
            return
        self.reply = None
        self.timer.stop()
        try:
            status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
            if self.timed_out:
                self.failed.emit("timeout", 0)
            elif status is not None and status != 200:
                self.failed.emit("http", status)
            elif reply.error() != QNetworkReply.NetworkError.NoError:
                self.failed.emit("network", 0)
            else:
                content_type = str(reply.header(QNetworkRequest.KnownHeaders.ContentTypeHeader))
                if content_type.split(";")[0].strip().lower() != "application/json":
                    self.failed.emit("content_type", 0)
                else:
                    self.received.emit(bytes(reply.readAll()))
        finally:
            # Qt 콜백 실행 중 즉시 삭제하지 않고 이벤트 루프에서 정리한다.
            reply.deleteLater()

    def close(self) -> None:
        """종료/재확인 시 늦은 응답이 화면을 갱신하지 못하도록 연결부터 해제한다."""
        self.timer.stop()
        if self.reply is not None:
            reply, self.reply = self.reply, None
            reply.finished.disconnect(self._finished)
            reply.abort()
            reply.deleteLater()
