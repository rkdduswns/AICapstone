"""소스 경로 없이 실제 Windows EXE의 HTTP·문서 추출·Qt 연결을 검증한다."""

import io
import json
import os
import shutil
import signal
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from docx import Document
from verify_windows_bundle import verify_bundle

ROOT = Path(__file__).resolve().parents[1]


def pdf_bytes() -> bytes:
    """폰트·본문·xref를 포함한 개인정보 없는 PDF로 번들 안의 pypdf 실행을 확인한다."""
    stream = b"BT /F1 12 Tf 72 720 Td (GangSearch PDF smoke) Tj ET"
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>",
               b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
               b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
               b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
               f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream",
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    result = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, obj in enumerate(objects, 1):
        offsets.append(len(result))
        result.extend(f"{number} 0 obj\n".encode() + obj + b"\nendobj\n")
    start = len(result)
    result.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        result.extend(f"{offset:010d} 00000 n \n".encode())
    result.extend(f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\n"
                  f"startxref\n{start}\n%%EOF\n".encode())
    return bytes(result)


def stop(process: subprocess.Popen) -> None:
    """onefile 부모·자식 프로세스를 남기지 않고 Backend의 정상 종료를 먼저 시도한다."""
    if process.poll() is not None:
        return
    try:
        process.send_signal(signal.CTRL_BREAK_EVENT)
        process.wait(timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        # GUI 앱은 콘솔 제어 신호를 받지 못할 수 있어 프로세스 트리 전체를 정리한다.
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], check=False,
                       capture_output=True)
        process.wait(timeout=10)


def _free_port() -> int:
    """검증에만 쓸 빈 loopback 포트를 얻고 실제 소유권은 worker의 bind로 확인한다."""
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        return reservation.getsockname()[1]


def _wait_json(process: subprocess.Popen, path: Path, timeout: float = 45) -> dict:
    """새 진단 결과가 완성될 때까지 기다리며 종료된 프로그램의 과거 결과를 재사용하지 않는다."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                pass
        assert process.poll() is None, "진단 결과를 쓰기 전에 프로그램이 종료됐습니다."
        time.sleep(0.02)
    raise AssertionError("진단 결과 대기 시간 초과")


def _wait_closed(port: int) -> None:
    """자신이 시작한 프로그램 종료 뒤 서버 포트가 실제로 해제되는지 확인한다."""
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        with socket.socket() as connection:
            connection.settimeout(0.1)
            if connection.connect_ex(("127.0.0.1", port)) != 0:
                return
        time.sleep(0.05)
    raise AssertionError("종료한 앱의 Backend 포트가 남아 있습니다.")


def main() -> None:
    """단일 EXE의 서버 수명·자료 보존·Qt 읽기·기존 서버 경계를 격리된 환경에서 검증한다."""
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread

    from desktop.windows_control import WindowsStopSignal

    sys.stdout.reconfigure(encoding="utf-8")
    if sys.platform != "win32":
        raise SystemExit("Windows EXE 검증은 Windows에서 실행해 주세요.")
    report = ROOT / "build/package-smoke.json"
    report.unlink(missing_ok=True)
    output = ROOT / "dist/강써치-Windows-x64"
    bundle = verify_bundle(output, ROOT)
    environment = {key: value for key, value in os.environ.items()
                   if key not in {"PYTHONPATH", "PYTHONHOME", "QT_PLUGIN_PATH",
                                  "QT_QPA_PLATFORM_PLUGIN_PATH", "QT_QPA_PLATFORM",
                                  "CONTEXTTRACE_BROWSER_TOKEN", "GANGSEARCH_BROWSER_TOKEN"}}
    checks = {"source_imports_disabled": True, "unicode_path": True,
              "bundle_code_identity": bundle["code_matches_head"],
              "bundle_exe_hashes": bundle["exe_hashes_verified"],
              "bundle_zip_contents": bundle["archive_verified"]}
    with tempfile.TemporaryDirectory(prefix="강써치 단일 실행 ") as directory:
        work = Path(directory)
        executable = work / "강써치.exe"
        shutil.copyfile(output / executable.name, executable)
        with executable.open("rb") as source:
            assert source.read(2) == b"MZ"
            source.seek(0x3C)
            pe_offset = int.from_bytes(source.read(4), "little")
            source.seek(pe_offset + 24 + 68)
            assert int.from_bytes(source.read(2), "little") == 2, "창 전용 실행 파일이 아닙니다."
        checks["single_windowed_executable"] = True
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        database = work / "가상 검증.db"
        port = _free_port()
        processes = []
        workers = []

        def request(path, data=None, headers=None, method=None, *, request_port=port):
            """환경 프록시 없이 이 검증의 로컬 서버만 호출한다."""
            req = urllib.request.Request(f"http://127.0.0.1:{request_port}{path}", data=data,
                                         headers=headers or {}, method=method)
            with opener.open(req, timeout=3) as response:
                return json.load(response)

        def start(arguments):
            """복사한 단일 EXE만 실행하며 소스 디렉터리나 별도 Backend 파일을 사용하지 않는다."""
            process = subprocess.Popen([str(executable), *arguments], cwd=work, env=environment,
                                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL,
                                       creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
            processes.append(process)
            return process

        def start_worker():
            """HTTP 자료 준비도 동일 EXE의 내부 역할로 수행하고 소유 종료 채널을 유지한다."""
            control = WindowsStopSignal()
            process = start(["--backend-worker", "--port", str(port), "--db-path", str(database),
                             "--owner-pid", str(os.getpid()), "--stop-event", control.name])
            workers.append((process, control))
            deadline = time.monotonic() + 30
            while True:
                assert process.poll() is None, f"worker 시작 실패: {process.returncode}"
                try:
                    if control.is_ready():
                        assert request("/health")["ok"] is True
                        return process, control
                except (OSError, urllib.error.URLError):
                    pass
                assert time.monotonic() < deadline, "worker 준비 시간 초과"
                time.sleep(0.05)

        def stop_worker(process, control):
            """강제 종료 전에 본인 worker의 정상 lifespan 종료를 요구한다."""
            control.request_stop()
            assert process.wait(timeout=10) == 0, "worker 정상 종료 실패"
            _wait_closed(port)
            control.close()

        def upload(name, content):
            """실제 PDF·DOCX 추출과 저장을 HTTP 경계에서 확인한다."""
            boundary = "GangSearchUnifiedSmoke"
            body = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
                    f'filename="{name}"\r\nContent-Type: application/octet-stream\r\n\r\n').encode()
            return request("/documents", body + content + f"\r\n--{boundary}--\r\n".encode(),
                           {"Content-Type": f"multipart/form-data; boundary={boundary}"})

        def diagnostic(name, *, db=None, reading=False, hold=0, diagnostic_port=port):
            """일반 UI 역할을 실행하며 이 경우 앱이 서버 시작과 종료를 직접 관리해야 한다."""
            result = work / f"{name}.json"
            arguments = ["--port", str(diagnostic_port), "--smoke-test-result", str(result)]
            if db is not None:
                arguments += ["--db-path", str(db)]
            if reading:
                arguments.append("--smoke-test-reading")
            if hold:
                arguments += ["--smoke-test-hold-ms", str(hold)]
            process = start(arguments)
            return process, _wait_json(process, result)

        try:
            worker, control = start_worker()
            health = request("/health")
            assert health["data"]["service"] == "contexttrace-backend" and health["data"]["version"]
            checks["health_metadata"] = True
            assert request("/activity/current")["ok"] and request("/records/recent?limit=20")["ok"]
            checks["activity_and_sqlite"] = True
            content = io.BytesIO()
            document = Document()
            document.add_paragraph("강써치 DOCX smoke")
            document.save(content)
            assert "DOCX smoke" in upload("sample.docx", content.getvalue())["data"]["extracted_text"]
            assert "PDF smoke" in upload("sample.pdf", pdf_bytes())["data"]["extracted_text"]
            checks["docx_pdf_and_persistence"] = True
            request("/privacy/paused", b'{"paused":true}',
                    {"Content-Type": "application/json", "X-ContextTrace-Client": "desktop"}, "PUT")
            try:
                upload("blocked.docx", content.getvalue())
            except urllib.error.HTTPError as error:
                assert error.code == 403
            else:
                raise AssertionError("일시정지 중 저장이 허용됐습니다.")
            checks["privacy_pause"] = True
            stop_worker(worker, control)
            checks["worker_graceful_shutdown"] = True

            # 서버를 따로 켜지 않은 상태에서 일반 앱 역할이 직접 시작·연결·종료한다.
            client, result = diagnostic("managed-reading", db=database, reading=True)
            assert client.wait(timeout=45) == 0, result
            reading_checks = result.pop("checks", None)
            assert result == {"ok": True, "frozen": True, "platform": "windows"}, result
            expected = {"health_confirmed", "activity_confirmed", "privacy_confirmed",
                        "document_list", "document_find", "document_source_none", "management_return"}
            assert isinstance(reading_checks, dict) and set(reading_checks) == expected
            assert all(value is True for value in reading_checks.values()), reading_checks
            checks.update({"native_reading_" + key: value for key, value in reading_checks.items()})
            checks["managed_auto_backend"] = True
            checks["native_qt_frozen_client_connection"] = True
            _wait_closed(port)
            checks["managed_normal_shutdown"] = True

            worker, control = start_worker()
            assert request("/privacy")["data"]["settings"]["paused"] is True
            assert len(request("/documents")["data"]["documents"]) == 2
            checks["privacy_restart_persistence"] = True
            attached, result = diagnostic("existing-server")
            assert attached.wait(timeout=45) == 0 and result["ok"] is True
            checks["external_server_reused"] = True
            assert worker.poll() is None and request("/health")["ok"]
            checks["external_server_not_stopped"] = True
            conflicting = work / "사용하면 안 되는 DB.db"
            rejected, result = diagnostic("explicit-db-conflict", db=conflicting)
            assert rejected.wait(timeout=45) == 1 and result["ok"] is False
            assert not conflicting.exists() and worker.poll() is None and request("/health")["ok"]
            checks["explicit_db_conflict_rejected"] = True
            stop_worker(worker, control)

            class WrongService(BaseHTTPRequestHandler):
                """다른 서비스의 점유 포트를 종료하거나 우회하지 않는지 확인한다."""

                def do_GET(self):
                    payload = b'{"ok":true,"data":{"service":"unrelated"},"error":null}'
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)

                def log_message(self, *_args):
                    """검증용 요청 정보도 사용자 작업 로그로 남기지 않는다."""

            wrong = ThreadingHTTPServer(("127.0.0.1", 0), WrongService)
            thread = Thread(target=wrong.serve_forever, daemon=True)
            thread.start()
            try:
                rejected, result = diagnostic("wrong-service", db=conflicting,
                                              diagnostic_port=wrong.server_port)
                assert rejected.wait(timeout=45) == 1 and result["ok"] is False
                assert not conflicting.exists()
                assert request("/health", request_port=wrong.server_port)["data"]["service"] == "unrelated"
                checks["wrong_service_rejected"] = True
            finally:
                wrong.shutdown()
                wrong.server_close()
                thread.join(timeout=3)

            first, result = diagnostic("crash-owner", db=database, hold=30_000)
            assert result["ok"] is True and first.poll() is None
            second, rejected = diagnostic("duplicate")
            assert second.wait(timeout=45) == 1 and rejected["ok"] is False
            assert first.poll() is None and request("/health")["ok"]
            checks["single_instance"] = True
            owner_pid = result["process_id"]
            assert type(owner_pid) is int and owner_pid > 0 and owner_pid != os.getpid()
            # 진단 결과를 생성한 본인 GUI만 강제 종료해 owner handle 감시를 검증한다.
            os.kill(owner_pid, signal.SIGTERM)
            first.wait(timeout=15)
            _wait_closed(port)
            checks["owner_crash_cleanup"] = True
            with sqlite3.connect(database) as connection:
                assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
            checks["crash_database_integrity"] = True
        finally:
            for process, control in workers:
                if process.poll() is None:
                    control.request_stop()
                    try:
                        process.wait(timeout=8)
                    except subprocess.TimeoutExpired:
                        stop(process)
                control.close()
            for process in processes:
                stop(process)
    report.write_text(json.dumps(checks, indent=2), encoding="utf-8")
    print(json.dumps(checks))


if __name__ == "__main__":
    main()
