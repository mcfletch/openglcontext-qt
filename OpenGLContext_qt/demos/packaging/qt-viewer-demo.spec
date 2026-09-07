# -*- mode: python ; coding: utf-8 -*-
"""Freeze the Qt viewer demo into one directory that needs no Python installed

    pyinstaller OpenGLContext_qt/demos/packaging/qt-viewer-demo.spec

The result is ``dist/qt-viewer-demo/``: the executables named in ``entry.py``
beside an ``_internal`` directory holding Python, Qt, the engine and the
libraries under them.

Almost nothing about the engine is described here.  PyOpenGL and OpenGLContext
carry their own PyInstaller hooks -- for the plug-in registries, the generated
resource modules, the shader sources and the GLFW library -- which PyInstaller
finds through their ``pyinstaller40`` entry points, and PySide6 carries one of
its own.  What is left for an application to say is which commands it offers,
which of its own files it opens at run time, and which backends it does not use.

The last of those is the whole of the difference from the Tk bundle in the
engine's own distribution: ``keep=['qt']`` rather than ``keep=['tk']``.  Qt is
the expensive one to carry, and this is the application that wants it.
"""

import os
import runpy

from OpenGLContext import packaging

ENTRY = os.path.join(SPECPATH, 'entry.py')  # noqa: F821 -- PyInstaller defines SPECPATH

# The entry script is read rather than imported: it declares the commands, and
# `runpy` leaves its `__main__` guard alone, so the table is not copied here to
# fall out of step with the one the bundle actually dispatches on.
DECLARED = runpy.run_path(ENTRY)

analysis = Analysis(  # noqa: F821
    [ENTRY],
    hiddenimports=DECLARED['MODULES'],
    # PySide6-Essentials is what this backend needs, and the engine names every
    # other toolkit in its registries; without this a bundle carries whichever
    # of them happen to be installed beside it.
    excludes=packaging.unused_backend_modules(keep=['qt']) + [
        # Qt modules nothing here imports. PySide6's own hook is thorough, and
        # thoroughness is what makes a bundle carrying WebEngine and 3D.
        'PySide6.QtWebEngineCore',
        'PySide6.QtWebEngineWidgets',
        'PySide6.Qt3DCore',
        'PySide6.QtCharts',
        'PySide6.QtMultimedia',
        # Development tooling that some library or other imports conditionally.
        'IPython',
        'matplotlib',
        'pytest',
    ],
    noarchive=False,
)
pyz = PYZ(analysis.pure)  # noqa: F821

# One executable per command, all sharing the single `_internal` directory that
# COLLECT assembles. A console application: the demo takes a scene to open on
# the command line and reports what it could not open, and a windowed build on
# Windows would drop those messages on the floor.
executables = [
    EXE(  # noqa: F821
        pyz,
        analysis.scripts,
        [],
        exclude_binaries=True,
        name=name,
        console=True,
        debug=False,
        strip=False,
        # UPX shrinks a bundle by a third and has a long history of producing
        # one that a virus scanner quarantines or that will not start at all.
        upx=False,
    )
    for name in sorted(DECLARED['COMMANDS'])
]

COLLECT(  # noqa: F821
    *executables,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name='qt-viewer-demo',
)
