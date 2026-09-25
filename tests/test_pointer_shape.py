"""The pointer's shape, asked of the Qt backend.

The engine asks every backend for a shape by one of its ``CURSORS`` names
through ``setPointerShape``; Qt's own ``setCursor`` takes a ``QCursor``.
"""
from OpenGLContext.context import CURSORS
from PySide6 import QtCore

from OpenGLContext_qt.qtcontext import QtContext


def test_its_table_is_written_in_the_engines_names():
    for name in QtContext.CURSOR_SHAPES:
        assert name in CURSORS, name


def test_every_shape_it_names_is_one_qt_has():
    for name, shape in QtContext.CURSOR_SHAPES.items():
        assert getattr(QtCore.Qt.CursorShape, shape, None) is not None, name


def test_it_has_the_ordinary_pointer():
    assert 'arrow' in QtContext.CURSOR_SHAPES


def test_a_shape_nobody_has_is_refused():
    class _Stand(QtContext):
        _pointerGrabbed = False

        def __init__(self):
            pass

    assert not _Stand().setPointerShape('teapot')


def test_nothing_is_set_while_the_pointer_is_grabbed():
    """Mouse-look hides the pointer; a hover must not put it back."""
    class _Stand(QtContext):
        _pointerGrabbed = True

        def __init__(self):
            pass

    assert not _Stand().setPointerShape('hand')
