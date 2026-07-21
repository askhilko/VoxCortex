from __future__ import annotations

import webbrowser
from collections.abc import Callable


SUPPORT_URL = "https://github.com/askhilko/VoxCortex/blob/main/SUPPORT.md"


def open_support_page(opener: Callable[..., bool] | None = None) -> bool:
    """Open the stable support page without handling payment data in the app."""
    browser_opener = opener or webbrowser.open
    return bool(browser_opener(SUPPORT_URL, new=2))
