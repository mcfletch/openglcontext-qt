"""PySide6 (Qt 6) window system for OpenGLContext

The ``qt`` window system is declared in this distribution's metadata, in the
``OpenGLContext.windowsystems`` entry-point group, so OpenGLContext finds it
without importing anything here: ``windowsystem='qt'`` in a definition, or
``OPENGLCONTEXT_BACKEND=qt``, opens a context on it.  The window system is
:mod:`OpenGLContext_qt.windowsystem`; :mod:`OpenGLContext_qt.qtcontext` names
the context class with it chosen.

Importing this package also registers ``qt`` with the plug-in registries
directly, for a program that has put the package on its path without
installing it.
"""

from OpenGLContext.plugins import (
    Context, InteractiveContext, VRMLContext, WindowSystem,
)

__version__ = "2.0.0a1"
__author__ = "Michael Colin Fletcher"
__license__ = "BSD-Style, see license.txt for details"

if WindowSystem.by_name("qt") is None:
    WindowSystem("qt", "OpenGLContext_qt.windowsystem.QtWindowSystem")
for _registry in (Context, InteractiveContext, VRMLContext):
    if _registry.by_name("qt") is None:
        _registry("qt", "OpenGLContext_qt.qtcontext.QtContext")
del _registry
