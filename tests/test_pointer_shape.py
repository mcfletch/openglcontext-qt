"""The pointer's shape, asked of the Qt backend.

Named apart from Qt's own ``setCursor``, which takes a ``QCursor``: the
engine asks every backend the same question in the same words, and a widget
class that already has that name is exactly why the engine's is
``setPointerShape``.
"""
import pytest

PySide6 = pytest.importorskip('PySide6')

from OpenGLContext_qt.qtcontext import QtContext  # noqa: E402


def test_its_table_is_written_in_the_engines_names():
    from OpenGLContext.context import CURSORS
    for name in QtContext.CURSOR_SHAPES:
        assert name in CURSORS, name


def test_every_shape_it_names_is_one_qt_has():
    from PySide6 import QtCore
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
