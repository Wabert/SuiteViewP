"""Non-blocking, fail-closed visibility of the Administrator launcher action."""

import logging

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QMenu

from suiteview.administrator.service import AccessRepository
from suiteview.core.build_env import has_developer_access

logger = logging.getLogger(__name__)


class _ProbeSignals(QObject):
    completed = pyqtSignal(bool)


class _AdminProbe(QRunnable):
    def __init__(self):
        super().__init__()
        self.signals = _ProbeSignals()

    def run(self):
        try:
            allowed = AccessRepository().is_admin()
        except Exception:
            logger.exception("Could not verify ADMIN access; Administrator remains unavailable")
            allowed = False
        self.signals.completed.emit(allowed)


class AdministratorMenuAccess(QObject):
    def __init__(self, menu: QMenu, action: QAction):
        super().__init__(menu)
        self.action = action
        self._pending = False
        self._probe = None
        action.setVisible(has_developer_access())
        menu.aboutToShow.connect(self.refresh)

    @pyqtSlot()
    def refresh(self):
        if has_developer_access():
            self.action.setVisible(True)
            return
        self.action.setVisible(False)
        if self._pending:
            return
        self._pending = True
        self._probe = _AdminProbe()
        self._probe.signals.completed.connect(self._completed)
        QThreadPool.globalInstance().start(self._probe)

    @pyqtSlot(bool)
    def _completed(self, allowed: bool):
        self._pending = False
        self._probe = None
        self.action.setVisible(allowed)
