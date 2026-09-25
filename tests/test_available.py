"""Whether Qt can start a GUI application here, asked without starting one."""

import os

from OpenGLContext_qt import available
from OpenGLContext_qt.available import gui_unavailable


def _environment(**changes):
    environment = dict(os.environ)
    environment.update(changes)
    return environment


def test_a_platform_that_starts_is_available():
    assert gui_unavailable(_environment(QT_QPA_PLATFORM="offscreen")) is None


def test_a_display_that_refuses_is_a_reason_not_an_abort():
    reason = gui_unavailable(
        _environment(QT_QPA_PLATFORM="xcb", DISPLAY=":987", WAYLAND_DISPLAY="")
    )
    assert reason is not None
    assert "qt.qpa.xcb" in reason


def test_a_child_that_hangs_is_a_reason(monkeypatch):
    monkeypatch.setattr(available, "_PROBE", "import time; time.sleep(10)")
    monkeypatch.setattr(available, "TIMEOUT", 0.2)
    assert "more than 0.2 seconds" in gui_unavailable()


def test_a_child_that_says_nothing_is_named_by_its_exit_status(monkeypatch):
    monkeypatch.setattr(available, "_PROBE", "raise SystemExit(3)")
    assert gui_unavailable().endswith("exit status 3")


def test_a_child_with_no_platform_messages_is_named_by_its_last_line(monkeypatch):
    monkeypatch.setattr(available, "_PROBE", 'import sys; sys.exit("the last word")')
    assert gui_unavailable().endswith("the last word")
