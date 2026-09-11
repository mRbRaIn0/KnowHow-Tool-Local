import sys
import types
from pathlib import Path
from unittest.mock import Mock, patch

import desktop


def test_webview_uses_product_name_and_maximized_window() -> None:
    webview = types.SimpleNamespace(create_window=Mock(), start=Mock())

    with patch.dict(sys.modules, {"webview": webview}):
        assert desktop._webview_fenster("http://127.0.0.1") is True

    assert webview.create_window.call_args.args[0] == "KnowHow Tool"
    assert webview.create_window.call_args.kwargs["fullscreen"] is False
    assert webview.create_window.call_args.kwargs["maximized"] is True


def test_browser_fallback_starts_maximized() -> None:
    process = Mock()
    with patch.object(desktop, "browser_programm", return_value="browser.exe"), \
            patch.object(desktop.subprocess, "Popen", return_value=process) as popen:
        assert desktop._browser_fenster("http://127.0.0.1", Path("dist")) is process

    assert "--start-maximized" in popen.call_args.args[0]
    assert "--start-fullscreen" not in popen.call_args.args[0]
