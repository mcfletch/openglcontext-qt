#!/usr/bin/env python
"""Installs OpenGLContext_qt using distutils

Run:
	python setup.py install
to install the package from the source archive.
"""
from distutils.core import setup
import sys, os
sys.path.insert(0, '.' )

def find_version( ):
	for line in open( os.path.join(
		'OpenGLContext_qt','__init__.py',
	)):
		if line.strip().startswith( '__version__' ):
			return eval(line.strip().split('=')[1].strip())
	raise RuntimeError( """No __version__ = 'string' in __init__.py""" )

version = find_version()

def is_package( path ):
	return os.path.isfile( os.path.join( path, '__init__.py' ))
def find_packages( root ):
	"""Find all packages under this directory"""
	for path, directories, files in os.walk( root ):
		if is_package( path ):
			yield path.replace( '/','.' )

if __name__ == "__main__":
	extraArguments = {
		'classifiers': [
			"""License :: OSI Approved :: BSD License""",
			"""Programming Language :: Python""",
			"""Topic :: Software Development :: Libraries :: Python Modules""",
			"""Topic :: Multimedia :: Graphics :: 3D Rendering""",
			"""Intended Audience :: Developers""",
			"""Environment :: X11 Applications""",
		],
		'keywords': 'PyOpenGL,OpenGL,Context,OpenGLContext,render,3D,TrueType,text,VRML,VRML97,scenegraph',
		'long_description' : """PyQt4 Context for the OpenGLContext rendering engine

Adds a PyQt4-based context to the OpenGLContext rendering engine
using the OpenGLContext plugin system.
""",
		'platforms': ['Linux'],
	}
	### Now the actual set up call
	setup (
		name = "OpenGLContext_qt",
		version = version,
		description = "PyQt4 context for OpenGLContext",
		author = "Mike C. Fletcher",
		author_email = "mcfletch@users.sourceforge.net",
		url = "http://pyopengl.sourceforge.net/context/",
		license = "BSD-style, see license.txt for details",

		packages = list(find_packages('OpenGLContext_qt')),
		# need to add executable scripts too...
		options = {
			'sdist': {
				'formats':['gztar','zip'],
			}
		},
		# non python files of examples      
		**extraArguments
	)
