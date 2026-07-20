from __future__ import annotations

import logging
import time

from .config import Profile, Settings
from .windows_input import send_hotkey

LOG = logging.getLogger(__name__)
OUTPUT_ACTIONS = {"copy", "paste", "paste_enter", "paste_ctrl_enter"}


def legacy_output_action(profile: Profile, mode: str) -> str:
    """Translate firmware 1.3 profile/mode settings during the transition release."""
    if not profile.paste:
        return "copy"
    if mode == "enter":
        return "paste_enter"
    if mode == "ctrl_enter":
        return "paste_ctrl_enter"
    if profile.send_hotkey == "enter":
        return "paste_enter"
    if profile.send_hotkey == "ctrl+enter":
        return "paste_ctrl_enter"
    return "paste"


class TextInserter:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def insert(self, text: str, action: str) -> None:
        if not text:
            raise ValueError("recognized text is empty")
        if action not in OUTPUT_ACTIONS:
            raise ValueError(f"unknown output action: {action}")
        if not self.settings.insertion_enabled or self.settings.diagnostic:
            LOG.info("Insertion suppressed by configuration; characters=%d", len(text))
            return
        import pyperclip

        previous = pyperclip.paste() if self.settings.restore_clipboard and action != "copy" else None
        pyperclip.copy(text)
        if action != "copy":
            time.sleep(self.settings.paste_delay_ms / 1000)
            send_hotkey("ctrl", "v")
            LOG.info("Текст вставлен в активное окно; символов=%d", len(text))

        hotkey = {"paste_enter": "enter", "paste_ctrl_enter": "ctrl+enter"}.get(action)
        if hotkey:
            time.sleep(0.05)
            send_hotkey(*hotkey.split("+"))
        if previous is not None:
            time.sleep(0.05)
            pyperclip.copy(previous)
