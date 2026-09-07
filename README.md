# OpenGLContext-qt

A Qt 6 / PySide6 backend for [OpenGLContext](https://github.com/mcfletch/openglcontext),
so an OpenGLContext scene can be a window in a Qt application — or an
application of its own that happens to be built on Qt.

The backend registers itself with OpenGLContext's plugin system under the name
`qt`, and supports both the compatibility (fixed-function) and core
(shader) profiles along with the rest of the `ContextDefinition` fields.

## Installation

```bash
pip install OpenGLContext-qt
```

That brings in OpenGLContext and `PySide6-Essentials`. The full `PySide6`
metapackage works just as well if you already have it — the Addons half of it
is not used here.

## Usage

Your code never has to import this package. Importing it is what registers the
backend — but `OpenGLContext/__init__.py` does that itself, in a try/except, so
`import OpenGLContext` picks up the `qt` plugin whenever this package is
installed and silently does not when it is not. Choosing the backend is
therefore all an application does:

```bash
OPENGLCONTEXT_BACKEND=qt oglc-gltf model.gltf
```

In code, either ask OpenGLContext for the backend by name:

```python
from OpenGLContext.context import Context

BaseContext = Context.getContextType('qt')
```

or subclass a Qt context directly:

```python
from OpenGLContext.scenegraph import basenodes
from OpenGLContext_qt.qtcontext import QtViewerContext


class MyContext(QtViewerContext):
    def OnInit(self):
        self.sg = basenodes.sceneGraph(children=[
            basenodes.Shape(geometry=basenodes.Teapot()),
        ])


if __name__ == '__main__':
    MyContext.ContextMainLoop()
```

Three contexts are available, matching the rest of OpenGLContext:

| Class                  | What it adds                                          |
| ---------------------- | ----------------------------------------------------- |
| `QtContext`            | A window, a GL context, and the render loop           |
| `QtInteractiveContext` | Camera movement, mouse and keyboard interaction       |
| `QtViewerContext`      | Opening a scene file: VRML97, OBJ or glTF             |

### Inside a Qt application

Creating a context creates a `QGuiApplication` only if there is not one
already, so a context can be created inside a program that has built its own
application object -- and equally in a program that has built nothing, which is
what a test, a benchmark or a script stepping frames for itself is. Qt requires
an application before any window exists and ends the process where there is
none, so the context asks for one however it is built rather than only on the
way into `ContextMainLoop`. Whichever call made the application owns it, and
only its own windows may end it (see **Closing a view** below).

To place the view in a widget layout, wrap it with `container()`:

```python
from PySide6 import QtWidgets

app = QtWidgets.QApplication([])
window = QtWidgets.QMainWindow()

view = MyContext()
window.setCentralWidget(view.container())
window.show()

view.MainLoop()
```

`OpenGLContext_qt/demos/qt_viewer.py` is the whole of that as a program to
read: a menu bar, a tree of the scene, and the engine's own viewer beside it,
with Qt owning the loop.

```bash
python -m OpenGLContext_qt.demos.qt_viewer model.glb
```

The same program in Tk and wx ships with the engine, in `OpenGLContext/demos/`,
and `docs/embedding.html` there covers what each toolkit needs.

Escape quits, as it does under every OpenGLContext backend — but only the
process it started. A context created inside somebody else's `QApplication`
closes its own window and leaves the host program running. Rebind the key if
you want something else:

```python
view.addEventHandler('keyboard', name='<escape>', function=my_handler)
```

**Closing a view.** `OnQuit()` is the orderly shutdown — pointer handed back,
render timer stopped, GL objects released, window closed — and for a context
that did not create the application it returns instead of ending the process.
Once it has, the context can be dropped like any other object; opening and
closing views for the life of a session is a supported thing to do.

## How it works

### A `QWindow`, not a `QOpenGLWidget`

The context is a `QWindow` with a `QOpenGLContext` of its own. A
`QOpenGLWidget` renders into a framebuffer object that Qt composites, so *its*
screen is not framebuffer 0 — and OpenGLContext's render passes bind
framebuffer 0 whenever they finish with one of their own: the bloom composite,
the selection buffer's blit, the back-buffer read behind every screenshot.
Under a `QOpenGLWidget` each of those would quietly go to the wrong target. A
`QWindow` draws to a real window surface, so every render path behaves exactly
as it does under the GLUT and GLFW backends. `container()` is how such a
window joins a widget interface.

### Desktop OpenGL, explicitly

The surface format asks for desktop OpenGL by name. Qt's default renderable
type is whatever the platform integration prefers, which under EGL — Wayland,
and X11 on many drivers — is OpenGL ES; a core-profile request without that is
refused outright there, and the ES context that a profile-less request produces
has none of the entry points PyOpenGL calls. A context that comes back as
OpenGL ES anyway is reported as an error rather than left to fail later inside
a shader.

### The render loop

Rendering runs from a Qt timer rather than from paint events. A frame is an
event cascade followed by a render; only the cascade always has work
(animations, timers, queued events) and only sometimes is there something new
to draw. The timer expresses that directly, and lets a burst of input events
coalesce into one render instead of forcing a render each. Its interval is
`drawPollTimeout`, and `OPENGLCONTEXT_STALL_MS` reports the phases of an
iteration the same way it does for the other backends.

## ContextDefinition support

Every field of `ContextDefinition` that describes the window is mapped to the
Qt surface format:

| Field                                     | Qt                                              |
| ----------------------------------------- | ----------------------------------------------- |
| `size`, `title`                           | window size and title                           |
| `profile`, `version`                      | `setProfile` / `setVersion`; `core` implies 3.3 |
| `doubleBuffer`                            | `setSwapBehavior`                               |
| `depthBuffer`, `stencilBuffer`            | buffer sizes (depth defaults to 24)             |
| `rgb`, `alpha`                            | colour channel sizes                            |
| `multisampleBuffer`, `multisampleSamples` | `setSamples`                                    |
| `stereo`                                  | `setStereo`                                     |
| `debug`                                   | `DebugContext`                                  |
| `vsync`                                   | `setSwapInterval`                               |
| `profileFile`                             | `cProfile` around the main loop                 |
| `pickEnabled`, `pickAsync`, `debug*`      | read by the engine, backend-independent         |

The rendering features — `shadows`, `bloom`, `ibl`, `transmission`,
`instancing`, `tessellationLOD`, `maximumLights`, `uiScale`, `audio` and the
rest — are read from the definition by the render passes, so they behave here
exactly as under any other backend, including live changes from the settings
overlay.

Three things are worth knowing:

- **`accumulationBuffer` does not exist.** Qt 6 dropped it with the
  fixed-function pipeline that used it. Asking for one logs a warning.
- **`vsync` is settled when the window is created.** The swap interval is part
  of the surface format, which cannot be changed for a live GL context, so a
  change made in the settings overlay is reported and takes effect next run.
- **`OPENGLCONTEXT_HIDDEN` is not supported.** Qt's offscreen surfaces have no
  default framebuffer to render into on the common EGL platforms. Use the
  `glfw` backend for headless capture.

## Mouse-look

`setPointerCapture` hides the pointer, grabs it, and warps it back to the
middle of the window after each movement, which is what makes the motion
unbounded — a pointer that stops at the edge of the screen is a view that stops
turning there. The warp comes back as an ordinary movement and is recognised
and discarded, so it does not cancel the movement that provoked it.

Both halves are requests the window system may refuse. Qt's Wayland plugin
grabs the pointer only for popup windows, and a Wayland compositor does not let
a client place the pointer at all. `setPointerCapture` answers **whether the
pointer was really taken**, so an application offering mouse-look can say so
instead of leaving the player to discover it; the cursor is hidden either way,
and turning then works inside the window and stops at its edge. A platform that
refuses is asked once and believed, so a mode entered and left repeatedly does
not fill the log with the same refusal.

## Development

```bash
pip install -e ".[dev]"
pytest            # the GL tests need a plugin that can render
ruff check .
```

The tests that render skip themselves, saying so, when the Qt platform plugin
in use gives no drawable GL surface — so a green run that rendered nothing is
visible rather than silent. Where that happens, name a plugin that works:

```bash
QT_QPA_PLATFORM=xcb pytest
```

## License

BSD-style; see [license.txt](license.txt). PySide6 is the Qt Company's own
bindings and is LGPL — a runtime dependency, with no Qt or PySide6 code copied
into this package.
