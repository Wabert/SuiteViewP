"""Serial, cancellable background preparation; Qt widgets stay on the GUI thread."""

from dataclasses import dataclass
import logging
from threading import Event
from typing import TYPE_CHECKING

from PyQt6.QtCore import QObject, QThread, Qt, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import QApplication
from PyQt6 import sip

from suiteview.core.db2_connection import _extract_odbc_message
from suiteview.core.odbc_utils import is_communication_error

if TYPE_CHECKING:
    from ..models.policy_information import PolicyInformation

logger = logging.getLogger(__name__)

DETAIL_STAGES = (
    "policy", "targets", "persons", "activity", "dividends", "loans",
    "advprod", "reinsurance", "support", "tables",
)
# Stages that feed a panel rather than a tab page.
PANEL_STAGES = ("tables",)


@dataclass(frozen=True)
class _LoadJob:
    token: int
    stage: str
    policy_number: str
    region: str
    company_code: str
    cancelled: Event
    seed: "PolicyInformation | None" = None


class _PolicyWorker(QObject):
    completed = pyqtSignal(int, str, object, str)
    stopped = pyqtSignal()

    def __init__(self, session_factory=None):
        super().__init__()
        self._session_factory = session_factory
        self._session = None
        self._token = None

    @pyqtSlot(object)
    def execute(self, job: _LoadJob):
        if job.cancelled.is_set():
            return
        result = None
        error = ""
        for attempt in range(2):
            if job.cancelled.is_set():
                return
            try:
                if job.stage == "coverages":
                    self._close_session()
                    if self._session_factory is None:
                        from ..services.policy_prefetch import PolicyLoadSession
                        factory = PolicyLoadSession
                    else:
                        factory = self._session_factory
                    self._session = factory(
                        job.policy_number, job.region, job.company_code, seed=job.seed,
                    )
                    self._token = job.token
                    result = self._session.load_initial()
                elif self._session is not None and self._token == job.token:
                    result = self._session.prepare(job.stage)
                else:
                    raise RuntimeError("The policy loading session is no longer available. Reload the policy.")
                break
            except Exception as exc:
                detail = _extract_odbc_message(exc)
                communication_failure = is_communication_error(detail)
                if communication_failure and attempt == 0:
                    # The session's failed scope has closed its private connections.
                    logger.warning(
                        "PolView %s communication failed; retrying once: %s",
                        job.stage, detail, exc_info=True,
                    )
                    continue
                logger.exception("PolView background %s failed", job.stage)
                error = (
                    "The database connection was interrupted and reconnecting once "
                    "did not resolve it. Retry the lookup or this tab. If it persists, "
                    "check network/VPN and database availability.\n\n" + detail
                    if communication_failure else detail
                )
                break
        if not job.cancelled.is_set():
            self.completed.emit(job.token, job.stage, result, error)

    def _close_session(self):
        if self._session is not None:
            self._session.close()
            self._session = None
        self._token = None

    @pyqtSlot()
    def stop(self):
        try:
            self._close_session()
        except Exception:
            logger.exception("Could not close the PolView background session")
        finally:
            self.stopped.emit()


class PolicyLoadController(QObject):
    """One worker per window, one queued page at a time; selected pages go first."""

    ready = pyqtSignal(int, str, object)
    failed = pyqtSignal(int, str, str)
    state_changed = pyqtSignal(str, str)
    settled = pyqtSignal(int)
    _execute = pyqtSignal(object)
    _stop = pyqtSignal()

    def __init__(self, session_factory=None):
        app = QApplication.instance()
        super().__init__(app)
        self.token = 0
        self.states: dict[str, str] = {}
        self._pending: list[str] = []
        self._running: str | None = None
        self._cancelled = Event()
        self._identity = ("", "", "")
        self._disposed = False
        self._thread = QThread(self)
        self._worker = _PolicyWorker(session_factory)
        self._worker.moveToThread(self._thread)
        self._execute.connect(self._worker.execute)
        self._stop.connect(self._worker.stop)
        self._worker.completed.connect(self._completed)
        self._worker.stopped.connect(self._thread.quit, Qt.ConnectionType.DirectConnection)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._on_thread_finished)
        app.aboutToQuit.connect(self.shutdown)

    @property
    def busy(self) -> bool:
        return self._running is not None or bool(self._pending)

    def start(self, policy_number, region, company_code, *, seed=None) -> int:
        if self._disposed:
            raise RuntimeError("The policy loader has been disposed.")
        self._cancelled.set()
        self.token += 1
        self._cancelled = Event()
        self._identity = (policy_number, region, company_code)
        self._pending.clear()
        self.states = {"coverages": "loading"}
        self._running = "coverages"
        if not self._thread.isRunning():
            self._thread.start()
        self._execute.emit(_LoadJob(
            self.token, "coverages", *self._identity, self._cancelled, seed,
        ))
        return self.token

    def prioritize(self, stage: str):
        if stage in self._pending:
            self._pending.remove(stage)
            self._pending.insert(0, stage)

    def retry(self, stage: str):
        if stage == "coverages" or self._disposed:
            return
        if self.states.get(stage) not in ("failed", "ready"):
            return
        self.states[stage] = "queued"
        self._pending.insert(0, stage)
        self.state_changed.emit(stage, "queued")
        self._dispatch_next()

    def _dispatch_next(self):
        if self._running is not None or self._disposed:
            return
        if not self._pending:
            self.settled.emit(self.token)
            return
        stage = self._pending.pop(0)
        self._running = stage
        self.states[stage] = "loading"
        self.state_changed.emit(stage, "loading")
        self._execute.emit(_LoadJob(
            self.token, stage, *self._identity, self._cancelled,
        ))

    @pyqtSlot(int, str, object, str)
    def _completed(self, token, stage, result, error):
        if token != self.token or self._disposed:
            return
        self._running = None
        if error:
            self.states[stage] = "failed"
            self.failed.emit(token, stage, error)
        else:
            self.states[stage] = "ready"
            if stage == "coverages" and result.policy.identity.exists:
                self._pending = [
                    key for key in DETAIL_STAGES
                    if key != "advprod" or result.policy.product.is_advanced_product
                ]
                self.states.update({key: "queued" for key in self._pending})
            self.ready.emit(token, stage, result)
        # A result handler may have started a different policy or disposed us.
        if token == self.token:
            self._dispatch_next()

    @pyqtSlot()
    def dispose(self):
        if self._disposed:
            return
        self._disposed = True
        self._cancelled.set()
        self._pending.clear()
        self._running = None
        if self._thread.isRunning():
            self._stop.emit()

    @pyqtSlot()
    def _on_thread_finished(self):
        if self._disposed:
            self.deleteLater()

    @pyqtSlot()
    def shutdown(self):
        if sip.isdeleted(self._thread):
            return
        self.dispose()
        # Never destroy a live QThread or close its ODBC handles from the GUI.
        self._thread.wait()
