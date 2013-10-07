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
try:
    from PySide import QtCore, QtGui, QtOpenGL
except ImportError, err:
    from PyQt4 import QtCore, QtGui, QtOpenGL
import sys 

class QtContext( 
    qtevents.EventHandlerMixin, 
    QtOpenGL.QGLWidget, 
    Context
):
    """Base class for all Qt-based contexts"""
    def __init__ (self, definition = None, parent=None, **named ):
        # set up double buffering and rgb display mode
        definition = self.setDefinition( definition )
        super(QtContext, self).__init__(
            self.formatFromDefinition( definition ), 
            parent,
        )
        self.setAutoBufferSwap( False )
        self.resize( *definition.size )
        Context.__init__ (self, definition)
    
    @classmethod
    def formatFromDefinition( cls, definition ):
        """Create a QGLFormat from definition parameters"""
        format = QtOpenGL.QGLFormat.defaultFormat()
        if hasattr( format, 'setProfile' ):
            if definition.profile == 'compatibility':
                format.setProfile( QtOpenGL.QGLFormat.CompatibilityProfile )
            elif definition.profile == 'core':
                if not definition.version[0]:
                    definition.version = [3,3]
                format.setVersion( *definition.version )
                format.setProfile( QtOpenGL.QGLFormat.CoreProfile )
            else:
                raise ValueError( "Unrecognized profile: %r", definition.profile )
        elif definition.profile != 'compatibility':
            raise RuntimeError( 'Unable to set profile, Qt needs version 4.8+ to set profile' )
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
        self.triggerRedraw(1)
    
    def triggerRedraw( self, force=False ):
        """Override triggerRedraw to do an update call..."""
        result = super( QtContext, self ).triggerRedraw( force )
        if force:
            # TODO: this should *not* be working this way, as it 
            # causes 100% CPU usage, basically there's no idle processing
            # so we have to trigger the next event cascade when we're 
            # done with this one...
            self.update()
        return result
    
    def resizeEvent( self, event ):
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
    
    def ProcessEvent( self, event ):
        result = super( QtContext, self ).ProcessEvent( event )
        return result 
    
    @classmethod
    def ContextMainLoop( cls, *args, **named ):
        """Mainloop for the GLUT testing context"""
        app = QtGui.QApplication(sys.argv)
        widget = cls(*args,**named)
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
