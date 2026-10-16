# 학습용 사본 — 실행/테스트에서 참조하는 구현 기준이 아닙니다.
# 주제: pytest와 비동기 UI 테스트
# 원본 경로: tests/client/test_connection.py
# 원본 브랜치: feat/phase4-client
# 원본 commit SHA: a3a1aec2ecce25bad7c1de7547279b766929d8a1
# 복사 날짜: 2026-10-15 (Asia/Seoul)
# 원본과 다른 점: 한국어 설명 주석만 추가. 코드·문자열·기존 docstring은 보존.
# 읽는 방법: 번호가 붙은 주석을 따라가고 같은 폴더의 explanation.md를 함께 읽습니다.
# import는 실제 프로젝트 패키지를 가리킵니다. 이 사본은 독립 실행용 앱/테스트가 아닙니다.

# [읽는 순서]
# 먼저 fixture(app/fake_server)와 대기 도우미를 보고, 순수 파서 → UI 응답 → timeout → 실제 서버 순으로 읽는다.
# pytest가 test_로 시작하는 함수를 수집하고 인자 이름에 맞는 fixture를 준비한다.
# 이 사본은 읽기용이다. 원본 테스트의 import/프로세스 실행 코드까지 보존되어 있으므로 직접 실행하지 않는다.
import json
import os
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest

# [1단계: 테스트 실행 환경 설정]
# Windows에서는 실제 플랫폼 플러그인을 사용하고 다른 OS에서는 offscreen을 기본값으로 둔다.
# Qt 애플리케이션을 만들기 전에 설정한다. setdefault는 이미 설정된 환경값을 덮어쓰지 않는다.
# 화면 없는 CI에서도 UI 상태를 검사하기 위한 설정이며 실제 Windows 사용성 검증을 대신하지 않는다.
# Windows uses its native platform plugin; Linux CI has no display server.
if sys.platform != "win32":
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from client.backend_client import read_version
from client.window import MainWindow

# [2단계: 가상 정상 응답]
# 실제 사용자 기록이 아닌 health 규격의 예시 데이터다.
# json.dumps는 JSON 문자열을 만들고 .encode()는 전송할 bytes로 바꾼다.
# 각 테스트는 여기에서 일부 필드를 바꿔 정상/오류 상황을 만든다.
GOOD = {"ok": True, "error": None, "data": {
    "service": "contexttrace-backend", "status": "running", "version": "0.1.0", "api_version": 1}}


# [3단계: Qt 애플리케이션 fixture]
# scope='module'은 이 파일의 테스트들이 같은 fixture 결과를 재사용한다는 뜻이다.
# QApplication이 이미 있으면 사용하고 없으면 하나 만든다. 여러 개를 만들지 않기 위한 패턴이다.
# 마지막 창을 닫아도 테스트 중인 앱이 종료되지 않게 설정한다.
@pytest.fixture(scope="module")
def app():
    instance = QApplication.instance() or QApplication([])
    instance.setQuitOnLastWindowClosed(False)
    return instance


# [4단계: 비동기 완료 조건 기다리기]
# predicate는 '버튼이 다시 활성화되었는가' 같은 bool 반환 함수다.
# 고정된 긴 sleep 대신 조건을 반복 확인하면서 app.processEvents로 Qt 이벤트를 처리한다.
# 이 함수는 테스트용 수동 이벤트 처리다. 제품 코드에서 같은 대기 루프를 복제하지 않는다.
def wait_for(app, predicate, timeout=5):
    # monotonic은 시스템 시각 조정에 영향을 받지 않는 경과 시간용 시계다.
    # 완료 조건이 안 되면 잠깐 쉬고 재확인하되 deadline 이후에는 명확히 테스트를 실패시킨다.
    # 이벤트 처리가 없으면 네트워크/타이머 콜백도 진행하지 못해 기다리기만 할 수 있다.
    deadline = time.monotonic() + timeout
    while not predicate():
        app.processEvents()
        if time.monotonic() >= deadline:
            pytest.fail("Qt operation timed out")
        time.sleep(0.005)
    app.processEvents()


# [5단계: 원하는 응답을 만드는 로컬 가상 HTTP 서버]
# 기본 범위가 function이므로 이 fixture를 사용하는 테스트마다 서버/설정이 새로 만들어진다.
# 반환할 본문·상태 코드·지연을 settings 사전에 두어 테스트에서 조절할 수 있게 한다.
# 이 서버는 전송과 UI 흐름을 시험한다. 실제 Windows 창 감지는 시험하지 않는다.
@pytest.fixture
def fake_server():
    settings = {"body": json.dumps(GOOD).encode(), "status": 200, "delay": 0}

    # 내부 클래스의 메서드는 바깥 fake_server의 settings를 참조한다.
    # 테스트가 settings를 바꾸면 다음 요청 처리에서 같은 사전의 변경값을 읽는다.
    # do_GET이라는 이름은 BaseHTTPRequestHandler가 GET 요청에서 호출하기로 정한 메서드다.
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            # 지연은 별도 서버 요청 처리 쪽에서 만든다. UI 스레드에서 서버 지연을 흉내 내지 않는다.
            # send_response → 헤더 → end_headers → 본문 순서로 HTTP 응답을 보낸다.
            time.sleep(settings["delay"])
            self.send_response(settings["status"])
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            try:
                self.wfile.write(settings["body"])
            # timeout/종료 테스트에서는 클라이언트가 먼저 취소해 응답을 쓸 연결이 사라질 수 있다.
            # 이 특정 상황의 연결 종료만 허용한다. 모든 예외를 무조건 무시하는 패턴은 아니다.
            except (BrokenPipeError, ConnectionResetError):
                return  # Expected when the client cancels a delayed test request.

        # 가상 서버의 기본 요청 로그가 테스트 출력을 채우지 않게 오버라이드한다.
        # *args는 여러 위치 인자를 묶어 받는 Python 문법이다.
        def log_message(self, *args):
            return

    # [5-1: 서버 시작과 테스트에 자원 전달]
    # 포트 0은 운영체제가 비어 있는 포트를 선택하게 한다. 실제 값은 server.server_port로 얻는다.
    # serve_forever를 별도 스레드에서 실행해 테스트 함수가 동시에 요청을 보낼 수 있게 한다.
    # daemon=True만 믿고 자원을 남기지 않고, 아래에서 명시적으로 종료한다.
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    # yield 앞은 준비, 넘긴 튜플은 테스트 입력, yield 뒤는 fixture 정리 단계다.
    # server.shutdown → server_close → thread.join으로 요청 루프·소켓·스레드를 정리한다.
    # 테스트가 assertion에 실패해도 pytest는 fixture 정리 단계를 진행한다.
    yield server.server_port, settings
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


# [6단계: 파서 단위 테스트 — 잘못된 API 버전]
# 한 테스트 함수를 네 입력으로 각각 실행한다. bool/문자열/다른 정수/누락 값에 대응한다.
# True는 Python에서 int의 하위 타입인 bool이므로 특별히 중요한 경계 사례다.
@pytest.mark.parametrize("version", [True, "1", 2, None])
def test_reject_incompatible_api_version(version):
    # 중첩 사전까지 별도 객체로 만들어 GOOD 원본을 오염시키지 않는다.
    # 얕은 복사만 하면 내부 data 사전이 공유되어 다음 테스트에 영향을 줄 수 있다.
    # JSON 왕복은 이 예시의 JSON 호환 데이터에 사용한 복사 방식이며 모든 객체의 일반 복사는 아니다.
    body = json.loads(json.dumps(GOOD))
    body["data"]["api_version"] = version
    # 이 블록에서 ValueError 또는 하위 예외가 발생해야 테스트가 통과한다.
    # 예외가 안 나거나 다른 종류만 발생하면 실패한다. '오류 입력을 거부함'이 기대 동작이다.
    with pytest.raises(ValueError):
        read_version(json.dumps(body).encode())


# [7단계: 파서 단위 테스트 — JSON 문법과 응답 구조]
# not json은 문법 오류, []/null은 파싱 가능하지만 잘못된 최상위 타입, {}는 필드 누락이다.
# 문법 검증과 서비스 응답 규격 검증이 서로 다름을 보여 준다.
@pytest.mark.parametrize("body", [b"not json", b"[]", b"null", b'{}'])
def test_reject_malformed_response(body):
    with pytest.raises(ValueError):
        read_version(body)


# [8단계: 실제 HTTP 왕복을 포함한 UI 응답 테스트]
# 정상, HTTP 500, 잘못된 JSON, 다른 서비스 응답을 같은 흐름으로 시험한다.
# **사전은 사전 펼치기 문법이다. GOOD의 필요한 부분만 덮어쓴 새 예시를 만든다.
@pytest.mark.parametrize("status,body,expected", [
    (200, json.dumps(GOOD).encode(), "연결됨"),
    (500, b'{}', "상태 확인 실패"),
    (200, b'bad json', "호환되지 않는 응답"),
    (200, json.dumps({**GOOD, "data": {**GOOD["data"], "service": "other"}}).encode(),
     "호환되지 않는 응답"),
])
# app/fake_server는 fixture, status/body/expected는 parametrize가 제공한다.
# 창을 만들고 버튼 클릭 후 비활성화 → 응답 뒤 활성화/문구/시각을 확인한다.
# 네트워크 함수를 가짜로 대체한 것이 아니라 가상 서버와 실제 Qt HTTP 경로를 사용한다.
def test_window_response(app, fake_server, status, body, expected):
    port, settings = fake_server
    settings.update(status=status, body=body)
    window = MainWindow(port)
    try:
        window.show()
        assert window.isVisible()
        assert window.status.text() == "미확인"
        window.button.click()
        assert not window.button.isEnabled()
        # [8-1: 중복 확인 방지]
        # 진행 중 객체를 보관하고 check를 다시 호출한 뒤 is로 같은 객체인지 확인한다.
        # 새 요청이 생겼다면 동일성 검사가 실패한다. 단순히 버튼 색상만 검사하는 것이 아니다.
        reply = window.backend.reply
        window.check()
        assert window.backend.reply is reply
        # lambda는 이름 없는 짧은 함수다. bool을 지금 계산해 넘기지 않고 나중에 반복 평가하도록 준다.
        # 테스트는 응답 처리 완료 후의 상태를 확인한다. 임의의 고정 지연에만 의존하지 않는다.
        wait_for(app, lambda: window.button.isEnabled())
        assert window.status.text().startswith(expected)
        assert window.checked_at.text() != "마지막 확인: 없음"
    # UI 검사가 실패하더라도 창을 닫아 다음 테스트에 요청/타이머가 남지 않게 한다.
    finally:
        window.close()


# [9단계: 느린 서버와 요청 중 종료]
# 서버 응답은 0.4초 지연하고 클라이언트 timeout은 50ms로 줄인다.
# 기다리는 동안 10ms 단발 타이머가 실행되었는지 ticks로 확인한다.
# timeout 문구뿐 아니라 이벤트 루프가 다른 이벤트도 처리했는지 검사한다.
def test_timeout_and_close_during_request(app, fake_server):
    port, settings = fake_server
    settings["delay"] = 0.4
    window = MainWindow(port)
    try:
        window.show()
        window.backend.timer.setInterval(50)
        ticks = []
        # singleShot은 이 테스트에서 앱 이벤트 루프가 진행했다는 관측용 콜백을 예약한다.
        # 실시간 성능 전체를 증명하는 검사는 아니며 '요청 대기로 UI 이벤트를 완전히 막지 않음'을 확인한다.
        QTimer.singleShot(10, lambda: ticks.append(True))
        window.check()
        wait_for(app, lambda: window.button.isEnabled())
        assert ticks
        assert window.status.text().startswith("시간 초과")
        # 두 번째 요청을 시작하자마자 창을 닫는다.
        # reply=None과 timer 정지를 검사해 종료 취소 경로를 별도로 확인한다.
        window.check()
        window.close()
        assert window.backend.reply is None
        assert not window.backend.timer.isActive()
    finally:
        window.close()


# [10단계: 실제 Backend 프로세스와 통합 검증]
# tmp_path는 pytest가 제공하는 테스트별 임시 디렉터리다. 로그를 저장소에 남기지 않는다.
# 서버 없음 → 실행 → 연결 성공 → 종료 → 실패를 반복해 복구 흐름을 확인한다.
# 실제 서버를 사용하지만 이 버전은 Phase 1 서버이므로 창 감지/저장 성공을 검증하지는 않는다.
def test_real_backend_failure_connection_and_recovery(app, tmp_path):
    """실제 Phase 1 서버의 연결 복구와 Phase 2 API 미구현 안내를 함께 확인한다."""
    # 사용 가능한 포트를 찾고 with 블록 종료 시 소켓을 닫는다.
    # 가상 서버의 port=0과 달리, 실제 Backend에 넘길 번호를 미리 고르는 과정이다.
    # 소켓 해제와 Backend bind 사이에는 다른 프로세스가 포트를 사용할 가능성이 남는다.
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    window = MainWindow(port)
    process = None
    # Path의 / 연산으로 경로를 결합하고 with로 파일 핸들을 정리한다.
    # 아래 subprocess의 표준 출력과 오류를 같은 임시 로그에 연결한다.
    with (tmp_path / "backend.log").open("w") as log:
        try:
            window.show()
            window.check()
            wait_for(app, lambda: window.button.isEnabled())
            # OS connection refusal timing can exceed the application deadline on Windows.
            assert window.status.text().startswith(("연결 안 됨", "시간 초과"))
            # 복구 과정을 두 번 반복한다. _는 반복 인덱스를 사용하지 않겠다는 관례다.
            for _ in range(2):
                # 현재 테스트와 같은 Python 실행 파일(sys.executable)로 별도 Backend 프로세스를 시작한다.
                # 인자 목록으로 전달하며 shell 명령 문자열을 조합하지 않는다.
                # Popen은 시작 후 프로세스 종료를 기다리지 않으므로 준비 상태를 아래에서 따로 확인한다.
                process = subprocess.Popen(
                    [sys.executable, "-m", "backend", "--port", str(port)], stdout=log, stderr=log)
                # 환경 프록시를 사용하지 않는 짧은 HTTP 확인용 클라이언트다.
                # 이 httpx 호출은 테스트의 준비 상태 점검용이며 제품 UI의 Qt 비동기 경로를 대체하지 않는다.
                with httpx.Client(trust_env=False, timeout=0.2) as client:
                    # poll() is None이면 자식 프로세스가 아직 실행 중이다.
                    # 프로세스 생존과 HTTP 준비 완료는 다르므로 /health가 200인지도 확인한다.
                    # 전송 오류는 아직 준비 중인 것으로 보고 wait_for가 제한 시간 안에 다시 확인한다.
                    def ready():
                        assert process.poll() is None
                        try:
                            return client.get(f"http://127.0.0.1:{port}/health").status_code == 200
                        except httpx.TransportError:
                            return False
                    wait_for(app, ready, timeout=10)
                window.button.click()
                wait_for(app, lambda: window.button.isEnabled())
                assert window.status.text().startswith("연결됨")
                # 연결은 성공해도 Phase 1 서버에는 현재 창/최근 기록 API가 없다.
                # 따라서 '기능 준비 중'과 비어 있는 화면이 이 테스트의 올바른 기대값이다.
                # Client가 가상/과거 값을 실제 감지 결과로 표시하지 않는지도 확인한다.
                wait_for(app, lambda: window.collection_status.text().startswith("기능 준비 중"))
                assert window.application.text() == "—"
                window.tabs.setCurrentWidget(window.recent)
                wait_for(app, lambda: window.recent.status.text().startswith("기능 준비 중"))
                assert window.recent.table.rowCount() == 0
                # 서버를 종료하고 wait로 종료 완료를 기다린 다음 클라이언트 재확인이 실패하는지 본다.
                # stop 요청만 보내고 즉시 검사하면 아직 살아 있는 서버와 경합할 수 있다.
                process.terminate()
                process.wait(timeout=10)
                window.button.click()
                wait_for(app, lambda: window.button.isEnabled())
                assert window.status.text().startswith(("연결 안 됨", "시간 초과"))
        finally:
            window.close()
            # [10-1: 실패 시에도 프로세스 회수]
            # 중간 assertion이 실패하면 서버가 남을 수 있으므로 최종 정리에서 생존 여부를 검사한다.
            # 살아 있으면 kill 후 wait로 종료를 회수한다. 창 닫기와 임시 로그 핸들 정리도 별도로 수행한다.
            if process is not None and process.poll() is None:
                process.kill()
                process.wait(timeout=5)
