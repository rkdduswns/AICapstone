# 학습용 사본 — 실행/테스트에서 참조하는 구현 기준이 아닙니다.
# 주제: PySide6 이벤트와 화면 상태
# 원본 경로: src/client/window.py
# 원본 브랜치: feat/phase4-client
# 원본 commit SHA: a3a1aec2ecce25bad7c1de7547279b766929d8a1
# 복사 날짜: 2026-10-15 (Asia/Seoul)
# 원본과 다른 점: 한국어 설명 주석만 추가. 코드·문자열·기존 docstring은 보존.
# 읽는 방법: 번호가 붙은 주석을 따라가고 같은 폴더의 explanation.md를 함께 읽습니다.
# import는 실제 프로젝트 패키지를 가리킵니다. 이 사본은 독립 실행용 앱/테스트가 아닙니다.

"""Backend 연결, 현재 작업 상태와 최근 저장 기록을 표시하는 화면."""

# [1단계: UI 도구와 통신 담당 객체의 책임 구분]
# QtCore는 시각/열거값, QtGui는 종료 이벤트, QtWidgets는 화면 구성 요소를 제공한다.
# 아래 client.* 객체가 HTTP 조회와 파싱을 담당하고 이 파일은 화면과 사용자 조작을 맡는다.
# 창 감지·DB 저장·활성 시간 계산은 여기서 수행하지 않는다.
from PySide6.QtCore import QDateTime, Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from client.activity_client import ActivityClient
from client.backend_client import BackendClient
from client.recent_records import RecentRecordsWidget
from client.time_values import format_duration, format_timestamp
from shared.activity import CurrentActivity
from shared.protocol import DEFAULT_PORT


# [2단계: 여러 곳에서 쓸 표시 라벨 만들기]
# 입력은 문자열, 출력은 설정된 QLabel이다. 호출할 때마다 새 라벨을 만든다.
# PlainText로 지정해 '<b>제목</b>' 같은 외부 데이터도 서식이 아닌 글자로 표시한다.
# 줄바꿈과 선택을 허용하고, 긴 문자열 때문에 가로 폭이 과도하게 커지지 않도록 한다.
def display_label(text: str) -> QLabel:
    """외부 문자열을 HTML로 해석하지 않고 긴 문자열도 창 너비 안에서 표시한다."""
    label = QLabel(text)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
    return label


# [3단계: 화면 클래스와 초기화]
# QWidget을 상속해 하나의 창을 구성한다. self는 C#의 this에 대응하는 인스턴스 참조다.
# __init__은 초기 구성이고, 이후 동작은 클릭·응답·탭 변경 등의 이벤트가 시작한다.
# 파일에 적힌 메서드 순서와 실제 호출 시간 순서는 다르다.
class MainWindow(QWidget):
    """감지 로직 없이 검증된 현재 상태만 표시하고 실패 시 이전 창 정보를 비운다."""

    def __init__(self, port: int = DEFAULT_PORT) -> None:
        # 부모 QWidget 초기화를 먼저 한다. Qt 객체가 준비된 뒤 제목·크기·자식 위젯을 설정한다.
        # QVBoxLayout(self)는 위젯을 세로로 배치하며 생성한 창에 레이아웃을 설치한다.
        super().__init__()
        self.setWindowTitle("ContextTrace — 작업 기록")
        self.resize(620, 660)
        layout = QVBoxLayout(self)
        # [3-1: 연결 상태 영역]
        # status는 결과 문구, checked_at은 확인 시각, button은 사용자의 요청 시작점이다.
        # 이 시각은 마지막 확인 시각이지 서버가 지금도 살아 있다는 실시간 보장은 아니다.
        # addWidget은 화면 배치를 등록한다. 아직 버튼 동작은 연결하지 않은 상태다.
        connection = QGroupBox("Backend 연결 · 마지막 확인 결과")
        connection_layout = QVBoxLayout(connection)
        self.status = display_label("미확인")
        self.checked_at = display_label("마지막 확인: 없음")
        self.button = QPushButton("연결 확인")
        connection_layout.addWidget(self.status)
        connection_layout.addWidget(self.checked_at)
        connection_layout.addWidget(self.button)
        layout.addWidget(connection)

        # [3-2: 현재 창·시간 영역]
        # QFormLayout은 '항목 이름 : 값' 형식의 배치다.
        # 서버 연결 상태와 실제 수집 상태를 별도 라벨로 둔다.
        # 연결이 정상이어도 활성 창이 없거나 아직 감지 API가 준비되지 않을 수 있기 때문이다.
        activity = QGroupBox("현재 활성 창")
        activity_layout = QFormLayout(activity)
        self.collection_status = display_label("대기 — Backend 연결을 확인해 주세요.")
        self.application = display_label("—")
        self.process = display_label("—")
        # 긴 제목과 여러 줄을 줄바꿈/스크롤로 확인하며 서식이나 링크로 실행하지 않는다.
        # 창 제목은 여러 줄/긴 문자열을 보여 줄 수 있는 읽기 전용 텍스트 영역으로 만든다.
        # setPlainText를 사용하므로 제목 문자열을 HTML이나 링크 동작으로 해석하지 않는다.
        self.window_title = QPlainTextEdit()
        self.window_title.setReadOnly(True)
        self.window_title.setTabChangesFocus(True)
        self.window_title.setMaximumHeight(96)
        self.window_title.setPlainText("—")
        self.activity_updated_at = display_label("마지막 정상 수신: 없음")
        self.started_at = display_label("—")
        self.active_duration = display_label("—")
        activity_layout.addRow("수집 상태", self.collection_status)
        activity_layout.addRow("프로그램", self.application)
        activity_layout.addRow("프로세스", self.process)
        activity_layout.addRow("창 제목", self.window_title)
        activity_layout.addRow("작업 시작 (PC 현지 시각)", self.started_at)
        activity_layout.addRow("누적 활성 시간", self.active_duration)
        activity_layout.addRow(self.activity_updated_at)
        # [3-3: 현재 작업과 최근 기록 탭]
        # 최근 기록은 별도 위젯에 맡긴다. 이 창은 탭 선택과 연결 가능 여부를 전달한다.
        # currentChanged.connect(...)는 '탭이 바뀌면 이 함수를 호출하라'는 연결이다.
        # self._tab_changed 뒤에 ()를 붙이면 지금 호출하므로 여기서는 함수 자체를 전달한다.
        self.tabs = QTabWidget()
        self.tabs.addTab(activity, "현재 작업")
        self.recent = RecentRecordsWidget(port, self)
        self.tabs.addTab(self.recent, "최근 기록")
        self.tabs.currentChanged.connect(self._tab_changed)
        layout.addWidget(self.tabs, 1)

        # [4단계: 신호를 화면 처리 함수와 연결]
        # ActivityClient는 자동 조회 결과/실패를, BackendClient는 연결 확인 결과를 알린다.
        # 부모로 self를 넘겨 Qt 객체의 소유 관계를 만든다. 종료 시 명시적 요청 취소도 수행한다.
        # connect는 C#의 이벤트 구독과 비교할 수 있고 emit은 신호 발생에 해당한다.
        # 이 연결이 새 작업 스레드를 생성한다는 뜻은 아니다.
        self.activity = ActivityClient(port, self)
        self.activity.activity_received.connect(self._show_activity)
        self.activity.activity_failed.connect(self._clear_activity)
        self.backend = BackendClient(port, self)
        # result(str)는 표시 문구, connection_changed(bool)는 동작을 결정할 상태다.
        # 문구를 분석해 성공 여부를 추측하지 않고 bool 신호로 자동 조회 시작을 판단한다.
        # button.clicked는 check와 연결된다. 버튼 클릭이 실제 요청 흐름의 시작이다.
        self.backend.result.connect(self._show_result)
        self.backend.connection_changed.connect(self._connection_changed)
        self.button.clicked.connect(self.check)

    # [5단계: 사용자가 '연결 확인'을 누른 순간]
    # 진행 중인 연결 확인이 있으면 무시한다. 버튼 비활성화와 함께 중복 요청을 방지한다.
    # 기존 자동 조회와 최근 기록 조회를 멈춰 이전 응답이 새 확인 결과와 섞이지 않게 한다.
    # 이전 창 정보를 지우고 '연결 중'을 표시한 다음 BackendClient에 요청을 맡긴다.
    # backend.check()는 응답을 기다리는 동기 호출이 아니므로 여기서 UI를 붙잡지 않는다.
    def check(self) -> None:
        """연결 재확인 동안 이전 조회를 취소해 늦은 결과가 섞이지 않게 한다."""
        if self.backend.reply is not None:
            return
        self.activity.stop()
        self.recent.set_connected(False)
        self._clear_activity("대기 — Backend 연결 확인 중")
        self.status.setText("연결 중")
        self.button.setEnabled(False)
        self.backend.check()

    # [6단계: 연결 확인 결과를 받은 뒤 표시]
    # 성공/실패 모두 이 함수에서 문구·확인 시각을 갱신하고 버튼을 다시 활성화한다.
    # '_' 접두사는 내부용 메서드라는 관례이며 Python이 외부 호출을 강제로 막지는 않는다.
    def _show_result(self, message: str) -> None:
        """연결 결과와 확인 시각은 현재 창 수신 상태와 별도로 표시한다."""
        self.status.setText(message)
        self.checked_at.setText("마지막 확인: " + self._now())
        self.button.setEnabled(True)

    # [7단계: 연결 확인 결과에 따라 후속 조회 제어]
    # True이면 현재 작업 자동 조회를 시작하고, 선택된 탭이 최근 기록이면 그 조회도 준비한다.
    # False이면 현재 창 정보를 비운다. check()에서 이미 이전 자동 조회를 멈춘 흐름을 함께 본다.
    # HTTP 200만으로 True가 되는 것은 아니다. BackendClient의 내용 검증도 통과해야 한다.
    def _connection_changed(self, connected: bool) -> None:
        """표시 문구를 분석하는 대신 검증 결과로 자동 조회 여부를 결정한다."""
        self.recent.set_connected(connected)
        if connected:
            self._clear_activity("확인 중 — 현재 창 정보를 기다리고 있습니다.")
            self.activity.start()
            self._tab_changed(self.tabs.currentIndex())
        else:
            self._clear_activity("수신 중단 — Backend 연결을 확인해 주세요.")

    # [8단계: 최근 기록 탭이 선택될 때]
    # 인덱스 자체보다 해당 위치의 위젯이 self.recent인지 확인한다.
    # is는 같은 객체인지 비교한다. 최근 기록을 실제로 사용할 때 필요한 조회를 요청한다.
    # load_if_needed 내부가 연결 여부/기존 로딩 상태를 다루며, 이 함수에서 DB에 접근하지 않는다.
    def _tab_changed(self, index: int) -> None:
        """최근 기록 탭을 사용할 때 조회하며 현재 창 폴링과 분리한다."""
        if self.tabs.widget(index) is self.recent:
            self.recent.load_if_needed()

    # [9단계: 현재 작업 스냅샷 표시]
    # 입력은 ActivityClient가 검증한 CurrentActivity 객체다. 여기서는 원시 JSON을 파싱하지 않는다.
    # 상태별 문구를 고르고, window=None이면 이전 프로그램과 시간을 지운다.
    # 전제는 파서가 collection_status와 window 관계를 검증했다는 것이다.
    def _show_activity(self, activity: CurrentActivity) -> None:
        """새 스냅샷으로 교체하며 비수집 상태에서는 이전 프로그램/제목을 지운다."""
        messages = {
            "collecting": "감지 중 — 현재 창 정보 자동 갱신",
            "no_active_window": "대기 — 활성 창 없음",
            "unsupported": "수집 불가 — 지원하지 않는 창 또는 환경",
            "error": "감지 오류 — 다음 조회에서 다시 확인합니다.",
        }
        if activity.window is None:
            self._clear_activity(messages[activity.collection_status])
        else:
            self.collection_status.setText(messages[activity.collection_status])
            window = activity.window
            # 값이 바뀐 위젯만 갱신한다. 특히 제목을 매 응답마다 다시 넣으면 선택/스크롤을 잃을 수 있다.
            # window_title or '(제목 없음)'은 빈 문자열을 표시용 대체 문구로 바꾸는 부분이다.
            # 원본 스냅샷의 제목을 수정하는 것은 아니다.
            if self.application.text() != window.application:
                self.application.setText(window.application)
            process = f"{window.process_name} · PID {window.process_id}"
            if self.process.text() != process:
                self.process.setText(process)
            title = window.window_title or "(제목 없음)"
            # 동일 창의 반복 응답은 사용자가 선택한 텍스트/스크롤 위치를 초기화하지 않는다.
            if self.window_title.toPlainText() != title:
                self.window_title.setPlainText(title)
            # 시간 정보 미제공과 활성 시간 0을 구분한다.
            # 시작 시각은 PC 현지 시각의 표시 형식으로, 누적 밀리초는 읽기 좋은 지속 시간으로 바꾼다.
            # 클라이언트에서 타이머로 시간을 늘리지 않는다. Backend 누적값을 표시하는 책임만 가진다.
            if activity.timing is None:
                self.started_at.setText("시간 정보 없음")
                self.active_duration.setText("시간 정보 없음")
            else:
                # 수신 시각과 분리하고 Backend 누적값만 표시한다. 로컬 타이머로 늘리지 않는다.
                self.started_at.setText(format_timestamp(activity.timing.started_at))
                self.active_duration.setText(format_duration(activity.timing.active_duration_ms))
        # 이 표시는 정상 규격의 스냅샷을 받은 시각이다.
        # no_active_window 같은 비수집 상태도 정상 응답이므로 수신 시각은 갱신될 수 있다.
        # 작업 시작 시각·누적 활성 시간과는 별도 의미다.
        self.activity_updated_at.setText("마지막 정상 수신: " + self._now())

    # [10단계: 실패하거나 창이 사라졌을 때 이전 값 제거]
    # 예전 Chrome 제목을 현재 감지 결과로 오인하지 않도록 관련 표시를 함께 비운다.
    # 마지막 정상 수신 시각은 여기서 지우지 않는다. 과거 수신 이력으로 남긴다.
    def _clear_activity(self, message: str) -> None:
        """이전 성공 데이터를 현재 감지 결과로 오인하지 않도록 즉시 비운다."""
        self.collection_status.setText(message)
        self.application.setText("—")
        self.process.setText("—")
        self.window_title.setPlainText("—")
        self.started_at.setText("—")
        self.active_duration.setText("—")

    # _now는 인스턴스 상태를 읽지 않아 staticmethod로 선언했다.
    # self 인자 없이 호출할 수 있으며 현재 시각의 표시 문자열만 반환한다.
    @staticmethod
    def _now() -> str:
        """수신 시각을 표시하며 작업 시작 시각이나 활성 시간으로 사용하지 않는다."""
        return QDateTime.currentDateTime().toString("yyyy-MM-dd HH:mm:ss")

    # [11단계: 창을 닫을 때 정리]
    # Qt가 닫기 이벤트에서 호출한다. 일반 메서드와 달리 부모 클래스가 정한 이름을 따른다.
    # 자동 조회·연결 요청·최근 기록 요청을 정리해 닫힌 화면에 늦은 응답이 도착하지 않게 한다.
    # 마지막으로 부모의 닫기 처리도 실행한다. 부모 관계만으로 네트워크 취소 순서를 대체하지 않는다.
    def closeEvent(self, event: QCloseEvent) -> None:
        """화면 종료 이후 자동 조회나 응답 콜백이 남지 않도록 모든 요청을 정리한다."""
        self.activity.stop()
        self.backend.close()
        self.recent.set_connected(False)
        super().closeEvent(event)
