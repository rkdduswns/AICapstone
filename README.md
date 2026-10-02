"""Windows의 현재 활성 창 정보를 수집하는 모듈."""

import ctypes
from ctypes import wintypes

# 프로세스 정보 조회에 필요한 Windows API 접근 권한
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

# Windows API 함수가 사용할 DLL을 불러온다.
user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

# Windows API가 핸들과 문자열을 올바른 형식으로 주고받도록
# 각 함수의 인자 타입과 반환 타입을 명시한다.
user32.GetForegroundWindow.argtypes = []
user32.GetForegroundWindow.restype = wintypes.HWND

user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextLengthW.restype = ctypes.c_int

user32.GetWindowTextW.argtypes = [
    wintypes.HWND,
    wintypes.LPWSTR,
    ctypes.c_int,
]
user32.GetWindowTextW.restype = ctypes.c_int

user32.GetWindowThreadProcessId.argtypes = [
    wintypes.HWND,
    ctypes.POINTER(wintypes.DWORD),
]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD

kernel32.OpenProcess.argtypes = [
    wintypes.DWORD,
    wintypes.BOOL,
    wintypes.DWORD,
]
kernel32.OpenProcess.restype = wintypes.HANDLE

kernel32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.LPWSTR,
    ctypes.POINTER(wintypes.DWORD),
]
kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL

kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL


def get_active_window_handle() -> int | None:
    """현재 활성 창의 핸들을 반환한다.

    활성 창이 없거나 핸들을 가져오지 못하면 None을 반환한다.
    """
    # GetForegroundWindow는 현재 사용자가 보고 있는 최상위 창의 핸들을 반환한다.
    handle = user32.GetForegroundWindow()

    if not handle:
        return None

    return int(handle)


def get_window_title(handle: int) -> str:
    """창 핸들을 이용해 창 제목을 가져온다.

    제목을 가져올 수 없는 경우 빈 문자열을 반환한다.
    """
    # 먼저 제목의 길이를 확인해 필요한 버퍼 크기를 계산한다.
    title_length = user32.GetWindowTextLengthW(handle)

    if title_length <= 0:
        return ""

    # Windows API가 기록할 수 있도록 제목 길이보다 1 크게 버퍼를 만든다.
    title_buffer = ctypes.create_unicode_buffer(title_length + 1)

    # 창 제목을 버퍼에 복사하고 실제 복사된 문자 수를 확인한다.
    copied_length = user32.GetWindowTextW(
        handle,
        title_buffer,
        len(title_buffer),
    )

    if copied_length <= 0:
        return ""

    return title_buffer.value

def get_process_id(handle: int) -> int | None:
    """창 핸들에 연결된 프로세스 ID를 반환한다.

    프로세스 ID를 가져오지 못하면 None을 반환한다.
    """
    # Windows API가 프로세스 ID를 기록할 변수
    process_id = wintypes.DWORD()

    # 창을 소유한 스레드 ID와 프로세스 ID를 가져온다.
    # 이 함수의 반환값은 스레드 ID이므로 process_id 변수를 별도로 확인한다.
    user32.GetWindowThreadProcessId(
        handle,
        ctypes.byref(process_id),
    )

    if process_id.value == 0:
        return None

    return int(process_id.value)

def get_process_name(process_id: int) -> str | None:
    """프로세스 ID에 해당하는 실행 파일 이름을 반환한다.

    프로세스 정보를 읽을 수 없거나 이름을 가져오지 못하면 None을 반환한다.
    """
    # 지정한 프로세스의 정보를 조회할 수 있도록 핸들을 연다.
    process_handle = kernel32.OpenProcess(
        PROCESS_QUERY_LIMITED_INFORMATION,
        False,
        process_id,
    )

    if not process_handle:
        return None

    try:
        # 실행 파일 경로를 저장할 유니코드 버퍼를 준비한다.
        path_buffer = ctypes.create_unicode_buffer(1024)
        path_length = wintypes.DWORD(len(path_buffer))

        # 프로세스의 실행 파일 전체 경로를 가져온다.
        success = kernel32.QueryFullProcessImageNameW(
            process_handle,
            0,
            path_buffer,
            ctypes.byref(path_length),
        )

        if not success:
            return None

        # 전체 경로에서 실행 파일 이름만 분리한다.
        return path_buffer.value.rsplit("\\", 1)[-1]

    finally:
        # 프로세스 핸들은 사용 후 반드시 닫아 리소스 누수를 방지한다.
        kernel32.CloseHandle(process_handle)

        # 실행 파일 이름을 사용자에게 표시할 앱 이름으로 변환한다.
APP_NAME_MAP = {
    "code.exe": "Visual Studio Code",
    "chrome.exe": "Google Chrome",
    "msedge.exe": "Microsoft Edge",
    "firefox.exe": "Mozilla Firefox",
    "explorer.exe": "파일 탐색기",
    "winword.exe": "Microsoft Word",
    "excel.exe": "Microsoft Excel",
    "powerpnt.exe": "Microsoft PowerPoint",
}


def normalize_app_name(process_name: str) -> str:
    """실행 파일 이름을 사용자에게 표시할 앱 이름으로 변환한다.

    등록되지 않은 프로그램은 실행 파일 이름을 그대로 반환한다.
    """
    # 대소문자 차이와 관계없이 앱 이름을 찾을 수 있도록 소문자로 변환한다.
    normalized_name = APP_NAME_MAP.get(process_name.lower())

    if normalized_name:
        return normalized_name

    return process_name
