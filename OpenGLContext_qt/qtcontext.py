"""Context functionality using the Qt windowing API, through PySide6

Registered with OpenGLContext's plugin system as the ``qt`` backend, so
``OPENGLCONTEXT_BACKEND=qt`` selects it wherever a context is chosen by name.

**The window is a** :class:`~PySide6.QtGui.QWindow` **with a**
:class:`~PySide6.QtGui.QOpenGLContext` **of its own, not a**
``QOpenGLWidget``.  A ``QOpenGLWidget`` renders into a framebuffer object that
Qt then composites, so *its* screen is not framebuffer 0 -- and OpenGLContext's
render passes bind framebuffer 0 whenever they finish with one of their own
(the bloom composite, the selection buffer's blit, the back-buffer read behind
every screenshot).  Under a ``QOpenGLWidget`` each of those would quietly go to
the wrong target.  A ``QWindow`` draws to a real window surface, where
framebuffer 0 is the screen and ``swapBuffers`` is a swap, so every render path
behaves exactly as it does under the GLUT and GLFW backends.  To place the view
in a widget layout, wrap it with :meth:`QtContext.container`.

**PyOpenGL speaks desktop OpenGL**, so the surface format asks for it by name.
Qt's default renderable type is whatever the platform integration prefers,
which under EGL -- Wayland, and X11 on many drivers -- is OpenGL ES; asking for
a core profile without saying "desktop" fails outright there, and the ES
context that a request without a profile produces has none of the entry points
this engine calls.
"""

import logging
import os
import sys
import time

from OpenGLContext import interactivecontext, vrmlcontext
from OpenGLContext.context import Context
from OpenGLContext.looptrace import LoopTrace
from OpenGLContext.move import viewplatformmixin
from PySide6 import QtCore, QtGui

from OpenGLContext_qt import qtevents

log = logging.getLogger(__name__)


def ensureApplication():
    """The process's ``QGuiApplication``, made if there is not one yet

    Answers ``(application, created)``, where ``created`` says whether this
    call is the one that made it -- which is what decides whether quitting a
    window may end the application with it.

    **Qt ends the process when a window is made without one**, through
    ``qFatal``: an abort rather than an exception, so nothing can catch it and
    offer the caller something else.  The question is therefore asked on every
    path that builds a window -- the constructor as much as
    :meth:`QtContext.ContextMainLoop` -- rather than only on the way into the
    main loop.  A host program that built its own application keeps it: Qt
    allows exactly one.
    """
    application = QtGui.QGuiApplication.instance()
    if application is not None:
        return application, False
    return QtGui.QGuiApplication(sys.argv), True

#: Colour channel depth requested for an RGB(A) window.  Qt takes each channel
#: separately where ``ContextDefinition`` has a single ``rgb`` flag.
COLOUR_BITS = 8

#: OpenGL version used when a core profile is asked for without one.  The
#: shaders OpenGLContext ships target ``#version 330 core``.
CORE_VERSION = (3, 3)

#: How long :meth:`QtContext.waitForExposure` will wait for the compositor to
#: give the new window a surface before giving up and letting the first expose
#: event finish the job.
EXPOSURE_TIMEOUT = 2.0

#: Asks the other backends for a window that renders without being mapped, for
#: headless capture.  Qt has no equivalent -- its offscreen surfaces have no
#: default framebuffer on the common EGL platforms -- so this backend says so
#: rather than quietly opening a window on somebody's screen.
HIDDEN_ENV = 'OPENGLCONTEXT_HIDDEN'


def hiddenRequested():
    """Whether the environment asked for a window nobody can see"""
    return os.environ.get(HIDDEN_ENV, '').strip().lower() in (
        '1', 'true', 'yes', 'on')


def surfaceFormatFromDefinition(definition):
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


class QtContext(qtevents.EventHandlerMixin, Context, QtGui.QWindow):
    """Implementation of the Context API on a Qt window

    ``Context`` is listed **before** ``QWindow``, unlike the mix-in order of
    every other backend.  PySide's initialisers are cooperative: ``QWindow``'s
    calls whatever ``__init__`` comes after it, and with ``Context`` there it
    builds the whole engine -- callbacks, event managers, ``OnInit`` -- part
    way through constructing the window it is supposed to be built on.  After
    ``QWindow`` there is only Qt's own hierarchy, so the chain ends where it
    should and each half is initialised in the order it needs.

    Rendering is driven from a Qt timer rather than from paint events: the
    engine's frame is an event cascade followed by a render, only the cascade
    always runs (animations, timers and queued events live there) and only
    sometimes is there anything new to draw.  A timer expresses that directly,
    and lets input events accumulate between frames instead of forcing a render
    each.
    """

    #: The QOpenGLContext this window renders through.
    glContext = None
    #: Set while ``OnInit`` is still waiting for the window to be given a
    #: surface it can render into.
    _initPending = False
    _renderTimerId = None
    _renderedFirst = False
    _loopTrace = None
    #: True when the pointer is hidden and grabbed for a mouse-look mode.
    _pointerGrabbed = False
    #: Set once the window system has refused this window the pointer, so it is
    #: not asked again for an answer that will not change.
    _pointerGrabRefused = False
    #: Where the pointer was last warped to, in global coordinates, so the move
    #: event the warp itself generates can be told from a real one.
    _pointerWarpedTo = None
    #: True when this context created the QGuiApplication, and so may end the
    #: process when the user quits.
    _ownsApplication = False
    #: Set while the context is shutting down, so the close event its own close
    #: raises does not start the shutdown again.
    _quitting = False

    def __init__(self, definition=None, parent=None, **named):
        """Create the window, its GL context, and the engine on top of them

        definition -- ContextDefinition (or a dictionary of its fields)
            describing the window to create; see
            :class:`OpenGLContext.contextdefinition.ContextDefinition`
        parent -- optional parent QWindow
        named -- individual definition fields, overriding the definition
        """
        # Before anything else Qt: a window made without a QGuiApplication
        # ends the process.  See ensureApplication.
        _application, created = ensureApplication()
        self._ownsApplication = created
        QtGui.QWindow.__init__(self, parent)
        # resolveDefinition rather than setDefinition plus a loop of setattr:
        # the engine's own resolution is where a field that follows from
        # another is worked out -- a profile named without a version settles
        # the version from it -- and a backend that sets the fields itself gets
        # the profile it was asked for beside a version left over from the
        # default, which the driver reads as a request for a different profile.
        definition = self.setDefinition(self.resolveDefinition(definition, **named))

        self.setSurfaceType(QtGui.QSurface.SurfaceType.OpenGLSurface)
        self.setFormat(surfaceFormatFromDefinition(definition))
        self.setTitle(definition.title or self.getApplicationName())
        self.resize(*[int(value) for value in definition.size])
        self.create()

        # Deliberately **not** parented to the window.  Qt destroys a QObject's
        # children from ``~QObject``, which runs after ``~QWindow`` has already
        # torn the platform surface down -- so a GL context parented here would
        # be destroyed pointing at a window that no longer exists, and taking
        # the process with it.  Owned by this attribute instead, and released
        # while the window is still whole (see releaseGL).
        #
        # requestedFormat rather than format: once the window has been created
        # the latter answers what the platform settled on, so a GL context built
        # from it would ask for whatever was already conceded rather than for
        # what the definition wants.
        self.glContext = QtGui.QOpenGLContext()
        self.glContext.setFormat(self.requestedFormat())
        if not self.glContext.create():
            raise RuntimeError(
                "Qt could not create an OpenGL context for %s"
                % (self.describeFormat(self.requestedFormat()),)
            )
        self.checkFormat(definition)

        if hiddenRequested():
            log.warning(
                "%s is not supported by the Qt backend, which needs a mapped "
                "window to render into; use the glfw backend for headless "
                "capture. A window will open.", HIDDEN_ENV,
            )
        self.show()
        self.waitForExposure()
        Context.__init__(self, definition)
        self._ready = True
        if self.isExposed():
            self.ViewPort(*self.framebufferSize())

    ### window <-> definition
    @staticmethod
    def describeFormat(format):
        """A one-line description of a surface format, for a log message"""
        return "OpenGL %d.%d %s (%s)" % (
            format.majorVersion(),
            format.minorVersion(),
            format.profile().name,
            format.renderableType().name,
        )

    def checkFormat(self, definition):
        """Complain if the context created is not the one that was asked for

        A driver may answer a request with something older or with an entirely
        different API, and every later failure then looks like a bug in the
        renderer.  An OpenGL ES context is fatal -- PyOpenGL calls desktop
        entry points that simply are not there -- while a version or profile
        that merely differs is reported and left to the caller.
        """
        got = self.glContext.format()
        if got.renderableType() != QtGui.QSurfaceFormat.RenderableType.OpenGL:
            raise RuntimeError(
                "Qt created an %s context; OpenGLContext needs desktop OpenGL. "
                "The platform plugin may be restricted to OpenGL ES."
                % (got.renderableType().name,)
            )
        wanted = self.requestedFormat()
        if (got.majorVersion(), got.minorVersion()) < (
            wanted.majorVersion(),
            wanted.minorVersion(),
        ):
            raise RuntimeError(
                "Asked for %s, got %s"
                % (self.describeFormat(wanted), self.describeFormat(got))
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
                self.describeFormat(got),
            )

    def framebufferSize(self):
        """The window's size in the physical pixels the viewport is measured in

        Qt sizes a window in logical pixels, which on a scaled display are
        fewer than the pixels actually rendered; a viewport set from the
        logical size leaves the rest of the window undrawn.
        """
        ratio = self.devicePixelRatio()
        size = self.size()
        return int(size.width() * ratio), int(size.height() * ratio)

    def waitForExposure(self, timeout=EXPOSURE_TIMEOUT):
        """Give Qt the chance to map the window, so ``OnInit`` can run now

        A window has no surface to render into until the compositor has shown
        it, and how long that takes is not this process's to decide.  Waiting
        here keeps the common case simple -- a script's ``OnInit`` runs inside
        the constructor, as it does under every other backend -- and the wait
        is bounded because a window that is never mapped must not become a
        window that never returns.  :meth:`exposeEvent` finishes the job in
        that case.

        Input is **left in the queue** rather than dispatched: the engine that
        would handle a keystroke does not exist yet -- ``Context.__init__`` has
        not run -- and Qt hands a shown window whatever the user is doing,
        starting with the release of the key that launched the program.  Held
        back, those events arrive intact once the loop is running.

        Returns whether the window is now exposed.
        """
        application = QtGui.QGuiApplication.instance()
        if application is None:
            return self.isExposed()
        deadline = time.time() + timeout
        while not self.isExposed() and time.time() < deadline:
            application.processEvents(
                QtCore.QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents, 10
            )
        return self.isExposed()

    ### Context API
    def setupCallbacks(self):
        """Ask the window manager for keyboard focus

        A QWindow delivers key events only while it is the active window, and
        a viewer whose keys do nothing until it is clicked reads as broken.
        """
        super(QtContext, self).setupCallbacks()
        self.requestActivate()

    def DoInit(self):
        """Run ``OnInit`` as soon as there is a surface to render into

        Deferred rather than skipped when the window is not yet exposed:
        ``OnInit`` is where an application builds its textures, its shaders and
        its scenegraph, and all of that needs a current GL context.
        """
        self._initPending = True
        self.completeInit()

    def completeInit(self):
        """Run the deferred ``OnInit`` if the window is ready for it"""
        if not self._initPending or not self.isExposed():
            return False
        self._initPending = False
        self.setCurrent()
        try:
            self.checkSurface()
        finally:
            self.unsetCurrent()
        Context.DoInit(self)
        return True

    def checkSurface(self):
        """Report a window whose GL surface cannot be drawn into

        A platform plugin can hand back a context that is current on no surface
        at all: ``makeCurrent`` answers true, every GL call succeeds, and the
        default framebuffer has no colour buffer to write to, so every frame is
        black and nothing anywhere raises.  The Qt Wayland plugin does this
        wherever the compositor will not give it a usable EGL window surface.
        Naming it costs one query at start-up and turns an evening of hunting
        into a line of output.

        Returns whether the surface can be drawn into.
        """
        from OpenGL.GL import GL_DRAW_BUFFER, GL_NONE, glGetIntegerv

        if int(glGetIntegerv(GL_DRAW_BUFFER)) != GL_NONE:
            return True
        application = QtGui.QGuiApplication.instance()
        log.error(
            "The %r platform plugin gave this window a GL context with no "
            "drawable surface: every frame will be black. Another plugin may "
            "work -- QT_QPA_PLATFORM=xcb, say -- or use the glfw backend.",
            application.platformName() if application is not None else 'Qt',
        )
        return False

    def setCurrent(self):
        """Make this window's GL context the current one

        A context belonging to another window system is let go of first.  A
        thread holds one GL context and the binding APIs do not know about each
        other, so Qt asking for a thread an EGL or GLX context from elsewhere
        in the process holds is refused -- and a refusal here is worse than it
        looks, since the GL calls that follow then go to whichever context
        *is* current and answer for that one.  See
        ``Context.releaseForeignContext``; Qt re-takes the thread on every
        ``makeCurrent``, so letting go costs it nothing.
        """
        Context.setCurrent(self)
        self.releaseForeignContext()
        if self.glContext is not None and not self.glContext.makeCurrent(self):
            log.warning("Qt would not make the GL context current")
            return
        self.bindContextResources(self._glHandle())

    def _glHandle(self):
        """The GL context handle the caches and PyOpenGL key on.

        The platform's own handle rather than Qt's object: what identifies a
        context to PyOpenGL is what the binding API calls it.  Read after the
        window is current, which is the only moment the answer is about this
        window.
        """
        from OpenGLContext import contextresources

        return contextresources.context_key()

    def SwapBuffers(self):
        """Present the rendered frame"""
        if self.glContext is not None:
            self.glContext.swapBuffers(self)

    def OnIdle(self, *arguments):
        """Animation hook for the Qt loop

        The default ``Context.OnIdle`` renders through ``drawPoll``, which
        would double up with the render this backend's own loop performs.
        Demos that animate override this to call ``triggerRedraw``.
        """
        return 0

    def OnResize(self, width, height):
        """Take the new window size, in framebuffer pixels"""
        self.ViewPort(width, height)
        self.triggerRedraw(1)

    def OnQuit(self, event=None):
        """Close the window, and end the process if this context started it

        A context created by :meth:`ContextMainLoop` *is* the application, and
        quitting it means quitting the process, as it does under every other
        backend.  A context embedded in somebody else's Qt application is a
        view inside it, and closing a view must not take the host program down
        with it -- so there, this closes the window and returns.

        Quitting twice is quitting once: closing the window raises a close
        event, which arrives back here, and a context that is already letting
        go of its GL objects must not start again half way through.

        The pointer is handed back first.  A window that closes while it still
        holds a hidden, grabbed pointer leaves the user with no cursor and the
        input still going to a window that is on its way out.
        """
        if self._quitting:
            return 0
        self._quitting = True
        self.setPointerCapture(False)
        self.suppressRedraw()
        self.stopRenderTimer()
        self.releaseGL()
        self.close()
        if self._ownsApplication:
            return Context.OnQuit(self, event)
        return 0

    def settingsChanged(self):
        """Re-read what a changed definition can still affect

        Almost everything a settings screen offers is read by the render pass
        every frame and needs nothing done here; what is left is the two
        window-level settings, the swap interval and whether the window fills
        the screen.
        """
        from OpenGLContext import renderoptions

        self.applyVSync()
        self.setFullscreen(renderoptions.fullscreen_window(self))
        Context.settingsChanged(self)

    def applyVSync(self, definition=None):
        """Report that a live context's swap interval cannot be changed

        It is part of the surface format, which is settled when the GL context
        is created, so a change is said out loud and takes effect the next time
        the program runs.  ``definition`` is what to read the wanted value from
        where it is not this context's own.
        """
        if self.glContext is None:
            return False
        source = self.contextDefinition if definition is None else definition
        wanted = bool(source.vsync)
        if bool(self.glContext.format().swapInterval()) != wanted:
            log.info(
                "vsync is part of the surface format under Qt; the change "
                "takes effect in a new window"
            )
        return False

    def setFullscreen(self, fullscreen):
        """Fill the screen, or go back to the window this context opened with

        Qt moves a window between the two without re-making its GL context, so
        nothing the engine has uploaded is lost, and a player can leave a
        full-screen game without restarting it.
        """
        state = QtCore.Qt.WindowState.WindowFullScreen
        already = bool(self.windowState() & state)
        if bool(fullscreen) == already:
            return True
        if fullscreen:
            self.showFullScreen()
        else:
            self.showNormal()
        self.triggerRedraw(1)
        return True

    def pumpWindowEvents(self):
        """Dispatch what Qt has queued; see Context.pumpWindowEvents"""
        application = QtGui.QGuiApplication.instance()
        if application is None:
            return False
        application.processEvents()
        return True

    def setPointerCapture(self, capture):
        """Hide and grab the pointer for a mouse-look movement mode

        The pointer is hidden, grabbed so it keeps reporting while it is over
        another window, and warped back to the middle of the window after each
        movement -- which is what makes the motion unbounded, since a pointer
        that stops at the edge of the screen is a view that stops turning
        there.

        Both the grab and the warp are requests the window system may refuse.
        Qt's Wayland plugin grabs only for popup windows, and a Wayland
        compositor does not let a client place the pointer at all.  **The answer
        says which happened**: false means the cursor is hidden but turning is
        limited to the window, and a caller that offers mouse-look can say so
        rather than leaving the player to discover it.
        """
        self._pointerGrabbed = bool(capture)
        self._pointerWarpedTo = None
        if capture:
            self.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.BlankCursor))
            grabbed = self.grabPointer(True)
            self.recentrePointer()
            return grabbed
        self.grabPointer(False)
        self.unsetCursor()
        return True

    def grabPointer(self, grab):
        """Ask the window system for every mouse event; answer whether it agreed

        A platform that refuses is asked once and then believed -- for letting
        go as well as for taking, since there is nothing to let go of.  Qt's
        Wayland plugin refuses for any window that is not a popup and warns
        every time it is asked either way, so a mode entered and left repeatedly
        would fill the log with news of something that cannot change while this
        window exists.
        """
        if self._pointerGrabRefused:
            return False
        granted = bool(self.setMouseGrabEnabled(grab))
        if grab and not granted:
            self._pointerGrabRefused = True
            application = QtGui.QGuiApplication.instance()
            log.info(
                "the %r platform plugin will not give this window the pointer; "
                "mouse-look will stop at the edge of the window",
                application.platformName() if application is not None else 'Qt',
            )
        return granted

    def recentrePointer(self):
        """Put the pointer back in the middle of the window, if it is grabbed"""
        if not self._pointerGrabbed:
            return
        centre = self.mapToGlobal(
            QtCore.QPoint(self.width() // 2, self.height() // 2)
        )
        self._pointerWarpedTo = centre
        # The screen-less overload, and deliberately so.  A global position is
        # unambiguous wherever the screens share one coordinate space, which is
        # every platform bar an X11 server configured with genuinely separate
        # ones -- and naming the window's QScreen instead
        # (``setPos(self.screen(), centre)``) leaves something behind that
        # brings down the teardown of a *later* window: a session that opens
        # and closes enough of them ends in a segmentation fault rather than an
        # error anything can catch.
        QtGui.QCursor.setPos(centre)

    def pointerWarpEcho(self, event):
        """Whether this movement is the one :meth:`recentrePointer` caused

        The warp arrives back as an ordinary movement, and a movement the
        program made itself is not motion the user asked for: left in, it
        cancels out every real movement and mouse-look never turns.
        """
        if self._pointerWarpedTo is None:
            return False
        echo = event.globalPosition().toPoint() == self._pointerWarpedTo
        if echo:
            self._pointerWarpedTo = None
        return echo

    ### Qt event handlers
    def exposeEvent(self, event):
        """Finish initialisation and size the viewport once there is a surface"""
        if not self._ready or not self.isExposed():
            return
        self.completeInit()
        self.OnResize(*self.framebufferSize())

    def resizeEvent(self, event):
        """Follow the window's size with the viewport"""
        if not self._ready or not self.isExposed():
            return
        self.OnResize(*self.framebufferSize())

    def closeEvent(self, event):
        """Treat closing the window as quitting"""
        self.OnQuit()

    ### the render loop
    def startRenderTimer(self):
        """Begin the timer that drives the render loop"""
        if self._renderTimerId is None:
            self._renderTimerId = self.startTimer(
                max(1, int(self.drawPollTimeout * 1000))
            )
        return self._renderTimerId

    def stopRenderTimer(self):
        """Stop the render loop's timer"""
        if self._renderTimerId is not None:
            self.killTimer(self._renderTimerId)
            self._renderTimerId = None

    def timerEvent(self, event):
        if event.timerId() == self._renderTimerId:
            self.loopIteration()
        else:
            super(QtContext, self).timerEvent(event)

    def loopIteration(self):
        """One pass of the render loop, timed phase by phase

        The phases exist because the frame counter can only see the render.  An
        application whose simulation lives in ``OnIdle`` stutters without the
        counter ever dipping, and the phase that names the culprit is the
        difference between a rendering problem and a simulation one.  See
        :mod:`OpenGLContext.looptrace`.  Qt's own event dispatch is what calls
        this, so there is no polling phase to charge for.
        """
        if not self._ready or self._initPending or not self.isExposed():
            return False
        # A private trace when a subclass has cleared setupLoopTrace's: a
        # diagnostic must never be the reason a loop will not run.
        trace = self._loopTrace or self.loopTrace or LoopTrace()
        with trace.iteration():
            with trace.phase('idle'):
                self.OnIdle()
            with trace.phase('draw'):
                # force=1 when a redraw is pending; force=0 still runs the event
                # cascade, so animations advance, and renders only if they
                # produced a visible change.
                if self.redrawRequest.is_set() or not self._renderedFirst:
                    self._renderedFirst = True
                    self.OnDraw(force=1)
                else:
                    self.OnDraw(force=0)
        return True

    def releaseWindow(self):
        """Let this window's GL objects and its GL context go

        The name every backend answers to; this one is :meth:`releaseGL`.
        """
        self.releaseGL()

    def releaseGL(self):
        """Let go of this window's GL objects, and then of the GL context

        The engine's caches own GL objects here, so they have to be dropped
        before the context goes away rather than left for a later window that
        the driver hands the same identifiers.

        The GL context itself goes at the end, **while the window it draws into
        is still whole**.  A QOpenGLContext's destructor reaches for the surface
        it was last current on, so one that outlives its window is a crash
        rather than a leak -- and the moment a Python object is destroyed is the
        collector's to choose unless somebody chooses it first.  Calling this
        twice is harmless; the second call has nothing to do.
        """
        glContext = self.glContext
        if glContext is None:
            return
        from OpenGLContext import contextresources

        if glContext.makeCurrent(self):
            try:
                contextresources.context_lost()
            finally:
                glContext.doneCurrent()
        # Both references, so the C++ object is destroyed here rather than
        # whenever the last of them happens to fall out of scope.
        self.glContext = None
        del glContext

    def MainLoop(self):
        """Run Qt's event loop with this context rendering inside it"""
        application = QtGui.QGuiApplication.instance()
        if application is None:
            raise RuntimeError(
                "A QGuiApplication must exist before the Qt main loop can run; "
                "use ContextMainLoop, or create the application yourself"
            )
        # We drive rendering ourselves, so suppress the synchronous in-callback
        # renders triggerPick/triggerRedraw would otherwise do.  A burst of
        # input events then coalesces into a single render per iteration
        # instead of one full render per event.
        self.deferRedraw = True
        self._loopTrace = self.loopTrace or LoopTrace()
        self.startRenderTimer()
        try:
            return application.exec()
        finally:
            self.stopRenderTimer()
            # A loop left while it was still slow -- a closed window, a Ctrl-C
            # -- holds an episode nobody has written.
            if self.stallJournal is not None:
                self.stallJournal.close()
            # The same argument for the session recording: what it holds of the
            # last few seconds is exactly what a session that ended badly is
            # worth reading for.
            self.stopTelemetry('mainloop-ended')
            self.releaseGL()

    @classmethod
    def ContextMainLoop(cls, *args, **named):
        """Create the context and run it as an application

        The context's own construction makes the QGuiApplication where there
        is not one already, and records whether it owns what it made.
        """
        instance = cls(*args, **named)
        if instance.contextDefinition.profileFile:
            import cProfile

            return cProfile.runctx(
                "instance.MainLoop()",
                globals(),
                locals(),
                instance.contextDefinition.profileFile,
            )
        return instance.MainLoop()

    def container(self, parent=None):
        """Wrap this window in a QWidget, for placing in a widget layout

        The way a QWindow joins a widget interface: the returned widget can be
        added to a layout, given a size policy and laid out beside the rest of
        an application's controls.  Requires ``PySide6.QtWidgets``, and so a
        ``QApplication`` rather than a bare ``QGuiApplication``.
        """
        from PySide6 import QtWidgets

        return QtWidgets.QWidget.createWindowContainer(self, parent)


class QtInteractiveContext(
    viewplatformmixin.ViewPlatformMixin,
    interactivecontext.InteractiveContext,
    QtContext,
):
    """Qt context providing camera, mouse and keyboard interaction"""


class QtViewerContext(vrmlcontext.VRMLContext, QtInteractiveContext):
    """Qt context that can open a scene file and show it

    What it adds to :class:`QtInteractiveContext` is everything a viewer needs
    and a program drawing its own geometry does not: ``load(url)``, which goes
    through OpenGLContext's loader registry and so reads VRML97, OBJ and glTF
    alike; the font providers text nodes need; and the viewpoint handling that
    binds a scene's own cameras.

    This is what the ``qt`` backend registers as its
    :class:`OpenGLContext.plugins.VRMLContext`, so it is what
    ``Context.getContextType('qt', plugins.VRMLContext)`` and every viewer built
    on ``testingcontext.getVRML()`` gets.
    """


if __name__ == "__main__":

    class TestContext(QtViewerContext):
        def OnInit(self):
            if sys.argv[1:]:
                self.load(sys.argv[1])

    TestContext.ContextMainLoop()
