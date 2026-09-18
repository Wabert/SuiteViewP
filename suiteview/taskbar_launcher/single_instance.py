"""Single-instance activation routed through the launcher's Qt restore path."""

import ctypes
import ctypes.wintypes as wt
import logging
import sys

logger = logging.getLogger(__name__)
_mutex_handles = []
_owned_mutexes = set()
_ACTIVATE_MESSAGE = "SuiteView_RestoreLauncher"


def owned_mutex_names() -> frozenset[str]:
    """Identities already held by this process, before profile initialization."""
    return frozenset(_owned_mutexes)


def _user32():
    user32 = ctypes.windll.user32
    user32.FindWindowW.argtypes = [wt.LPCWSTR, wt.LPCWSTR]
    user32.FindWindowW.restype = wt.HWND
    user32.RegisterWindowMessageW.argtypes = [wt.LPCWSTR]
    user32.RegisterWindowMessageW.restype = wt.UINT
    user32.PostMessageW.argtypes = [
        wt.HWND, wt.UINT, ctypes.c_size_t, ctypes.c_ssize_t,
    ]
    user32.PostMessageW.restype = wt.BOOL
    user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
    user32.GetWindowThreadProcessId.restype = wt.DWORD
    user32.AllowSetForegroundWindow.argtypes = [wt.DWORD]
    user32.AllowSetForegroundWindow.restype = wt.BOOL
    return user32


def activation_message() -> int:
    if sys.platform != "win32":
        return 0
    message = _user32().RegisterWindowMessageW(_ACTIVATE_MESSAGE)
    if not message:
        raise ctypes.WinError()
    return message


def request_activation(hwnd: int) -> None:
    """Ask the owning UI thread to show, activate and re-dock the launcher."""
    user32 = _user32()
    pid = wt.DWORD()
    if user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid)):
        # The shortcut process has foreground permission; pass it to the owner.
        user32.AllowSetForegroundWindow(pid.value)
    if not user32.PostMessageW(hwnd, activation_message(), 0, 0):
        raise ctypes.WinError()


def acquire_or_activate(
    mutex_name: str = "SuiteView_SingleInstance_Mutex",
    window_titles: tuple[str, ...] = ("SuiteView",),
) -> bool:
    """Keep the first process alive; subsequent launches only request restore."""
    if sys.platform != "win32":
        return True
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [wt.LPVOID, wt.BOOL, wt.LPCWSTR]
    kernel32.CreateMutexW.restype = wt.HANDLE
    kernel32.CloseHandle.argtypes = [wt.HANDLE]
    kernel32.CloseHandle.restype = wt.BOOL
    mutex = kernel32.CreateMutexW(None, False, mutex_name)
    error = ctypes.get_last_error()
    if not mutex:
        raise ctypes.WinError(error)
    if error != 183:  # ERROR_ALREADY_EXISTS
        _mutex_handles.append(mutex)
        _owned_mutexes.add(mutex_name)
        return True

    kernel32.CloseHandle(mutex)
    user32 = _user32()
    for title in window_titles:
        hwnd = user32.FindWindowW(None, title)
        if hwnd:
            request_activation(hwnd)
            return False
    logger.warning(
        "SuiteView is already running but its launcher is not ready. "
        "Try the shortcut again after startup, or use the system tray."
    )
    return False
