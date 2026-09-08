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

#: The size asked for. Comfortably above the smallest top-level window a
#: platform will make -- Windows will not give one narrower than about 150
#: pixels, whatever is asked -- so that what this measures is the context and
#: not the window manager's floor.
ASKED = (320, 240)

#: Build a context the plain way, with no application made first, and report
#: what it says its size is, what the window is, and what the display scaling
#: between them is.
DRIVE = """
from OpenGLContext_qt.qtcontext import QtInteractiveContext
context = QtInteractiveContext(size=%r)
try:
    print('VIEWPORT %%s %%s' %% context.getViewPort())
    print('WINDOW %%s %%s' %% (context.size().width(), context.size().height()))
    print('RATIO %%s' %% (context.devicePixelRatio(),))
finally:
    context.releaseWindow()
""" % (ASKED,)


def reported(output, name):
    """The numbers on the ``name`` line of the subprocess's report."""
    for line in output.splitlines():
        if line.startswith(name + ' '):
            return [float(part) for part in line.split()[1:]]
    raise AssertionError('the child printed no %s line:\n%s' % (name, output))


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


def test_the_window_is_the_size_that_was_asked_for(built):
    """The size reaches the window, in the logical pixels Qt sizes windows in."""
    if 'no drawable GL surface' in built.stderr:
        pytest.skip('this Qt platform plugin gives no drawable GL surface')
    assert reported(built.stdout, 'WINDOW') == list(ASKED), \
        built.stdout + built.stderr


def test_it_knows_its_size(built):
    """The viewport it reports is the drawable it has, not the size asked for.

    Qt sizes a window in logical pixels and a scaled display renders more than
    that: at 125% a 320x240 window is a 400x300 framebuffer. The viewport has
    to be the pixels GL actually draws, or the rest of the window is left
    undrawn -- which is why ``QtContext.framebufferSize`` multiplies by the
    device pixel ratio, and why the glfw backend takes the framebuffer size
    rather than the requested one.
    """
    if 'no drawable GL surface' in built.stderr:
        pytest.skip('this Qt platform plugin gives no drawable GL surface')
    viewport = reported(built.stdout, 'VIEWPORT')
    window = reported(built.stdout, 'WINDOW')
    ratio, = reported(built.stdout, 'RATIO')
    assert viewport == [int(window[0] * ratio), int(window[1] * ratio)], \
        built.stdout + built.stderr
