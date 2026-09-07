# Shipping the Qt viewer demo

The two ways an application built on this backend reaches somebody who has no
Python and no Qt.  The engine's own distribution has the same pair for the Tk
demo, in `OpenGLContext/demos/packaging/`, and the two are worth reading
together: what differs between them is one word in each file.

## A frozen bundle

    pyinstaller OpenGLContext_qt/demos/packaging/qt-viewer-demo.spec

`dist/qt-viewer-demo/` is then a directory holding a Python runtime, Qt, the
engine and the demo, entered through `oglc-qt-viewer`.  Zip it and it runs on a
machine with a graphics driver and nothing else.

* [`qt-viewer-demo.spec`](qt-viewer-demo.spec) -- what PyInstaller is told.
  `unused_backend_modules(keep=['qt'])` leaves out the toolkits this application
  does not use; the Qt modules listed beside it are ones PySide6's own hook is
  thorough enough to collect and nothing here imports.
* [`entry.py`](entry.py) -- the commands the bundle offers, one executable each
  from a single copy of the libraries.

## A Debian package

    OpenGLContext_qt/demos/packaging/build-deb.sh

`dist/openglcontext-qt-viewer-demo_1.0.0-1_amd64.deb` installs under
`/opt/openglcontext-qt-viewer-demo`, links `oglc-qt-viewer` into `/usr/bin` and
adds a desktop menu entry.  It carries its own Python and its own Qt.

* [`build-deb.sh`](build-deb.sh) -- fetches a relocatable CPython and calls
  `oglc-deb`; the options are commented in it.
* [`deb-project/`](deb-project) -- the demo as a *distribution*.  A package needs
  a console script to put in `/usr/bin` and to name in a menu entry, and
  `OpenGLContext_qt.demos` deliberately declares none, so shipping one means
  making it an application.

Until the engine stack is on PyPI, pass the requirements file that pins it:

    OpenGLContext_qt/demos/packaging/build-deb.sh -r requirements-stack.txt

## What is verified, and what is not

The Tk pair these are written from has been built and run: the bundle renders a
frame, and the package installs, puts its command in `/usr/bin` and renders one
from there.  These two have not, a Qt build being large enough that doing it on
every push would be most of a test run.  What the suites hold is the part that
drifts: `entry.py` and `deb-project` name their command as a string, and
`tests/test_demo_packaging.py` resolves those strings, so a renamed module or a
renamed `main` fails there rather than in a build nobody runs until a release.
