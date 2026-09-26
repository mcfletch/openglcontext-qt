"""OpenGLContext events built from Qt's input events

The event classes, key table and modifier reading the Qt window system
(:mod:`OpenGLContext_qt.windowsystem`) builds its events with.  Positions are
handed to the event classes in framebuffer pixels with y counting downward;
each counts y upward from the bottom, as everything downstream of the context
does.
"""

from typing import Any, Optional

from OpenGLContext.events import keyboardevents, mouseevents
from OpenGLContext.events.mouseevents import WHEEL_UP
from PySide6 import QtCore

#: What Qt reports for one notch of a conventional mouse wheel: rotation is
#: given in eighths of a degree and a notch turns the wheel 15 degrees.  A
#: high-resolution wheel or a touchpad reports smaller amounts, which are summed
#: until they make a notch (see
#: :meth:`OpenGLContext_qt.windowsystem.QtWindowSystem.wheelNotches`).
WHEEL_DETENT = 120.0

#: Mouse buttons in the X11 numbering the whole of OpenGLContext uses.  The
#: wheel is buttons 3 and 4 there, which is why the middle button is 2 rather
#: than the 1 its position might suggest.
BUTTON_MAPPING = (
    (0, QtCore.Qt.MouseButton.LeftButton),
    (1, QtCore.Qt.MouseButton.RightButton),
    (2, QtCore.Qt.MouseButton.MiddleButton),
)


def modifiersOf(qtEvent: Any) -> tuple[int, int, int]:
    """The shift, control and alt triple a Qt event was delivered with

    A function rather than a method on the event classes, because the window
    system reads it too: a key it has to *hold* is remembered with the modifiers its
    press carried, so the release focus loss never delivered matches the
    binding the press matched.
    """
    modifiers = qtEvent.modifiers()
    return (
        bool(modifiers & QtCore.Qt.KeyboardModifier.ShiftModifier),
        bool(modifiers & QtCore.Qt.KeyboardModifier.ControlModifier),
        bool(modifiers & QtCore.Qt.KeyboardModifier.AltModifier),
    )


def nameForKey(key: Any, text: str = '') -> str:
    """The OpenGLContext name of a Qt key code

    Split out from the event so a key transition the engine has to *make* --
    the release focus loss never delivered -- is named exactly as the press
    was, and matches the binding the press matched.
    """
    name = KEYBOARD_MAPPING.get(key)
    if name is not None:
        return str(name)
    if 0x20 <= key <= 0x7E:
        return chr(key).lower()
    return text or '<unknown-%d>' % (key,)


class QtXEvent(object):
    """Base class for the Qt-specific event classes

    Holds the translations from Qt's way of describing an input event to
    OpenGLContext's: the modifier triple, the button numbering and the key
    names.
    """

    def _getModifiers(self, qtEvent: Any) -> tuple[int, int, int]:
        """The shift, control and alt triple for a Qt event"""
        return modifiersOf(qtEvent)

    def _getButton(self, qtEvent: Any) -> Optional[int]:
        """The button this event is about, or None for one we do not model"""
        button = qtEvent.button()
        for local, marker in BUTTON_MAPPING:
            if button == marker:
                return local
        return None

    def _getButtons(self, qtEvent: Any) -> tuple[int, ...]:
        """Every button currently held, as OpenGLContext numbers them"""
        held = qtEvent.buttons()
        return tuple(local for local, marker in BUTTON_MAPPING if held & marker)

    def _getName(self, qtEvent: Any) -> str:
        """The OpenGLContext name of the key a Qt key event is about.

        Printable keys are named by their unshifted character in lower case, so
        a binding reads ``'w'`` whether or not shift is down -- the modifiers
        are reported separately and a binding that wants shift says so.
        """
        return nameForKey(int(qtEvent.key()), qtEvent.text())


class QtMouseButtonEvent(QtXEvent, mouseevents.MouseButtonEvent):
    """Qt-specific mouse-button event"""

    def __init__(self, context: Any, qtEvent: Any, x: float, y: float,
                 state: int = 0) -> None:
        super(QtMouseButtonEvent, self).__init__()
        if hasattr(context, "currentPass"):
            self.renderingPass = context.currentPass
        self.modifiers = self._getModifiers(qtEvent)
        button = self._getButton(qtEvent)
        if button is not None:
            self.button = button
        self.state = state
        self.pickPoint = x, context.getViewPort()[1] - y


class QtWheelEvent(QtXEvent, mouseevents.MouseButtonEvent):
    """One notch of the wheel, as the press and release of a button

    Separate from :class:`QtMouseButtonEvent` because Qt's wheel event names no
    button at all: the button is which way the wheel turned, which the caller
    has already worked out.
    """

    def __init__(self, context: Any, qtEvent: Any, x: float, y: float,
                 button: int = WHEEL_UP, state: int = 0) -> None:
        super(QtWheelEvent, self).__init__()
        if hasattr(context, "currentPass"):
            self.renderingPass = context.currentPass
        self.modifiers = self._getModifiers(qtEvent)
        self.button = button
        self.state = state
        self.pickPoint = x, context.getViewPort()[1] - y


class QtMouseMoveEvent(QtXEvent, mouseevents.MouseMoveEvent):
    """Qt-specific mouse-movement event"""

    def __init__(self, context: Any, qtEvent: Any, x: float,
                 y: float) -> None:
        super(QtMouseMoveEvent, self).__init__()
        if hasattr(context, "currentPass"):
            self.renderingPass = context.currentPass
        self.modifiers = self._getModifiers(qtEvent)
        self.buttons = self._getButtons(qtEvent)
        self.pickPoint = x, context.getViewPort()[1] - y


class QtKeyboardEvent(QtXEvent, keyboardevents.KeyboardEvent):
    """Qt-specific key-transition event"""

    def __init__(self, context: Any, qtEvent: Any, state: int = 0) -> None:
        super(QtKeyboardEvent, self).__init__()
        if hasattr(context, "currentPass"):
            self.renderingPass = context.currentPass
        self.modifiers = self._getModifiers(qtEvent)
        self.name = self._getName(qtEvent)
        self.state = state


class QtKeypressEvent(QtXEvent, keyboardevents.KeypressEvent):
    """Qt-specific character-input event

    Named by the character Qt produced rather than by the key, so shift and the
    keyboard layout are already applied: this is what a text field types.
    """

    def __init__(self, context: Any, qtEvent: Any) -> None:
        super(QtKeypressEvent, self).__init__()
        if hasattr(context, "currentPass"):
            self.renderingPass = context.currentPass
        self.modifiers = self._getModifiers(qtEvent)
        self.name = qtEvent.text()


def _keyboardMapping() -> dict[Any, str]:
    """The named (non-printable) keys, keyed by Qt's integer key code"""
    Key = QtCore.Qt.Key
    mapping = {
        Key.Key_Tab: "<tab>",
        Key.Key_Backspace: "<backspace>",
        Key.Key_Return: "<return>",
        Key.Key_Enter: "<return>",
        Key.Key_Escape: "<escape>",
        Key.Key_Insert: "<insert>",
        Key.Key_Delete: "<delete>",
        Key.Key_Pause: "<pause>",
        Key.Key_Print: "<print>",
        Key.Key_Home: "<home>",
        Key.Key_End: "<end>",
        Key.Key_Left: "<left>",
        Key.Key_Right: "<right>",
        Key.Key_Up: "<up>",
        Key.Key_Down: "<down>",
        Key.Key_PageUp: "<pageup>",
        Key.Key_PageDown: "<pagedown>",
        Key.Key_Shift: "<shift>",
        Key.Key_Control: "<ctrl>",
        Key.Key_Alt: "<alt>",
        Key.Key_CapsLock: "<capslock>",
        Key.Key_NumLock: "<numlock>",
        Key.Key_ScrollLock: "<scroll>",
        Key.Key_Back: "<back>",
        Key.Key_Forward: "<forward>",
    }
    for index in range(1, 36):
        mapping[getattr(Key, "Key_F%s" % (index,))] = "<F%s>" % (index,)
    return {int(key): name for key, name in mapping.items()}


#: Qt key code (as an int) to the name OpenGLContext bindings use.  Printable
#: keys are absent and named from their character; see ``QtXEvent._getName``.
#: Space is one of them, and comes out as ``" "``, which is how every backend
#: spells it.
KEYBOARD_MAPPING = _keyboardMapping()

__all__ = [
    'KEYBOARD_MAPPING',
    'QtKeyboardEvent',
    'QtKeypressEvent',
    'QtMouseButtonEvent',
    'QtMouseMoveEvent',
    'QtWheelEvent',
    'QtXEvent',
    'WHEEL_DETENT',
    'modifiersOf',
    'nameForKey',
]
