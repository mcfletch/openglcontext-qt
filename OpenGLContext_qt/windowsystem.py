"""The Qt window system: a QWindow with a QOpenGLContext of its own

Registered with OpenGLContext as the ``qt`` window system through the
``openglcontext.windowsystems`` entry point, so ``windowsystem='qt'`` in a
definition, or ``OPENGLCONTEXT_BACKEND=qt``, opens a context here.

**The window is a** :class:`~PySide6.QtGui.QWindow` **with a**
:class:`~PySide6.QtGui.QOpenGLContext` **of its own, not a**
``QOpenGLWidget``.  A ``QOpenGLWidget`` renders into a framebuffer object that
Qt then composites, so *its* screen is not framebuffer 0 -- and OpenGLContext's
render passes bind framebuffer 0 whenever they finish with one of their own
(the bloom composite, the selection buffer's blit, the back-buffer read behind
every screenshot).  Under a ``QOpenGLWidget`` each of those would quietly go to
the wrong target.  A ``QWindow`` draws to a real window surface, where
framebuffer 0 is the screen and ``swapBuffers`` is a swap, so every render path
behaves exactly as it does under the GLUT and GLFW window systems.

``context.window`` is that window.  To place the view in a widget layout, wrap
it in a container::

    container = QtWidgets.QWidget.createWindowContainer(context.window, parent)

or ``context.windowsystem.container(parent)``, which is the same call.

**PyOpenGL speaks desktop OpenGL**, so the surface format asks for it by name.
Qt's default renderable type is whatever the platform integration prefers,
which under EGL -- Wayland, and X11 on many drivers -- is OpenGL ES; asking for
a core profile without saying "desktop" fails outright there, and the ES
context that a request without a profile produces has none of the entry points
this engine calls.
"""
from __future__ import annotations

import logging
import sys
import time
from collections.abc import Hashable
from typing import TYPE_CHECKING, Any, ClassVar, Optional

from OpenGL.GL import GL_DRAW_BUFFER, GL_NONE, glGetIntegerv
from OpenGLContext import renderoptions
from OpenGLContext.events import keyboardevents
from OpenGLContext.events.wheel import WheelNotches
from OpenGLContext.windowsystem.base import WindowSystem
from PySide6 import QtCore, QtGui

from OpenGLContext_qt.qtevents import (
    WHEEL_DETENT, QtKeyboardEvent, QtKeypressEvent, QtMouseButtonEvent,
    QtMouseMoveEvent, QtWheelEvent, modifiersOf, nameForKey,
)

if TYPE_CHECKING:
    from OpenGLContext.contextdefinition import ContextDefinition

log = logging.getLogger(__name__)

__all__ = (
    'COLOUR_BITS',
    'CORE_VERSION',
    'EXPOSURE_TIMEOUT',
    'HIDDEN_ENV',
    'QtWindow',
    'QtWindowSystem',
    'describeFormat',
    'ensureApplication',
    'hiddenRequested',
    'surfaceFormatFromDefinition',
)

#: Colour channel depth requested for an RGB(A) window.  Qt takes each channel
#: separately where ``ContextDefinition`` has a single ``rgb`` flag.
COLOUR_BITS = 8

#: OpenGL version used when a core profile is asked for without one.  The
#: shaders OpenGLContext ships target ``#version 330 core``.
CORE_VERSION = (3, 3)

#: How long :meth:`QtWindowSystem.waitForExposure` will wait for the compositor
#: to give the new window a surface before giving up and letting the first
#: expose event finish the job.
EXPOSURE_TIMEOUT = 2.0

#: Asks the other window systems for a window that renders without being
#: mapped, for headless capture.  Qt has no equivalent -- its offscreen
#: surfaces have no default framebuffer on the common EGL platforms -- so this
#: window system says so rather than quietly opening a window on somebody's
#: screen.
HIDDEN_ENV = 'OPENGLCONTEXT_HIDDEN'


def platformName() -> str:
    """What Qt calls the platform plugin in use, or 'Qt' where nothing can say.

    ``QGuiApplication.instance()`` is declared to answer the *core* application,
    which knows nothing about platforms, so the kind is asked rather than
    assumed.
    """
    application = QtGui.QGuiApplication.instance()
    return (application.platformName()
            if isinstance(application, QtGui.QGuiApplication) else 'Qt')


def ensureApplication() -> Any:
    """The process's ``QGuiApplication``, made if there is not one yet

    Answers ``(application, created)``, where ``created`` says whether this
    call is the one that made it -- which is what decides whether quitting a
    window may end the application with it.

    **Qt ends the process when a window is made without one**, through
    ``qFatal``: an abort rather than an exception, so nothing can catch it and
    offer the caller something else.  The question is therefore asked on every
    path that builds a window.  A host program that built its own application
    keeps it: Qt allows exactly one.
    """
    application = QtGui.QGuiApplication.instance()
    if application is not None:
        return application, False
    return QtGui.QGuiApplication(sys.argv), True


def hiddenRequested() -> bool:
    """Whether the environment asked for a window nobody can see

    The engine's reading of the switch (:func:`OpenGLContext.renderoptions.hidden_window`),
    which reports a value that is neither a yes nor a no.
    """
    return renderoptions.hidden_window()


def surfaceFormatFromDefinition(definition: Any) -> Any:
    """Build the :class:`~PySide6.QtGui.QSurfaceFormat` a ContextDefinition asks for

    Every field of the definition that describes the *window* rather than the
    rendering is mapped here; the rendering features (shadows, bloom, IBL and
    the rest) are read from the definition by the render passes themselves.

    ``accumulationBuffer`` has no Qt equivalent -- Qt 6 dropped it along with
    the fixed-function pipeline that used it -- and is reported rather than
    silently ignored, since a caller asking for one is asking for something
    this window will not have.
    """
    format = QtGui.QSurfaceFormat()
    format.setRenderableType(QtGui.QSurfaceFormat.RenderableType.OpenGL)

    major, minor = int(definition.version[0]), int(definition.version[1])
    if definition.profile == "core":
        if (major, minor) < CORE_VERSION:
            major, minor = CORE_VERSION
        format.setVersion(major, minor)
        format.setProfile(QtGui.QSurfaceFormat.OpenGLContextProfile.CoreProfile)
    elif definition.profile == "compatibility":
        if major:
            format.setVersion(major, minor)
        # Asked for, whatever version was named -- including none.  A driver
        # free to choose picks the profile it likes: Mesa answers a request
        # that names neither with a 4.6 *core* context, and the fixed-function
        # calls a compatibility profile is asked for precisely so that they
        # work then fail at the first glMatrixMode.  Below GL 3.2 there are no
        # profiles to choose between and the attribute is ignored, which costs
        # the request nothing.
        format.setProfile(
            QtGui.QSurfaceFormat.OpenGLContextProfile.CompatibilityProfile
        )
    else:
        raise ValueError("Unrecognised profile: %r" % (definition.profile,))

    format.setSwapBehavior(
        QtGui.QSurfaceFormat.SwapBehavior.DoubleBuffer
        if definition.doubleBuffer
        else QtGui.QSurfaceFormat.SwapBehavior.SingleBuffer
    )
    format.setDepthBufferSize(
        definition.depthBuffer if definition.depthBuffer > -1 else 24
    )
    if definition.stencilBuffer > -1:
        format.setStencilBufferSize(definition.stencilBuffer)
    if definition.rgb:
        format.setRedBufferSize(COLOUR_BITS)
        format.setGreenBufferSize(COLOUR_BITS)
        format.setBlueBufferSize(COLOUR_BITS)
    # A window with an alpha channel is transparent to any compositor that
    # honours destination alpha, so cleared pixels show what is behind the
    # window.  Only ask for one when the definition does.
    format.setAlphaBufferSize(COLOUR_BITS if definition.alpha else 0)

    if definition.multisampleSamples > 0:
        format.setSamples(definition.multisampleSamples)
    elif definition.multisampleBuffer > 0:
        format.setSamples(4)
    if definition.stereo > 0:
        format.setStereo(True)
    if definition.debug:
        format.setOption(QtGui.QSurfaceFormat.FormatOption.DebugContext)
    format.setSwapInterval(1 if definition.vsync else 0)
    if definition.accumulationBuffer > -1:
        log.warning(
            "Qt provides no accumulation buffer; ignoring the %d bits requested",
            definition.accumulationBuffer,
        )
    return format


def describeFormat(format: Any) -> str:
    """A one-line description of a surface format, for a log message"""
    return "OpenGL %d.%d %s (%s)" % (
        format.majorVersion(),
        format.minorVersion(),
        format.profile().name,
        format.renderableType().name,
    )


class QtWindow(QtGui.QWindow):
    """The QWindow a context draws in, handing Qt's events to its window system

    A ``QWindow``'s virtual event handlers are its callback registration, so
    each is overridden here to pass the event on and nothing more.  Nothing of
    the application's context shares this namespace.
    """

    def __init__(self, system: QtWindowSystem, parent: Any = None) -> None:
        super().__init__(parent)
        self.system = system

    def exposeEvent(self, event: Any) -> None:  # noqa: ARG002 QWindow's virtual
        self.system.onExpose()

    def resizeEvent(self, event: Any) -> None:  # noqa: ARG002 QWindow's virtual
        self.system.onResize()

    def closeEvent(self, event: Any) -> None:  # noqa: ARG002 QWindow's virtual
        self.system.onClose()

    def keyPressEvent(self, event: Any) -> None:
        self.system.onKeyPress(event)

    def keyReleaseEvent(self, event: Any) -> None:
        self.system.onKeyRelease(event)

    def focusOutEvent(self, event: Any) -> None:
        self.system.onFocusOut()
        super().focusOutEvent(event)

    def mouseMoveEvent(self, event: Any) -> None:
        self.system.onMouseMove(event)

    def mousePressEvent(self, event: Any) -> None:
        self.system.onMousePress(event)

    def mouseReleaseEvent(self, event: Any) -> None:
        self.system.onMouseRelease(event)

    def wheelEvent(self, event: Any) -> None:
        self.system.onWheel(event)

    def timerEvent(self, event: Any) -> None:
        if not self.system.onTimer(event):
            super().timerEvent(event)


class QtWindowSystem(WindowSystem):
    """A Qt window, and the translation of its events

    Rendering is driven from a Qt timer rather than from paint events: the
    engine's frame is an event cascade followed by a render, only the cascade
    always runs (animations, timers and queued events live there) and only
    sometimes is there anything new to draw.  A timer expresses that directly,
    and lets input events accumulate between frames instead of forcing a render
    each.
    """

    name = 'qt'
    acceptsParent = True
    pollsEvents = False

    #: Qt's own cursor shapes, by the name a control asks for. Qt carries a
    #: picture for each rather than reading a desktop theme, so every one of
    #: these is there wherever Qt runs.
    CURSOR_SHAPES: ClassVar[dict[str, str]] = {
        'arrow': 'ArrowCursor',
        'hand': 'PointingHandCursor',
        'text': 'IBeamCursor',
        'crosshair': 'CrossCursor',
        'resize-x': 'SizeHorCursor',
        'resize-y': 'SizeVerCursor',
        'resize': 'SizeAllCursor',
        'no': 'ForbiddenCursor',
    }

    window: Optional[QtWindow] = None
    #: The QOpenGLContext this window renders through.
    glContext: Any = None
    #: True once the context's event managers exist, so input can be handed
    #: to them.  Qt hands a shown window whatever the user is doing from that
    #: moment, and a keystroke arriving before the managers are built would
    #: reach a context with nothing to dispatch it with.
    engineReady = False
    #: True when this window system created the QGuiApplication, and so may
    #: end the process when the user quits.
    ownsApplication = False
    #: Set while the context is shutting down, so the close event its own
    #: close raises does not start the shutdown again.
    quitting = False
    renderTimerId: Optional[int] = None
    #: True when the pointer is hidden and grabbed for a mouse-look mode.
    pointerGrabbed = False
    #: Set once the platform has refused this window the pointer, so it is not
    #: asked again for an answer that will not change.
    pointerGrabRefused = False
    #: Where the pointer was last warped to, in global coordinates, so the move
    #: event the warp itself generates can be told from a real one.
    pointerWarpedTo: Any = None
    #: Counts a stream of wheel reports into whole notches.
    wheelCounter: Optional[WheelNotches] = None

    # -- lifetime ----------------------------------------------------------

    def open(self, definition: ContextDefinition, parent: Any = None) -> bool:
        # Before anything else Qt: a window made without a QGuiApplication
        # ends the process.  See ensureApplication.
        _application, self.ownsApplication = ensureApplication()
        window = self.window = QtWindow(self, parent)
        window.setSurfaceType(QtGui.QSurface.SurfaceType.OpenGLSurface)
        window.setFormat(surfaceFormatFromDefinition(definition))
        window.setTitle(definition.title or self.context.getApplicationName())
        window.resize(*[int(value) for value in definition.size])
        window.create()

        # Deliberately **not** parented to the window.  Qt destroys a QObject's
        # children from ``~QObject``, which runs after ``~QWindow`` has already
        # torn the platform surface down -- so a GL context parented here would
        # be destroyed pointing at a window that no longer exists, and taking
        # the process with it.  Held by this attribute instead, and released
        # while the window is still whole (see release).
        #
        # requestedFormat rather than format: once the window has been created
        # the latter answers what the platform settled on, so a GL context built
        # from it would ask for whatever was already conceded rather than for
        # what the definition wants.
        self.glContext = QtGui.QOpenGLContext()
        self.glContext.setFormat(window.requestedFormat())
        if not self.glContext.create():
            raise RuntimeError(
                "Qt could not create an OpenGL context for %s"
                % (describeFormat(window.requestedFormat()),)
            )
        self.checkFormat(definition)

        if hiddenRequested():
            log.warning(
                "%s is not supported by the Qt window system, which needs a "
                "mapped window to render into; use the glfw window system for "
                "headless capture. A window will open.", HIDDEN_ENV,
            )
        window.show()
        if not self.waitForExposure():
            return False
        self.makeCurrent()
        self.checkSurface()
        return True

    def checkFormat(self, definition: Any) -> None:
        """Complain if the context created is not the one that was asked for

        A driver may answer a request with something older or with an entirely
        different API, and every later failure then looks like a bug in the
        renderer.  An OpenGL ES context is fatal -- PyOpenGL calls desktop
        entry points that simply are not there -- while a profile that merely
        differs is reported and left to the caller.
        """
        if self.glContext is None or self.window is None:
            raise RuntimeError(
                "the window has no GL context to describe; it was destroyed, "
                "or never made")
        got = self.glContext.format()
        if got.renderableType() != QtGui.QSurfaceFormat.RenderableType.OpenGL:
            raise RuntimeError(
                "Qt created an %s context; OpenGLContext needs desktop OpenGL. "
                "The platform plugin may be restricted to OpenGL ES."
                % (got.renderableType().name,)
            )
        wanted = self.window.requestedFormat()
        if (got.majorVersion(), got.minorVersion()) < (
            wanted.majorVersion(),
            wanted.minorVersion(),
        ):
            raise RuntimeError(
                "Asked for %s, got %s" % (describeFormat(wanted), describeFormat(got))
            )
        # Both directions: a compatibility request answered with a core context
        # is the one that goes on to fail, since the fixed-function entry points
        # it was asked for are the ones a core profile does not have.
        profiles = QtGui.QSurfaceFormat.OpenGLContextProfile
        expected = {
            "core": profiles.CoreProfile,
            "compatibility": profiles.CompatibilityProfile,
        }.get(definition.profile)
        if expected is not None and got.profile() != expected:
            log.warning(
                "Asked for a %s profile, got %s; the driver may be reporting "
                "the profile inaccurately, or may have ignored the request",
                definition.profile,
                describeFormat(got),
            )

    def waitForExposure(self, timeout: float = EXPOSURE_TIMEOUT) -> bool:
        """Give Qt the chance to map the window, so ``OnInit`` can run now

        A window has no surface to render into until the compositor has shown
        it, and how long that takes is not this process's to decide.  Waiting
        here keeps the common case simple -- a script's ``OnInit`` runs inside
        the constructor, as it does under every other window system -- and the
        wait is bounded because a window that is never mapped must not become
        a window that never returns.  :meth:`onExpose` finishes the job in that
        case.

        Input is **left in the queue** rather than dispatched: the engine that
        would handle a keystroke does not exist yet, and Qt hands a shown
        window whatever the user is doing, starting with the release of the key
        that launched the program.  Held back, those events arrive intact once
        the loop is running.

        Returns whether the window is now exposed.
        """
        window = self.window
        assert window is not None
        application = QtGui.QGuiApplication.instance()
        if application is None:
            return bool(window.isExposed())
        deadline = time.time() + timeout
        while not window.isExposed() and time.time() < deadline:
            application.processEvents(
                QtCore.QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents, 10
            )
        return bool(window.isExposed())

    def checkSurface(self) -> bool:
        """Report a window whose GL surface cannot be drawn into

        A platform plugin can hand back a context that is current on no surface
        at all: ``makeCurrent`` answers true, every GL call succeeds, and the
        default framebuffer has no colour buffer to write to, so every frame is
        black and nothing anywhere raises.  The Qt Wayland plugin does this
        wherever the compositor will not give it a usable EGL window surface.
        Naming it costs one query at start-up and turns an evening of hunting
        into a line of output.

        Called with the window's context current.  Returns whether the surface
        can be drawn into.
        """
        if int(glGetIntegerv(GL_DRAW_BUFFER)) != GL_NONE:
            return True
        log.error(
            "The %r platform plugin gave this window a GL context with no "
            "drawable surface: every frame will be black. Another plugin may "
            "work -- QT_QPA_PLATFORM=xcb, say -- or use the glfw window system.",
            platformName(),
        )
        return False

    def release(self) -> None:
        """Let go of this window's GL objects, and then of the GL context

        The GL context goes at the end, **while the window it draws into is
        still whole**.  A QOpenGLContext's destructor reaches for the surface
        it was last current on, so one that outlives its window is a crash
        rather than a leak -- and the moment a Python object is destroyed is
        the collector's to choose unless somebody chooses it first.
        """
        self.stopRenderTimer()
        glContext = self.glContext
        if glContext is None:
            return
        if glContext.makeCurrent(self.window):
            try:
                self.context.releaseContextResources(self.glHandle())
            finally:
                glContext.doneCurrent()
        else:
            self.context.releaseContextResources(None)
        # Both references, so the C++ object is destroyed here rather than
        # whenever the last of them happens to fall out of scope.
        self.glContext = None
        del glContext

    def quit(self) -> bool:
        """Close the window; end the process only if this started it

        A context whose window system made the ``QGuiApplication`` *is* the
        application.  A context embedded in somebody else's Qt application is a
        view inside it, and closing a view must not take the host program down.

        Quitting twice is quitting once: closing the window raises a close
        event, which arrives back here, and a context that is already letting
        go of its GL objects must not start again half way through.

        The pointer is handed back first.  A window that closes while it still
        holds a hidden, grabbed pointer leaves the user with no cursor and the
        input still going to a window that is on its way out.
        """
        if self.quitting:
            return False
        self.quitting = True
        self.finished = True
        self.setPointerCapture(False)
        self.release()
        if self.window is not None:
            self.window.close()
        return self.ownsApplication

    def container(self, parent: Any = None) -> Any:
        """Wrap the window in a QWidget, for placing in a widget layout

        Requires ``PySide6.QtWidgets``, and so a ``QApplication`` rather than a
        bare ``QGuiApplication``.
        """
        from PySide6 import QtWidgets  # noqa: PLC0415 a native library of its own, loaded only for a widget layout

        assert self.window is not None, 'the window has been released'
        return QtWidgets.QWidget.createWindowContainer(self.window, parent)

    # -- current and presenting --------------------------------------------

    def makeCurrent(self) -> Optional[Hashable]:
        """Make the window's GL context current

        A context belonging to another window system is let go of first.  A
        thread holds one GL context and the binding APIs do not know about each
        other, so Qt asking for a thread an EGL or GLX context from elsewhere
        in the process holds is refused -- and a refusal here is worse than it
        looks, since the GL calls that follow then go to whichever context
        *is* current and answer for that one.  Qt re-takes the thread on every
        ``makeCurrent``, so letting go costs it nothing.
        """
        if self.glContext is None:
            return None
        self.context.releaseForeignContext()
        if not self.glContext.makeCurrent(self.window):
            log.warning("Qt would not make the GL context current")
            return None
        return self.glHandle()

    def swap(self) -> None:
        if self.glContext is not None:
            self.glContext.swapBuffers(self.window)

    def drawableSize(self) -> tuple[int, int]:
        """The window's size in the physical pixels the viewport is measured in

        Qt sizes a window in logical pixels, which on a scaled display are
        fewer than the pixels actually rendered; a viewport set from the
        logical size leaves the rest of the window undrawn.
        """
        window = self.window
        assert window is not None
        ratio = window.devicePixelRatio()
        size = window.size()
        return int(size.width() * ratio), int(size.height() * ratio)

    def applyVSync(self, definition: Any) -> bool:
        """Report that a live context's swap interval cannot be changed

        It is part of the surface format, which is settled when the GL context
        is created, so a change is said out loud and takes effect the next time
        the program runs.
        """
        if self.glContext is None or definition is None:
            return False
        if bool(self.glContext.format().swapInterval()) != bool(definition.vsync):
            log.info(
                "vsync is part of the surface format under Qt; the change "
                "takes effect in a new window"
            )
        return False

    # -- requests of the window --------------------------------------------

    def setFullscreen(self, fullscreen: bool) -> bool:
        """Fill the screen, or go back to the window this context opened with

        Qt moves a window between the two without re-making its GL context, so
        nothing the engine has uploaded is lost, and a player can leave a
        full-screen game without restarting it.
        """
        window = self.window
        if window is None:
            return False
        state = QtCore.Qt.WindowState.WindowFullScreen
        if bool(fullscreen) == bool(window.windowState() & state):
            return True
        if fullscreen:
            window.showFullScreen()
        else:
            window.showNormal()
        self.context.triggerRedraw(1)
        return True

    def setPointerShape(self, name: str) -> bool:
        """Show this pointer; False for a shape Qt has not got."""
        if self.window is None or self.pointerGrabbed:
            return False
        shape = self.CURSOR_SHAPES.get(str(name or 'arrow'))
        if shape is None:
            return False
        constant = getattr(QtCore.Qt.CursorShape, shape, None)
        if constant is None:
            return False
        self.window.setCursor(QtGui.QCursor(constant))
        return True

    def setPointerCapture(self, capture: bool) -> bool:
        """Hide and grab the pointer for a mouse-look movement mode

        The pointer is hidden, grabbed so it keeps reporting while it is over
        another window, and warped back to the middle of the window after each
        movement -- which is what makes the motion unbounded, since a pointer
        that stops at the edge of the screen is a view that stops turning
        there.

        Both the grab and the warp are requests the window system may refuse.
        Qt's Wayland plugin grabs only for popup windows, and a Wayland
        compositor does not let a client place the pointer at all.  **The
        answer says which happened**: false means the cursor is hidden but
        turning is limited to the window, and a caller that offers mouse-look
        can say so rather than leaving the player to discover it.
        """
        window = self.window
        if window is None:
            return False
        self.pointerGrabbed = bool(capture)
        self.pointerWarpedTo = None
        if capture:
            window.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.BlankCursor))
            grabbed = self.grabPointer(True)
            self.recentrePointer()
            return grabbed
        self.grabPointer(False)
        window.unsetCursor()
        return True

    def grabPointer(self, grab: bool) -> bool:
        """Ask the platform for every mouse event; answer whether it agreed

        A platform that refuses is asked once and then believed -- for letting
        go as well as for taking, since there is nothing to let go of.  Qt's
        Wayland plugin refuses for any window that is not a popup and warns
        every time it is asked either way, so a mode entered and left repeatedly
        would fill the log with news of something that cannot change while this
        window exists.
        """
        if self.pointerGrabRefused or self.window is None:
            return False
        granted = bool(self.window.setMouseGrabEnabled(grab))
        if grab and not granted:
            self.pointerGrabRefused = True
            log.info(
                "the %r platform plugin will not give this window the pointer; "
                "mouse-look will stop at the edge of the window",
                platformName(),
            )
        return granted

    def recentrePointer(self) -> None:
        """Put the pointer back in the middle of the window, if it is grabbed"""
        window = self.window
        if not self.pointerGrabbed or window is None:
            return
        centre = window.mapToGlobal(
            QtCore.QPoint(window.width() // 2, window.height() // 2)
        )
        self.pointerWarpedTo = centre
        # The screen-less overload, and deliberately so.  A global position is
        # unambiguous wherever the screens share one coordinate space, which is
        # every platform bar an X11 server configured with genuinely separate
        # ones -- and naming the window's QScreen instead
        # (``setPos(window.screen(), centre)``) leaves something behind that
        # brings down the teardown of a *later* window: a session that opens
        # and closes enough of them ends in a segmentation fault rather than an
        # error anything can catch.
        QtGui.QCursor.setPos(centre)

    def pointerWarpEcho(self, event: Any) -> bool:
        """Whether this movement is the one :meth:`recentrePointer` caused

        Takes the event rather than a point: Qt answers a warp in *global*
        coordinates, which is what :meth:`recentrePointer` recorded.  A
        movement the program made itself is not motion the user asked for:
        left in, it cancels out every real movement and mouse-look never
        turns.
        """
        if self.pointerWarpedTo is None:
            return False
        echo = bool(event.globalPosition().toPoint() == self.pointerWarpedTo)
        if echo:
            self.pointerWarpedTo = None
        return echo

    # -- the loop -----------------------------------------------------------

    def bindCallbacks(self) -> None:
        """Let input through, and ask the window manager for keyboard focus

        A QWindow delivers key events only while it is the active window, and
        a viewer whose keys do nothing until it is clicked reads as broken.
        """
        self.engineReady = True
        if self.window is not None:
            self.window.requestActivate()

    def pump(self) -> bool:
        application = QtGui.QGuiApplication.instance()
        if application is None:
            return False
        application.processEvents()
        return True

    def running(self) -> bool:
        window = self.window
        return (window is not None and not self.finished
                and self.context.initialised and bool(window.isExposed()))

    def startRenderTimer(self) -> int:
        """Begin the timer that drives the render loop"""
        assert self.window is not None
        if self.renderTimerId is None:
            self.renderTimerId = self.window.startTimer(
                max(1, int(self.context.drawPollTimeout * 1000))
            )
        return self.renderTimerId

    def stopRenderTimer(self) -> None:
        """Stop the render loop's timer"""
        if self.renderTimerId is not None and self.window is not None:
            self.window.killTimer(self.renderTimerId)
        self.renderTimerId = None

    def onTimer(self, event: Any) -> bool:
        """Draw a frame if this is the render timer; answer whether it was"""
        if event.timerId() != self.renderTimerId:
            return False
        self.loopIteration()
        return True

    def mainLoop(self) -> Any:
        """Run Qt's event loop with this context rendering inside it"""
        application = QtGui.QGuiApplication.instance()
        if application is None:
            raise RuntimeError(
                "A QGuiApplication must exist before the Qt main loop can run; "
                "use ContextMainLoop, or create the application yourself"
            )
        # Qt's own dispatch delivers the input, so a burst of it only flags a
        # redraw and costs one frame.
        self.context.deferRedraw = True
        self.startRenderTimer()
        try:
            return application.exec()
        finally:
            self.stopRenderTimer()
            self.context.closeJournals('mainloop-ended')
            self.release()

    # -- the window's events ------------------------------------------------

    def onExpose(self) -> None:
        """Finish initialisation and size the viewport once there is a surface"""
        window = self.window
        if not self.engineReady or window is None or not window.isExposed():
            return
        context = self.context
        if not context.initialised:
            self.makeCurrent()
            self.checkSurface()
            context.completeInit()
        context.OnResize(*self.drawableSize())

    def onResize(self) -> None:
        """Follow the window's size with the viewport"""
        window = self.window
        if (not self.engineReady or window is None or not window.isExposed()
                or not self.context.initialised):
            return
        self.context.OnResize(*self.drawableSize())

    def onClose(self) -> None:
        """Treat closing the window as quitting"""
        self.context.OnQuit()

    # -- keyboard -----------------------------------------------------------

    def onKeyPress(self, event: Any) -> None:
        """A key went down.

        An auto-repeat is passed through as another key-down, which is what a
        held key means to a handler that acts once per press.
        """
        if not self.engineReady:
            return
        context = self.context
        if event.isAutoRepeat():
            context.noteNativeRepeat()     # Qt supplies them; do not double up
        context.noteKeyDown(int(event.key()), modifiersOf(event))
        context.ProcessEvent(QtKeyboardEvent(context, event, 1))
        if event.text():
            context.ProcessEvent(QtKeypressEvent(context, event))

    def onKeyRelease(self, event: Any) -> None:
        """A key came up.

        **An auto-repeat release is not a release.**  X11 delivers a key-up
        immediately followed by a key-down for every repeat of a held key, and
        reporting those as real releases would make anything reading held keys
        -- navigation above all -- see the key let go and taken again dozens of
        times a second.  Qt marks them, so they are dropped here and only the
        genuine release reaches the engine.
        """
        if not self.engineReady or event.isAutoRepeat():
            return
        self.context.noteKeyUp(int(event.key()))
        self.context.ProcessEvent(QtKeyboardEvent(self.context, event, 0))

    def emitKey(self, key: Any, state: int, modifiers: Any) -> None:
        """Send a key transition Qt did not report.

        ``modifiers`` is the triple that came with the press, so the synthetic
        release matches the binding the press did.
        """
        context = self.context
        made = QtKeyboardEvent.__new__(QtKeyboardEvent)
        keyboardevents.KeyboardEvent.__init__(made)
        if hasattr(context, 'currentPass'):
            made.renderingPass = context.currentPass
        made.modifiers = modifiers
        made.name = nameForKey(key)
        made.state = state
        context.ProcessEvent(made)

    def onFocusOut(self) -> None:
        """Forget what is held when the window loses focus.

        No key-up arrives for a key that was down when focus went elsewhere, so
        without this the key stays held for the rest of the session and the
        camera keeps moving with nobody touching the keyboard.  The sampler is
        cleared *and* the releases are sent, because an application that tracks
        held keys from the events has no other way to learn of them.
        """
        if not self.engineReady:
            return
        self.context.getInputState().clear()
        self.context.clearHeldKeys()

    # -- pointer -------------------------------------------------------------

    def framebufferPoint(self, event: Any) -> tuple[int, int]:
        """A Qt event's position in framebuffer pixels, y still counting down.

        Qt reports positions in logical window pixels, while the viewport and
        the selection buffer are sized in physical framebuffer pixels; on a
        scaled display the two differ, and feeding the raw position into a pick
        point lands the pick on the wrong pixel.
        """
        assert self.window is not None
        ratio = self.window.devicePixelRatio()
        position = event.position()
        return int(position.x() * ratio), int(position.y() * ratio)

    def onMouseMove(self, event: Any) -> None:
        """The pointer moved.

        The movement sampler is told directly as well as through the pick
        queue: a mouse-look mode wants every scrap of motion as it happens,
        while a pick event is only delivered once the selection buffer resolves
        it -- and not at all when the pointer is over nothing or picking is off.

        A movement the window made itself -- the warp that keeps a grabbed
        pointer in the middle of the window -- updates where the pointer is and
        goes no further: it is not motion the user asked for, and it is not a
        click on anything.
        """
        if not self.engineReady:
            return
        context = self.context
        x, y = self.framebufferPoint(event)
        echo = self.pointerWarpEcho(event)
        if echo:
            context.forgetPointerOrigin()
        context.recordPointerMotion(x, context.getViewPort()[1] - y)
        if echo:
            return
        self.recentrePointer()
        context.addPickEvent(QtMouseMoveEvent(context, event, x, y))
        context.triggerPick()

    def onMousePress(self, event: Any) -> None:
        if not self.engineReady:
            return
        x, y = self.framebufferPoint(event)
        self.context.addPickEvent(QtMouseButtonEvent(self.context, event, x, y, state=1))
        self.context.triggerPick()

    def onMouseRelease(self, event: Any) -> None:
        if not self.engineReady:
            return
        x, y = self.framebufferPoint(event)
        self.context.addPickEvent(QtMouseButtonEvent(self.context, event, x, y, state=0))
        self.context.triggerPick()

    def onWheel(self, event: Any) -> None:
        """Scrolling, as the pair of button events a wheel notch is.

        Qt reports scrolling as an angle rather than as the wheel buttons
        everything downstream reads (see
        :data:`~OpenGLContext.events.mouseevents.WHEEL_UP`), so each whole notch
        becomes a press and a release here.  Only vertical rotation is used:
        nothing in the interface scrolls sideways.
        """
        if not self.engineReady:
            return
        x, y = self.framebufferPoint(event)
        for button in self.wheelNotches(event.angleDelta().y()):
            for state in (1, 0):
                self.context.addPickEvent(
                    QtWheelEvent(self.context, event, x, y, button=button, state=state)
                )
        self.context.triggerPick()

    def wheelNotches(self, rotation: float) -> list[int]:
        """The whole notches in one report of ``rotation``, carrying the rest.

        The counting is :class:`OpenGLContext.events.wheel.WheelNotches`, which
        every window system whose toolkit states a detent size shares; Qt's is
        :data:`~OpenGLContext_qt.qtevents.WHEEL_DETENT`.
        """
        if self.wheelCounter is None:
            self.wheelCounter = WheelNotches(WHEEL_DETENT)
        return list(self.wheelCounter.notches(rotation))
