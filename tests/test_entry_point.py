"""The entry point that makes ``qt`` a window system OpenGLContext can open

OpenGLContext finds window systems in other distributions through the
``openglcontext.windowsystems`` entry-point group, reading the name and the
import path from the installed metadata without importing anything.  A
declaration naming a class that has moved, or one that is not a
``WindowSystem``, is found by nothing until somebody asks for ``qt`` and is
told it will not import.
"""
from OpenGL.plugins import importByName
from OpenGLContext import windowsystem
from OpenGLContext.windowsystem.base import WindowSystem

from OpenGLContext_qt.windowsystem import QtWindowSystem

from conftest import declaredEntryPoints

GROUP = 'openglcontext.windowsystems'


def declared():
    return declaredEntryPoints()[1].get(GROUP, {})


def test_the_project_declares_the_qt_window_system():
    assert declared().get('qt') == 'OpenGLContext_qt.windowsystem:QtWindowSystem'


def test_it_is_the_only_window_system_declared():
    assert list(declared()) == ['qt']


def test_the_declared_path_loads_the_window_system_class():
    """Resolved the way the engine resolves a registered path."""
    loaded = importByName(declared()['qt'].replace(':', '.'))
    assert loaded is QtWindowSystem
    assert issubclass(loaded, WindowSystem)
    assert loaded.name == 'qt'


def test_the_engine_loads_it_by_name():
    assert windowsystem.load('qt') is QtWindowSystem
