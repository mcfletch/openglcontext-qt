"""Translation from Qt input events to their OpenGLContext equivalents

The mix-in here is listed *before* :class:`~PySide6.QtGui.QWindow` in
:class:`OpenGLContext_qt.qtcontext.QtContext`, so the ``*Event`` methods below
are the ones Qt calls: a Qt window's virtual event handlers are its callback
registration, where another toolkit has an explicit ``set*Callback``.

Coordinates arrive in Qt's logical window pixels with y counting downward.
Everything downstream of the context works in *framebuffer* pixels with y
counting upward from the bottom, and the two differ on any scaled display, so
the conversion happens once, here.
"""

from typing import TYPE_CHECKING, Any, Dict, Optional, Tuple

from OpenGLContext.events import eventhandlermixin, keyboardevents, mouseevents
from OpenGLContext.events.mouseevents import WHEEL_UP
from OpenGLContext.events.wheel import WheelNotches
from PySide6 import QtCore

#: What Qt reports for one notch of a conventional mouse wheel: rotation is
#: given in eighths of a degree and a notch turns the wheel 15 degrees.  A
#: high-resolution wheel or a touchpad reports smaller amounts, which are summed
#: until they make a notch (see :meth:`EventHandlerMixin._wheelNotches`).
WHEEL_DETENT = 120.0

#: Mouse buttons in the X11 numbering the whole of OpenGLContext uses.  The
#: wheel is buttons 3 and 4 there, which is why the middle button is 2 rather
#: than the 1 its position might suggest.
BUTTON_MAPPING = (
    (0, QtCore.Qt.MouseButton.LeftButton),
    (1, QtCore.Qt.MouseButton.RightButton),
    (2, QtCore.Qt.MouseButton.MiddleButton),
)


class EventHandlerMixin(eventhandlermixin.EventHandlerMixin):
    """Qt-specific event handler mix-in

    Converts Qt's window events into the OpenGLContext events the rest of the
    engine dispatches, and feeds the movement sampler the pointer motion that
    mouse-look needs but picking never delivers.

    The window this is mixed into supplies ``devicePixelRatio``,
    ``recentrePointer`` and ``pointerWarpEcho``; see
    :class:`OpenGLContext_qt.qtcontext.QtContext`.
    """

    #: Set by the window once the engine behind it exists; see
    #: :class:`OpenGLContext_qt.qtcontext.QtContext`.
    _ready = False

    if TYPE_CHECKING:
        # What this mix-in needs of the classes beside it, declared for a
        # checker and nothing else: `QtContext` mixes it with `Context` and
        # `QWindow`, which is where each of these actually comes from, and a
        # base of either name here would put a second copy in the MRO.
        def addPickEvent(self, event: Any) -> None: ...
        def triggerPick(self) -> None: ...
        def getViewPort(self) -> Tuple[int, int]: ...
        def recentrePointer(self) -> None: ...
        #: Takes the event rather than a point, unlike the other backends'
        #: method of this name: Qt answers a warp in *global* coordinates,
        #: which is what `QtContext.recentrePointer` recorded.
        def pointerWarpEcho(self, event: Any) -> bool: ...
        #: QWindow's, in logical pixels per device pixel.
        def devicePixelRatio(self) -> float: ...

    def engineReady(self) -> bool:
        """Whether the engine behind this window can be told about input yet

        **A window is on screen before its context is finished.**  Qt hands a
        shown window whatever the user is doing from that moment, and the event
        managers that dispatch a keystroke are not built until
        ``Context.__init__`` has run -- so an event arriving in the gap would
        reach a context with nothing to dispatch it with, and the failure would
        surface inside a Qt virtual call where it reads as a Qt problem.
        """
        return self._ready

    ### KEYBOARD interactions
    def keyPressEvent(self, event: Any) -> None:
        """Convert a key-down to a context-style event.

        An auto-repeat is passed through as another key-down, which is what a
        held key means to a handler that acts once per press.
        """
        if not self.engineReady():
            return
        if event.isAutoRepeat():
            self.noteNativeRepeat()     # Qt supplies them; do not double up
        self.noteKeyDown(int(event.key()), _modifiersOf(event))
        self.ProcessEvent(QtKeyboardEvent(self, event, 1))
        if event.text():
            self.ProcessEvent(QtKeypressEvent(self, event))

    def keyReleaseEvent(self, event: Any) -> None:
        """Convert a key-up to a context-style event.

        **An auto-repeat release is not a release.**  X11 delivers a key-up
        immediately followed by a key-down for every repeat of a held key, and
        reporting those as real releases would make anything reading held keys
        -- navigation above all -- see the key let go and taken again dozens of
        times a second.  Qt marks them, so they are dropped here and only the
        genuine release reaches the engine.
        """
        if not self.engineReady() or event.isAutoRepeat():
            return
        self.noteKeyUp(int(event.key()))
        self.ProcessEvent(QtKeyboardEvent(self, event, 0))

    def emitKey(self, key: Any, state: int, modifiers: Any) -> None:
        """Send a key transition the window system did not report.

        For focus loss, where Qt delivers no release at all.  ``modifiers`` is
        the triple that came with the press, so the synthetic release matches
        the binding the press did; see
        :class:`OpenGLContext.events.eventhandlermixin.HeldKeyMixin`.
        """
        made = QtKeyboardEvent.__new__(QtKeyboardEvent)
        keyboardevents.KeyboardEvent.__init__(made)
        if hasattr(self, 'currentPass'):
            made.renderingPass = self.currentPass
        made.modifiers = modifiers
        made.name = _nameForKey(key)
        made.state = state
        self.ProcessEvent(made)

    def focusOutEvent(self, event: Any) -> None:
        """Forget what is held when the window loses focus.

        No key-up arrives for a key that was down when focus went elsewhere, so
        without this the key stays held for the rest of the session and the
        camera keeps moving with nobody touching the keyboard.  The sampler is
        cleared *and* the releases are sent, because an application that tracks
        held keys from the events has no other way to learn of them.
        """
        state = getattr(self, 'getInputState', None)
        if self.engineReady() and state is not None:
            state().clear()
        self.clearHeldKeys()
        # QWindow's, supplied by the class this is mixed into: a checker
        # reading this file alone sees only the engine's mix-in above.
        super(EventHandlerMixin, self).focusOutEvent(event)  # type: ignore[misc]

    ### MOUSE interactions
    def mouseMoveEvent(self, event: Any) -> None:
        """Convert pointer motion to a context-style event.

        The movement sampler is told directly as well as through the pick
        queue: a mouse-look mode wants every scrap of motion as it happens,
        while a pick event is only delivered once the selection buffer resolves
        it -- and not at all when the pointer is over nothing or picking is off.

        A movement the window made itself -- the warp that keeps a grabbed
        pointer in the middle of the window -- updates where the pointer is and
        goes no further: it is not motion the user asked for, and it is not a
        click on anything.
        """
        if not self.engineReady():
            return
        x, y = self._framebufferPoint(event)
        echo = self.pointerWarpEcho(event)
        record = getattr(self, 'recordPointerMotion', None)
        if record is not None:
            if echo:
                forget = getattr(self, 'forgetPointerOrigin', None)
                if forget is not None:
                    forget()
            record(x, self.getViewPort()[1] - y)
        if echo:
            return
        self.recentrePointer()
        self.addPickEvent(QtMouseMoveEvent(self, event, x, y))
        self.triggerPick()

    def mousePressEvent(self, event: Any) -> None:
        """Convert a mouse-button press to a context-style event"""
        if not self.engineReady():
            return
        x, y = self._framebufferPoint(event)
        self.addPickEvent(QtMouseButtonEvent(self, event, x, y, state=1))
        self.triggerPick()

    def mouseReleaseEvent(self, event: Any) -> None:
        """Convert a mouse-button release to a context-style event"""
        if not self.engineReady():
            return
        x, y = self._framebufferPoint(event)
        self.addPickEvent(QtMouseButtonEvent(self, event, x, y, state=0))
        self.triggerPick()

    def wheelEvent(self, event: Any) -> None:
        """Convert scrolling to the pair of button events a wheel notch is.

        Qt reports scrolling as an angle rather than as the wheel buttons
        everything downstream reads (see
        :data:`~OpenGLContext.events.mouseevents.WHEEL_UP`), so each whole notch
        becomes a press and a release here.  Only vertical rotation is used:
        nothing in the interface scrolls sideways.
        """
        if not self.engineReady():
            return
        x, y = self._framebufferPoint(event)
        for button in self._wheelNotches(event.angleDelta().y()):
            for state in (1, 0):
                self.addPickEvent(
                    QtWheelEvent(self, event, x, y, button=button, state=state)
                )
        self.triggerPick()

    def _wheelNotches(self, rotation: float) -> Any:
        """The whole notches in one report of ``rotation``, carrying the rest.

        The counting is :class:`OpenGLContext.events.wheel.WheelNotches`, which
        every backend whose toolkit states a detent size shares; Qt's is
        :data:`WHEEL_DETENT`.
        """
        counter = self.__dict__.get('_wheelCounter')
        if counter is None:
            counter = self.__dict__['_wheelCounter'] = WheelNotches(
                WHEEL_DETENT)
        return counter.notches(rotation)

    def _framebufferPoint(self, event: Any) -> Tuple[float, float]:
        """A Qt event's position in framebuffer pixels, y still counting down.

        Qt reports positions in logical window pixels, while the viewport and
        the selection buffer are sized in physical framebuffer pixels; on a
        scaled display the two differ, and feeding the raw position into a pick
        point lands the pick on the wrong pixel -- clicking an object misses
        while clicking a scaled-away offset hits.
        """
        ratio = self.devicePixelRatio()
        position = event.position()
        return int(position.x() * ratio), int(position.y() * ratio)


def _modifiersOf(qtEvent: Any) -> Tuple[int, int, int]:
    """The shift, control and alt triple a Qt event was delivered with

    A function rather than a method on the event classes, because the window
    reads it too: a key it has to *hold* is remembered with the modifiers its
    press carried, so the release focus loss never delivered matches the
    binding the press matched.
    """
    modifiers = qtEvent.modifiers()
    return (
        bool(modifiers & QtCore.Qt.KeyboardModifier.ShiftModifier),
        bool(modifiers & QtCore.Qt.KeyboardModifier.ControlModifier),
        bool(modifiers & QtCore.Qt.KeyboardModifier.AltModifier),
    )


def _nameForKey(key: Any, text: str = '') -> str:
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

    def _getModifiers(self, qtEvent: Any) -> Tuple[int, int, int]:
        """The shift, control and alt triple for a Qt event"""
        return _modifiersOf(qtEvent)

    def _getButton(self, qtEvent: Any) -> Optional[int]:
        """The button this event is about, or None for one we do not model"""
        button = qtEvent.button()
        for local, marker in BUTTON_MAPPING:
            if button == marker:
                return local
        return None

    def _getButtons(self, qtEvent: Any) -> Tuple[int, ...]:
        """Every button currently held, as OpenGLContext numbers them"""
        held = qtEvent.buttons()
        return tuple(local for local, marker in BUTTON_MAPPING if held & marker)

    def _getName(self, qtEvent: Any) -> str:
        """The OpenGLContext name of the key a Qt key event is about.

        Printable keys are named by their unshifted character in lower case, so
        a binding reads ``'w'`` whether or not shift is down -- the modifiers
        are reported separately and a binding that wants shift says so.
        """
        return _nameForKey(int(qtEvent.key()), qtEvent.text())


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


def _keyboardMapping() -> Dict[Any, str]:
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
    'EventHandlerMixin',
    'KEYBOARD_MAPPING',
    'QtKeyboardEvent',
    'QtKeypressEvent',
    'QtMouseButtonEvent',
    'QtMouseMoveEvent',
    'QtWheelEvent',
    'QtXEvent',
    'WHEEL_DETENT',
]
