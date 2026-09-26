"""Shared Qt worker controller.

Workers are plain ``QObject`` instances that create their thread-owned
resources inside ``run``. ``WorkerController`` owns the ``QThread`` lifecycle and
forwards the standard signals every SuiteView background task uses.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from PyQt6.QtCore import QObject, QThread, pyqtSignal

logger = logging.getLogger(__name__)


class _WorkerInvoker(QObject):
    """Run a worker from inside the worker thread and report uncaught errors."""

    def __init__(self, worker: QObject) -> None:
        super().__init__()
        self.worker = worker

    def run(self) -> None:
        try:
            self.worker.run()  # type: ignore[attr-defined]
        except Exception as exc:
            logger.exception("Unhandled worker error")
            signals: WorkerSignals = getattr(self.worker, "signals")
            signals.error.emit(str(exc))
            signals.finished.emit()


class WorkerSignals(QObject):
    """Standard signal surface for SuiteView background workers."""

    progress = pyqtSignal(object)
    result = pyqtSignal(object)
    error = pyqtSignal(object)
    cancelled = pyqtSignal()
    finished = pyqtSignal()


class WorkerController(QObject):
    """Run a ``QObject`` worker on a ``QThread`` without blocking the UI thread.

    Args:
        owner: Qt owner whose lifetime bounds the worker thread.
        worker: QObject with a ``run`` method and a ``signals`` attribute.
        cancel: Optional callable used by :meth:`cancel`.
    """

    progress = pyqtSignal(object)
    result = pyqtSignal(object)
    error = pyqtSignal(object)
    cancelled = pyqtSignal()
    finished = pyqtSignal()

    def __init__(
        self,
        owner: QObject | None,
        worker: QObject,
        *,
        cancel: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(owner)
        if not hasattr(worker, "run"):
            raise TypeError("WorkerController workers must provide run()")
        signals = getattr(worker, "signals", None)
        if signals is None:
            raise TypeError("WorkerController workers must expose WorkerSignals as .signals")

        self.worker = worker
        self.thread = QThread(owner)
        self._invoker = _WorkerInvoker(worker)
        self._cancel = cancel
        self._running = False
        self._thread_finished = False

        self.worker.moveToThread(self.thread)
        self._invoker.moveToThread(self.thread)
        self.thread.started.connect(self._invoker.run)
        signals.progress.connect(self.progress.emit)
        signals.result.connect(self.result.emit)
        signals.error.connect(self.error.emit)
        signals.cancelled.connect(self.cancelled.emit)
        signals.finished.connect(self.thread.quit)
        signals.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self._on_thread_finished)
        self.thread.finished.connect(self._invoker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        if owner is not None:
            owner.destroyed.connect(self.cancel)

    def start(self) -> None:
        """Start the worker thread."""
        self._running = True
        self.thread.start()

    def cancel(self) -> None:
        """Ask the worker to stop; do not wait on the UI thread."""
        if self._thread_finished:
            return
        try:
            if self._cancel is not None:
                self._cancel()
            elif hasattr(self.worker, "cancel"):
                self.worker.cancel()  # type: ignore[attr-defined]
        except RuntimeError:
            logger.debug("Worker was already deleted during cancel", exc_info=True)

    def is_running(self) -> bool:
        """Return whether the backing thread is still active."""
        return self._running and not self._thread_finished and self.thread.isRunning()

    def _run_worker(self) -> None:
        try:
            self.worker.run()  # type: ignore[attr-defined]
        except Exception as exc:
            logger.exception("Unhandled worker error")
            signals: WorkerSignals = getattr(self.worker, "signals")
            signals.error.emit(str(exc))
            signals.finished.emit()

    def _on_thread_finished(self) -> None:
        self._running = False
        self._thread_finished = True
        self.finished.emit()


class CallableWorker(QObject):
    """Small worker wrapper for pure callables that return one result."""

    def __init__(self, work: Callable[[], Any], parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.signals = WorkerSignals(self)
        self._work = work
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        try:
            if self._cancelled:
                self.signals.cancelled.emit()
                return
            self.signals.result.emit(self._work())
        except Exception as exc:
            logger.exception("Callable worker failed")
            self.signals.error.emit(str(exc))
        finally:
            self.signals.finished.emit()
