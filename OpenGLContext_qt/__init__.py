"""PySide6 (Qt 6) Context implementation for OpenGLContext

Importing this package registers the ``qt`` backend with OpenGLContext's plugin
system, which is all that is needed for ``OPENGLCONTEXT_BACKEND=qt`` -- or
``Context.getContextType('qt')`` -- to find it.  OpenGLContext imports this
package itself if it is installed, so an application usually imports nothing
from here at all.

Registration is deliberately the *only* thing this module does: the contexts
themselves live in :mod:`OpenGLContext_qt.qtcontext` and are loaded when one is
asked for, so a program using another backend does not pay for Qt.
"""

from OpenGLContext.plugins import Context, InteractiveContext, VRMLContext

__version__ = "2.0.0a1"
__author__ = "Michael Colin Fletcher"
__license__ = "BSD-Style, see license.txt for details"

Context(
    "qt",
    "OpenGLContext_qt.qtcontext.QtContext",
)
InteractiveContext(
    "qt",
    "OpenGLContext_qt.qtcontext.QtInteractiveContext",
)
VRMLContext(
    "qt",
    "OpenGLContext_qt.qtcontext.QtViewerContext",
)
