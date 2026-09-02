"""What a ContextDefinition asks Qt for

The mapping from OpenGLContext's description of a window to Qt's is where a
backend quietly loses features: a field nobody translated is a setting the user
changed and nothing obeyed.  These tests are the record of which field means
what, and they need no window -- a QSurfaceFormat is a value.
"""

import logging

import pytest
from OpenGLContext.contextdefinition import ContextDefinition
from PySide6 import QtGui

from OpenGLContext_qt import qtcontext
from OpenGLContext_qt.qtcontext import CORE_VERSION, surfaceFormatFromDefinition

Format = QtGui.QSurfaceFormat


def formatFor(**named):
    return surfaceFormatFromDefinition(ContextDefinition(**named))


def test_desktop_opengl_is_asked_for_by_name():
    """PyOpenGL calls desktop entry points, and Qt's default under EGL is ES.

    An ES context has none of them, and asking for a core profile without
    saying "desktop" is refused outright on those platforms.
    """
    assert formatFor().renderableType() == Format.RenderableType.OpenGL


def test_a_core_profile_is_asked_for_as_one():
    format = formatFor(profile='core')
    assert format.profile() == Format.OpenGLContextProfile.CoreProfile


def test_a_core_profile_with_no_version_gets_the_one_the_shaders_need():
    format = formatFor(profile='core', version=(0, 0))
    assert (format.majorVersion(), format.minorVersion()) == CORE_VERSION


def test_a_higher_core_version_is_left_alone():
    format = formatFor(profile='core', version=(4, 5))
    assert (format.majorVersion(), format.minorVersion()) == (4, 5)


def test_a_compatibility_profile_is_asked_for_as_one():
    format = formatFor(profile='compatibility', version=(3, 2))
    assert format.profile() == Format.OpenGLContextProfile.CompatibilityProfile
    assert (format.majorVersion(), format.minorVersion()) == (3, 2)


def test_a_compatibility_context_with_no_version_still_names_the_profile():
    """Naming no version leaves the driver free to choose the profile too.

    Below GL 3.2 there are no profiles to choose between and the attribute is
    ignored, so naming one costs the request nothing -- while leaving it unsaid
    gets a *core* context from a driver that defaults to its highest version,
    and the fixed-function entry points a compatibility profile is asked for
    are exactly the ones that are then missing.
    """
    format = formatFor(profile='compatibility', version=(0, 0))
    assert format.profile() == Format.OpenGLContextProfile.CompatibilityProfile
    # Still no version: what it asks for is a profile, not a level.
    assert (format.majorVersion(), format.minorVersion()) == (2, 0)


def test_an_unknown_profile_is_refused():
    with pytest.raises(ValueError):
        formatFor(profile='immediate')


def test_double_buffering_is_the_default():
    assert formatFor().swapBehavior() == Format.SwapBehavior.DoubleBuffer


def test_single_buffering_can_be_asked_for():
    assert (formatFor(doubleBuffer=False).swapBehavior()
            == Format.SwapBehavior.SingleBuffer)


def test_a_depth_buffer_is_provided_without_being_asked_for():
    """Every renderer here depth-tests; a window with no depth buffer draws the
    back of a model over its front."""
    assert formatFor().depthBufferSize() == 24


def test_a_requested_depth_size_is_used():
    assert formatFor(depthBuffer=32).depthBufferSize() == 32


def test_the_stencil_buffer_follows_the_definition():
    assert formatFor(stencilBuffer=8).stencilBufferSize() == 8


def test_no_alpha_channel_unless_it_is_wanted():
    """A window with destination alpha is transparent to a compositor that
    honours it, so cleared pixels show whatever is behind the window."""
    assert formatFor(alpha=False).alphaBufferSize() == 0
    assert formatFor(alpha=True).alphaBufferSize() > 0


def test_colour_channels_are_asked_for_when_rgb_is_wanted():
    format = formatFor(rgb=True)
    assert (format.redBufferSize(), format.greenBufferSize(),
            format.blueBufferSize()) == (8, 8, 8)


def test_multisample_samples_are_passed_through():
    assert formatFor(multisampleSamples=8).samples() == 8


def test_asking_for_a_multisample_buffer_without_a_count_gets_a_count():
    """Qt has no separate 'want multisampling' switch: it counts samples, and a
    buffer with no samples in it is not multisampled at all."""
    assert formatFor(multisampleBuffer=1).samples() == 4


def test_stereo_is_passed_through():
    assert formatFor(stereo=1).stereo()
    assert not formatFor().stereo()


def test_a_debug_context_is_asked_for_when_debugging():
    assert formatFor(debug=True).testOption(Format.FormatOption.DebugContext)
    assert not formatFor(debug=False).testOption(Format.FormatOption.DebugContext)


def test_vsync_becomes_the_swap_interval():
    assert formatFor(vsync=True).swapInterval() == 1
    assert formatFor(vsync=False).swapInterval() == 0


def test_an_accumulation_buffer_is_reported_rather_than_ignored(caplog):
    """Qt 6 dropped the accumulation buffer with the pipeline that used it.

    A caller who asked for one is going to render something wrong; saying so is
    the only thing that can be done about it.
    """
    with caplog.at_level(logging.WARNING):
        formatFor(accumulationBuffer=16)
    assert 'accumulation' in caplog.text.lower()


def test_nothing_is_said_when_no_accumulation_buffer_was_asked_for(caplog):
    with caplog.at_level(logging.WARNING):
        formatFor()
    assert 'accumulation' not in caplog.text.lower()


# -- a window nobody can see --------------------------------------------------

@pytest.mark.parametrize('value', ['1', 'true', 'YES', 'on'])
def test_a_hidden_window_is_recognised_as_a_request(value, monkeypatch):
    """The other backends answer it; a request this one cannot meet has to be
    seen before it can be reported."""
    monkeypatch.setenv(qtcontext.HIDDEN_ENV, value)
    assert qtcontext.hiddenRequested()


@pytest.mark.parametrize('value', ['', '0', 'off', 'no', ' '])
def test_anything_else_is_not_a_request_for_one(value, monkeypatch):
    monkeypatch.setenv(qtcontext.HIDDEN_ENV, value)
    assert not qtcontext.hiddenRequested()


def test_an_unset_variable_asks_for_nothing(monkeypatch):
    monkeypatch.delenv(qtcontext.HIDDEN_ENV, raising=False)
    assert not qtcontext.hiddenRequested()
