"""단일 EXE의 실행 역할과 Client로 전달하는 인자를 검증한다."""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from desktop.__main__ import main


@pytest.mark.parametrize("arguments", [
    ["--port", "0"], ["--port", "65536"], ["--owner-pid", "7"],
    ["--stop-event", "unused"], ["--backend-worker"],
    ["--backend-worker", "--owner-pid", "-1", "--stop-event", "unused"],
    ["--backend-worker", "--owner-pid", "4294967296", "--stop-event", "unused"],
    ["--smoke-test-reading"],
])
def test_invalid_role_never_starts_application(arguments, monkeypatch):
    """잘못된 내부 역할·포트·진단 옵션은 서버나 사용자 창을 만들기 전에 거부한다."""
    monkeypatch.setitem(sys.modules, "desktop.launcher", SimpleNamespace(
        BackendSupervisor=lambda *_args: pytest.fail("서버를 시작하면 안 됩니다."),
    ))
    with pytest.raises(SystemExit) as error:
        main(arguments)
    assert error.value.code == 2


def test_worker_dispatch_does_not_call_client(monkeypatch, tmp_path):
    """Backend 역할은 GUI 실행과 별개로 소유 제어 인자를 전달한다."""
    calls = []
    monkeypatch.setitem(sys.modules, "desktop.backend_worker", SimpleNamespace(
        run_worker=lambda *args: calls.append(args) or 17,
    ))
    monkeypatch.setitem(sys.modules, "client.__main__", SimpleNamespace(
        main=lambda **_kwargs: pytest.fail("작업 프로세스에서 Client를 실행하면 안 됩니다."),
    ))
    database = tmp_path / "가상.db"
    assert main(["--backend-worker", "--port", "9123", "--db-path", str(database),
                 "--owner-pid", "7", "--stop-event", "test-event"]) == 17
    assert calls == [(9123, database, 7, "test-event")]


def test_parent_dispatch_preserves_client_arguments_and_owns_supervisor(monkeypatch, tmp_path):
    """Client에는 기존 포트·진단 옵션만 보내고 DB 경로는 실행 조합 계층에서 관리한다."""
    calls, clients = [], []
    window = SimpleNamespace()

    class Supervisor:
        """실제 프로세스 없이 소유 객체와 시작 횟수를 확인한다."""

        def __init__(self, owner, port, db_path):
            self.owner = owner
            calls.append((port, db_path))

        def start(self):
            calls.append("start")

    def client_main(*, startup_hook):
        """기존 Client 인자와 화면이 표시된 뒤 시작하는 hook을 관찰한다."""
        clients.append(list(sys.argv[1:]))
        startup_hook(window)
        return 9

    original = sys.argv
    monkeypatch.setitem(sys.modules, "desktop.launcher", SimpleNamespace(BackendSupervisor=Supervisor))
    monkeypatch.setitem(sys.modules, "client.__main__", SimpleNamespace(main=client_main))
    database, result = tmp_path / "가상.db", tmp_path / "result.json"
    assert main(["--port", "9123", "--db-path", str(database),
                 "--smoke-test-result", str(result), "--smoke-test-reading"]) == 9
    assert sys.argv is original
    assert clients == [["--port", "9123", "--smoke-test-result", str(result), "--smoke-test-reading"]]
    assert calls == [(9123, Path(database).resolve()), "start"]
    assert window._desktop_backend.owner is window
