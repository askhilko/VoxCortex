from __future__ import annotations

from unittest.mock import Mock

from voxcortex.links import SUPPORT_URL, open_support_page


def test_support_url_points_to_public_project_page() -> None:
    assert SUPPORT_URL == "https://github.com/askhilko/VoxCortex/blob/main/SUPPORT.md"


def test_open_support_page_uses_default_browser() -> None:
    opener = Mock(return_value=True)

    assert open_support_page(opener)
    opener.assert_called_once_with(SUPPORT_URL, new=2)
