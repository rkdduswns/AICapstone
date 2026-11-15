"""실행·네트워크 없이 작은 가상 배포본으로 빌드 식별과 ZIP 일치 경계를 검증한다."""

import hashlib
import importlib
import json
import subprocess
import warnings
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from tools.verify_windows_bundle import EXE_NAMES, verify_bundle


def test_failed_preflight_cannot_leave_previous_success_report(tmp_path, monkeypatch):
    """배포본 검증 실패 뒤에 과거 성공 JSON이 남거나 프로그램이 실행되지 않는다."""
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "tools"))
    smoke = importlib.import_module("tools.smoke_windows_exe")
    report = tmp_path / "build/package-smoke.json"
    report.parent.mkdir()
    report.write_text('{"previous_success":true}', encoding="utf-8")
    monkeypatch.setattr(smoke, "ROOT", tmp_path)
    monkeypatch.setattr(smoke, "sys", SimpleNamespace(
        platform="win32", stdout=SimpleNamespace(reconfigure=lambda **_kwargs: None),
    ))

    def reject(*_args):
        """실행 파일을 검사하기 전에 배포본 불일치가 확인된 상황을 재현한다."""
        raise ValueError("배포본 불일치")

    monkeypatch.setattr(smoke, "verify_bundle", reject)
    monkeypatch.setattr(smoke.subprocess, "Popen", lambda *_args, **_kwargs:
                        pytest.fail("검증 실패 후 프로그램을 실행하면 안 됩니다."))
    with pytest.raises(ValueError, match="배포본 불일치"):
        smoke.main()
    assert not report.exists()


def git(repository, *arguments):
    """임시 저장소만 수정하며 사용자 hook·자동 줄바꿈 설정에 의존하지 않는다."""
    return subprocess.run([
        "git", "-c", "user.name=BundleTest", "-c", "user.email=bundle@example.test",
        "-c", "core.autocrlf=false", "-c", f"core.hooksPath={repository / 'unused-hooks'}",
        *arguments,
    ], cwd=repository, capture_output=True, text=True, encoding="utf-8", check=True).stdout.strip()


def commit(repository):
    """테스트가 명시적으로 만든 내용만 로컬 커밋으로 기록한다."""
    git(repository, "add", ".")
    git(repository, "commit", "-qm", "synthetic bundle source")
    return git(repository, "rev-parse", "HEAD")


@pytest.fixture
def repository(tmp_path):
    """실제 프로젝트와 사용자 Git 상태를 건드리지 않는 최소 실행 코드 저장소다."""
    root = tmp_path / "repository"
    root.mkdir()
    git(root, "init", "-q")
    for name, content in (("src/client.py", "print('synthetic')\n"),
                          ("pyproject.toml", "[project]\nname='synthetic'\n"),
                          ("tools/build_windows.py", "# synthetic packager\n")):
        file = root / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(content, encoding="utf-8")
    commit(root)
    return root


def archive(bundle, alter=None):
    """배포 폴더의 파일만 압축하며 변형 함수로 손상·중복 ZIP을 재현한다."""
    members = [(f"{bundle.name}/{file.relative_to(bundle).as_posix()}", file.read_bytes())
               for file in sorted(bundle.rglob("*")) if file.is_file()]
    if alter:
        members = alter(members)
    with warnings.catch_warnings():
        # 중복 항목 자체가 거부되는지 확인하는 테스트만 의도적으로 중복 ZIP을 만든다.
        warnings.simplefilter("ignore", UserWarning)
        with ZipFile(bundle.with_suffix(".zip"), "w", ZIP_DEFLATED) as output:
            for name, content in members:
                output.writestr(name, content)


def hashes(bundle):
    """작은 가상 단일 EXE의 현재 해시를 배포 규격대로 쓴다."""
    (bundle / "SHA256SUMS.txt").write_text("".join(
        f"{hashlib.sha256((bundle / name).read_bytes()).hexdigest()}  {name}\n"
        for name in sorted(EXE_NAMES)), encoding="utf-8")


@pytest.fixture
def bundle(repository, tmp_path):
    """실제 PE 실행 대신 MZ 헤더만 가진 바이트와 필수 문서/확장을 준비한다."""
    root = tmp_path / "배포 자료" / "강써치-Windows-x64"
    root.mkdir(parents=True)
    for name in EXE_NAMES:
        (root / name).write_bytes(b"MZsynthetic-" + name.encode())
    for name in ("README.md", "HISTORY-LINKING.md", "browser-extension/manifest.json",
                 "browser-extension/capture.js"):
        file = root / name
        file.parent.mkdir(exist_ok=True)
        file.write_text("synthetic fixture", encoding="utf-8")
    (root / "BUILD.json").write_text(
        json.dumps({"commit": git(repository, "rev-parse", "HEAD")}), encoding="utf-8")
    hashes(root)
    archive(root)
    return root


def test_current_source_bundle_is_verified_without_writes(repository, bundle):
    """폴더·ZIP·저장소가 같으면 JSON 결과를 내고 어느 파일도 수정하지 않는다."""
    before = {str(file): file.read_bytes() for file in bundle.parent.rglob("*") if file.is_file()}
    result = verify_bundle(bundle, repository)
    assert result == {
        "build_commit": git(repository, "rev-parse", "HEAD"),
        "head_commit": git(repository, "rev-parse", "HEAD"), "code_matches_head": True,
        "exe_hashes_verified": True, "archive_verified": True, "files_verified": 7,
    }
    json.dumps(result)
    assert before == {str(file): file.read_bytes()
                      for file in bundle.parent.rglob("*") if file.is_file()}
    assert git(repository, "status", "--porcelain") == ""


def test_different_commit_with_same_execution_code_is_allowed(repository, bundle):
    """문서만 추가한 후속/병합 커밋은 빌드와 실행 코드가 같으면 구분해 허용한다."""
    built = json.loads((bundle / "BUILD.json").read_text(encoding="utf-8"))["commit"]
    (repository / "README.md").write_text("documentation only", encoding="utf-8")
    head = commit(repository)
    result = verify_bundle(bundle, repository)
    assert result["build_commit"] == built and result["head_commit"] == head != built


@pytest.mark.parametrize("name", ["src/backend.py", "pyproject.toml", "tools/build_windows.py"])
def test_runtime_or_packager_difference_rejects_old_bundle(repository, bundle, name):
    """Backend 포함 실행 코드·의존성·빌드 방식이 달라지면 이전 EXE를 통과시키지 않는다."""
    file = repository / name
    file.write_text("changed runtime", encoding="utf-8")
    commit(repository)
    with pytest.raises(ValueError, match="실행 코드가 다릅니다"):
        verify_bundle(bundle, repository)


@pytest.mark.parametrize("name", ["src/client.py", "src/untracked.py"])
def test_uncommitted_runtime_cannot_be_silently_verified(repository, bundle, name):
    """추적 파일 수정과 새 실행 파일 모두 커밋 기준 검증에서 제외하지 않는다."""
    (repository / name).write_text("uncommitted runtime", encoding="utf-8")
    with pytest.raises(ValueError, match="커밋되지 않은 실행 코드"):
        verify_bundle(bundle, repository)


def test_unknown_build_commit_does_not_fetch_or_accept(repository, bundle):
    """형식만 맞는 미확인 커밋을 원격 조회나 현재 커밋 대체로 보완하지 않는다."""
    (bundle / "BUILD.json").write_text(json.dumps({"commit": "a" * 40}), encoding="utf-8")
    archive(bundle)
    with pytest.raises(ValueError, match="로컬 저장소"):
        verify_bundle(bundle, repository)


@pytest.mark.parametrize("content", [
    "[]", "null", "{", '{"commit":1}', '{"commit":"short"}',
    '{"commit":"' + "a" * 41 + '"}',
    '{"commit":"' + "a" * 40 + '","commit":"' + "b" * 40 + '"}',
    '{"commit":"' + "a" * 40 + '","invalid":NaN}',
])
def test_invalid_or_ambiguous_build_metadata_is_rejected(repository, bundle, content):
    """잘못된 JSON·전체 SHA가 아닌 값·중복 필드로 빌드 식별을 우회할 수 없다."""
    (bundle / "BUILD.json").write_text(content, encoding="utf-8")
    archive(bundle)
    with pytest.raises(ValueError):
        verify_bundle(bundle, repository)


def test_changed_executable_is_rejected_before_launch(repository, bundle):
    """PE 모양을 유지해도 해시가 달라진 EXE는 실행 전에 거부한다."""
    (bundle / "강써치.exe").write_bytes(b"MZchanged executable")
    with pytest.raises(ValueError, match="해시가 일치하지"):
        verify_bundle(bundle, repository)


def test_non_pe_file_is_rejected_even_with_updated_hash_and_zip(repository, bundle):
    """잘못된 실행 파일의 해시와 ZIP까지 함께 바꿔도 Windows PE로 오인하지 않는다."""
    (bundle / "강써치.exe").write_bytes(b"not a Windows executable")
    hashes(bundle)
    archive(bundle)
    with pytest.raises(ValueError, match="PE 실행 파일 헤더"):
        verify_bundle(bundle, repository)


@pytest.mark.parametrize("kind", ["duplicate", "missing", "extra", "malformed"])
def test_hash_list_requires_exact_one_executable(repository, bundle, kind):
    """누락·중복·추가 이름과 형식 오류를 허용하지 않는다."""
    lines = (bundle / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines()
    if kind == "duplicate":
        lines.append(lines[0])
    elif kind == "missing":
        lines.pop()
    elif kind == "extra":
        lines.append("a" * 64 + "  unrelated.exe")
    else:
        lines[0] = "invalid hash"
    (bundle / "SHA256SUMS.txt").write_text("\n".join(lines), encoding="utf-8")
    with pytest.raises(ValueError, match="SHA256SUMS"):
        verify_bundle(bundle, repository)


@pytest.mark.parametrize("kind", ["missing", "extra", "duplicate", "traversal", "absolute", "backslash"])
def test_archive_requires_exact_safe_unique_members(repository, bundle, kind):
    """추가/누락·중복·상위/절대/역슬래시 경로를 압축 해제하지 않고 거부한다."""
    def alter(members):
        """정상 항목의 이름만 바꿔서 각 ZIP 경계를 재현한다."""
        if kind == "missing":
            return members[1:]
        if kind == "extra":
            return [*members, (bundle.name + "/extra.txt", b"extra")]
        if kind == "duplicate":
            return [*members, members[0]]
        names = {"traversal": bundle.name + "/../outside.txt",
                 "absolute": "/outside.txt", "backslash": bundle.name + "\\outside.txt"}
        return [*members, (names[kind], b"outside")]

    archive(bundle, alter)
    with pytest.raises(ValueError, match="ZIP"):
        verify_bundle(bundle, repository)


def test_archive_file_bytes_must_match_current_bundle(repository, bundle):
    """정확한 파일 이름만으로는 이전 문서·확장·실행 파일이 섞인 ZIP을 통과시키지 않는다."""
    archive(bundle, lambda members: [(name, b"stale content" if name.endswith("capture.js") else body)
                                     for name, body in members])
    with pytest.raises(ValueError, match="ZIP 내용"):
        verify_bundle(bundle, repository)


def test_required_docs_cannot_be_missing_from_both_folder_and_zip(repository, bundle):
    """폴더와 ZIP에서 함께 누락된 안내 문서도 정상 배포본으로 처리하지 않는다."""
    (bundle / "README.md").unlink()
    archive(bundle)
    with pytest.raises(ValueError, match="누락"):
        verify_bundle(bundle, repository)


@pytest.mark.parametrize("name", [
    "강써치-Client.exe", "강써치-Backend.exe", "nested/helper.exe", "unrelated.EXE",
])
def test_extra_executable_is_rejected_even_when_zip_matches(repository, bundle, name):
    """폴더와 ZIP에 구형·중첩 EXE가 같이 남아도 단일 실행 파일 배포로 통과하지 않는다."""
    file = bundle / name
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_bytes(b"MZextra executable")
    archive(bundle)
    with pytest.raises(ValueError, match="실행 파일 하나"):
        verify_bundle(bundle, repository)


def test_build_uses_unified_entry_and_keeps_dll_path_isolation(tmp_path, monkeypatch):
    """실제 빌드를 하지 않고 단일 GUI 진입점과 기존 DLL 경로 격리가 유지되는지 확인한다."""
    from tools import build_windows as builder

    monkeypatch.setattr(builder, "ROOT", tmp_path)
    monkeypatch.setattr(builder, "OUTPUT", tmp_path / "dist/강써치-Windows-x64")
    monkeypatch.setattr(builder, "sys", SimpleNamespace(
        executable=str(tmp_path / "python/python.exe"), base_prefix=str(tmp_path / "runtime"),
    ))
    monkeypatch.setenv("SystemRoot", str(tmp_path / "Windows"))
    monkeypatch.setenv("PATH", "unrelated-dll-location")
    calls = []
    monkeypatch.setattr(builder.subprocess, "run", lambda *args, **kwargs: calls.append((args, kwargs)))
    builder.build_program()
    assert len(calls) == 1
    command, options = calls[0][0][0], calls[0][1]
    assert command[-1] == str(tmp_path / "src/desktop/__main__.py")
    assert "--onefile" in command and "--windowed" in command and "--console" not in command
    assert command[command.index("--name") + 1] == "강써치"
    assert "--exclude-module" not in command
    assert command[command.index("--collect-submodules") + 1] == "uvicorn"
    assert command[command.index("--collect-data") + 1] == "docx"
    assert command[command.index("--copy-metadata") + 1] == "gangsearch"
    assert "unrelated-dll-location" not in options["env"]["PATH"]
    assert options["env"]["PYTHONIOENCODING"] == "utf-8" and options["check"] is True


def test_cleanup_removes_only_known_legacy_files_in_output(tmp_path, monkeypatch):
    """새 실행 파일·다른 산출물은 보존하며 정해진 구형 실행 파일 두 개만 교체한다."""
    from tools import build_windows as builder

    output = tmp_path / "dist/강써치-Windows-x64"
    output.mkdir(parents=True)
    monkeypatch.setattr(builder, "ROOT", tmp_path)
    monkeypatch.setattr(builder, "OUTPUT", output)
    for name in ("강써치.exe", "강써치-Client.exe", "강써치-Backend.exe", "unrelated.txt"):
        (output / name).write_text("synthetic", encoding="utf-8")
    builder.remove_legacy_executables()
    assert {file.name for file in output.iterdir()} == {"강써치.exe", "unrelated.txt"}


def test_cleanup_refuses_output_outside_distribution_root(tmp_path, monkeypatch):
    """계산된 폴더가 허용된 dist 밖이면 파일을 하나도 제거하지 않는다."""
    from tools import build_windows as builder

    output = tmp_path / "outside"
    output.mkdir()
    legacy = output / "강써치-Client.exe"
    legacy.write_text("preserve", encoding="utf-8")
    monkeypatch.setattr(builder, "ROOT", tmp_path)
    monkeypatch.setattr(builder, "OUTPUT", output)
    with pytest.raises(ValueError, match="배포 폴더 밖"):
        builder.remove_legacy_executables()
    assert legacy.read_text(encoding="utf-8") == "preserve"
