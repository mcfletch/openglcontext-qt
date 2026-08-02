"""Turning Qt input events into OpenGLContext ones

Real ``QKeyEvent`` / ``QMouseEvent`` / ``QWheelEvent`` objects rather than
stand-ins: the translation is almost entirely a matter of which Qt accessor
means what, and a stub proves only that the stub agrees with the test.  The
*window* is a stand-in, because none of this needs one.
"""

import pytest
from OpenGLContext.events.mouseevents import WHEEL_DOWN, WHEEL_UP
from PySide6 import QtCore, QtGui

from OpenGLContext_qt import qtevents

NO_MODIFIER = QtCore.Qt.KeyboardModifier.NoModifier
NO_BUTTON = QtCore.Qt.MouseButton.NoButton
LEFT = QtCore.Qt.MouseButton.LeftButton
RIGHT = QtCore.Qt.MouseButton.RightButton
MIDDLE = QtCore.Qt.MouseButton.MiddleButton


class Widget(object):
    """Stands in for QWindow: the class the mix-in defers to for Qt's own part

    Only the handlers the mix-in chains to need to be here; ``focusOutEvent``
    is the one it does not consume.
    """

    def focusOutEvent(self, event):
        self.chained = True


class Window(qtevents.EventHandlerMixin, Widget):
    """A stand-in for the window the mix-in is normally part of

    Records what reached the engine, and answers the few things the mix-in asks
    of the window it lives on.
    """

    chained = False
    # The window sets this once its context exists; a real one starts False.
    _ready = True
    height = 600
    ratio = 1.0
    warpEcho = False

    def __init__(self, **named):
        self.__dict__.update(named)
        self.processed = []
        self.picks = []
        self.motions = []
        self.recentred = 0
        self.forgotten = 0
        self.picked = 0

    ### the window's side of the protocol
    def devicePixelRatio(self):
        return self.ratio

    def getViewPort(self):
        return (800, self.height)

    def pointerWarpEcho(self, event):
        return self.warpEcho

    def recentrePointer(self):
        self.recentred += 1

    def recordPointerMotion(self, x, y):
        self.motions.append((x, y))

    def forgetPointerOrigin(self):
        self.forgotten += 1

    ### the engine's side
    def ProcessEvent(self, event):
        self.processed.append(event)

    def addPickEvent(self, event):
        self.picks.append(event)

    def triggerPick(self):
        self.picked += 1


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
    window = Window(_ready=False)
    window.keyPressEvent(keyEvent(QtCore.Qt.Key.Key_W, text='w'))
    window.keyReleaseEvent(keyEvent(QtCore.Qt.Key.Key_W,
                                    QtCore.QEvent.Type.KeyRelease, text='w'))
    window.mousePressEvent(mouseEvent(QtCore.QEvent.Type.MouseButtonPress))
    window.mouseReleaseEvent(mouseEvent(QtCore.QEvent.Type.MouseButtonRelease))
    window.mouseMoveEvent(mouseEvent(QtCore.QEvent.Type.MouseMove))
    window.wheelEvent(wheelEvent(qtevents.WHEEL_DETENT))
    assert window.processed == []
    assert window.picks == []
    assert window.picked == 0
    assert window.motions == []


def test_losing_focus_before_the_engine_exists_is_survivable():
    window = Interactive(_ready=False)
    window.focusOutEvent(None)
    assert window.state.cleared == 0
    assert window.chained


# -- keyboard ----------------------------------------------------------------

def test_a_key_press_reaches_the_engine_as_a_key_down():
    window = Window()
    window.keyPressEvent(keyEvent(QtCore.Qt.Key.Key_Escape))
    assert [(event.name, event.state) for event in window.processed] == [
        ('<escape>', 1)]


def test_a_key_release_reaches_the_engine_as_a_key_up():
    window = Window()
    window.keyReleaseEvent(keyEvent(QtCore.Qt.Key.Key_Escape,
                                    QtCore.QEvent.Type.KeyRelease))
    assert [(event.name, event.state) for event in window.processed] == [
        ('<escape>', 0)]


def test_typing_a_character_reports_the_character_as_well_as_the_key():
    """A text field wants what was typed; a binding wants which key it was."""
    window = Window()
    window.keyPressEvent(keyEvent(QtCore.Qt.Key.Key_A, text='A',
                                  modifiers=QtCore.Qt.KeyboardModifier.ShiftModifier))
    kinds = [(event.type, event.name) for event in window.processed]
    assert kinds == [('keyboard', 'a'), ('keypress', 'A')]


def test_an_auto_repeat_release_is_not_a_release():
    """X11 sends a release and a press for every repeat of a held key.

    Reported as real releases, anything watching held keys sees the key let go
    and taken again dozens of times a second, and navigation stutters to a
    halt.
    """
    window = Window()
    window.keyReleaseEvent(keyEvent(QtCore.Qt.Key.Key_W,
                                    QtCore.QEvent.Type.KeyRelease,
                                    text='w', autorepeat=True))
    assert window.processed == []


def test_an_auto_repeat_press_is_another_press():
    """Which is what a held key means to a handler that acts once per press."""
    window = Window()
    window.keyPressEvent(keyEvent(QtCore.Qt.Key.Key_W, text='w', autorepeat=True))
    assert [event.state for event in window.processed if event.type == 'keyboard'] == [1]


@pytest.mark.parametrize('key,name', [
    (QtCore.Qt.Key.Key_Up, '<up>'),
    (QtCore.Qt.Key.Key_PageDown, '<pagedown>'),
    (QtCore.Qt.Key.Key_F5, '<F5>'),
    (QtCore.Qt.Key.Key_Enter, '<return>'),
    (QtCore.Qt.Key.Key_Return, '<return>'),
])
def test_named_keys_use_the_names_bindings_are_written_with(key, name):
    window = Window()
    window.keyPressEvent(keyEvent(key))
    assert window.processed[0].name == name


@pytest.mark.parametrize('key,name', [
    (QtCore.Qt.Key.Key_W, 'w'),
    (QtCore.Qt.Key.Key_7, '7'),
    (QtCore.Qt.Key.Key_Space, ' '),
    (QtCore.Qt.Key.Key_BracketLeft, '['),
    (QtCore.Qt.Key.Key_Minus, '-'),
])
def test_printable_keys_are_named_by_their_unshifted_character(key, name):
    window = Window()
    window.keyPressEvent(keyEvent(key))
    assert window.processed[0].name == name


def test_a_shifted_letter_is_still_the_key_it_is_printed_on():
    """``'w'`` whether or not shift is down: the modifiers are reported
    separately, and a binding that wants shift says so."""
    window = Window()
    window.keyPressEvent(keyEvent(QtCore.Qt.Key.Key_W, text='W',
                                  modifiers=QtCore.Qt.KeyboardModifier.ShiftModifier))
    event = window.processed[0]
    assert event.name == 'w'
    assert event.modifiers == (True, False, False)


def test_the_modifier_triple_is_shift_control_alt_in_that_order():
    window = Window()
    window.keyPressEvent(keyEvent(
        QtCore.Qt.Key.Key_W,
        modifiers=(QtCore.Qt.KeyboardModifier.ControlModifier
                   | QtCore.Qt.KeyboardModifier.AltModifier)))
    assert window.processed[0].modifiers == (False, True, True)


class InputState(object):
    def __init__(self):
        self.cleared = 0

    def clear(self):
        self.cleared += 1


class Interactive(Window):
    """A context that samples held keys, as an interactive one does"""

    def __init__(self, **named):
        super(Interactive, self).__init__(**named)
        self.state = InputState()

    def getInputState(self):
        return self.state


def test_losing_focus_forgets_what_was_held():
    """No key-up arrives for a key that was down when focus went elsewhere.

    Without this the key stays held for the rest of the session, and the camera
    keeps moving with nobody touching the keyboard.
    """
    window = Interactive()
    window.focusOutEvent(None)
    assert window.state.cleared == 1


def test_losing_focus_still_reaches_qt():
    """Qt has its own work to do on focus loss; consuming the event would take
    it away."""
    window = Interactive()
    window.focusOutEvent(None)
    assert window.chained


def test_a_context_that_samples_nothing_survives_losing_focus():
    """A plain QtContext has no movement sampler to clear."""
    window = Window()
    window.focusOutEvent(None)
    assert window.chained


# -- mouse -------------------------------------------------------------------

def test_a_click_becomes_a_pick_event_and_a_pick():
    window = Window()
    window.mousePressEvent(mouseEvent(QtCore.QEvent.Type.MouseButtonPress))
    assert len(window.picks) == 1
    assert window.picks[0].state == 1
    assert window.picked == 1


def test_a_release_reports_the_button_going_up():
    window = Window()
    window.mouseReleaseEvent(mouseEvent(QtCore.QEvent.Type.MouseButtonRelease))
    assert window.picks[0].state == 0


@pytest.mark.parametrize('button,number', [(LEFT, 0), (RIGHT, 1), (MIDDLE, 2)])
def test_buttons_use_the_numbering_the_rest_of_openglcontext_uses(button, number):
    window = Window()
    window.mousePressEvent(mouseEvent(QtCore.QEvent.Type.MouseButtonPress,
                                      button=button))
    assert window.picks[0].button == number


def test_the_pick_point_counts_up_from_the_bottom_of_the_window():
    """OpenGL's origin, not the window system's: y is flipped once, here."""
    window = Window(height=600)
    window.mousePressEvent(mouseEvent(QtCore.QEvent.Type.MouseButtonPress,
                                      x=100, y=150))
    assert window.picks[0].pickPoint == (100, 450)


def test_the_pick_point_is_in_framebuffer_pixels():
    """On a scaled display the window's pixels are not the ones rendered, and a
    pick in window pixels lands somewhere the user did not click."""
    window = Window(height=600, ratio=2.0)
    window.mousePressEvent(mouseEvent(QtCore.QEvent.Type.MouseButtonPress,
                                      x=100, y=150))
    assert window.picks[0].pickPoint == (200, 300)


def test_a_drag_reports_the_buttons_that_are_held():
    window = Window()
    window.mouseMoveEvent(mouseEvent(QtCore.QEvent.Type.MouseMove,
                                     button=NO_BUTTON, buttons=LEFT | RIGHT))
    assert window.picks[0].buttons == (0, 1)


def test_movement_reaches_the_sampler_as_well_as_the_pick_queue():
    """Mouse-look is not picking: a pick event arrives only once the selection
    buffer resolves it, and not at all when picking is off."""
    window = Window(height=600)
    window.mouseMoveEvent(mouseEvent(QtCore.QEvent.Type.MouseMove, x=10, y=20))
    assert window.motions == [(10, 580)]


def test_a_real_movement_puts_a_grabbed_pointer_back_in_the_middle():
    window = Window()
    window.mouseMoveEvent(mouseEvent(QtCore.QEvent.Type.MouseMove))
    assert window.recentred == 1


def test_the_windows_own_warp_is_not_motion_the_user_made():
    """It is exactly the reverse of the movement that caused it: counted, the
    view never turns at all."""
    window = Window(warpEcho=True)
    window.mouseMoveEvent(mouseEvent(QtCore.QEvent.Type.MouseMove))
    assert window.forgotten == 1
    assert window.picks == []
    assert window.picked == 0
    assert window.recentred == 0


def test_the_warp_still_says_where_the_pointer_now_is():
    """Otherwise the next real movement is measured from where the pointer was
    before the window moved it."""
    window = Window(height=600, warpEcho=True)
    window.mouseMoveEvent(mouseEvent(QtCore.QEvent.Type.MouseMove, x=40, y=50))
    assert window.motions == [(40, 550)]


# -- the wheel ---------------------------------------------------------------

def test_a_notch_of_the_wheel_is_a_button_pressed_and_released():
    """No wheel is ever held: a notch is an increment, and everything
    downstream reads it as a button that goes down and straight back up."""
    window = Window()
    window.wheelEvent(wheelEvent(qtevents.WHEEL_DETENT))
    assert [(event.button, event.state) for event in window.picks] == [
        (WHEEL_UP, 1), (WHEEL_UP, 0)]


def test_turning_the_wheel_the_other_way_is_the_other_button():
    window = Window()
    window.wheelEvent(wheelEvent(-qtevents.WHEEL_DETENT))
    assert [event.button for event in window.picks] == [WHEEL_DOWN, WHEEL_DOWN]


def test_several_notches_in_one_report_are_several_notches():
    window = Window()
    window.wheelEvent(wheelEvent(int(qtevents.WHEEL_DETENT * 3)))
    assert len(window.picks) == 6


def test_a_touchpads_fractions_add_up_to_a_notch():
    """A touchpad reports part of a notch at a time; summed, a slow drag
    scrolls once it has asked for a whole one."""
    window = Window()
    for _ in range(4):
        window.wheelEvent(wheelEvent(int(qtevents.WHEEL_DETENT / 4)))
    assert len(window.picks) == 2         # one notch: a press and a release


def test_a_fraction_on_its_own_scrolls_nothing():
    window = Window()
    window.wheelEvent(wheelEvent(int(qtevents.WHEEL_DETENT / 4)))
    assert window.picks == []


def test_turning_back_drops_what_was_carried():
    """Jitter over a touchpad must not accumulate into a notch in the direction
    it is not moving."""
    window = Window()
    window.wheelEvent(wheelEvent(int(qtevents.WHEEL_DETENT * 0.75)))
    window.wheelEvent(wheelEvent(-int(qtevents.WHEEL_DETENT * 0.75)))
    assert window.picks == []


def test_a_report_of_nothing_scrolls_nothing():
    window = Window()
    window.wheelEvent(wheelEvent(0))
    assert window.picks == []
    assert window.picked == 1        # the pick pass still runs; there is just nothing in it
