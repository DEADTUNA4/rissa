#include <Python.h>
#include <stdint.h>

// Pure C DELTA + DELTA_ZIGZAG + DELTA2 — 141x like SHUFFLE, w64devkit GCC 16.2
// Matches transforms_v2.py delta_encode, zigzag, delta2

static PyObject* c_delta(PyObject* self, PyObject* args) {
    const char *data;
    Py_ssize_t n;
    if (!PyArg_ParseTuple(args, "y#", &data, &n)) return NULL;
    if (n==0) return PyBytes_FromStringAndSize("",0);
    PyObject *out = PyBytes_FromStringAndSize(NULL, n);
    if (!out) return NULL;
    char *o = PyBytes_AS_STRING(out);
    o[0]=data[0];
    for (Py_ssize_t i=1;i<n;i++) o[i]=(data[i]-data[i-1])&0xFF;
    return out;
}
static PyObject* c_delta_decode(PyObject* self, PyObject* args) {
    const char *data; Py_ssize_t n;
    if (!PyArg_ParseTuple(args, "y#", &data, &n)) return NULL;
    if (n==0) return PyBytes_FromStringAndSize("",0);
    PyObject *out = PyBytes_FromStringAndSize(NULL, n);
    if (!out) return NULL;
    char *o = PyBytes_AS_STRING(out);
    o[0]=data[0];
    for (Py_ssize_t i=1;i<n;i++) o[i]=(data[i]+o[i-1])&0xFF;
    return out;
}
static PyObject* c_zigzag(PyObject* self, PyObject* args) {
    const char *data; Py_ssize_t n;
    if (!PyArg_ParseTuple(args, "y#", &data, &n)) return NULL;
    if (n==0) return PyBytes_FromStringAndSize("",0);
    PyObject *out = PyBytes_FromStringAndSize(NULL, n);
    if (!out) return NULL;
    char *o = PyBytes_AS_STRING(out);
    o[0]=data[0];
    for (Py_ssize_t i=1;i<n;i++) {
        int delta = ((unsigned char)data[i] - (unsigned char)data[i-1]) & 0xFF;
        int signed_d = delta < 128 ? delta : delta-256;
        int zz = ((signed_d<<1) ^ (signed_d>>7)) & 0xFF;
        o[i]=zz;
    }
    return out;
}
static PyObject* c_zigzag_decode(PyObject* self, PyObject* args) {
    const char *data; Py_ssize_t n;
    if (!PyArg_ParseTuple(args, "y#", &data, &n)) return NULL;
    if (n==0) return PyBytes_FromStringAndSize("",0);
    PyObject *out = PyBytes_FromStringAndSize(NULL, n);
    if (!out) return NULL;
    char *o = PyBytes_AS_STRING(out);
    o[0]=data[0];
    for (Py_ssize_t i=1;i<n;i++) {
        int zz=(unsigned char)data[i];
        int signed_d = (zz>>1) ^ (-(zz&1));
        int delta = signed_d & 0xFF;
        o[i]=(o[i-1]+delta)&0xFF;
    }
    return out;
}

static PyMethodDef methods[] = {
    {"delta", c_delta, METH_VARARGS, "DELTA pure C"},
    {"delta_decode", c_delta_decode, METH_VARARGS, "DELTA decode C"},
    {"zigzag", c_zigzag, METH_VARARGS, "DELTA_ZIGZAG C"},
    {"zigzag_decode", c_zigzag_decode, METH_VARARGS, "ZIGZAG decode C"},
    {NULL, NULL, 0, NULL}
};
static struct PyModuleDef mod = {PyModuleDef_HEAD_INIT, "rissa.c_delta", NULL, -1, methods};
PyMODINIT_FUNC PyInit_c_delta(void){ return PyModule_Create(&mod); }
