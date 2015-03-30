///////////////////////////////////////////////////////////////////////
//                                                                   //
// /resample.c                                                       //
//                                                                   //
// Copyright 2014, Monash University                                 //
//                                                                   //
// This file is part of the program runviewer, in the labscript      //
// suite (see http://labscriptsuite.org), and is licensed under the  //
// Simplified BSD License. See the license.txt file in the root of   //
// the project for the full license.                                 //
//                                                                   //
///////////////////////////////////////////////////////////////////////

#include "Python.h"
#include "math.h"
#include "numpy/arrayobject.h"
#include <stdio.h>

static PyObject *
resample(PyObject *dummy, PyObject *args)
{
    // Parse the input arguments:
    PyObject *arg1=NULL, *arg2=NULL, *arg3=NULL, *out=NULL;
    PyObject *x_in=NULL, *y_in=NULL, *x_out=NULL, *y_out=NULL; 
    double stop_time;
    
    if (!PyArg_ParseTuple(args, "OOOO!d", &arg1, &arg2, &arg3,
        &PyArray_Type, &out, &stop_time)) return NULL;

    // Convert the input objects to np arrays:
    x_in = PyArray_FROM_OTF(arg1, NPY_FLOAT64, NPY_IN_ARRAY);
    if (x_in == NULL) return NULL;
    y_in = PyArray_FROM_OTF(arg2, NPY_FLOAT64, NPY_IN_ARRAY);
    if (y_in == NULL) goto fail;
    x_out = PyArray_FROM_OTF(arg3, NPY_FLOAT64, NPY_IN_ARRAY);
    if (x_out == NULL) goto fail;
    y_out = PyArray_FROM_OTF(out, NPY_FLOAT64, NPY_INOUT_ARRAY);
    if (y_out == NULL) goto fail;
    
    // The data contained in the np arrays:
    double * x_in_data;
    double * x_out_data;
    double * y_in_data;
    double * y_out_data;
    
    x_in_data = PyArray_DATA(x_in);
    x_out_data = PyArray_DATA(x_out);
    y_in_data = PyArray_DATA(y_in);
    y_out_data = PyArray_DATA(y_out);
    
    // The length of the input and output arrays:
    int n_in;
    int n_out;
    
    n_in = ((npy_intp *)PyArray_DIMS(x_in))[0];
    n_out = ((npy_intp *)PyArray_DIMS(x_out))[0];
    
    // The indices for traversing th input and output arrays:
    int i;
    int j;
    
    //storage of jump values (for determining locations of max/min points within a time step)
    double positive_jump_value;
    int positive_jump_index;
    double negative_jump_value;
    int negative_jump_index;
    double jump;
    
    i = 0;
    j = 1;
    // A couple of special cases that I don't want to have to put extra checks in for:
    if(x_out_data[n_out - 1] < x_in_data[0] || x_out_data[0] > stop_time){
        // We're all the way to the left of the data or all the way to the right. Fill with NaNs:
        while(i < n_out-1){
            y_out_data[i] = 0.0/0.0;
            i++;
        }
    }
    else if(x_out_data[0] > x_in_data[n_in-1]){
        // We're after the final clock tick, but before stop_time
        while(i < n_out-1){
            if(x_out_data[i] < stop_time){
                y_out_data[i] = y_in_data[n_in-1];
            }
            else{
                y_out_data[i] = 0.0/0.0;
            }
            i++;
        }
    }
    else{
        // Until we get to the data, fill the output array with NaNs (which
        // get ignored when plotted)
        while(x_out_data[i] < x_in_data[0]){
            y_out_data[i++] = 0.0/0.0;
            y_out_data[i++] = 0.0/0.0;
            y_out_data[i++] = 0.0/0.0;
        }
        // If we're some way into the data, we need to skip ahead to where
        // we want to get the first datapoint from:
        while(x_in_data[j] < x_out_data[i]){
            j++;
        }
        // Get the first datapoint:
        //y_out_data[i] = y_in_data[j-1];
        //i++;
        // Get values until we get to the end of the data:
        while((j < n_in) && (i < n_out-2)){
            // This is 'nearest neighbour on the left' interpolation. It's
            // what we want if none of the source values checked in the
            // upcoming loop are used:
            y_out_data[i] = y_in_data[j-1];
            i+= 2;
            positive_jump_value = 0;
            positive_jump_index = j-1;
            negative_jump_value = 0;
            negative_jump_index = j-1;
            while((j < n_in) && (x_in_data[j] < x_out_data[i])){
                jump = y_in_data[j] - y_out_data[i-2];
                // would using this source value cause a bigger positive jump?
                if (jump > 0 && jump > positive_jump_value)
                {
                    positive_jump_value = jump;
                    positive_jump_index = j;
                }
                // would using this source value cause a bigger negative jump?
                else if (jump < 0 && jump < negative_jump_value)
                {
                    negative_jump_value = jump;
                    negative_jump_index = j;
                }
                j++;
            }
            
            if (positive_jump_index < negative_jump_index)
            {
                y_out_data[i-1] = y_in_data[positive_jump_index];
                y_out_data[i] = y_in_data[negative_jump_index];
                // TODO: We could override the x_out values with x_in[jump_index]
            }
            else
            {
                y_out_data[i-1] = y_in_data[negative_jump_index];
                y_out_data[i] = y_in_data[positive_jump_index];
            }
            i++;
        }
        // Get the last datapoint, if we got that far:
        if(j < n_in){
            // If the sample rate of the raw data is low, then the current
            // j point could be outside the current plot view range
            // If so, decrease j so that we take a value that is within the 
            // plot view range.
            if(x_in_data[j] > x_out_data[n_out-1] && j > 0){
                j--;
            }
            y_out_data[i] = y_in_data[j];
            i++;
        }
        // Fill the remainder of the array with the last datapoint,
        // if t < stop_time, and then NaNs after that:
        while(i < n_out-1){
            if(x_out_data[i] < stop_time){
                y_out_data[i] = y_in_data[n_in-1];
            }
            else{
                y_out_data[i] = 0.0/0.0;
            }
            i++;
        }
    }
    
    Py_DECREF(x_in);
    Py_DECREF(y_in);
    Py_DECREF(x_out);
    Py_DECREF(y_out);
    Py_INCREF(Py_None);
    return Py_None;

 fail:
    Py_XDECREF(x_in);
    Py_XDECREF(y_in);
    Py_XDECREF(x_out);
    PyArray_XDECREF_ERR(y_out);
    return NULL;
}

static PyMethodDef 
module_functions[] = {
    {"resample", resample, METH_VARARGS, ""},
    {NULL}
};

void 
initresample(void)
{
   Py_InitModule3("resample", module_functions,"");
   import_array();
}
