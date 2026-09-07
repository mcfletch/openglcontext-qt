#! /usr/bin/env python3
"""A view inside a Qt application: a menu, a scene tree, and the engine's viewer

Run it, with a scene to open or without one::

    python -m OpenGLContext_qt.demos.qt_viewer model.glb
    python -m OpenGLContext_qt.demos.qt_viewer https://example.com/scene.gltf

The Qt backend needs a platform plugin that gives a drawable GL surface; the
Wayland plugin does not in every container, so ``QT_QPA_PLATFORM=xcb`` is worth
knowing about.

The whole of the engine in here is four calls, and the rest is Qt:

* :func:`OpenGLContext.viewer.viewerFor` gives the viewer over the Qt backend.
  The window is a ``QWindow``, and
  :meth:`~OpenGLContext_qt.qtcontext.QtContext.container` wraps it in a widget
  that goes in a layout beside everything else.
* :meth:`~OpenGLContext.viewer.sceneviewer.SceneViewerMixin.openSource` opens a
  path or a URL, on a worker thread.
* :class:`~OpenGLContext.outline.SceneOutline` is the scene as rows, which fill
  the ``QTreeWidget``.
* :meth:`~OpenGLContext_qt.qtcontext.QtContext.startRenderTimer` asks Qt to
  drive the frames.  Qt's own timer calls ``loopIteration`` from then on, so
  unlike the Tk demo there is no per-frame callback here.

**A ``QApplication``, not a ``QGuiApplication``**, and it has to exist before
the view is built: the view makes one itself if there is none, Qt allows
exactly one, and a widget layout needs the widgets version.

A tree of a few thousand rows is what ``QTreeWidget`` is for; past that, Qt's
answer is a ``QAbstractItemModel`` over the same
:class:`~OpenGLContext.outline.SceneOutline`, whose rows carry the path,
depth and expandability such a model is written from.

The same program is written for Tk and wx in :mod:`OpenGLContext.demos`.
"""
import sys

from OpenGLContext.outline import SceneOutline, nodeSummary
from OpenGLContext.viewer import viewerFor
from PySide6 import QtCore, QtWidgets
from pydispatch import dispatcher

#: What the file chooser offers, which is what the viewer's adapters read.
SCENE_FILES = 'Scenes (*.gltf *.glb *.wrl *.wrz *.obj *.json);;Every file (*)'

#: Where a row's outline path is kept on its tree item.
PATH_ROLE = QtCore.Qt.ItemDataRole.UserRole


class SceneView(viewerFor('qt')):  # type: ignore[misc]  # base chosen at run time
    """The engine's viewer, as one widget in somebody else's window"""

    #: Called on the GUI thread once a scene has been built, if a host set it.
    onScene = None
    #: Called when the view has finished: quit from inside, or its window
    #: closed.  A view in somebody else's window never ends their process, so
    #: what that should mean is the host's to decide.
    onFinish = None

    def hasSceneToShow(self):
        """The host opens scenes, so the engine's launch screen stays down

        Starting with nothing to show is a viewer with its shelf open, which is
        right for ``oglc-view`` and wrong here: this application has a File
        menu of its own, and a second menu over the top of the first is no
        welcome at all.
        """
        return True

    def onSceneReady(self):
        """A scene has been built and swapped in -- on the render thread

        Which is Qt's own thread here, since Qt's timer is what drives the
        loop, so a host told from here may touch its widgets directly.
        """
        super().onSceneReady()
        if self.onScene is not None:
            self.onScene()

    def OnQuit(self, event=None):
        """The view is done with -- tell the host, which owns the window"""
        result = super().OnQuit(event)
        if self.onFinish is not None:
            self.onFinish()
        return result


class ViewerWindow(QtWidgets.QMainWindow):
    """A window with a menu, a scene tree, and a view of the scene"""

    #: The scene changed underneath the outline.  A **signal** rather than a
    #: call, because the change arrives on whichever thread made it -- the
    #: loader's worker thread, most often -- and a queued connection is how Qt
    #: gets back onto the thread its widgets belong to.
    outlineChanged = QtCore.Signal()
    #: The same, for a field of the one node the panel is showing.
    nodeChanged = QtCore.Signal()

    def __init__(self, source=None):
        super().__init__()
        self.setWindowTitle('OpenGLContext in Qt')
        self.resize(960, 600)

        self.view = SceneView(size=(720, 560))
        # This loop is Qt's, so the frames are too: with this set, an input
        # event asks for a redraw instead of rendering where it was handled,
        # and a burst of them costs one frame rather than one each.  Every
        # backend's own `MainLoop` does the same, for the same reason.
        self.view.deferRedraw = True

        splitter = QtWidgets.QSplitter(self)
        splitter.addWidget(self.buildPanel(splitter))
        splitter.addWidget(self.view.container(splitter))
        splitter.setStretchFactor(1, 3)
        self.setCentralWidget(splitter)
        self.buildMenu()

        #: The scene as rows, refilling the tree through a queued signal.
        self.outline = SceneOutline(self.view.sg,
                                    onChange=self.outlineChanged.emit)
        self.outlineChanged.connect(self.fillTree)
        self.nodeChanged.connect(self.showDetail)
        #: The node the detail panel is following, if any.
        self.watching = None

        # Wired once there is an outline for them to work on, since the first
        # of them runs as soon as anything is opened.
        self.view.onScene = self.onSceneReady
        self.view.onFinish = self.close

        self.showDetail()
        if source:
            self.open(source)

    # -- building the window ----------------------------------------------
    def buildMenu(self):
        """The application's own menu bar, over the engine's two entry points"""
        fileMenu = self.menuBar().addMenu('&File')
        fileMenu.addAction('Open file…', 'Ctrl+O', self.onOpenFile)
        fileMenu.addAction('Open URL…', self.onOpenURL)
        fileMenu.addSeparator()
        fileMenu.addAction('Quit', 'Ctrl+Q', self.close)

    def buildPanel(self, parent):
        """The tree of the scene, and what the selected node holds"""
        panel = QtWidgets.QWidget(parent)
        layout = QtWidgets.QVBoxLayout(panel)
        self.tree = QtWidgets.QTreeWidget(panel)
        self.tree.setHeaderLabels(['Node', 'Field'])
        self.tree.setColumnWidth(0, 160)
        self.tree.itemSelectionChanged.connect(self.onSelect)
        self.tree.itemExpanded.connect(self.onOpenRow)
        self.tree.itemCollapsed.connect(self.onCloseRow)
        layout.addWidget(self.tree, 1)

        self.detail = QtWidgets.QPlainTextEdit(panel)
        self.detail.setReadOnly(True)
        self.detail.setMaximumHeight(180)
        layout.addWidget(self.detail)
        self.status = QtWidgets.QLabel('', panel)
        layout.addWidget(self.status)
        return panel

    # -- the menu ---------------------------------------------------------
    def onOpenFile(self):
        chosen, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, 'Open a scene', '', SCENE_FILES)
        if chosen:
            self.open(chosen)

    def onOpenURL(self):
        typed, accepted = QtWidgets.QInputDialog.getText(
            self, 'Open URL', 'Address of a scene:')
        if accepted and typed:
            self.open(typed)

    def open(self, source):
        """Show *source*, which may be a path or a URL

        The load runs on a worker thread, so this returns at once and the
        window keeps drawing what it already has until the scene arrives.
        """
        self.status.setText('Loading %s' % (source,))
        self.view.openSource(source)

    def closeEvent(self, event):
        """Let go of the scene and the GL context as the window goes

        The host owns the loop, so closing this window is not ending the
        process, and ``releaseWindow`` is what gives the driver back every
        texture, buffer and shader the engine uploaded.
        """
        self.watch(None)
        self.outline.close()
        self.view.stopRenderTimer()
        self.view.releaseWindow()
        super().closeEvent(event)

    # -- the scene --------------------------------------------------------
    def onSceneReady(self):
        """A scene the worker thread loaded has been built and swapped in"""
        self.outline.root = self.view.sg
        self.status.setText(str(self.view.source or ''))
        self.fillTree()

    # -- the tree ---------------------------------------------------------
    def fillTree(self):
        """Put the outline's rows in the tree, as it stands now

        Qt's own expand and collapse signals are silenced while this runs: the
        outline is what decides which rows there are, and a row opened here to
        match it would otherwise be reported back as a request to open it.
        """
        selected = self.outline.selection
        self.tree.blockSignals(True)
        try:
            self.tree.clear()
            items = {(): self.tree.invisibleRootItem()}
            for row in self.outline.rows:
                item = QtWidgets.QTreeWidgetItem(
                    items[row.path[:-1]] if row.path else self.tree,
                    [row.label, row.field or ''])
                item.setData(0, PATH_ROLE, row.path)
                items[row.path] = item
                if row.expandable:
                    item.setExpanded(row.path in self.outline.expanded)
                    if row.path not in self.outline.expanded:
                        # A tree draws the arrow for an item that has children,
                        # so a row waiting to be opened is given one to stand
                        # for them.
                        QtWidgets.QTreeWidgetItem(item, ['…'])
                if row.path == selected:
                    item.setSelected(True)
        finally:
            self.tree.blockSignals(False)

    def onOpenRow(self, item):
        """The arrow beside a row was clicked: open it in the model too"""
        path = item.data(0, PATH_ROLE)
        if path is not None:
            self.outline.expand(path)
            self.fillTree()

    def onCloseRow(self, item):
        path = item.data(0, PATH_ROLE)
        if path is not None:
            self.outline.collapse(path)
            self.fillTree()

    def onSelect(self):
        chosen = self.tree.selectedItems()
        self.outline.select(chosen[0].data(0, PATH_ROLE) if chosen else None)
        self.watch(self.outline.selected)
        self.showDetail()

    # -- watching the selected node ---------------------------------------
    def watch(self, node):
        """Follow *node*'s fields, and stop following whatever came before

        Every field of every node announces a change through pydispatcher, so
        a panel showing one node keeps up with an animation moving it, a route
        firing into it, or anything else editing the scene.  The notice can
        come from any thread, so it is emitted rather than acted on.
        """
        if self.watching is not None:
            dispatcher.disconnect(self.onNodeChanged, sender=self.watching)
        self.watching = node
        if node is not None:
            dispatcher.connect(self.onNodeChanged, sender=node)

    def onNodeChanged(self, signal=None, sender=None, **named):
        self.nodeChanged.emit()

    def showDetail(self):
        """Redraw the panel: what the selected node is, and what it holds"""
        row = self.outline.selectedRow
        if row is None:
            lines = ['Nothing selected']
        else:
            lines = ['%s %s' % (row.nodeType, row.defName) if row.defName
                     else row.nodeType]
            lines += ['%s = %s' % pair for pair in nodeSummary(row.node)]
        self.detail.setPlainText('\n'.join(lines))


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    # Before the view: it would make a QGuiApplication of its own otherwise,
    # Qt allows exactly one, and `container` needs the widgets one.
    application = QtWidgets.QApplication(sys.argv)
    window = ViewerWindow(source=argv[0] if argv else None)
    window.show()
    # Qt's timer drives the engine's loop from here on.  Started after the
    # window is shown, since a frame is only drawn once there is a surface.
    window.view.startRenderTimer()
    return application.exec()


if __name__ == '__main__':
    sys.exit(main())
