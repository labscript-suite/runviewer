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
    def __init__(self, *args, **kwargs):
        QTabBar.__init__(self, *args, **kwargs)
        self.setAcceptDrops(True)
        
    def mousePressEvent(self, e):
        print 'mousepress', e
        QTabBar.mousePressEvent(self, e)
        
    def mouseMoveEvent(self, e):
        print 'mousemove', e
        drag = QDrag(self)
        
        mimeData = QMimeData()

        drag.setMimeData(mimeData)
        dropAction = drag.start(Qt.MoveAction)
        QTabBar.mouseMoveEvent(self, e)
        
        
    def dragEnterEvent(self, e):
        print 'dragenter', e

#        QTabBar.dragEnterEvent(self,e)
        e.accept()
        
    def dropEvent(self, e):
        print 'dropevent', e
        QTabBar.dropEvent(self, e)
                    
class ViewPort(object):
    def __init__(self, container_layout):
        #ui = QUiLoader().load('viewport.ui')
        tab_widget = QTabWidget()
        tab_bar = DragDropTabBar()
        tab_widget.setTabBar(tab_bar)
        tab_widget.setMovable(True)
                
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
        
        shot = runviewer.Shot('/home/bilbo/20121023T000422_crossed_beam_bec_09.h5')
        trace = shot.traces[0]
        x, y = trace.times, trace.data
        x, y = runviewer.resample(x,y,x.min(),x.max(),100000)
        
        win = pg.GraphicsWindow(title="Basic plotting examples")
        win.resize(800,600)
        p1 = win.addPlot(title="Basic array plotting", x=x, y=y, pen=pen)

if __name__ == '__main__':
    qapplication = QApplication([])
    app = RunViewer()
    qapplication.exec_()


