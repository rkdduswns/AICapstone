"""Windows 배포 폴더·ZIP·빌드 식별이 같은 실행 코드를 가리키는지 읽기 전용으로 검증한다."""

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath
from zipfile import BadZipFile, ZipFile

ROOT = Path(__file__).resolve().parents[1]
EXE_NAMES = frozenset({"강써치.exe"})
RUNTIME_PATHS = ("src", "pyproject.toml", "tools/build_windows.py",
                 "tools/install_browser_native_host.ps1")
REQUIRED_FILES = EXE_NAMES | {
    "BUILD.json", "SHA256SUMS.txt", "README.md", "HISTORY-LINKING.md",
    "browser-extension/manifest.json",
    "install_browser_native_host.ps1", "NATIVE-MESSAGING.md",
}


def _git(repository: Path, *arguments: str) -> str:
    """사용자 문자열을 shell에 넣지 않고 로컬 저장소만 조회한다. 원격을 가져오지 않는다."""
    result = subprocess.run(["git", "--no-optional-locks", *arguments], cwd=repository, capture_output=True,
                            text=True, encoding="utf-8", errors="replace", check=False)
    if result.returncode != 0:
        raise ValueError("빌드 커밋을 로컬 저장소에서 확인할 수 없거나 실행 코드가 다릅니다.")
    return result.stdout.strip()


def _json_object(pairs: list[tuple[str, object]]) -> dict:
    """중복 키가 서로 다른 빌드 식별을 숨기는 JSON은 받지 않는다."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("BUILD.json에 중복된 필드가 있습니다.")
        result[key] = value
    return result


def _invalid_constant(_value: str) -> None:
    """표준 JSON에 없는 NaN·Infinity도 손상된 빌드 식별로 처리한다."""
    raise ValueError("BUILD.json이 표준 JSON 형식이 아닙니다.")


def _digest(source) -> str:
    """큰 EXE·ZIP 항목을 메모리에 모두 올리지 않고 스트리밍으로 해시한다."""
    return hashlib.file_digest(source, "sha256").hexdigest()


def _verify_bundle(output: Path, repository: Path) -> dict:
    """로컬 빌드 식별·원본 파일 해시·압축 파일의 정확한 구성을 순서대로 확인한다."""
    output = output.resolve(strict=True)
    files = {}
    for file in output.rglob("*"):
        if file.is_file():
            if not file.resolve().is_relative_to(output):
                raise ValueError("배포 폴더 밖을 가리키는 파일은 검증할 수 없습니다.")
            if file.name.lower() == "com.contexttrace.auth.json":
                raise ValueError("PC별 Native Messaging 설정은 배포본에 포함할 수 없습니다.")
            files[file.relative_to(output).as_posix()] = file
    if not REQUIRED_FILES <= files.keys():
        raise ValueError("배포본의 실행 파일·빌드 식별·문서·확장 파일이 누락됐습니다.")
    # ZIP과 폴더가 함께 잘못 구성돼도 구형 두 EXE나 하위 폴더의 별도 EXE를 허용하지 않는다.
    executables = {name for name in files if PurePosixPath(name).suffix.casefold() == ".exe"}
    if executables != EXE_NAMES:
        raise ValueError("배포본에는 강써치.exe 실행 파일 하나만 있어야 합니다.")
    build = json.loads(files["BUILD.json"].read_text(encoding="utf-8"),
                       object_pairs_hook=_json_object, parse_constant=_invalid_constant)
    commit = build.get("commit") if isinstance(build, dict) else None
    if not isinstance(commit, str) or re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise ValueError("BUILD.json의 commit은 전체 40자리 Git 커밋이어야 합니다.")
    _git(repository, "cat-file", "-e", f"{commit}^{{commit}}")
    head = _git(repository, "rev-parse", "HEAD")
    if _git(repository, "status", "--porcelain", "--untracked-files=all", "--", *RUNTIME_PATHS):
        raise ValueError("커밋되지 않은 실행 코드가 있어 배포본과 대조할 수 없습니다.")
    # 문서/검증 도구만 바뀐 병합 커밋은 허용하지만 실행 코드와 빌드 방식은 같아야 한다.
    _git(repository, "diff", "--quiet", commit, "HEAD", "--", *RUNTIME_PATHS)

    expected_hashes = {}
    for line in files["SHA256SUMS.txt"].read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if match is None or match[2] not in EXE_NAMES or match[2] in expected_hashes:
            raise ValueError("SHA256SUMS.txt의 실행 파일 이름·해시·중복 항목을 확인해 주세요.")
        expected_hashes[match[2]] = match[1]
    if expected_hashes.keys() != EXE_NAMES:
        raise ValueError("SHA256SUMS.txt에는 강써치.exe 해시 하나가 있어야 합니다.")
    digests = {}
    for name, file in files.items():
        with file.open("rb") as source:
            if name in EXE_NAMES and source.read(2) != b"MZ":
                raise ValueError("Windows PE 실행 파일 헤더가 올바르지 않습니다.")
            source.seek(0)
            digests[name] = _digest(source)
    if any(digests[name] != expected_hashes[name] for name in EXE_NAMES):
        raise ValueError("실행 파일과 SHA256SUMS.txt 해시가 일치하지 않습니다.")

    archive_names = {f"{output.name}/{name}": name for name in files}
    with ZipFile(output.with_suffix(".zip")) as archive:
        members = archive.infolist()
        names = [item.filename for item in members]
        if len(names) != len(set(names)):
            raise ValueError("ZIP에 중복된 파일 항목이 있습니다.")
        for name in names:
            path = PurePosixPath(name)
            if ("\\" in name or path.is_absolute() or ".." in path.parts
                    or path.as_posix() != name):
                raise ValueError("ZIP에 올바르지 않은 파일 경로가 있습니다.")
        if set(names) != archive_names.keys():
            raise ValueError("ZIP의 누락·추가 파일 또는 배포 폴더 이름이 일치하지 않습니다.")
        for member in members:
            with archive.open(member) as source:
                if _digest(source) != digests[archive_names[member.filename]]:
                    raise ValueError("ZIP 내용과 현재 배포 폴더의 파일이 일치하지 않습니다.")
    return {"build_commit": commit, "head_commit": head, "code_matches_head": True,
            "exe_hashes_verified": True, "archive_verified": True, "files_verified": len(files)}


def verify_bundle(output: Path, repository: Path) -> dict:
    """검증 결과를 JSON 가능한 값으로 반환하며 실패는 실행 전에 ValueError로 알린다.

    이 검증은 파일 간 일치와 소스 기준을 확인한다. 코드 서명이나 배포자 인증은 아니다.
    파일·설정·Git을 수정하지 않고 외부 앱·네트워크도 사용하지 않는다.
    """
    try:
        return _verify_bundle(Path(output), Path(repository))
    except (OSError, UnicodeError, BadZipFile, RuntimeError) as error:
        raise ValueError("배포본 파일·ZIP 또는 로컬 Git을 읽어 검증할 수 없습니다.") from error


def main() -> int:
    """명시한 배포본을 조회하고 성공/실패를 간단한 JSON과 종료 코드로 제공한다."""
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="강써치 Windows 배포본 일치 검증")
    parser.add_argument("--bundle", type=Path, default=ROOT / "dist/강써치-Windows-x64")
    parser.add_argument("--repo", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        result = {"ok": True, **verify_bundle(args.bundle, args.repo)}
    except ValueError as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
