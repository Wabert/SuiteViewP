"""Shared imports for File Explorer mixins.

The File Explorer is being split from a historical monolith. This module keeps
common Qt/stdlib dependencies in one place while the focused mixins settle.
"""
from __future__ import annotations

import ctypes
import json
import logging
import math
import os
import re
import shutil
import stat as stat_module
import string
import subprocess
import sys
import tempfile
import time
import webbrowser
from ctypes import windll
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

try:
    import winreg
except ImportError:  # pragma: no cover - non-Windows development host
    winreg = None

try:
    import openpyxl
    from openpyxl.styles import Font, PatternFill
except ImportError:  # pragma: no cover - optional Excel export dependency
    openpyxl = None
    Font = None
    PatternFill = None

try:
    import pandas as pd
except ImportError:  # pragma: no cover - optional preview dependency
    pd = None

try:
    from PIL import Image
except ImportError:  # pragma: no cover - optional image preview dependency
    Image = None

try:
    import win32com.client
    from win32com.client import dynamic as win32com_dynamic
except ImportError:  # pragma: no cover - optional Windows COM automation
    win32com = None
    win32com_dynamic = None

from PyQt6.QtCore import (
    QFileInfo,
    QMimeData,
    QPersistentModelIndex,
    QRegularExpression,
    QSize,
    QSortFilterProxyModel,
    QThread,
    QTimer,
    Qt,
    QUrl,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QAction,
    QDesktopServices,
    QDrag,
    QDragEnterEvent,
    QDragMoveEvent,
    QDropEvent,
    QIcon,
    QStandardItem,
    QStandardItemModel,
)
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFileIconProvider,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStyle,
    QStyledItemDelegate,
    QToolBar,
    QToolButton,
    QTreeView,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from suiteview.core.access_control import guard_app_access
from suiteview.core.json_store import write_json
from suiteview.core.profile_paths import profile_path
from suiteview.core.support_files import guard_support_file_paths
from suiteview.file_nav.sharepoint_client import (
    SharePointDepthScanWorker,
    SharePointDiscoverWorker,
    SharePointDownloadWorker,
    SharePointListWorker,
    SharePointResolveWorker,
    get_sharepoint_client,
    is_sp_path,
    make_sp_path,
    parse_sp_path,
)
from suiteview.ui.dialogs.batch_rename_dialog import BatchRenameDialog
from suiteview.ui.dialogs.mainframe_upload_dialog import MainframeUploadDialog
from suiteview.ui.dialogs.shortcuts_dialog import AddBookmarkDialog, show_compact_confirm
from suiteview.ui.widgets.bookmark_data_manager import get_bookmark_manager
from suiteview.ui.widgets.bookmark_widgets import BookmarkContainer, BookmarkContainerRegistry
