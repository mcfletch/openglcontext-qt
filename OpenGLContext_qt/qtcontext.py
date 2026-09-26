"""Qt: :class:`~OpenGLContext.context.Context` on the qt window system

``QtContext`` is ``Context`` with ``windowsystem = 'qt'`` chosen, taking an
optional parent ``QWindow`` as its second argument.  The window, its events
and its loop are :mod:`OpenGLContext_qt.windowsystem`'s, and
``context.window`` is the ``QWindow`` an application places in its layout::

    view = QtContext(parent=None, size=(800, 600))
    layout.addWidget(view.windowsystem.container(splitter))

``QtInteractiveContext`` and ``QtViewerContext`` are the same class: every
Context has the camera, the event managers and the scene loading.
"""
from typing import Any

from OpenGLContext.context import Context

from OpenGLContext_qt.windowsystem import (
    COLOUR_BITS, CORE_VERSION, EXPOSURE_TIMEOUT, HIDDEN_ENV, describeFormat,
    ensureApplication, hiddenRequested, surfaceFormatFromDefinition,
)

__all__ = (
    'COLOUR_BITS',
    'CORE_VERSION',
    'EXPOSURE_TIMEOUT',
    'HIDDEN_ENV',
    'QtContext',
    'QtInteractiveContext',
    'QtViewerContext',
    'describeFormat',
    'ensureApplication',
    'hiddenRequested',
    'surfaceFormatFromDefinition',
)


class QtContext(Context):
    """A Context on the qt window system"""

    windowSystemName = 'qt'

    def __init__(self, definition: Any = None, parent: Any = None,
                 **named: Any) -> None:
        """definition -- as for :class:`~OpenGLContext.context.Context`
        parent -- a QWindow to open inside, or None for a window of its own
        named -- individual definition fields
        """
        super().__init__(definition, parent=parent, **named)


QtInteractiveContext = QtContext
QtViewerContext = QtContext
