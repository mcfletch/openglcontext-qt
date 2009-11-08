#! /usr/bin/env python
"""PyQt OpenGLContext plug-in

Note that this code is BSD licenced, but that PyQT is GPL licenced,
your code that uses this package will likely be constrained by the GPL!
"""
from OpenGL.GL import *
from OpenGLContext.context import Context
from OpenGLContext import contextdefinition
from OpenGLContext import interactivecontext
from OpenGLContext.move import viewplatformmixin
from OpenGLContext import vrmlcontext
from OpenGLContext_qt import qtevents
from PyQt4 import QtCore, QtGui, QtOpenGL, Qt
import sys 

class QtContext( 
    qtevents.EventHandlerMixin, 
    QtOpenGL.QGLWidget, 
    Context
):
    """Base class for all Qt-based contexts"""
    def __init__ (self, definition = None, parent=None, **named ):
        # set up double buffering and rgb display mode
        if definition is None:
            definition = contextdefinition.ContextDefinition( **named )
        else:
            for key,value in named.items():
                setattr( definition, key, value )
        self.contextDefinition = definition
        super(QtContext, self).__init__(
            self.formatFromDefinition( definition ), 
            parent,
        )
        self.setAutoBufferSwap( False )
        Context.__init__ (self, definition)
    
    @classmethod
    def formatFromDefinition( cls, definition ):
        """Create a QGLFormat from definition parameters"""
        format = QtOpenGL.QGLFormat.defaultFormat()
        format.setDoubleBuffer(bool(definition.doubleBuffer))
        format.setStereo(definition.stereo)
        for (df,bset,vset) in [
            (definition.depthBuffer,format.setDepth,format.setDepthBufferSize),
            (definition.stencilBuffer,format.setStencil,format.setStencilBufferSize),
            (definition.multisampleBuffer,None,format.setSampleBuffers),
            (definition.multisampleSamples,None,format.setSamples),
            (definition.accumulationBuffer,format.setAccum,format.setAccumBufferSize),
        ]:
            if df > -1:
                if bset:
                    bset( bool(df) )
                if df and vset:
                    vset( df )
        return format
    
    def setupCallbacks( self ):
        """Setup our Qt-level callbacks"""
        super( QtContext, self ).setupCallbacks()
        self.setFocusPolicy( QtCore.Qt.StrongFocus )
        # TODO: only set mouse tracking if we have handlers for it
        self.setMouseTracking(True)
        
    
    def paintEvent( self, event ):
        """Could override, but not really necessary"""
        #self.setCurrent()
        self.triggerRedraw(1)
        #self.swapBuffers()
    def resizeEvent( self, event ):
        """Could override, but not really necessary"""
        size = event.size()
        self.setCurrent()
        try:
            self.ViewPort( size.width(), size.height() )
        finally:
            self.unsetCurrent()
        self.triggerRedraw(1)
    def setCurrent (self):
        ''' Acquire the GL "focus" '''
        Context.setCurrent( self )
        self.makeCurrent()
    def SwapBuffers (self,):
        """Implementation: swap the buffers"""
        self.swapBuffers()
    @classmethod
    def ContextMainLoop( cls, *args, **named ):
        """Mainloop for the GLUT testing context"""
        app = QtGui.QApplication(sys.argv)
        widget = cls(None)
        widget.resize(640, 480)
        widget.show()
        sys.exit(app.exec_())

class QtInteractiveContext (
	viewplatformmixin.ViewPlatformMixin,
	interactivecontext.InteractiveContext,
	QtContext,
):
	'''Qt context providing camera, mouse and keyboard interaction '''

class VRMLContext(
	vrmlcontext.VRMLContext,
	QtInteractiveContext
):
	"""GLUT-specific VRML97-aware Testing Context"""


if __name__ == "__main__":
    import os
    class TestContext( VRMLContext ):
        def OnInit( self ):
            self.load( sys.argv[1] )
    TestContext.ContextMainLoop()
