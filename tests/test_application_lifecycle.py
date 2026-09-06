"""A Qt context can be built without the main loop having been entered

Qt requires a ``QGuiApplication`` before any window exists, and ends the process
with ``qFatal`` -- an abort, not an exception -- when a window is made without
one.  So a backend that creates the application only on its way into the main
loop is one whose windows can only be made that way, and everything that builds
a context and steps it itself (a test, a benchmark, a view embedded in a program
with its own loop) ends the process instead of getting a window.

The construction runs in a subprocess: what is under test is a failure that
takes the interpreter with it, and a check inside this one would be measuring an
application some other test has already made.
"""
import os
import subprocess
import sys

import pytest

#: Build a context the plain way, with no application made first, and report
#: what it says its size is.
DRIVE = """
from OpenGLContext_qt.qtcontext import QtInteractiveContext
context = QtInteractiveContext(size=(64, 48))
try:
    print('SIZE %s %s' % context.getViewPort())
finally:
    context.releaseWindow()
"""


@pytest.fixture
def built():
    """The subprocess's report, or the signal that killed it"""
    environment = dict(os.environ, OPENGLCONTEXT_HIDDEN='1')
    return subprocess.run(
        [sys.executable, '-c', DRIVE],
        capture_output=True, text=True, timeout=120, env=environment,
    )


def test_a_context_built_outside_the_main_loop_survives(built):
    assert built.returncode == 0, (
        'building a context ended the process (%s)\n%s'
        % (built.returncode, built.stderr))


def test_it_knows_its_size(built):
    if 'no drawable GL surface' in built.stderr:
        pytest.skip('this Qt platform plugin gives no drawable GL surface')
    assert 'SIZE 64 48' in built.stdout, built.stdout + built.stderr
