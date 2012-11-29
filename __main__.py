from PySide import QtGui, QtCore
import h5_lock
import pyqtgraph as pg

pg.setConfigOption('background', 'w')
pg.setConfigOption('foreground', 'k')
pg.setConfigOption('useOpenGL', False)
pen = pg.mkPen('k', width=2)

import runviewer
shot = runviewer.Shot('/home/bilbo/20121023T000422_crossed_beam_bec_09.h5')
trace = shot.traces[0]
x, y = trace.times, trace.data

app = QtGui.QApplication([])

win = pg.GraphicsWindow(title="Basic plotting examples")
win.resize(800,600)

p1 = win.addPlot(title="Basic array plotting", x=x, y=y, pen=pen)

app.exec_()


