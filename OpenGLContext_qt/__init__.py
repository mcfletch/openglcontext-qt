"""PyQt4-based OpenGLContext Context implementation

Note that this code is BSD licenced, but that PyQt is GPL licenced,
your code that uses this package will likely be constrained by the GPL!

Note: all of the Contexts defined here are defined in the same 
module, so there is no load-time benefit to using a QtContext
instead of a VRMLContext, though the VRMLContext will do more 
setup/registration when used than the QtContext.
"""
from OpenGLContext.plugins import Context,InteractiveContext,VRMLContext
__version__ = '1.0.0a1'
Context( 
    'qt', 'OpenGLContext_qt.qtcontext.QtContext',
)
InteractiveContext( 
    'qt', 'OpenGLContext_qt.qtcontext.QtInteractiveContext',
)
VRMLContext( 
    'qt', 'OpenGLContext_qt.qtcontext.VRMLContext',
)
