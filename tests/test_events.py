"""Turning Qt input events into OpenGLContext ones

Real ``QKeyEvent`` / ``QMouseEvent`` / ``QWheelEvent`` objects rather than
stand-ins: the translation is almost entirely a matter of which Qt accessor
means what, and a stub proves only that the stub agrees with the test.  The
window system's handlers are the real ones; the *window* and the context are
stand-ins, because none of this needs a window.
"""

import pytest
from OpenGLContext.context import Context
from OpenGLContext.events.eventhandlermixin import HeldKeyMixin
from OpenGLContext.events.mouseevents import WHEEL_DOWN, WHEEL_UP
from PySide6 import QtCore, QtGui

from OpenGLContext_qt import qtevents
from OpenGLContext_qt.windowsystem import QtWindow, QtWindowSystem

NO_MODIFIER = QtCore.Qt.KeyboardModifier.NoModifier
NO_BUTTON = QtCore.Qt.MouseButton.NoButton
LEFT = QtCore.Qt.MouseButton.LeftButton
RIGHT = QtCore.Qt.MouseButton.RightButton
MIDDLE = QtCore.Qt.MouseButton.MiddleButton


class InputState(object):
    def __init__(self):
        self.cleared = 0

    def clear(self):
        self.cleared += 1


class Host(HeldKeyMixin):
    """The part of a context the window system calls, recording what it is told

    The held-key tracking is the real :class:`HeldKeyMixin`, and a key it sends
    goes back through the window system as a context's does.
    """

    emitKey = Context.emitKey
    height = 600

    def __init__(self, height=600):
        self.height = height
        self.processed = []
        self.picks = []
        self.motions = []
        self.forgotten = 0
        self.picked = 0
        self.state = InputState()

    def getViewPort(self):
        return (800, self.height)

    def getInputState(self):
        return self.state

    def recordPointerMotion(self, x, y):
        self.motions.append((x, y))

    def forgetPointerOrigin(self):
        self.forgotten += 1

    def ProcessEvent(self, event):
        self.processed.append(event)

    def addPickEvent(self, event):
        self.picks.append(event)

    def triggerPick(self):
        self.picked += 1


class Window(object):
    """Stands in for the QWindow: the display scaling is all these ask of it"""

    def __init__(self, ratio=1.0):
        self.ratio = ratio

    def devicePixelRatio(self):
        return self.ratio


class System(QtWindowSystem):
    """The Qt window system, with the pointer warp answered rather than made

    Warping the pointer needs a window on a screen, and what is under test
    here is what the handlers do with the answer; the warp itself is tested
    against a real window in ``test_context_gl.py``.
    """

    warpEcho = False

    def __init__(self, ready=True, height=600, ratio=1.0, warpEcho=False):
        host = Host(height=height)
        super().__init__(host)
        host.windowsystem = self
        self.window = Window(ratio)
        self.engineReady = ready
        self.warpEcho = warpEcho
        self.recentred = 0

    def pointerWarpEcho(self, event):  # noqa: ARG002 QtWindowSystem.pointerWarpEcho's signature
        return self.warpEcho

    def recentrePointer(self):
        self.recentred += 1


def keyEvent(key, kind=QtCore.QEvent.Type.KeyPress, text='', modifiers=NO_MODIFIER,
             autorepeat=False):
    return QtGui.QKeyEvent(kind, key, modifiers, 0, 0, 0, text, autorepeat)


def mouseEvent(kind, x=100, y=200, button=LEFT, buttons=None, modifiers=NO_MODIFIER):
    point = QtCore.QPointF(x, y)
    if buttons is None:
        buttons = button
    return QtGui.QMouseEvent(kind, point, point, button, buttons, modifiers)


def wheelEvent(rotation, x=10, y=20):
    point = QtCore.QPointF(x, y)
    return QtGui.QWheelEvent(
        point, point, QtCore.QPoint(0, 0), QtCore.QPoint(0, rotation),
        NO_BUTTON, NO_MODIFIER, QtCore.Qt.ScrollPhase.NoScrollPhase, False,
    )


# -- input that arrives too early ---------------------------------------------

def test_input_before_the_engine_exists_is_dropped():
    """Qt hands a shown window whatever the user is doing, and the window is on
    screen before ``Context.__init__`` has built the event managers.

    The release of the key that launched the program is the usual one: it
    arrives during start-up, and dispatching it reaches a context that has
    nothing to dispatch it with.
    """
    system = System(ready=False)
    system.onKeyPress(keyEvent(QtCore.Qt.Key.Key_W, text='w'))
    system.onKeyRelease(keyEvent(QtCore.Qt.Key.Key_W,
                                 QtCore.QEvent.Type.KeyRelease, text='w'))
    system.onMousePress(mouseEvent(QtCore.QEvent.Type.MouseButtonPress))
    system.onMouseRelease(mouseEvent(QtCore.QEvent.Type.MouseButtonRelease))
    system.onMouseMove(mouseEvent(QtCore.QEvent.Type.MouseMove))
    system.onWheel(wheelEvent(qtevents.WHEEL_DETENT))
    assert system.context.processed == []
    assert system.context.picks == []
    assert system.context.picked == 0
    assert system.context.motions == []


def test_losing_focus_before_the_engine_exists_is_survivable():
    system = System(ready=False)
    system.onFocusOut(None)
    assert system.context.state.cleared == 0


# -- keyboard ----------------------------------------------------------------

def test_a_key_press_reaches_the_engine_as_a_key_down():
    system = System()
    system.onKeyPress(keyEvent(QtCore.Qt.Key.Key_Escape))
    assert [(event.name, event.state) for event in system.context.processed] == [
        ('<escape>', 1)]


def test_a_key_release_reaches_the_engine_as_a_key_up():
    system = System()
    system.onKeyRelease(keyEvent(QtCore.Qt.Key.Key_Escape,
                                 QtCore.QEvent.Type.KeyRelease))
    assert [(event.name, event.state) for event in system.context.processed] == [
        ('<escape>', 0)]


def test_typing_a_character_reports_the_character_as_well_as_the_key():
    """A text field wants what was typed; a binding wants which key it was."""
    system = System()
    system.onKeyPress(keyEvent(QtCore.Qt.Key.Key_A, text='A',
                               modifiers=QtCore.Qt.KeyboardModifier.ShiftModifier))
    kinds = [(event.type, event.name) for event in system.context.processed]
    assert kinds == [('keyboard', 'a'), ('keypress', 'A')]


def test_an_auto_repeat_release_is_not_a_release():
    """X11 sends a release and a press for every repeat of a held key.

    Reported as real releases, anything watching held keys sees the key let go
    and taken again dozens of times a second, and navigation stutters to a
    halt.
    """
    system = System()
    system.onKeyRelease(keyEvent(QtCore.Qt.Key.Key_W,
                                 QtCore.QEvent.Type.KeyRelease,
                                 text='w', autorepeat=True))
    assert system.context.processed == []


def test_an_auto_repeat_press_is_another_press():
    """Which is what a held key means to a handler that acts once per press."""
    system = System()
    system.onKeyPress(keyEvent(QtCore.Qt.Key.Key_W, text='w', autorepeat=True))
    assert [event.state for event in system.context.processed if event.type == 'keyboard'] == [1]


@pytest.mark.parametrize('key,name', [
    (QtCore.Qt.Key.Key_Up, '<up>'),
    (QtCore.Qt.Key.Key_PageDown, '<pagedown>'),
    (QtCore.Qt.Key.Key_F5, '<F5>'),
    (QtCore.Qt.Key.Key_Enter, '<return>'),
    (QtCore.Qt.Key.Key_Return, '<return>'),
])
def test_named_keys_use_the_names_bindings_are_written_with(key, name):
    system = System()
    system.onKeyPress(keyEvent(key))
    assert system.context.processed[0].name == name


@pytest.mark.parametrize('key,name', [
    (QtCore.Qt.Key.Key_W, 'w'),
    (QtCore.Qt.Key.Key_7, '7'),
    (QtCore.Qt.Key.Key_Space, ' '),
    (QtCore.Qt.Key.Key_BracketLeft, '['),
    (QtCore.Qt.Key.Key_Minus, '-'),
])
def test_printable_keys_are_named_by_their_unshifted_character(key, name):
    system = System()
    system.onKeyPress(keyEvent(key))
    assert system.context.processed[0].name == name


def test_a_shifted_letter_is_still_the_key_it_is_printed_on():
    """``'w'`` whether or not shift is down: the modifiers are reported
    separately, and a binding that wants shift says so."""
    system = System()
    system.onKeyPress(keyEvent(QtCore.Qt.Key.Key_W, text='W',
                               modifiers=QtCore.Qt.KeyboardModifier.ShiftModifier))
    event = system.context.processed[0]
    assert event.name == 'w'
    assert event.modifiers == (True, False, False)


def test_the_modifier_triple_is_shift_control_alt_in_that_order():
    system = System()
    system.onKeyPress(keyEvent(
        QtCore.Qt.Key.Key_W,
        modifiers=(QtCore.Qt.KeyboardModifier.ControlModifier
                   | QtCore.Qt.KeyboardModifier.AltModifier)))
    assert system.context.processed[0].modifiers == (False, True, True)


def test_losing_focus_forgets_what_was_held():
    """No key-up arrives for a key that was down when focus went elsewhere.

    Without this the key stays held for the rest of the session, and the camera
    keeps moving with nobody touching the keyboard.
    """
    system = System()
    system.onFocusOut(None)
    assert system.context.state.cleared == 1


def test_losing_focus_sends_the_release_qt_never_will():
    system = System()
    system.onKeyPress(keyEvent(QtCore.Qt.Key.Key_W, text='w'))
    system.context.processed = []
    system.onFocusOut(None)
    assert system.context.heldKeys() == {}
    assert [(event.name, event.state) for event in system.context.processed] == [
        ('w', 0)]


@pytest.mark.usefixtures('application')
def test_losing_focus_reaches_the_window_system_and_still_reaches_qt(monkeypatch):
    """Qt has its own work to do on focus loss; consuming the event would take
    it away.  A real QtWindow, since what is under test is its override."""
    chained = []
    monkeypatch.setattr(QtGui.QWindow, 'focusOutEvent',
                        lambda _window, event: chained.append(event))
    system = System()
    window = QtWindow(system)
    try:
        event = QtGui.QFocusEvent(QtCore.QEvent.Type.FocusOut)
        window.focusOutEvent(event)
        assert system.context.state.cleared == 1
        assert chained == [event]
    finally:
        window.destroy()


# -- mouse -------------------------------------------------------------------

def test_a_click_becomes_a_pick_event_and_a_pick():
    system = System()
    system.onMousePress(mouseEvent(QtCore.QEvent.Type.MouseButtonPress))
    assert len(system.context.picks) == 1
    assert system.context.picks[0].state == 1
    assert system.context.picked == 1


def test_a_release_reports_the_button_going_up():
    system = System()
    system.onMouseRelease(mouseEvent(QtCore.QEvent.Type.MouseButtonRelease))
    assert system.context.picks[0].state == 0


@pytest.mark.parametrize('button,number', [(LEFT, 0), (RIGHT, 1), (MIDDLE, 2)])
def test_buttons_use_the_numbering_the_rest_of_openglcontext_uses(button, number):
    system = System()
    system.onMousePress(mouseEvent(QtCore.QEvent.Type.MouseButtonPress,
                                   button=button))
    assert system.context.picks[0].button == number


def test_the_pick_point_counts_up_from_the_bottom_of_the_window():
    """OpenGL's origin, not the window system's: y is flipped once, here."""
    system = System(height=600)
    system.onMousePress(mouseEvent(QtCore.QEvent.Type.MouseButtonPress,
                                   x=100, y=150))
    assert system.context.picks[0].pickPoint == (100, 450)


def test_the_pick_point_is_in_framebuffer_pixels():
    """On a scaled display the window's pixels are not the ones rendered, and a
    pick in window pixels lands somewhere the user did not click."""
    system = System(height=600, ratio=2.0)
    system.onMousePress(mouseEvent(QtCore.QEvent.Type.MouseButtonPress,
                                   x=100, y=150))
    assert system.context.picks[0].pickPoint == (200, 300)


def test_a_drag_reports_the_buttons_that_are_held():
    system = System()
    system.onMouseMove(mouseEvent(QtCore.QEvent.Type.MouseMove,
                                  button=NO_BUTTON, buttons=LEFT | RIGHT))
    assert system.context.picks[0].buttons == (0, 1)


def test_movement_reaches_the_sampler_as_well_as_the_pick_queue():
    """Mouse-look is not picking: a pick event arrives only once the selection
    buffer resolves it, and not at all when picking is off."""
    system = System(height=600)
    system.onMouseMove(mouseEvent(QtCore.QEvent.Type.MouseMove, x=10, y=20))
    assert system.context.motions == [(10, 580)]


def test_a_real_movement_puts_a_grabbed_pointer_back_in_the_middle():
    system = System()
    system.onMouseMove(mouseEvent(QtCore.QEvent.Type.MouseMove))
    assert system.recentred == 1


def test_the_windows_own_warp_is_not_motion_the_user_made():
    """It is exactly the reverse of the movement that caused it: counted, the
    view never turns at all."""
    system = System(warpEcho=True)
    system.onMouseMove(mouseEvent(QtCore.QEvent.Type.MouseMove))
    assert system.context.forgotten == 1
    assert system.context.picks == []
    assert system.context.picked == 0
    assert system.recentred == 0


def test_the_warp_still_says_where_the_pointer_now_is():
    """Otherwise the next real movement is measured from where the pointer was
    before the window moved it."""
    system = System(height=600, warpEcho=True)
    system.onMouseMove(mouseEvent(QtCore.QEvent.Type.MouseMove, x=40, y=50))
    assert system.context.motions == [(40, 550)]


# -- the wheel ---------------------------------------------------------------

def test_a_notch_of_the_wheel_is_a_button_pressed_and_released():
    """No wheel is ever held: a notch is an increment, and everything
    downstream reads it as a button that goes down and straight back up."""
    system = System()
    system.onWheel(wheelEvent(qtevents.WHEEL_DETENT))
    assert [(event.button, event.state) for event in system.context.picks] == [
        (WHEEL_UP, 1), (WHEEL_UP, 0)]


def test_turning_the_wheel_the_other_way_is_the_other_button():
    system = System()
    system.onWheel(wheelEvent(-qtevents.WHEEL_DETENT))
    assert [event.button for event in system.context.picks] == [WHEEL_DOWN, WHEEL_DOWN]


def test_several_notches_in_one_report_are_several_notches():
    system = System()
    system.onWheel(wheelEvent(int(qtevents.WHEEL_DETENT * 3)))
    assert len(system.context.picks) == 6


def test_a_touchpads_fractions_add_up_to_a_notch():
    """A touchpad reports part of a notch at a time; summed, a slow drag
    scrolls once it has asked for a whole one."""
    system = System()
    for _ in range(4):
        system.onWheel(wheelEvent(int(qtevents.WHEEL_DETENT / 4)))
    assert len(system.context.picks) == 2         # one notch: a press and a release


def test_a_fraction_on_its_own_scrolls_nothing():
    system = System()
    system.onWheel(wheelEvent(int(qtevents.WHEEL_DETENT / 4)))
    assert system.context.picks == []


def test_turning_back_drops_what_was_carried():
    """Jitter over a touchpad must not accumulate into a notch in the direction
    it is not moving."""
    system = System()
    system.onWheel(wheelEvent(int(qtevents.WHEEL_DETENT * 0.75)))
    system.onWheel(wheelEvent(-int(qtevents.WHEEL_DETENT * 0.75)))
    assert system.context.picks == []


def test_a_report_of_nothing_scrolls_nothing():
    system = System()
    system.onWheel(wheelEvent(0))
    assert system.context.picks == []
    assert system.context.picked == 1        # the pick pass still runs; there is just nothing in it
