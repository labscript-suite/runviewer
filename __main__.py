from PySide.QtCore import *
from PySide.QtGui import *
from PySide.QtUiTools import QUiLoader

import h5_lock
import pyqtgraph as pg

import runviewer

from IPython import embed

pg.setConfigOption('background', 'w')
pg.setConfigOption('foreground', 'k')
pg.setConfigOption('useOpenGL', False)
pen = pg.mkPen('k', width=2)

class DragDropTabBar(QTabBar):
    def __init__(self, tab_widget):
        QTabBar.__init__(self)
        self.setAcceptDrops(True)
        self.tab_widget = tab_widget
        self.tab_widget.setTabBar(self)
        self.tab_widget.setMovable(True)
                
    def mousePressEvent(self, e):
        print 'mousepress', e
        QTabBar.mousePressEvent(self, e)
        
    def mouseMoveEvent(self, e):
        
        if (self.x() < e.x() < (self.x() + self.width()) and 
            self.y() < e.y() < (self.y() + self.height())):
            print 'in!'
            QTabBar.mouseMoveEvent(self, e)
        else:
            print 'out!'
            current_index = self.currentIndex()
            print current_index
            text = self.tabText(current_index)
            icon = self.tabIcon(current_index)
            widget = self.tab_widget.currentWidget()
            self.moving_tab = text, icon, widget
            print text, icon, widget
            self.removeTab(current_index)
            drag = QDrag(self)
            mimeData = QMimeData()
            drag.setMimeData(mimeData)
            dropAction = drag.start(Qt.MoveAction)
            print 'foo!'
    
    def dragMoveEvent(self, e):
        QTabBar.mouseMoveEvent(self, e)
        print 'drag move'
    
    def dragLeaveEvent(self, e):
        print 'drag leave'
            
    def dragEnterEvent(self, e):
        text, icon, widget = self.moving_tab
        self.tab_widget.addTab(widget, icon, text)
        print text, icon, widget
        print 'dragenter', e
        e.accept()
        
    def dropEvent(self, e):
        print 'dropevent', e
        QTabBar.dropEvent(self, e)
                    
class ViewPort(object):
    def __init__(self, container_layout):
        #ui = QUiLoader().load('viewport.ui')
        tab_widget = QTabWidget()
        tab_bar = DragDropTabBar(tab_widget)
                
        container_layout.addWidget(tab_widget)
        tab_widget.addTab(QWidget(), 'foo')
        tab_widget.addTab(QWidget(), 'bar')

        
class RunViewer(object):
    def __init__(self):
        # Load the gui:
        ui = QUiLoader().load('main.ui')
        self.window = ui
        container_widgets = [ui.container_1,
                             ui.container_2,
                             ui.container_3,
                             ui.container_4]
        self.viewports = []
        for widget in container_widgets:
            container_layout = widget.layout()
            viewport = ViewPort(container_layout)
            self.viewports.append(viewport)
            
        
        self.window.show()
        
#        shot = runviewer.Shot('/home/bilbo/20121023T000422_crossed_beam_bec_09.h5')
#        trace = shot.traces[0]
#        x, y = trace.times, trace.data
#        x, y = runviewer.resample(x,y,x.min(),x.max(),100000)
#        
#        win = pg.GraphicsWindow(title="Basic plotting examples")
#        win.resize(800,600)
#        p1 = win.addPlot(title="Basic array plotting", x=x, y=y, pen=pen)

if __name__ == '__main__':
    qapplication = QApplication([])
    app = RunViewer()
    qapplication.exec_()


