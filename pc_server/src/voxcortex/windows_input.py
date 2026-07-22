from __future__ import annotations

import ctypes
import os
from ctypes import wintypes


KEYS = {
    "ctrl": 0x11,
    "shift": 0x10,
    "alt": 0x12,
    "enter": 0x0D,
    "v": 0x56,
}

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("value",)
    _fields_ = [("type", wintypes.DWORD), ("value", INPUT_UNION)]


def _keyboard_input(key: int, *, key_up: bool = False) -> INPUT:
    flags = KEYEVENTF_KEYUP if key_up else 0
    return INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(key, 0, flags, 0, 0))


def send_hotkey(*keys: str) -> None:
    """Send one keyboard chord to the current foreground window."""
    if not keys:
        return
    normalized = [key.lower() for key in keys]
    try:
        virtual_keys = [KEYS[key] for key in normalized]
    except KeyError as exc:
        raise ValueError(f"Unsupported hotkey key: {exc.args[0]}") from exc

    if os.name != "nt":
        raise OSError("Keyboard input is supported only on Windows")

    events = [_keyboard_input(key) for key in virtual_keys]
    events.extend(_keyboard_input(key, key_up=True) for key in reversed(virtual_keys))
    array = (INPUT * len(events))(*events)
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
    user32.SendInput.restype = wintypes.UINT
    sent = user32.SendInput(len(events), array, ctypes.sizeof(INPUT))
    if sent != len(events):
        raise ctypes.WinError(ctypes.get_last_error())


def foreground_window() -> int | None:
    """Return the native handle of the current foreground window on Windows."""
    if os.name != "nt":
        return None
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetForegroundWindow.restype = wintypes.HWND
    handle = user32.GetForegroundWindow()
    return int(handle) if handle else None


def root_window(handle: int) -> int:
    """Resolve a child Tk window handle to its native top-level window."""
    if os.name != "nt":
        return handle
    GA_ROOT = 2
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetAncestor.argtypes = (wintypes.HWND, wintypes.UINT)
    user32.GetAncestor.restype = wintypes.HWND
    resolved = user32.GetAncestor(wintypes.HWND(handle), GA_ROOT)
    return int(resolved) if resolved else handle


def window_process_id(handle: int) -> int | None:
    if os.name != "nt":
        return None
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    process_id = wintypes.DWORD()
    if not user32.GetWindowThreadProcessId(wintypes.HWND(handle), ctypes.byref(process_id)):
        return None
    return int(process_id.value)


def activate_window(handle: int | None) -> bool:
    """Bring a previously active window back before emitting a paste hotkey."""
    if handle is None or os.name != "nt":
        return False
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.IsWindow.argtypes = (wintypes.HWND,)
    user32.IsWindow.restype = wintypes.BOOL
    user32.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
    user32.ShowWindow.restype = wintypes.BOOL
    user32.SetForegroundWindow.argtypes = (wintypes.HWND,)
    user32.SetForegroundWindow.restype = wintypes.BOOL
    if not user32.IsWindow(wintypes.HWND(handle)):
        return False
    user32.ShowWindow(wintypes.HWND(handle), 9)  # SW_RESTORE
    return bool(user32.SetForegroundWindow(wintypes.HWND(handle)))
