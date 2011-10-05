#include "Python.h"
#include "numpy/arrayobject.h"
#include <stdio.h>

static PyObject * 
hello_world(PyObject *self, PyObject *args)
{
    return Py_BuildValue("s","hello, world!");
}

static PyObject *
resample(PyObject *dummy, PyObject *args)
{
    PyObject *arg1=NULL, *arg2=NULL, *arg3=NULL, *out=NULL;
    PyObject *x_in=NULL, *y_in=NULL, *x_out=NULL, *y_out=NULL;
    if (!PyArg_ParseTuple(args, "OOOO!", &arg1, &arg2, &arg3,
        &PyArray_Type, &out)) return NULL;

    x_in = PyArray_FROM_OTF(arg1, NPY_FLOAT, NPY_IN_ARRAY);
    if (x_in == NULL) return NULL;
    y_in = PyArray_FROM_OTF(arg2, NPY_FLOAT, NPY_IN_ARRAY);
    if (y_in == NULL) goto fail;
    x_out = PyArray_FROM_OTF(arg3, NPY_FLOAT, NPY_IN_ARRAY);
    if (x_out == NULL) goto fail;
    y_out = PyArray_FROM_OTF(out, NPY_FLOAT, NPY_INOUT_ARRAY);
    if (y_out == NULL) goto fail;
    
    float * x_in_data;
    float * x_out_data;
    float * y_in_data;
    float * y_out_data;
    
    int n_in;
    int n_out;
    
    x_in_data = PyArray_DATA(x_in);
    x_out_data = PyArray_DATA(x_out);
    y_in_data = PyArray_DATA(y_in);
    y_out_data = PyArray_DATA(y_out);
    
    n_in = ((npy_intp *)PyArray_DIMS(x_in))[0];
    n_out = ((npy_intp *)PyArray_DIMS(x_out))[0];
    
    int i;
    int j;
    int k;
    int l;
    int maxdiff;
    float y_init;
    
    j = 0;
    for(i = 0; i < n_out; i++){
        k = 0;
        while((j < n_in) && (x_in_data[j] < x_out_data[i])){
            j++;
            k++;
        }
        if((j==n_in) || (k == 0)){
            y_out_data[i] = 0.0/0.0;
        }
        else if(x_in_data[j] == x_out_data[i]){
            y_out_data[i] = y_in_data[j];
        }
        else{
            if(i==0){
                y_init = y_in_data[0];
            }
            else{
                y_init = y_in_data[i-1];
            }
            maxdiff = -1;
            for(l=j-k; l<j; l++){
                if (y_in_data[l] - y_init > maxdiff){
                    y_out_data[i] = y_in_data[l];
                    maxdiff = y_in_data[l] - y_init;
                }
                else if(y_init - y_in_data[l] > maxdiff){
                    y_out_data[i] = y_in_data[l];
                    maxdiff = y_init - y_in_data[l];
                }
            }
        }
    }
    
    /* code that makes use of arguments */
    /* You will probably need at least
       nd = PyArray_NDIM(<..>)    -- number of dimensions
       dims = PyArray_DIMS(<..>)  -- npy_intp array of length nd
                                     showing length in each dim.
       dptr = (double *)PyArray_DATA(<..>) -- pointer to data.

       If an error occurs goto fail.
     */

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
    {"hello_world", hello_world, METH_VARARGS, "say hello"},
    {"resample", resample, METH_VARARGS, ""},
    {NULL}
};

void 
initresample(void)
{
   Py_InitModule3("resample", module_functions,"A minimal module");
   import_array();
}
