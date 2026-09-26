"""WorkerController adapters shared by RateManager panels."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PyQt6.QtCore import QObject

from suiteview.ui.workers import WorkerController, WorkerSignals


class RateManagerWorker(QObject):
    """Base class for RateManager jobs run by ``WorkerController``."""

    def __init__(self) -> None:
        super().__init__()
        self.signals = WorkerSignals(self)

    def emit_progress(self, fraction: float, message: str) -> None:
        self.signals.progress.emit((fraction, message))

    def emit_result(self, result: Any) -> None:
        self.signals.result.emit(result)

    def emit_error(self, message: str) -> None:
        self.signals.error.emit(message)

    def run(self) -> None:
        try:
            self._run()
        except Exception as exc:
            self.emit_error(str(exc))
        finally:
            self.signals.finished.emit()

    def _run(self) -> None:
        raise NotImplementedError


class WorkupWorker(RateManagerWorker):
    """Run a workup operation that accepts ``progress_cb``."""

    def __init__(self, operation: Callable, *args: Any) -> None:
        super().__init__()
        self._operation = operation
        self._args = args

    def _run(self) -> None:
        result = self._operation(
            *self._args,
            progress_cb=lambda fraction, message: self.emit_progress(
                fraction,
                message,
            ),
        )
        if getattr(result, "error", None):
            self.emit_error(result.error)
        else:
            self.emit_result(result)


def connect_pair_progress(controller: WorkerController, slot: Callable[[float, str], None]) -> None:
    """Connect ``WorkerSignals.progress`` tuple payloads to a two-argument slot."""
    controller.progress.connect(lambda payload: slot(*payload))


def start_workup_worker(
    owner: QObject,
    operation: Callable,
    args: tuple[Any, ...],
    *,
    on_progress: Callable[[float, str], None],
    on_result: Callable[[Any], None],
    on_error: Callable[[str], None],
) -> WorkerController:
    """Create, connect and start a workup worker controller."""
    controller = WorkerController(owner, WorkupWorker(operation, *args))
    connect_pair_progress(controller, on_progress)
    controller.result.connect(on_result)
    controller.error.connect(on_error)
    controller.start()
    return controller
