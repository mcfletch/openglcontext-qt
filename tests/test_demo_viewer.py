"""The embedding demo: a view as one widget in a Qt application.

:mod:`OpenGLContext_qt.demos.qt_viewer` is read as much as run, which is a
reason to hold it to the suite rather than an excuse not to: a sample that has
stopped working teaches the wrong thing to everybody who copies it.

Every step runs in a subprocess of its own.  Qt allows exactly one application
object, the demo needs the widgets one (``QApplication``) for a widget layout,
and the rest of this suite shares a bare ``QGuiApplication`` for the session.
The subprocess is also what lets a step close the window it was given.

The engine's own distribution has the same program in Tk and wx, and tests the
Tk one the same way.  See ``plans/EMBEDDING-EXAMPLES.md`` there.
"""

import os
import subprocess
import sys

import pytest

DRIVER = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      'helpers', '_qt_viewer_drive.py')


@pytest.fixture(scope='module')
def drive(drawable, application):
    """Run the driver for one step, and return what it reported

    Skipped where this platform plugin gives no drawable GL surface, which is
    the same condition the rest of the suite's rendering tests are held to --
    asked of the session's own window rather than guessed from the platform's
    name.
    """
    if not drawable:
        pytest.skip(
            "the %r Qt platform plugin gives no drawable GL surface; try "
            "QT_QPA_PLATFORM=xcb" % (application.platformName(),))

    def run(*steps):
        result = subprocess.run(
            [sys.executable, DRIVER] + list(steps),
            capture_output=True, text=True, timeout=600,
        )
        assert 'DONE' in result.stdout, (
            'the Qt viewer driver did not finish:\n%s\n%s'
            % (result.stdout, result.stderr))
        reported = {}
        for line in result.stdout.splitlines():
            head, _, tail = line.partition(' ')
            reported[head] = tail
        return reported

    return run


class TestTheQtDemo:
    def test_the_loaded_scene_reaches_the_tree(self, drive):
        reported = drive('tree')
        assert reported['LOADED'] == 'True'
        assert int(reported['ROWS']) > 1
        assert reported['HASROOT'] == 'True'
        assert reported['MATCHES'] == 'True', (
            'the tree should show the outline row for row')

    def test_opening_a_row_opens_it_in_the_model(self, drive):
        reported = drive('expanding')
        assert reported['EXPANDED'] == 'True'
        assert reported['GREW'] == 'True'
        assert reported['COLLAPSED'] == 'True'
        assert reported['BACK'] == 'True'

    def test_selecting_a_row_names_a_node_and_follows_it(self, drive):
        reported = drive('selecting')
        assert reported['SELECTED'] == 'True'
        assert reported['WATCHING'] == 'True'
        assert reported['DETAIL']

    def test_a_change_to_the_watched_node_reaches_the_panel(self, drive):
        """Which is what pydispatcher is doing in there, and what the window's
        own signals carry back onto the thread its widgets belong to."""
        reported = drive('watching')
        assert reported['TOLD'] == 'True'
        assert reported['RENAMED'] == 'True'

    def test_the_menu_opens_a_scene_through_the_engine(self, drive):
        reported = drive('opening')
        assert reported['EMPTY'] == 'True'
        assert reported['OPENED'] == 'True'
        assert reported['LOADED'] == 'True'
        assert reported['STATUS'] == '_scene.wrl'

    def test_closing_the_window_releases_the_context(self, drive):
        reported = drive('quitting')
        assert reported['RELEASED'] == 'True'
        assert reported['WATCHING'] == 'True'
        assert reported['OUTLINE'] == 'True'
        assert reported['WINDOW'] == 'True'

    def test_a_view_that_finishes_takes_the_host_window_with_it(self, drive):
        """A view inside somebody else's window never ends their process, so
        the host is the one that decides; here the view is why the window is
        there."""
        assert drive('viewfinished')['WINDOW'] == 'True'
