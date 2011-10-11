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
    if (!PyArg_ParseTuple(args, "OOOO!", &arg1, &arg2, &arg3,
        &PyArray_Type, &out)) return NULL;

    // Convert the input objects to np arrays:
    x_in = PyArray_FROM_OTF(arg1, NPY_FLOAT, NPY_IN_ARRAY);
    if (x_in == NULL) return NULL;
    y_in = PyArray_FROM_OTF(arg2, NPY_FLOAT, NPY_IN_ARRAY);
    if (y_in == NULL) goto fail;
    x_out = PyArray_FROM_OTF(arg3, NPY_FLOAT, NPY_IN_ARRAY);
    if (x_out == NULL) goto fail;
    y_out = PyArray_FROM_OTF(out, NPY_FLOAT, NPY_INOUT_ARRAY);
    if (y_out == NULL) goto fail;
    
    // The data contained in the np arrays:
    float * x_in_data;
    float * x_out_data;
    float * y_in_data;
    float * y_out_data;
    
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
    
    i = 0;
    j = 1;
    
    // Until we get to the data, fill the output array with NaNs (which
    // get ignored when plotted)
    while(x_out_data[i] < x_in_data[0]){
        y_out_data[i] = 0.0/0.0;
        i++;
    }
    // If we're some way into the data, we need to skip ahead to where
    // we want to get the first datapoint from:
    while(x_in_data[j] < x_out_data[i]){
        j++;
    }
    // Get the first datapoint:
    y_out_data[i] = y_in_data[j-1];
    i++;
    // Get values until we get to the end of the data:
    while((j < n_in) && (i < n_out)){
        // This is 'nearest neighbour on the left' interpolation. It's
        // what we want if none of the source values checked in the
        // upcoming loop are used:
        y_out_data[i] = y_in_data[j-1];
        while((j < n_in) && (x_in_data[j] < x_out_data[i])){
            // Would using this source value cause the interpolated values
            // to make a bigger jump?
            if(abs(y_in_data[j] - y_out_data[i-1]) > abs(y_out_data[i] - y_out_data[i-1])){
                // If so, use this source value:
                y_out_data[i] = y_in_data[j];
            }
            j++;
        }
        i++;
    }
    // Get the last datapoint, if we got that far:
    if(i < n_out){
        y_out_data[i] = y_in_data[n_in - 1];
        i++;
    }
    // Fill the remainder of the array with NaNs:
    while(i < n_out){
        y_out_data[i] = 0.0/0.0;
        i++;
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
