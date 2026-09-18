"""Asynchronous loopback health requests using Qt's event loop."""

import json

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkProxy, QNetworkReply, QNetworkRequest

from shared.protocol import API_VERSION, DEFAULT_PORT, SERVICE_NAME


def read_version(payload: bytes) -> str:
    body = json.loads(payload)
    if not isinstance(body, dict) or body.get("ok") is not True or body.get("error") is not None:
        raise ValueError("Invalid response envelope")
    if "error" not in body:
        raise ValueError("Missing error field")
    status = body.get("data")
    if not isinstance(status, dict):
        raise ValueError("Missing health status")
    if (status.get("service") != SERVICE_NAME or status.get("status") != "running"
            or type(status.get("api_version")) is not int
            or status["api_version"] != API_VERSION):
        raise ValueError("Incompatible service")
    version = status.get("version")
    if not isinstance(version, str) or not version.strip():
        raise ValueError("Missing version")
    return version


class BackendClient(QObject):
    result = Signal(str)

    def __init__(self, port: int = DEFAULT_PORT, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.port = port
        self.manager = QNetworkAccessManager(self)
        self.manager.setProxy(QNetworkProxy(QNetworkProxy.ProxyType.NoProxy))
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(3000)
        self.timer.timeout.connect(self._timeout)
        self.reply: QNetworkReply | None = None
        self.timed_out = False

    def check(self) -> None:
        if self.reply is not None:
            return
        self.timed_out = False
        request = QNetworkRequest(QUrl(f"http://127.0.0.1:{self.port}/health"))
        request.setRawHeader(b"Accept", b"application/json")
        request.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,
                             QNetworkRequest.RedirectPolicy.ManualRedirectPolicy)
        self.reply = self.manager.get(request)
        self.reply.finished.connect(self._finished)
        self.timer.start()

    def _timeout(self) -> None:
        if self.reply is not None:
            self.timed_out = True
            self.reply.abort()

    def _finished(self) -> None:
        reply = self.reply
        if reply is None:
            return
        self.reply = None
        self.timer.stop()
        try:
            status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
            if self.timed_out:
                message = "시간 초과 — 다시 확인해 주세요."
            elif status is not None and status != 200:
                message = "상태 확인 실패 — HTTP 오류"
            elif reply.error() != QNetworkReply.NetworkError.NoError:
                message = "연결 안 됨 — Backend 실행 후 다시 확인해 주세요."
            else:
                content_type = str(reply.header(QNetworkRequest.KnownHeaders.ContentTypeHeader))
                try:
                    if content_type.split(";")[0].strip().lower() != "application/json":
                        raise ValueError("Invalid content type")
                    version = read_version(bytes(reply.readAll()))
                    message = f"연결됨 — Backend {version}"
                except (ValueError, UnicodeDecodeError):
                    message = "호환되지 않는 응답"
            self.result.emit(message)
        finally:
            reply.deleteLater()

    def close(self) -> None:
        self.timer.stop()
        if self.reply is not None:
            reply, self.reply = self.reply, None
            reply.finished.disconnect(self._finished)
            reply.abort()
            reply.deleteLater()
