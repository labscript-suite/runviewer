#####################################################################
#                                                                   #
# resample.pyx                                                      #
#                                                                   #
# Copyright 2014-2018 Monash University                             #
#                                                                   #
# This file is part of the program runviewer, in the labscript      #
# suite (see http://labscriptsuite.org), and is licensed under the  #
# Simplified BSD License. See the license.txt file in the root of   #
# the project for the full license.                                 #
#                                                                   #
#####################################################################

cimport cython
import numpy as np

cdef double NAN = np.nan

@cython.initializedcheck(False)
@cython.boundscheck(False)
@cython.wraparound(False)
@cython.nonecheck(False)
@cython.cdivision(True)
def resample(double [:] x_in, double [:] y_in,
             double [:] x_out, double [:] y_out, double stop_time):
    
    cdef int N_out
    cdef int N_in
    cdef int positive_jump_index
    cdef int negative_jump_index
    cdef double positive_jump_value
    cdef double negative_jump_value
    cdef double jump
    cdef int i
    cdef int j

    N_in = x_in.shape[0]
    N_out = x_out.shape[0]
    with nogil:
        # A couple of special cases that I don't want to have to put extra checks
        # in for:
        if x_out[N_out - 1] < x_in[0] or x_out[0] > stop_time:
            # We're all the way to the left of the data or all the way to the
            # right. Fill with NaNs:
            y_out[:] = NAN
        elif x_out[0] > x_in[N_in - 1]:
            # We're after the final clock tick, but before stop_time
            i = 0
            while i < N_out - 1:
                if x_out[i] < stop_time:
                    y_out[i] = y_in[N_in - 1]
                else:
                    y_out[i] = NAN
                i += 1
        else:
            i = 0
            j = 1
            # Until we get to the data, fill the output array with NaNs (which get
            # ignored when plotted)
            while x_out[i] < x_in[0]:
                y_out[i:i+3] = NAN
                i += 3
            # If we're some way into the data, we need to skip ahead to where we
            # want to get the first datapoint from:
            while x_in[j] < x_out[i]:
                j += 1

            # Get values until we get to the end of the data:

            # Leave one spare for the final data point and one because
            # stepMode=True requires len(y)=len(x)-1
            while j < N_in and i < N_out - 2:  
                # This is 'nearest neighbour on the left' interpolation. It's
                # what we want if none of the source values checked in the
                # upcoming loop are used:
                y_out[i] = y_in[j - 1]
                i += 2
                positive_jump_value = 0
                positive_jump_index = j - 1
                negative_jump_value = 0
                negative_jump_index = j - 1
                # now find the max and min values between this x_out time point and
                # the next x_out timepoint print i
                while j < N_in and x_in[j] < x_out[i]:
                    jump = y_in[j] - y_out[i - 2]
                    # would using this source value cause a bigger positive jump?
                    if jump > 0 and jump > positive_jump_value:
                        positive_jump_value = jump
                        positive_jump_index = j
                    # would using this source value cause a bigger negative jump?
                    elif jump < 0 and jump < negative_jump_value:
                        negative_jump_value = jump
                        negative_jump_index = j
                    j += 1

                if positive_jump_index < negative_jump_index:
                    y_out[i - 1] = y_in[positive_jump_index]
                    y_out[i] = y_in[negative_jump_index]
                    # TODO: We could override the x_out values with
                    # x_in[jump_index]
                else:
                    y_out[i - 1] = y_in[negative_jump_index]
                    y_out[i] = y_in[positive_jump_index]

                i += 1

            # Get the last datapoint:
            if j < N_in:
                # If the sample rate of the raw data is low, then the current j
                # point could be outside the current plot view range If so,
                # decrease j so that we take a value that is within the plot view
                # range.
                if x_in[j] > x_out[N_out - 1] and j > 0:
                    j -= 1

                y_out[i] = y_in[j]
                i += 1
            # Fill the remainder of the array with the last datapoint,
            # if t < stop_time, and then NaNs after that:
            while i < N_out - 1:
                if x_out[i] < stop_time:
                    y_out[i] = y_in[N_in - 1]
                else:
                    y_out[i] = NAN
                i += 1
