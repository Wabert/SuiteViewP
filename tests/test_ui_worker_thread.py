"""WorkerController runs worker code on its own thread, never the UI thread."""
import threading

from PyQt6.QtCore import QObject
from PyQt6.QtWidgets import QApplication

from suiteview.ui.workers import WorkerController, WorkerSignals


class _ThreadProbe(QObject):
    def __init__(self):
        super().__init__()
        self.signals = WorkerSignals()
        self.ran_on = None

    def run(self):
        self.ran_on = threading.get_ident()
        self.signals.result.emit(self.ran_on)
        self.signals.finished.emit()


def test_worker_runs_off_the_ui_thread(qtbot):
    app = QApplication.instance() or QApplication([])
    probe = _ThreadProbe()
    controller = WorkerController(None, probe)
    results = []
    controller.result.connect(results.append)

    controller.start()
    qtbot.waitUntil(lambda: bool(results), timeout=5000)
    app.processEvents()

    assert results[0] != threading.get_ident()
