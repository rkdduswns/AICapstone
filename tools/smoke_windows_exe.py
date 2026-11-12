"""소스 경로 없이 실제 Windows EXE의 HTTP·문서 추출·Qt 연결을 검증한다."""

import io
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from docx import Document

ROOT = Path(__file__).resolve().parents[1]


def pdf_bytes() -> bytes:
    """폰트·본문·xref를 포함한 개인정보 없는 PDF로 번들 안의 pypdf 실행을 확인한다."""
    stream = b"BT /F1 12 Tf 72 720 Td (ContextTrace PDF smoke) Tj ET"
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


def main() -> None:
    """빌드 산출물 사본을 한글/공백 경로에서 실행하고 실제 결과만 JSON에 기록한다."""
    if sys.platform != "win32":
        raise SystemExit("Windows EXE 검증은 Windows에서 실행해 주세요.")
    output = ROOT / "dist/ContextTrace-Windows-x64"
    environment = {key: value for key, value in os.environ.items()
                   if key not in {"PYTHONPATH", "PYTHONHOME", "QT_PLUGIN_PATH",
                                  "QT_QPA_PLATFORM_PLUGIN_PATH", "QT_QPA_PLATFORM",
                                  "CONTEXTTRACE_BROWSER_TOKEN"}}
    checks = {"source_imports_disabled": True, "unicode_path": True}
    with tempfile.TemporaryDirectory(prefix="ContextTrace 한글 ") as directory:
        work = Path(directory)
        for name in ("Client", "Backend"):
            exe = output / f"ContextTrace-{name}.exe"
            assert exe.read_bytes()[:2] == b"MZ", "Windows PE 실행 파일이 아닙니다."
            shutil.copyfile(exe, work / exe.name)
        backend = work / "ContextTrace-Backend.exe"
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

        def request(path, data=None, headers=None, method=None):
            """환경 프록시와 소스 ASGI 앱을 거치지 않고 실행 파일의 loopback 서버에 요청한다."""
            req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data,
                                         headers=headers or {}, method=method)
            with opener.open(req, timeout=3) as response:
                return json.load(response)

        def upload(name, content):
            """실제 multipart 바이트를 전송해 lxml·docx·pypdf·저장 모듈 누락을 찾는다."""
            boundary = "ContextTraceSmokeBoundary"
            data = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
                    f'filename="{name}"\r\nContent-Type: application/octet-stream\r\n\r\n').encode()
            return request("/documents", data + content + f"\r\n--{boundary}--\r\n".encode(),
                           {"Content-Type": f"multipart/form-data; boundary={boundary}"})

        with (work / "backend.log").open("w", encoding="utf-8") as log:
            process = subprocess.Popen([str(backend), "--port", str(port), "--db-path",
                                        str(work / "검증.db")], cwd=work, env=environment,
                                       stdout=log, stderr=log,
                                       creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
            try:
                deadline = time.monotonic() + 60
                while True:
                    assert process.poll() is None, "Backend EXE가 준비 전에 종료됐습니다."
                    try:
                        health = request("/health")
                        break
                    except (OSError, urllib.error.URLError):
                        assert time.monotonic() < deadline, "Backend EXE 준비 시간 초과"
                        time.sleep(0.1)
                assert health["data"]["service"] == "contexttrace-backend"
                assert health["data"]["version"]
                checks["health_metadata"] = True
                assert request("/activity/current")["ok"] is True
                assert request("/records/recent?limit=20")["ok"] is True
                checks["activity_and_sqlite"] = True
                docx = io.BytesIO()
                document = Document()
                document.add_paragraph("ContextTrace DOCX smoke")
                document.save(docx)
                assert "DOCX smoke" in upload("sample.docx", docx.getvalue())["data"]["extracted_text"]
                assert "PDF smoke" in upload("sample.pdf", pdf_bytes())["data"]["extracted_text"]
                assert len(request("/documents")["data"]["documents"]) == 2
                checks["docx_pdf_and_persistence"] = True
                request("/privacy/paused", b'{"paused":true}',
                        {"Content-Type": "application/json", "X-ContextTrace-Client": "desktop"},
                        "PUT")
                try:
                    upload("blocked.docx", docx.getvalue())
                except urllib.error.HTTPError as error:
                    assert error.code == 403
                else:
                    raise AssertionError("일시정지 중 업로드가 허용됐습니다.")
                checks["privacy_pause"] = True
                result_path = work / "client-result.json"
                client = subprocess.Popen([str(work / "ContextTrace-Client.exe"), "--port", str(port),
                                           "--smoke-test-result", str(result_path)], cwd=work,
                                          env=environment,
                                          creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
                try:
                    assert client.wait(timeout=60) == 0, "Client EXE 연결 진단 실패"
                finally:
                    stop(client)
                result = json.loads(result_path.read_text(encoding="utf-8"))
                assert result == {"ok": True, "frozen": True, "platform": "windows"}, result
                checks["native_qt_frozen_client_connection"] = True
            finally:
                stop(process)
                # 실패 로그도 CI 콘솔에 남기되 가상 데이터만 사용한다.
                print((work / "backend.log").read_text(encoding="utf-8", errors="replace"))
        assert (work / "검증.db").exists()
    (ROOT / "build/package-smoke.json").write_text(json.dumps(checks, indent=2), encoding="utf-8")
    print(json.dumps(checks))


if __name__ == "__main__":
    main()
