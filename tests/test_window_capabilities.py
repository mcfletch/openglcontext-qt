"""The window-level capabilities every OpenGLContext backend offers.

A project on Qt should be choosing a window system, not a subset of the engine,
so this backend is held to the same contract as the ones in the engine's own
distribution: pointer capture for mouse-look, full screen at run time, and a
report of what the swap interval can be told to do.

Where a Qt limit is real it is a *report* rather than a silence: `applyVSync`
answers False because the interval is part of a surface format settled when the
context is created, and a caller that is told can say so.

See `plans/BACKEND-PARITY.md` in the OpenGLContext distribution.
"""

import pytest
from PySide6 import QtCore, QtGui

from OpenGLContext.context import Context
from OpenGLContext_qt.qtcontext import QtContext


class TestTheContractIsMet:
    """The methods the engine's base class declares, answered here."""

    @pytest.mark.parametrize('capability', [
        'setPointerCapture', 'setFullscreen', 'applyVSync',
    ])
    def test_the_backend_answers_for_itself(self, capability):
        assert capability in QtContext.__dict__, (
            'Qt inherits the base answer for %s' % (capability,))

    @pytest.mark.parametrize('capability', [
        'setPointerCapture', 'setFullscreen', 'applyVSync',
    ])
    def test_the_base_class_declares_it(self, capability):
        assert callable(getattr(Context, capability, None))


class TestFullScreen:
    def test_a_window_can_fill_the_screen(self, context_factory):
        context = context_factory()
        assert context.setFullscreen(True) is True
        assert context.windowState() & QtCore.Qt.WindowState.WindowFullScreen

    def test_and_come_back_from_it(self, context_factory):
        context = context_factory()
        context.setFullscreen(True)
        assert context.setFullscreen(False) is True
        assert not (context.windowState()
                    & QtCore.Qt.WindowState.WindowFullScreen)

    def test_asking_for_what_it_already_is_is_no_work(self, context_factory):
        context = context_factory()
        assert context.setFullscreen(False) is True
        assert not (context.windowState()
                    & QtCore.Qt.WindowState.WindowFullScreen)

    def test_the_gl_context_survives_the_trip(self, context_factory):
        """Everything the engine has uploaded lives in it."""
        context = context_factory()
        before = context.glContext
        context.setFullscreen(True)
        context.setFullscreen(False)
        assert context.glContext is before

    def test_a_settings_change_is_applied(self, context_factory, monkeypatch):
        context = context_factory()
        context.contextDefinition.fullscreen = True
        context.settingsChanged()
        assert context.windowState() & QtCore.Qt.WindowState.WindowFullScreen


class TestVSync:
    def test_it_reports_that_a_live_context_cannot_be_changed(self,
                                                              context_factory):
        context = context_factory()
        assert context.applyVSync() is False

    def test_a_changed_setting_is_said_out_loud(self, context_factory, caplog):
        context = context_factory(vsync=True)
        context.contextDefinition.vsync = False
        with caplog.at_level('INFO'):
            context.applyVSync()
        assert 'vsync' in caplog.text.lower()

    def test_an_unchanged_setting_says_nothing(self, context_factory, caplog):
        context = context_factory(vsync=True)
        with caplog.at_level('INFO'):
            context.applyVSync()
        assert 'takes effect in a new window' not in caplog.text


class TestHeldKeys:
    """No key-up arrives for a key that was down when focus went elsewhere."""

    def _press(self, context, key=QtCore.Qt.Key.Key_W, repeat=False):
        return QtGui.QKeyEvent(QtCore.QEvent.Type.KeyPress, key,
                               QtCore.Qt.KeyboardModifier.NoModifier, 'w',
                               repeat)

    def test_a_key_that_goes_down_is_held(self, context_factory):
        context = context_factory()
        context.keyPressEvent(self._press(context))
        assert int(QtCore.Qt.Key.Key_W) in context.heldKeys()

    def test_a_key_that_comes_up_is_not(self, context_factory):
        context = context_factory()
        context.keyPressEvent(self._press(context))
        context.keyReleaseEvent(QtGui.QKeyEvent(
            QtCore.QEvent.Type.KeyRelease, QtCore.Qt.Key.Key_W,
            QtCore.Qt.KeyboardModifier.NoModifier, 'w'))
        assert context.heldKeys() == {}

    def test_losing_focus_sends_the_release_qt_never_will(self, context_factory):
        context = context_factory()
        watcher = _Watcher()
        # Held by the test, deliberately: handlers are weakly referenced, and
        # one with no other reference to it dies before it is ever called.
        context.addEventHandler('keyboard', name='w', state=0,
                                modifiers=(0, 0, 0), function=watcher.saw)
        context.keyPressEvent(self._press(context))
        context.focusOutEvent(QtGui.QFocusEvent(
            QtCore.QEvent.Type.FocusOut))
        assert context.heldKeys() == {}
        assert watcher.events, 'the key stayed down for the rest of the session'

    def test_qts_own_repeat_stops_the_synthetic_one(self, context_factory):
        context = context_factory()
        context.keyPressEvent(self._press(context))
        assert context._nativeRepeat is False
        context.keyPressEvent(self._press(context, repeat=True))
        assert context._nativeRepeat is True


class _Watcher:
    """Something for a weakly-referenced handler to be a method of."""

    def __init__(self):
        self.events = []

    def saw(self, event):
        self.events.append(event)


class TestTheLoopClosesItsJournals:
    def test_the_telemetry_is_stopped_with_the_loop(self, context_factory,
                                                    monkeypatch):
        """A session that ended badly is exactly the one worth reading."""
        context = context_factory()
        stopped = []
        monkeypatch.setattr(type(context), 'stopTelemetry',
                            lambda self, reason: stopped.append(reason))
        application = QtGui.QGuiApplication.instance()
        monkeypatch.setattr(type(application), 'exec', lambda self: 0)
        context.MainLoop()
        assert stopped == ['mainloop-ended']
