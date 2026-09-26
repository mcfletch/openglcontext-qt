"""The pointer's shape, asked of the Qt window system.

The engine asks every window system for a shape by one of its ``CURSORS``
names through ``setPointerShape``; Qt's own ``setCursor`` takes a ``QCursor``.

A ``QCursor`` made with no ``QGuiApplication`` is a ``qFatal`` -- the process
aborts -- so the case that sets one asks for the session's application, as any
window of this window system has one.
"""
import pytest
from OpenGLContext.context import CURSORS
from PySide6 import QtCore

from OpenGLContext_qt.windowsystem import QtWindowSystem


class _Window:
    """The one thing ``setPointerShape`` asks of a window, recorded."""

    def __init__(self):
        self.cursors = []

    def setCursor(self, cursor):
        self.cursors.append(cursor.shape())


def _windowSystem(grabbed=False):
    """A Qt window system with a recording stand-in for its window."""
    system = QtWindowSystem(context=None)
    system.window = _Window()
    system.pointerGrabbed = grabbed
    return system


def test_its_table_is_written_in_the_engines_names():
    for name in QtWindowSystem.CURSOR_SHAPES:
        assert name in CURSORS, name


def test_every_shape_it_names_is_one_qt_has():
    for name, shape in QtWindowSystem.CURSOR_SHAPES.items():
        assert getattr(QtCore.Qt.CursorShape, shape, None) is not None, name


def test_it_has_the_ordinary_pointer():
    assert 'arrow' in QtWindowSystem.CURSOR_SHAPES


@pytest.mark.usefixtures('application')
def test_a_shape_it_has_is_set_on_the_window():
    system = _windowSystem()
    assert system.setPointerShape('hand')
    assert system.window.cursors == [QtCore.Qt.CursorShape.PointingHandCursor]


def test_a_shape_nobody_has_is_refused():
    system = _windowSystem()
    assert not system.setPointerShape('teapot')
    assert system.window.cursors == []


def test_nothing_is_set_while_the_pointer_is_grabbed():
    """Mouse-look hides the pointer; a hover must not put it back."""
    system = _windowSystem(grabbed=True)
    assert not system.setPointerShape('hand')
    assert system.window.cursors == []
