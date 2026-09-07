#! /usr/bin/env python3
"""Drive one thing the Qt viewer demo does, and report what happened.

Run as a subprocess by ``tests/test_demo_viewer.py``: each named step builds the
demo's real window with a real GL context, does the one thing, prints what came
of it and stops.

A subprocess per step, and a subprocess at all: Qt allows exactly one
application object, the demo needs the widgets one, and the rest of this suite
shares a bare ``QGuiApplication`` for the whole session.

Usage:  _qt_viewer_drive.py <step> [<step> ...]
"""
import os
import sys
import time

os.environ.setdefault('OPENGLCONTEXT_NO_VSYNC', '1')
os.environ['OPENGLCONTEXT_DISABLE_FPS_DISPLAY'] = '1'

from PySide6 import QtCore, QtWidgets                           # noqa: E402
from vrml import protofunctions                                 # noqa: E402

from OpenGLContext.scenegraph import basenodes                  # noqa: E402
from OpenGLContext_qt.demos.qt_viewer import (                  # noqa: E402
    PATH_ROLE, ViewerWindow,
)

MODEL = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     '_scene.wrl')

#: How long to give an asynchronous load before calling it a failure, in
#: seconds.  Generous: a software rasteriser on a busy machine is what this has
#: to finish under.  Counted in seconds rather than in frames, because an
#: iteration with nothing to do returns at once and a thousand of them are no
#: time at all for a worker thread to load anything in.
LOAD_SECONDS = 60.0

application = QtWidgets.QApplication(sys.argv[:1])


def say(name, value):
    print('%s %s' % (name, value), flush=True)


def built(source=None):
    """The demo's window, shown, with its first frame drawn"""
    window = ViewerWindow(source=source)
    window.show()
    frames(window, 1)
    return window


def frames(window, count):
    """Pump Qt and the engine's loop, the way Qt's own render timer does"""
    for _ in range(count):
        application.processEvents(QtCore.QEventLoop.AllEvents, 10)
        window.view.loopIteration()


def loaded(window):
    """Pump frames until the scene the worker thread is loading is on screen"""
    deadline = time.time() + LOAD_SECONDS
    while time.time() < deadline:
        frames(window, 1)
        if window.tree.topLevelItemCount():
            return True
        time.sleep(0.01)
    return False


def treeLabels(window):
    """What the tree is showing, top to bottom"""
    def below(item):
        found = []
        for index in range(item.childCount()):
            child = item.child(index)
            found.append(child.text(0))
            found.extend(below(child))
        return found
    return below(window.tree.invisibleRootItem())


def itemAt(window, path):
    """The tree item standing for an outline path"""
    def find(item):
        for index in range(item.childCount()):
            child = item.child(index)
            if child.data(0, PATH_ROLE) == path:
                return child
            found = find(child)
            if found is not None:
                return found
        return None
    return find(window.tree.invisibleRootItem())


# -- the steps --------------------------------------------------------------
def tree():
    """The scene reaches the tree control"""
    window = built(MODEL)
    say('LOADED', loaded(window))
    labels = treeLabels(window)
    say('ROWS', len(labels))
    say('HASROOT', 'sceneGraph' in labels)
    say('MATCHES', len(window.outline.rows) == len(
        [label for label in labels if label != '…']))


def expanding():
    """Opening a row in the tree opens it in the model, and shows more"""
    window = built(MODEL)
    loaded(window)
    before = len(window.outline.rows)
    window.onOpenRow(itemAt(window, (0,)))
    say('EXPANDED', (0,) in window.outline.expanded)
    say('GREW', len(window.outline.rows) > before)
    window.onCloseRow(itemAt(window, (0,)))
    say('COLLAPSED', (0,) not in window.outline.expanded)
    say('BACK', len(window.outline.rows) == before)


def selecting():
    """Selecting a row names the node, and the panel says what it is"""
    window = built(MODEL)
    loaded(window)
    itemAt(window, (0,)).setSelected(True)
    window.onSelect()
    say('SELECTED', window.outline.selected is not None)
    say('WATCHING', window.watching is window.outline.selected)
    say('DETAIL', window.detail.toPlainText().splitlines()[0])


def watching():
    """A change to the selected node reaches the panel through pydispatcher"""
    window = built()
    window.outline.root = basenodes.sceneGraph(
        children=[basenodes.Transform(DEF='hub')])
    window.fillTree()
    itemAt(window, (0,)).setSelected(True)
    window.onSelect()
    node = window.outline.selected
    node.translation = (3, 4, 5)
    application.processEvents()
    say('TOLD', '[3. 4. 5.]' in window.detail.toPlainText())
    protofunctions.defName(node, 'renamed')
    application.processEvents()             # deliver the queued signal
    say('RENAMED', 'renamed' in treeLabels(window))


def opening():
    """The File menu's own handler opens a scene through the engine"""
    window = built()
    say('EMPTY', window.view.source is None)
    window.open(MODEL)
    say('OPENED', window.view.source == MODEL)
    say('LOADED', loaded(window))
    say('STATUS', os.path.basename(window.status.text()))


def quitting():
    """Closing the host's window takes the GL context with it"""
    window = built(MODEL)
    loaded(window)
    window.close()
    say('RELEASED', window.view.glContext is None)
    say('WATCHING', window.watching is None)
    say('OUTLINE', window.outline.rows == [])
    say('WINDOW', not window.isVisible())


def viewfinished():
    """A view that quits itself takes the host's window down with it"""
    window = built(MODEL)
    window.view.OnQuit()
    application.processEvents()
    say('WINDOW', not window.isVisible())


STEPS = {
    'tree': tree,
    'expanding': expanding,
    'selecting': selecting,
    'watching': watching,
    'opening': opening,
    'quitting': quitting,
    'viewfinished': viewfinished,
}


if __name__ == '__main__':
    for name in sys.argv[1:]:
        STEPS[name]()
    say('DONE', '')
