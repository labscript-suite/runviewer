Introduction
============

Runviewer is used for viewing, graphically, the expected changes in each output across one
or more shots, and is shown in :numref:`fig-interface`. Its use is optional, but can be extremely useful for
debugging the behaviour of experiment logic. The output traces are generated directly from
the set of hardware instructions stored in a given hdf5 file. This provides a faithful representation
of what the hardware will actually do. In effect, runviewer provides a low level
representation of the experiment, which complements the high level representation provided
by the experiment logic written using the labscript API. As such, runviewer traces provide
a way to view the quantisation of outputs, [2]_ which can be seen in the `central_Bq` and
`central_bias_z_coil` channels in :numref:`fig-interface`. You can also view the pseudoclock outputs.
The `pulseblaster_0_ni_clock` and `pulseblaster_0_novatech_clock` channels demonstrate
the independent clocking of devices from a single PulseBlaster pseudoclock. Similarly,
`pulseblaster_1_clock` shows an entirely independent secondary pseudoclock.

.. _fig-interface:

.. figure:: img/runviewer_interface.png
    :alt: Runviewer runviewer

    An example of the runviewer interface.

.. rubric:: Footnotes

.. [1] Documentation taken from Starkey, Phillip T. *A software framework for control and automation of precisely timed experiments*
    PhD Thesis, Monash University (2019) https://doi.org/10.26180/5d1db8ffe29ef

.. [2] While this is always true in time, the output values may not be correctly quantised if the labscript
    device implementation does not quantise the output values correctly and instead relies on BLACS, 
    the device programming API or the device firmware, to correctly quantise the output values.