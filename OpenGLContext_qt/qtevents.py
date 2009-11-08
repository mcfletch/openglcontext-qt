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
        self.triggerRedraw(1)
#        event.accept()
    def keyReleaseEvent( self, event ):
        """Convert event to context-style event"""
        self.ProcessEvent( QtKeyboardEvent( self, event, 0 ))
        if event.text():
            self.ProcessEvent( QtKeypressEvent( self, event ) )
        self.triggerRedraw(1)
        # TODO: only accept if we have a binding...
#        event.accept()
        
    def mouseMoveEvent(self, event):
        """Convert event to context-style event"""
        self.addPickEvent( QtMouseMoveEvent( self, event ))
        self.triggerPick()
    def mousePressEvent(self, event):
        """Convert event to context-style event"""
        self.addPickEvent( QtMouseButtonEvent( self, event, state=True ))
        self.triggerPick()
    def mouseReleaseEvent( self, event):
        """Convert event to context-style event"""
        self.addPickEvent( QtMouseButtonEvent( self, event, state=False ))
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
            name = unicode(qtEvent.text())
        return name
    BUTTON_MAPPING = ( 
        (0,QtCore.Qt.LeftButton), 
        (1,QtCore.Qt.MidButton), 
        (2,QtCore.Qt.RightButton),
    )
    def _getButton( self, qtEvent ):
        buttons = qtEvent.button()
        for local, marker in self.BUTTON_MAPPING:
            if buttons & marker:
                return local 
        return None
    def _getButtons( self, qtEvent ):
        buttons = qtEvent.buttons()
        pressed = []
        for local, marker in self.BUTTON_MAPPING:
            if buttons & marker:
                pressed.append( local )
        return tuple(pressed)

class QtMouseButtonEvent( QtXEvent, mouseevents.MouseButtonEvent ):
    """Qt-specific mouse button event"""
    BUTTON_MAPPING = ( (0,1), (1,3), (2,2))
    def __init__( self, context, qtEvent, state=0 ):
        super (QtMouseButtonEvent, self).__init__()
        if hasattr( context, 'currentPass'):
            self.renderingPass = context.currentPass
        self.modifiers = self._getModifiers(qtEvent)
        self.button = self._getButton(qtEvent)
        self.state = state
        self.pickPoint = qtEvent.x(), context.getViewPort()[1]- qtEvent.y()
        
class QtMouseMoveEvent( QtXEvent, mouseevents.MouseMoveEvent ):
    """Qt-specific mouse movement event"""
    def __init__( self, context, qtEvent ):
        super (QtMouseMoveEvent, self).__init__()
        if hasattr( context, 'currentPass'):
            self.renderingPass = context.currentPass
        self.modifiers = self._getModifiers(qtEvent)
        self.buttons = self._getButtons(qtEvent)
        self.pickPoint = qtEvent.x(), context.getViewPort()[1]- qtEvent.y()

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
