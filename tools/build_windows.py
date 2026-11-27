"""Windows에서 Client·Backend를 각각 단일 EXE로 묶고 배포 ZIP을 만든다."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "dist" / "강써치-Windows-x64"


def build_program(component: str) -> None:
    """런타임과 필요한 모듈만 포함하고 동적 Uvicorn import·버전 메타데이터를 명시한다."""
    name = f"강써치-{component.title()}"
    command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile",
               "--noupx", "--name", name, "--paths", str(ROOT / "src"),
               "--distpath", str(OUTPUT), "--workpath", str(ROOT / "build" / component),
               "--specpath", str(ROOT / "build"), "--copy-metadata", "gangsearch"]
    if component == "client":
        command += ["--windowed", "--exclude-module", "backend", "--exclude-module", "onnxruntime",
                    "--exclude-module", "tokenizers"]
    else:
        command += ["--console", "--collect-submodules", "uvicorn", "--collect-data", "docx", "--collect-binaries", "onnxruntime",
                    "--exclude-module", "sentence_transformers", "--exclude-module", "torch",
                    "--exclude-module", "client", "--exclude-module", "PySide6",
                    "--exclude-module", "shiboken6"]
    command.append(str(ROOT / "src" / component / "__main__.py"))
    # 다른 개발 도구의 동명 DLL이 PATH에서 섞이지 않게 Python·Windows 경로만 사용한다.
    # Qt의 icuuc.dll은 Windows 제공 API를 사용하며 Poppler 등의 ICU와 호환되지 않는다.
    windows = Path(os.environ["SystemRoot"])
    environment = dict(os.environ)
    environment["PATH"] = os.pathsep.join(map(str, [
        Path(sys.executable).parent, Path(sys.base_prefix), windows / "System32", windows,
    ]))
    environment["PYTHONIOENCODING"] = "utf-8"
    subprocess.run(command, cwd=ROOT, env=environment, check=True)


def bundle_e5() -> None:
    """고정 리비전의 공식 파일을 받고 Git LFS 포인터의 SHA-256과 대조한다."""
    import re
    import urllib.request

    base = "https://huggingface.co/intfloat/multilingual-e5-small"
    revision = "ccc66d3bcd826f577e26b9a4072cc5fe3a7ad6a3"
    target = OUTPUT / "models" / "multilingual-e5-small"
    target.mkdir(parents=True, exist_ok=True)
    for name in ("model.onnx", "tokenizer.json"):
        relative = f"{revision}/onnx/{name}"
        with urllib.request.urlopen(f"{base}/raw/{relative}", timeout=60) as response:
            pointer = response.read(1024).decode("ascii")
        expected = re.search(r"^oid sha256:([0-9a-f]{64})$", pointer, re.MULTILINE)
        if not expected:
            raise ValueError(f"Missing E5 LFS digest: {name}")
        path = target / name
        subprocess.run(["curl.exe", "--fail", "--location", "--retry", "3", "--output", str(path),
                        f"{base}/resolve/{relative}?download=true"], check=True)
        with path.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != expected.group(1):
                raise ValueError(f"E5 checksum mismatch: {name}")
    # 배포 파일의 출처와 모델 라이선스를 함께 제공한다.
    shutil.copyfile(ROOT / "docs/dev/e5-notice.txt", target / "NOTICE.txt")


def assemble_bundle() -> Path:
    """검증 가능한 빌드 식별·해시와 수동 브라우저 확장·실행 안내를 함께 배포한다."""
    extension = OUTPUT / "browser-extension"
    if extension.exists():
        # 기존 산출물을 지우기 전에 실제 경로가 이번 배포 폴더 안인지 확인한다.
        if extension.resolve().parent != OUTPUT.resolve() or not OUTPUT.resolve().is_relative_to(
            (ROOT / "dist").resolve()
        ):
            raise ValueError("배포 폴더 밖의 확장 경로는 교체할 수 없습니다.")
        shutil.rmtree(extension)
    shutil.copytree(ROOT / "src/browser/extension", extension)
    shutil.copyfile(ROOT / "docs/dev/windows-exe.md", OUTPUT / "README.md")
    shutil.copyfile(ROOT / "docs/dev/history-source-linking.md", OUTPUT / "HISTORY-LINKING.md")
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    packages = {name: version(name) for name in ("gangsearch", "pyinstaller", "PySide6",
                                                "fastapi", "uvicorn", "pypdf", "python-docx")}
    (OUTPUT / "BUILD.json").write_text(
        json.dumps({"commit": sha, "python": sys.version, "packages": packages}, indent=2),
        encoding="utf-8")
    hashes = []
    for name in ("Client", "Backend"):
        file = OUTPUT / f"강써치-{name}.exe"
        with file.open("rb") as source:
            hashes.append(f"{hashlib.file_digest(source, 'sha256').hexdigest()}  {file.name}")
    (OUTPUT / "SHA256SUMS.txt").write_text("\n".join(hashes) + "\n", encoding="utf-8")
    archive = OUTPUT.with_suffix(".zip")
    with ZipFile(archive, "w", ZIP_DEFLATED) as bundle:
        for file in sorted(OUTPUT.rglob("*")):
            if file.is_file():
                bundle.write(file, file.relative_to(OUTPUT.parent))
    return archive


def main() -> None:
    """Windows x64에서만 빌드하여 Linux 실행 파일을 EXE로 오인해 배포하지 않는다."""
    # 영문 Windows의 cp1252 콘솔에서도 한글 산출물 경로를 출력한다.
    sys.stdout.reconfigure(encoding="utf-8")
    if sys.platform != "win32" or sys.maxsize <= 2**32:
        raise SystemExit("Windows x64 Python에서 실행해 주세요.")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for component in ("backend", "client"):
        build_program(component)
    bundle_e5()
    print(assemble_bundle())


if __name__ == "__main__":
    main()
