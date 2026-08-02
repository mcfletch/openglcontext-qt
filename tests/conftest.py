"""Fixtures for the Qt backend's tests

The GL tests render real frames through a real window, because a Qt context
that has been mocked out proves only that the mocks agree with each other --
and the failures this backend is most likely to have (a surface format the
driver will not give, a window with no drawable surface, a viewport that
ignores display scaling) are all invisible without one.

They are skipped, with a reason that says what to do about it, when the Qt
platform plugin in use cannot give a window a drawable GL surface.
"""

import pytest
from PySide6 import QtGui


@pytest.fixture(scope='session')
def application():
    """The one QGuiApplication the whole session shares

    Qt allows exactly one, and it must exist before any window.  The bare
    ``QGuiApplication`` rather than a ``QApplication``, because that is all the
    backend itself requires -- only ``QtContext.container`` needs widgets.
    """
    instance = QtGui.QGuiApplication.instance()
    if instance is None:
        instance = QtGui.QGuiApplication([])
    return instance


@pytest.fixture(scope='session')
def drawable(application):
    """Whether a window on this platform plugin can be rendered into

    Answered by making one and asking OpenGL, rather than by guessing from the
    platform's name: the same plugin works on one machine and not on the next.
    """
    from OpenGLContext_qt.qtcontext import QtInteractiveContext

    context = QtInteractiveContext(size=(64, 64))
    try:
        context.setCurrent()
        try:
            return context.checkSurface()
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
def context_factory(gl):
    """Make contexts, each with a window and GL context of its own

    A fresh window per test rather than a shared one: GL state left behind by
    one test is the usual cause of a suite that passes a file at a time and
    fails as a whole.
    """
    made = []

    def factory(cls=None, **named):
        if cls is None:
            from OpenGLContext_qt.qtcontext import QtInteractiveContext as cls
        context = cls(**named)
        made.append(context)
        return context

    yield factory
    for context in made:
        _dispose(context)


def _dispose(context):
    """Shut a context's window down without ending the process

    Through ``OnQuit``, which is the backend's own shutdown -- pointer handed
    back, timer stopped, GL objects released, window closed -- so the tests
    exercise that rather than a second version of it written here.  It ends the
    process only for a context that started the application, and none of these
    did.

    Nothing is retained afterwards.  A context that has quit can be dropped like
    any other object, and a fixture that quietly held its windows for the life
    of the session would be hiding exactly the failure this suite should show.
    """
    context.OnQuit()
