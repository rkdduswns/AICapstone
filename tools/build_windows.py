"""Windows에서 Client·Backend를 각각 단일 EXE로 묶고 배포 ZIP을 만든다."""

import hashlib
import json
import shutil
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "dist" / "ContextTrace-Windows-x64"


def build_program(component: str) -> None:
    """런타임과 필요한 모듈만 포함하고 동적 Uvicorn import·버전 메타데이터를 명시한다."""
    name = f"ContextTrace-{component.title()}"
    command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile",
               "--noupx", "--name", name, "--paths", str(ROOT / "src"),
               "--distpath", str(OUTPUT), "--workpath", str(ROOT / "build" / component),
               "--specpath", str(ROOT / "build"), "--copy-metadata", "contexttrace"]
    if component == "client":
        command += ["--windowed", "--exclude-module", "backend"]
    else:
        command += ["--console", "--collect-submodules", "uvicorn", "--collect-data", "docx",
                    "--exclude-module", "client", "--exclude-module", "PySide6",
                    "--exclude-module", "shiboken6"]
    command.append(str(ROOT / "src" / component / "__main__.py"))
    subprocess.run(command, cwd=ROOT, check=True)


def assemble_bundle() -> Path:
    """검증 가능한 빌드 식별·해시와 수동 브라우저 확장·실행 안내를 함께 배포한다."""
    extension = OUTPUT / "browser-extension"
    if extension.exists():
        shutil.rmtree(extension)
    shutil.copytree(ROOT / "src/browser/extension", extension)
    shutil.copyfile(ROOT / "docs/dev/windows-exe.md", OUTPUT / "README.md")
    shutil.copyfile(ROOT / "docs/dev/history-source-linking.md", OUTPUT / "HISTORY-LINKING.md")
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    packages = {name: version(name) for name in ("contexttrace", "pyinstaller", "PySide6",
                                                "fastapi", "uvicorn", "pypdf", "python-docx")}
    (OUTPUT / "BUILD.json").write_text(
        json.dumps({"commit": sha, "python": sys.version, "packages": packages}, indent=2),
        encoding="utf-8")
    hashes = []
    for name in ("Client", "Backend"):
        file = OUTPUT / f"ContextTrace-{name}.exe"
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
    if sys.platform != "win32" or sys.maxsize <= 2**32:
        raise SystemExit("Windows x64 Python에서 실행해 주세요.")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for component in ("backend", "client"):
        build_program(component)
    print(assemble_bundle())


if __name__ == "__main__":
    main()
