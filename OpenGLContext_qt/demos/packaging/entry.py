#! /usr/bin/env python
"""What a frozen Qt viewer-demo bundle runs

One executable, named after the command it runs and recognised by the name it
was run under -- see :mod:`OpenGLContext.packaging.multicall`.  A single command
does not need any of that, and it is used here because the table is where a
second one is added, and because most of a bundle's size is the interpreter and
the libraries: an application that ships a tool beside it gets a second
executable for a line here rather than a second bundle.
"""

import sys

from OpenGLContext.packaging.multicall import command_modules, run

#: Executable name -> the ``module:attribute`` it runs.  ``qt-viewer-demo.spec``
#: builds one executable per key and hands ``command_modules(COMMANDS)`` to
#: PyInstaller, so this table is the only place a command is declared.
COMMANDS = {
    'oglc-qt-viewer': 'OpenGLContext_qt.demos.qt_viewer:main',
}

#: The modules to tell a freezer about, since the table above names them as
#: strings.  Read from the ``.spec``.
MODULES = command_modules(COMMANDS)

if __name__ == '__main__':
    sys.exit(run(COMMANDS))
