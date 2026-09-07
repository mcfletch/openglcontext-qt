#! /bin/sh
# Build a .deb of the Qt viewer demo, carrying its own Python and its own Qt.
#
#     OpenGLContext_qt/demos/packaging/build-deb.sh
#     OpenGLContext_qt/demos/packaging/build-deb.sh -r requirements-stack.txt
#
# Nothing outside the package is needed to run it: no system Python, no system
# Qt, no virtual environment for the user to make, no pip at install time.  It
# installs under /opt/openglcontext-qt-viewer-demo, links the command into
# /usr/bin and adds a desktop menu entry.  Anything given on the command line is
# passed through to oglc-deb, which is where `-r` for an unreleased stack goes.
#
# What is worth knowing here:
#
#   --backend qt   Nothing of Qt is pruned -- it is a wheel in the environment
#                  rather than part of CPython, which is what pruning touches --
#                  but a package should say what it opens its window with, and
#                  saying so is what makes the Tk build's `--backend tk` more
#                  than an incantation.
#   --menu         which command the menu entry runs.  The default is the one
#                  named after the package, and this package's command is not,
#                  so without this it would install with no entry at all.
#   --bindir       /usr/games and the Game menu category are the defaults, this
#   --categories   being an engine for games; a viewer is a graphics tool.
#
# A Qt package is large -- PySide6-Essentials is most of it.  See
# `docs/packaging.html` in the engine, and `qt-viewer-demo.spec` beside this for
# the frozen bundle, which is the same application delivered the other way.
set -eu

here=$(cd "$(dirname "$0")" && pwd)
runtime=${RUNTIME:-build/runtime}
output=${OUTPUT:-dist}
version=${PYTHON_VERSION:-3.12}

# A relocatable CPython -- one that finds its standard library beside itself
# rather than at a path compiled into it -- which is what lets the environment
# be built here by an ordinary user and run from /opt.
if [ ! -d "$runtime" ]; then
    uv python install --install-dir "$runtime" "$version"
fi

exec oglc-deb \
    --project "$here/deb-project" \
    --runtime "$runtime" \
    --backend qt \
    --command oglc-qt-viewer \
    --menu oglc-qt-viewer \
    --menu-name 'OpenGLContext viewer (Qt)' \
    --section graphics \
    --categories 'Graphics;3DGraphics;Viewer;' \
    --bindir /usr/bin \
    --output "$output" \
    "$@"
