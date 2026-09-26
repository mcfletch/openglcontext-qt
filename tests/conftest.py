"""Fixtures for the Qt window system's tests

The GL tests render real frames through a real window, because a Qt context
that has been mocked out proves only that the mocks agree with each other --
and the failures this window system is most likely to have (a surface format the
driver will not give, a window with no drawable surface, a viewport that
ignores display scaling) are all invisible without one.

They are skipped, with a reason that says what to do about it, when the Qt
platform plugin in use cannot give a window a drawable GL surface, or when Qt
cannot start a GUI application here at all.
"""

import pathlib

import pytest
from PySide6 import QtGui

import OpenGLContext_qt
from OpenGLContext_qt.available import gui_unavailable
from OpenGLContext_qt.qtcontext import QtInteractiveContext


#: This checkout's project file, which declares the entry points.
PYPROJECT = pathlib.Path(__file__).resolve().parent.parent / 'pyproject.toml'


def declaredEntryPoints():
    """The ``[project]`` table of ``pyproject.toml``, and its entry points by group

    ``tomllib`` is imported here rather than with the module: it is Python
    3.11's, and the rest of the suite runs on 3.10.
    """
    import tomllib  # noqa: PLC0415 Python 3.11 and later, and only these tests read TOML

    with PYPROJECT.open('rb') as stream:
        project = tomllib.load(stream)['project']
    return project, project.get('entry-points', {})


@pytest.fixture(scope='session')
def installed_metadata(tmp_path_factory):
    """A directory holding this distribution's metadata as an installer writes it

    The ``.dist-info`` an installer makes from this checkout's
    ``pyproject.toml``: the name, the version and ``entry_points.txt``.  Put
    first on a child's path it is the distribution ``importlib.metadata``
    finds, so what is tested is what this checkout declares rather than what
    was installed from some earlier one.
    """
    project, groups = declaredEntryPoints()
    root = tmp_path_factory.mktemp('site')
    distribution = project['name'].replace('-', '_').lower()
    info = root / ('%s-%s.dist-info' % (distribution, OpenGLContext_qt.__version__))
    info.mkdir()
    (info / 'METADATA').write_text(
        'Metadata-Version: 2.1\nName: %s\nVersion: %s\n'
        % (project['name'], OpenGLContext_qt.__version__))
    (info / 'entry_points.txt').write_text(''.join(
        '[%s]\n%s\n' % (group, ''.join(
            '%s = %s\n' % (name, value) for name, value in entries.items()))
        for group, entries in groups.items()))
    return root


@pytest.fixture(scope='session')
def application():
    """The one QGuiApplication the whole session shares

    Qt allows exactly one, and it must exist before any window.  The bare
    ``QGuiApplication`` rather than a ``QApplication``, because that is all the
    window system itself requires -- only ``QtWindowSystem.container`` needs
    widgets.
    """
    instance = QtGui.QGuiApplication.instance()
    if instance is None:
        # Qt ends the process when it cannot start, so it is asked first in a
        # child; the tests that need an application then skip with its reason.
        reason = gui_unavailable()
        if reason is not None:
            pytest.skip(reason)
        instance = QtGui.QGuiApplication([])
    return instance


@pytest.fixture(scope='session')
def drawable(application):  # noqa: ARG001 a window needs the QGuiApplication made first
    """Whether a window on this platform plugin can be rendered into

    Answered by making one and asking OpenGL, rather than by guessing from the
    platform's name: the same plugin works on one machine and not on the next.
    """
    context = QtInteractiveContext(size=(64, 64))
    try:
        context.setCurrent()
        try:
            return context.windowsystem.checkSurface()
        finally:
            context.unsetCurrent()
    finally:
        _dispose(context)


@pytest.fixture
def gl(drawable, application):
    """Skip a test that needs to render when nothing here can render"""
    if not drawable:
        pytest.skip(
            "the %r Qt platform plugin gives no drawable GL surface; try "
            "QT_QPA_PLATFORM=xcb" % (application.platformName(),)
        )
    return application


@pytest.fixture
def context_factory(gl):  # noqa: ARG001 requested for its skip where nothing can render
    """Make contexts, each with a window and GL context of its own

    A fresh window per test rather than a shared one: GL state left behind by
    one test is the usual cause of a suite that passes a file at a time and
    fails as a whole.
    """
    made = []

    def factory(cls=None, **named):
        if cls is None:
            cls = QtInteractiveContext
        context = cls(**named)
        made.append(context)
        return context

    yield factory
    for context in made:
        _dispose(context)


def _dispose(context):
    """Shut a context's window down without ending the process

    Through ``OnQuit``, which is the window system's own shutdown -- pointer handed
    back, timer stopped, GL objects released, window closed -- so the tests
    exercise that rather than a second version of it written here.  It ends the
    process only for a context that started the application, and none of these
    did.

    Nothing is retained afterwards.  A context that has quit can be dropped like
    any other object, and a fixture that quietly held its windows for the life
    of the session would be hiding exactly the failure this suite should show.
    """
    context.OnQuit()
