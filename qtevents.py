"""Module providing translation from wxPython events to OpenGLContext events"""
from OpenGLContext.events import mouseevents, keyboardevents, eventhandlermixin
from PyQt4 import QtCore, QtGui, QtOpenGL
import time

class EventHandlerMixin( eventhandlermixin.EventHandlerMixin):
    """Qt-specific event handler mix-in

    Basically provides translation from Qt4 events
    to their OpenGLContext-specific equivalents (the
    concrete versions of which are also defined in this
    module).
    """
    ### KEYBOARD interactions
    
    def keyPressEvent(self, event ):
        """Convert event to context-style event"""
        self.ProcessEvent( QtKeyboardEvent( self, event, 1 ))
    def keyReleaseEvent( self, event ):
        """Convert event to context-style event"""
        self.ProcessEvent( QtKeyboardEvent( self, event, 0 ))
        if event.text():
            QtKeypressEvent( self, event )
        # TODO: only accept if we have a binding...
        event.accept()
        
    def mousePressEvent(self, event):
        """Convert event to context-style event"""
    def mouseMoveEvent(self, event):
        """Convert event to context-style event"""
    def mouseReleaseEvent( self, event):
        """Convert event to context-style event"""
        
    def wxOnKeyDown( self, event ):
        '''Convert a key-press to a context-style event'''
        self.ProcessEvent( wxKeyboardEvent( self, event, 1))
        event.Skip()
    def wxOnKeyUp( self, event ):
        '''Convert a key-release to a context-style event'''
        self.ProcessEvent( wxKeyboardEvent( self, event, 0))
    def wxOnCharacter( self, event ):
        """Convert character (non-control) press to context event"""
        self.ProcessEvent( wxKeypressEvent( self, event))
    ### MOUSE Interaction
    def wxOnMouseButton(self, event ):
        """Convert mouse-button event to context event"""
        self.addPickEvent( wxMouseButtonEvent( self, event))
        self.triggerPick()
    def wxOnMouseMove(self, event ):
        """Convert mouse-movement event to context event"""
        self.addPickEvent( wxMouseMoveEvent( self, event))
        self.triggerPick()

class QtXEvent(object):
    """Base-class for all Qt-specific event classes
    """
    def _getModifiers( self, qtEventObject):
        """Get a three-tupple of shift, control, alt status"""
        mods = qtEventObject.modifiers()
        return (
            bool(mods & QtCore.Qt.ShiftModifier),
            bool(mods & QtCore.Qt.ControlModifier),
            bool(mods & QtCore.Qt.AltModifier),
        )
    def _getName( self, qtEvent ):
        key = qtEvent.key()
        if key in keyboardMapping:
            name = keyboardMapping[key] 
        else:
            name = qtEvent.text()
        return name
        
#
#class wxMouseButtonEvent( wxXEvent, mouseevents.MouseButtonEvent ):
#    """wxPython-specific mouse button event"""
#    BUTTON_MAPPING = ( (0,1), (1,3), (2,2))
#    def __init__( self, context, wxEventObject ):
#        super (wxMouseButtonEvent, self).__init__()
#        if hasattr( context, 'currentPass'):
#            self.renderingPass = context.currentPass
#        self.modifiers = self._getModifiers(wxEventObject)
#        self.button = None
#        for local, wx in self.BUTTON_MAPPING:
#            if wx == wxEventObject.Button:
#                self.button = local
#                self.state = wxEventObject.ButtonDown( wx )
#                break 
#        if self.button is None:
#            for local,wx in self.self.BUTTON_MAPPING:
#                if wxEventObject.Button( wx ):
#                    self.button = local
#                    self.state = wxEventObject.ButtonDown( wx )
#                    break
#        self.pickPoint = wxEventObject.GetX(), context.getViewPort()[1]- wxEventObject.GetY()
#        
#class wxMouseMoveEvent( wxXEvent, mouseevents.MouseMoveEvent ):
#    """wxPython-specific mouse movement event"""
#    def __init__( self, context, wxEventObject ):
#        super (wxMouseMoveEvent, self).__init__()
#        if hasattr( context, 'currentPass'):
#            self.renderingPass = context.currentPass
#        self.modifiers = self._getModifiers(wxEventObject)
#        buttons = []
#        for local, method in ( (0,"LeftIsDown"), (1,"MiddleIsDown"), (2,"RightIsDown")):
#            if getattr( wxEventObject, method )():
#                buttons.append( local )
#        self.buttons = tuple( buttons )
#        self.pickPoint = wxEventObject.GetX(), context.getViewPort()[1]- wxEventObject.GetY()

class QtKeyboardEvent( QtXEvent, keyboardevents.KeyboardEvent ):
    """Qt-specific keyboard event"""
    def __init__( self, context, qtEvent, state=0 ):
        super (QtKeyboardEvent, self).__init__()
        if hasattr( context, 'currentPass'):
            self.renderingPass = context.currentPass
        self.modifiers = self._getModifiers(qtEvent)
        self.name = self._getName( qtEvent )
        self.state = state
class QtKeypressEvent( QtXEvent,keyboardevents.KeypressEvent ):
    """Qt-specific key-press event"""
    def __init__( self, context, qtEvent):
        super (QtKeypressEvent, self).__init__()
        if hasattr( context, 'currentPass'):
            self.renderingPass = context.currentPass
        self.modifiers = self._getModifiers(qtEvent)
        self.name = self._getName( qtEvent )

keyboardMapping = {
    QtCore.Qt.Key_Tab: '<tab>',
    QtCore.Qt.Key_Backspace: '<backspace>',
    QtCore.Qt.Key_Return: '<return>',
    QtCore.Qt.Key_Escape: '<escape>',
    QtCore.Qt.Key_Insert: '<insert>',
    QtCore.Qt.Key_Enter: '<return>',
    QtCore.Qt.Key_Delete: '<delete>',
    QtCore.Qt.Key_Pause: '<pause>',
    QtCore.Qt.Key_Print: '<print>',
    QtCore.Qt.Key_Home: '<home>',
    QtCore.Qt.Key_End: '<end>',
    QtCore.Qt.Key_Left: '<left>',
    QtCore.Qt.Key_Right: '<right>',
    QtCore.Qt.Key_Up: '<up>',
    QtCore.Qt.Key_Down: '<down>',
    QtCore.Qt.Key_PageUp: '<pageup>',
    QtCore.Qt.Key_PageDown: '<pagedown>',
    QtCore.Qt.Key_Shift: '<shift>',
    QtCore.Qt.Key_Control: '<ctrl>',
    QtCore.Qt.Key_Alt: '<alt>',
    QtCore.Qt.Key_Space: ' ',
    QtCore.Qt.Key_PageDown: '<pagedown>',
    QtCore.Qt.Key_PageDown: '<pagedown>',
    QtCore.Qt.Key_CapsLock: '<capslock>',
    QtCore.Qt.Key_NumLock: '<numlock>',
    QtCore.Qt.Key_ScrollLock: '<scroll>',
    QtCore.Qt.Key_Back: '<back>',
    QtCore.Qt.Key_Forward: '<forward>',
}
for i in range( 1,35 ):
    keyboardMapping[ getattr( QtCore.Qt,'Key_F%s'%(i,))] = '<F%s>'%(i,)
del i
