"""Whether Qt can start a GUI application on this machine.

Qt ends the process (``qFatal``) when no platform plugin can be loaded or the
display refuses the connection, so the question cannot be asked in the
process that wants the answer. :func:`gui_unavailable` asks a child process
to make a ``QGuiApplication`` and reports what stopped it.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Mapping

__all__ = ["gui_unavailable"]

_PROBE = "from PySide6.QtGui import QGuiApplication; QGuiApplication([])"

#: Seconds the child is given; a platform plugin that loads answers in well
#: under a second.
TIMEOUT = 30.0


def gui_unavailable(environment: Mapping[str, str] | None = None) -> str | None:
    """Why Qt cannot start a GUI application here, or None when it can.

    ``environment`` is the environment the application would run in (default:
    this process's). The reason is Qt's own platform messages (the
    ``qt.qpa.`` lines, which name the plugin and what it could not do), or
    the last line the child wrote where there are none.
    """
    try:
        child = subprocess.run(
            [sys.executable, "-c", _PROBE],
            env=None if environment is None else dict(environment),
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return "starting a QGuiApplication took more than %s seconds" % (TIMEOUT,)
    if child.returncode == 0:
        return None
    lines = [line.strip() for line in child.stderr.splitlines() if line.strip()]
    platform = [line for line in lines if line.startswith("qt.qpa.")]
    if platform:
        detail = "; ".join(platform)
    elif lines:
        detail = lines[-1]
    else:
        detail = "exit status %d" % (child.returncode,)
    return "Qt cannot start a GUI application here: %s" % (detail,)
