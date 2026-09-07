"""The Qt demo's packaging: the commands it names as strings still resolve.

A frozen bundle and a Debian package each declare their command as text -- a
``module:attribute`` in `entry.py`, a `[project.scripts]` line in the deb
project -- so a renamed module or a renamed ``main`` breaks neither a test nor
an import, only a build that nobody runs until a release.  These resolve them.

The builds themselves are not run here: a Qt bundle is large enough that doing
it on every push would be most of a run.  The engine's own distribution has the
same pair for Tk, and builds and runs both by hand; what those need from the
engine is held by its `test_packaging.py`, `test_appdir.py` and `test_deb.py`.

See `OpenGLContext_qt/demos/packaging/README.md`.
"""

import importlib
import os
import runpy
import tomllib

import OpenGLContext_qt

PACKAGING = os.path.join(os.path.dirname(OpenGLContext_qt.__file__),
                         'demos', 'packaging')


def commands():
    """The ``{name: 'module:attribute'}`` table the entry script declares"""
    return runpy.run_path(os.path.join(PACKAGING, 'entry.py'))['COMMANDS']


def scripts():
    """The ``[project.scripts]`` of the distribution the package is built from"""
    with open(os.path.join(PACKAGING, 'deb-project', 'pyproject.toml'),
              'rb') as source:
        return tomllib.load(source)['project']['scripts']


def resolve(target):
    """The callable a ``module:attribute`` string names"""
    module, _, attribute = target.partition(':')
    return getattr(importlib.import_module(module), attribute)


class TestTheCommandsResolve:
    def test_every_frozen_command_names_something_callable(self):
        for name, target in commands().items():
            assert callable(resolve(target)), '%s -> %s' % (name, target)

    def test_every_packaged_script_names_something_callable(self):
        for name, target in scripts().items():
            assert callable(resolve(target)), '%s -> %s' % (name, target)

    def test_the_two_deliver_the_same_application(self):
        assert scripts() == commands()

    def test_the_freezer_is_told_about_them(self):
        """They are named as strings, so nothing following imports finds them."""
        declared = runpy.run_path(os.path.join(PACKAGING, 'entry.py'))
        for target in declared['COMMANDS'].values():
            assert target.partition(':')[0] in declared['MODULES']


class TestWhatTheBuildsAreToldAboutQt:
    def test_the_bundle_keeps_qt_and_leaves_the_rest(self):
        from OpenGLContext import packaging

        excluded = packaging.unused_backend_modules(keep=['qt'])
        assert 'PySide6' not in excluded
        assert 'tkinter' in excluded and 'wx' in excluded

    def test_the_package_says_which_backend_it_opens_a_window_with(self):
        with open(os.path.join(PACKAGING, 'build-deb.sh')) as script:
            assert '--backend qt' in script.read()

    def test_the_deb_project_depends_on_this_distribution(self):
        with open(os.path.join(PACKAGING, 'deb-project', 'pyproject.toml'),
                  'rb') as source:
            project = tomllib.load(source)['project']
        assert 'OpenGLContext-qt' in project['dependencies']
