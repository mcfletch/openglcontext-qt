"""The backend doing its actual job: a window, a GL context, and frames

These render for real.  A Qt context that has been mocked out proves only that
the mocks agree with each other, and the mistakes this backend is most likely
to make -- a surface format the driver will not give, a viewport that ignores
display scaling, a render that goes to the wrong framebuffer -- are all
invisible without a window on a screen.
"""

import subprocess
import sys

import numpy as np
import pytest
from OpenGLContext import plugins
from OpenGLContext.capture import read_back_buffer
from OpenGLContext.context import Context
from OpenGLContext.scenegraph import basenodes
from PySide6 import QtCore, QtGui

from OpenGLContext_qt import qtcontext

Format = QtGui.QSurfaceFormat


class Scene(qtcontext.QtViewerContext):
    """A context with something in it, that keeps the frames it renders"""

    def OnInit(self):
        self.frames = []
        self.sg = basenodes.sceneGraph(children=[
            basenodes.Transform(
                translation=(0, 0, -4),
                children=[basenodes.Shape(
                    geometry=basenodes.Teapot(size=1.5),
                    appearance=basenodes.Appearance(
                        material=basenodes.Material(diffuseColor=(1, .4, .2)),
                    ),
                )],
            ),
            basenodes.PointLight(location=(4, 4, 6)),
        ])

    def SwapBuffers(self):
        """Keep the finished frame before it is swapped away

        Reading the back buffer *after* the swap returns whatever the driver
        left there, which is usually nothing.
        """
        self.frames.append(read_back_buffer()[0])
        super(Scene, self).SwapBuffers()


# -- registration -------------------------------------------------------------

@pytest.mark.parametrize('kind,name', [
    ('Context', 'QtContext'),
    ('InteractiveContext', 'QtInteractiveContext'),
    ('VRMLContext', 'QtViewerContext'),
])
def test_installing_this_package_is_enough_to_find_the_backend(kind, name):
    """An application asks for ``qt`` and imports nothing of ours to get it.

    In a **subprocess** that imports only OpenGLContext, because that is the
    whole claim: registration happens on ``import OpenGLContext_qt``, and what
    makes it automatic is that ``OpenGLContext/__init__`` does that import
    itself.  A test in this process proves nothing -- the package is already
    imported here, by the tests themselves.
    """
    source = (
        "import OpenGLContext\n"
        "from OpenGLContext import plugins\n"
        "from OpenGLContext.context import Context\n"
        "found = Context.getContextType('qt', plugins.%s)\n"
        "print(found.__name__ if found is not None else 'MISSING')\n" % (kind,)
    )
    result = subprocess.run(
        [sys.executable, '-c', source],
        capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.split()[-1] == name, result.stdout


def test_the_registry_names_the_backend_qt():
    """The name an application spells in OPENGLCONTEXT_BACKEND."""
    assert 'qt' in [plugin.name for plugin in plugins.InteractiveContext.all()]


def test_asking_for_a_backend_nobody_registered_answers_nothing():
    """So a mis-spelled backend name fails as a name, not as an import."""
    assert Context.getContextType('qt-6', plugins.InteractiveContext) is None


# -- the window ---------------------------------------------------------------

def test_a_compatibility_context_can_be_created(context_factory):
    context = context_factory(profile='compatibility')
    assert context.glContext.isValid()
    assert context.glContext.format().renderableType() == Format.RenderableType.OpenGL


def test_a_core_context_gets_a_core_profile(context_factory):
    """The whole point of asking: the shader render path needs 3.3 core."""
    context = context_factory(profile='core')
    format = context.glContext.format()
    assert format.profile() == Format.OpenGLContextProfile.CoreProfile
    assert (format.majorVersion(), format.minorVersion()) >= qtcontext.CORE_VERSION


def test_the_engine_is_told_it_is_a_core_profile_context(context_factory):
    """It is what the render pass selects the shader pipeline on."""
    assert context_factory(profile='core').coreProfile
    assert not context_factory(profile='compatibility').coreProfile


def test_the_viewport_is_sized_in_framebuffer_pixels(context_factory):
    """Not the window's logical size: on a scaled display the two differ, and a
    viewport in logical pixels leaves a band of the window undrawn."""
    context = context_factory(size=(320, 240))
    assert context.getViewPort() == context.framebufferSize()
    ratio = context.devicePixelRatio()
    assert context.framebufferSize() == (int(320 * ratio), int(240 * ratio))


def test_a_resize_takes_the_viewport_with_it(context_factory):
    context = context_factory(size=(320, 240))
    context.OnResize(200, 100)
    assert context.getViewPort() == (200, 100)


def test_the_window_is_titled(context_factory):
    assert context_factory(title='A Window').title() == 'A Window'


def test_a_window_with_no_title_is_named_after_the_application(context_factory):
    context = context_factory()
    assert context.title() == context.getApplicationName()


def test_asking_for_no_vsync_gets_no_vsync(context_factory):
    """Uncapping the frame rate is how a benchmark measures one."""
    context = context_factory(vsync=False)
    assert context.format().swapInterval() == 0


# -- rendering ----------------------------------------------------------------

def renderFrames(context, count=3):
    """Draw ``count`` frames and answer the last one, as pixels"""
    for _ in range(count):
        context.OnDraw(force=1)
    assert context.frames, "the render pass never presented a frame"
    return context.frames[-1]


@pytest.mark.parametrize('profile', ['compatibility', 'core'])
def test_a_scene_actually_reaches_the_screen(context_factory, profile):
    """The end-to-end claim this backend exists to make.

    Anything less -- that OnDraw returned true, that no GL error was raised --
    is satisfied just as well by a context rendering into a framebuffer nobody
    will ever see, which is exactly the failure a Qt backend is prone to.
    """
    context = context_factory(Scene, size=(320, 240), profile=profile)
    pixels = renderFrames(context)
    assert pixels.max() > 0, "the frame is entirely black"


def test_the_teapot_is_where_it_was_put(context_factory):
    """A frame that is not black is not yet a frame with the scene in it: the
    middle is where the model is, and the corners are where it is not."""
    context = context_factory(Scene, size=(320, 240))
    pixels = renderFrames(context)
    height, width = pixels.shape[:2]
    middle = pixels[height // 3:2 * height // 3, width // 3:2 * width // 3]
    corner = pixels[:height // 8, :width // 8]
    assert middle.max() > 0
    assert corner.max() == 0


def test_the_frame_fills_the_window(context_factory):
    context = context_factory(Scene, size=(320, 240))
    pixels = renderFrames(context)
    assert (pixels.shape[1], pixels.shape[0]) == context.framebufferSize()


def test_the_render_loop_draws(context_factory):
    """What the timer calls, once per iteration."""
    context = context_factory(Scene, size=(160, 120))
    assert context.loopIteration()
    assert context.frames


def test_the_loop_does_not_draw_before_the_window_is_ready(context_factory):
    """Qt delivers timer events to a window that is still being built."""
    context = context_factory(Scene, size=(160, 120))
    context._ready = False
    assert not context.loopIteration()


def test_the_timer_that_drives_the_loop_can_be_started_and_stopped(context_factory):
    context = context_factory(size=(160, 120))
    assert context.startRenderTimer()
    assert context.startRenderTimer() == context._renderTimerId   # not a second one
    context.stopRenderTimer()
    assert context._renderTimerId is None


# -- input, as Qt actually delivers it ----------------------------------------

def sendEvent(context, event):
    """Hand Qt an event for this window, the way the window system would"""
    QtGui.QGuiApplication.sendEvent(context, event)


def keyEvent(key, text, kind=QtGui.QKeyEvent.Type.KeyPress):
    return QtGui.QKeyEvent(kind, key, QtCore.Qt.KeyboardModifier.NoModifier,
                           0, 0, 0, text, False)


def mouseEvent(kind, x, y, button=QtCore.Qt.MouseButton.LeftButton):
    point = QtCore.QPointF(x, y)
    return QtGui.QMouseEvent(kind, point, point, button, button,
                             QtCore.Qt.KeyboardModifier.NoModifier)


def test_a_key_dispatched_by_qt_reaches_a_binding(context_factory):
    """The wiring, not the translation: Qt has to find the mix-in's handlers on
    the real class for any of the rest of it to matter."""
    context = context_factory(size=(160, 120))
    pressed = []
    context.handler = lambda event: pressed.append(event.name)   # held weakly
    context.addEventHandler('keyboard', name='k', state=1, function=context.handler)
    sendEvent(context, keyEvent(QtCore.Qt.Key.Key_K, 'k'))
    assert pressed == ['k']


def test_typed_text_dispatched_by_qt_reaches_a_binding(context_factory):
    context = context_factory(size=(160, 120))
    typed = []
    context.handler = lambda event: typed.append(event.name)
    context.addEventHandler('keypress', name='K', function=context.handler)
    sendEvent(context, keyEvent(QtCore.Qt.Key.Key_K, 'K'))
    assert typed == ['K']


def clicked(context, x, y):
    """Click at ``x, y`` and answer what is waiting in the pick queue

    ``deferRedraw`` is what the main loop sets, and it is what leaves the event
    there to be read: without it the click renders a selection pass on the spot,
    which dispatches the event and empties the queue behind it.
    """
    context.deferRedraw = True
    context.pickEvents.clear()
    sendEvent(context, mouseEvent(QtGui.QMouseEvent.Type.MouseButtonPress, x, y))
    return list(context.getPickEvents().values())


def test_a_click_dispatched_by_qt_reaches_the_pick_queue(context_factory):
    """A button event is answered by the selection render rather than
    immediately, so the queue is where it lands first."""
    context = context_factory(size=(160, 120))
    assert [event.type for event in clicked(context, 20, 30)] == ['mousebutton']


def test_the_click_lands_where_it_was_made(context_factory):
    context = context_factory(size=(160, 120))
    event = clicked(context, 20, 30)[0]
    ratio = context.devicePixelRatio()
    assert event.pickPoint == (int(20 * ratio),
                               context.getViewPort()[1] - int(30 * ratio))


def test_the_click_names_the_button_that_was_pressed(context_factory):
    context = context_factory(size=(160, 120))
    context.deferRedraw = True
    context.pickEvents.clear()
    sendEvent(context, mouseEvent(QtGui.QMouseEvent.Type.MouseButtonPress, 20, 30,
                                  button=QtCore.Qt.MouseButton.RightButton))
    assert [event.button for event in context.getPickEvents().values()] == [1]


# -- the pointer --------------------------------------------------------------

def test_grabbing_the_pointer_hides_it(context_factory):
    """A visible cursor over a mouse-look view is a cursor sitting in the
    middle of the screen doing nothing."""
    context = context_factory()
    context.setPointerCapture(True)
    assert context.cursor().shape() == QtCore.Qt.CursorShape.BlankCursor


def test_capturing_says_whether_the_pointer_was_really_taken(context_factory):
    """A platform that will not hand it over is not a platform that did."""
    context = context_factory()
    # Asked of Qt first, and by probing rather than by reading the plugin's
    # name: a platform that refuses the grab outright is one where "it really
    # was taken" cannot be asserted of anything, and the refusal is what the
    # case below covers instead.
    if not context.setMouseGrabEnabled(True):
        pytest.skip(
            'the %r Qt platform plugin does not grab the pointer for ordinary '
            'windows; test_a_refused_grab_is_reported_as_a_refusal covers what '
            'this backend does about that'
            % (QtGui.QGuiApplication.platformName(),)
        )
    context.setMouseGrabEnabled(False)
    assert context.setPointerCapture(True) is True


def test_a_refused_grab_is_reported_as_a_refusal(context_factory):
    """Qt's Wayland plugin grabs only for popup windows, and claiming a capture
    that did not happen leaves mouse-look silently stopping at the window edge
    with nothing able to say why."""
    context = context_factory()
    context.setMouseGrabEnabled = lambda grab: False
    assert context.setPointerCapture(True) is False
    # Hidden all the same: turning still works inside the window.
    assert context.cursor().shape() == QtCore.Qt.CursorShape.BlankCursor


def test_a_platform_that_refuses_once_is_not_asked_again(context_factory):
    """It warns every time it is asked -- to let go as much as to take, since
    there is nothing to let go of -- and the answer cannot change while this
    window exists."""
    context = context_factory()
    asked = []
    context.setMouseGrabEnabled = lambda grab: asked.append(grab) or False
    for _ in range(3):
        context.setPointerCapture(True)
        context.setPointerCapture(False)
    assert asked == [True]


def test_releasing_the_pointer_gives_it_back(context_factory):
    context = context_factory()
    context.setPointerCapture(True)
    assert context.setPointerCapture(False)
    assert context.cursor().shape() != QtCore.Qt.CursorShape.BlankCursor


def test_the_warp_the_window_made_is_recognised(context_factory):
    """It arrives as an ordinary movement; counted, it cancels the movement
    that provoked it and the view never turns."""
    context = context_factory()
    context.setPointerCapture(True)
    warped = context._pointerWarpedTo
    assert warped is not None
    assert context.pointerWarpEcho(_Motion(warped))


def test_only_the_one_warp_is_discarded(context_factory):
    """A second movement to the same place is the user putting it there."""
    context = context_factory()
    context.setPointerCapture(True)
    warped = context._pointerWarpedTo
    context.pointerWarpEcho(_Motion(warped))
    assert not context.pointerWarpEcho(_Motion(warped))


def test_a_movement_somewhere_else_is_the_users(context_factory):
    context = context_factory()
    context.setPointerCapture(True)
    warped = context._pointerWarpedTo
    assert not context.pointerWarpEcho(
        _Motion(QtCore.QPoint(warped.x() + 17, warped.y())))


def test_nothing_is_discarded_when_the_pointer_is_free(context_factory):
    context = context_factory()
    assert not context.pointerWarpEcho(_Motion(QtCore.QPoint(1, 1)))


class _Motion(object):
    """The one thing ``pointerWarpEcho`` asks a mouse event for

    A real ``QMouseEvent`` answers a ``QPointF``, so this does too -- a stub
    that answers something easier to build tests the stub.
    """

    def __init__(self, point):
        self.point = QtCore.QPointF(point)

    def globalPosition(self):
        return self.point


# -- quitting -----------------------------------------------------------------

def test_closing_a_view_does_not_take_the_host_program_with_it(context_factory):
    """A context inside somebody else's Qt application is one view in it, and
    escape must not end their process."""
    context = context_factory(size=(160, 120))
    assert context.OnQuit() == 0
    assert not context.isVisible()


def test_quitting_twice_is_quitting_once(context_factory):
    """Closing the window raises a close event, which arrives back here; the
    second pass must not start letting go of the GL objects again."""
    context = context_factory(size=(160, 120))
    context.OnQuit()
    assert context.OnQuit() == 0
    assert context._quitting


def test_closing_the_window_quits_the_context(context_factory):
    context = context_factory(size=(160, 120))
    context.close()
    assert context._quitting


def test_the_gl_context_goes_before_the_window_it_draws_into(context_factory):
    """A QOpenGLContext must not outlive the surface it was made current on.

    Qt destroys a QObject's children from ``~QObject``, which runs *after*
    ``~QWindow`` has already torn the platform surface down -- so a GL context
    parented to its window is destroyed pointing at a window that is no longer
    there.  It is owned here instead, and let go of while the window is still
    whole.
    """
    context = context_factory(size=(64, 64))
    assert context.glContext is not None
    assert context.glContext.parent() is None, (
        "the GL context is a child of the window, so Qt will destroy it last")
    context.OnQuit()
    assert context.glContext is None


def test_opening_and_closing_many_views_does_not_kill_the_process(gl):
    """A long-running application opens and closes views all session.

    Each one here does what a viewer does -- renders, takes the pointer for
    mouse-look, gives it back, quits -- and is then dropped, with a collection
    forced so the remains are cleared up at a point of this test's choosing
    rather than in the middle of the next window's shutdown.  Nothing may be
    left over that has to be tidied in a particular order.

    A window's remains meeting another window's teardown is a **crash** rather
    than a failure anything can report, so this asserts by surviving.  It is
    not a complete guard: the fault it is modelled on takes a wider mixture of
    windows than one test makes, and the suite as a whole is what catches that.
    """
    import gc

    from OpenGLContext_qt.qtcontext import QtInteractiveContext

    for _ in range(12):
        context = QtInteractiveContext(size=(64, 64))
        context.OnDraw(force=1)
        context.setPointerCapture(True)
        context.setPointerCapture(False)
        context.OnQuit()
        del context
        gc.collect()

    # Rendering in a survivor rather than merely reaching this line: the claim
    # is that the process came through it with GL still usable.
    survivor = QtInteractiveContext(size=(64, 64))
    try:
        survivor.OnDraw(force=1)
        assert survivor.glContext.isValid()
    finally:
        survivor.OnQuit()


# ``QtContext.container`` has no test here on purpose.  Handing a live GL window
# to a widget container and then taking it back so the test can shut it down
# destroys the platform window under the context, and the process goes with it;
# what it would be testing is two lines of delegation to Qt's own
# createWindowContainer.  It is exercised by putting a view in a real
# application, which is the only place the arrangement makes sense.


# -- what a definition change can still do ------------------------------------

def test_a_vsync_change_is_reported_rather_than_pretended(context_factory, caplog):
    """The swap interval is part of the surface format, which is settled when
    the GL context is made; a settings screen that showed it changing would be
    lying about what the window is doing."""
    import logging

    context = context_factory(vsync=True)
    context.contextDefinition.vsync = False
    with caplog.at_level(logging.INFO):
        context.settingsChanged()
    assert 'vsync' in caplog.text


def test_a_definition_change_asks_for_a_new_frame(context_factory):
    context = context_factory(Scene, size=(160, 120))
    context.redrawRequest.clear()
    context.deferRedraw = True
    context.settingsChanged()
    assert context.redrawRequest.is_set()


# -- numpy is what the frames come back as ------------------------------------

def test_frames_come_back_as_images(context_factory):
    context = context_factory(Scene, size=(160, 120))
    pixels = renderFrames(context, 1)
    assert isinstance(pixels, np.ndarray)
    assert pixels.dtype == np.uint8
    assert pixels.shape[2] == 3
