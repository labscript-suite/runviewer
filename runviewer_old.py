#!/usr/bin/env python
"""
show how to add a matplotlib FigureCanvasGTK or FigureCanvasGTKAgg widget to a
gtk.Window
"""

import gtk

from matplotlib.figure import Figure
from numpy import arange, sin, pi

# uncomment to select /GTK/GTKAgg/GTKCairo
#from matplotlib.backends.backend_gtk import FigureCanvasGTK as FigureCanvas
from matplotlib.backends.backend_gtkagg import FigureCanvasGTKAgg as FigureCanvas
#from matplotlib.backends.backend_gtkcairo import FigureCanvasGTKCairo as FigureCanvas


win = gtk.Window()
win.connect("destroy", lambda x: gtk.main_quit())
win.set_default_size(400,300)
win.set_title("Labscript experiment preview")

f = Figure(figsize=(5,4), dpi=100)
a = f.add_subplot(411)
t = arange(0.0,30.0,0.01)
s = sin(2*pi*t)
a.plot(t,s)
a2 = f.add_subplot(412)
a2.plot(t,s)
a3 = f.add_subplot(413)
a3.plot(t,s)
a4 = f.add_subplot(414)
a4.plot(t,s)
canvas = FigureCanvas(f)  # a gtk.DrawingArea
win.add(canvas)

dy = 0.1
dx = 0.1

class Callbacks:
    def onscroll(self, event):
        print event.button, event.key, event.button, event.step, event.inaxes
        if event.key == 'control' and event.inaxes:
            xmin, xmax, ymin, ymax = event.inaxes.axis()
            event.inaxes.set_ylim(ymin + event.step*dy, ymax + event.step*dy)
        else:
            for axis in [a, a2, a3, a4]:
                xmin, xmax, ymin, ymax = axis.axis()
                axis.set_xlim(xmin + event.step*dy, xmax + event.step*dx)
        canvas.draw_idle()


callbacks = Callbacks()
canvas.mpl_connect('scroll_event',callbacks.onscroll)

win.show_all()
gtk.main()





