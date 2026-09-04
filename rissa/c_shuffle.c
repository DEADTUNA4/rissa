#include <Python.h>
#include <stdint.h>
#include <string.h>

// Pure C SHUFFLE stride-4 — 5 int ops, uint8, AVX2-ready
// rissa input: row-major interleaved [a0,b0,c0,d0, a1,b1,c1,d1, ...]
// output: col-major [a0,a1,..., b0,b1,..., c0,c1,..., d0,d1,...]
// Matches transforms_v2.py shuffle_encode stride=4

static PyObject* c_shuffle(PyObject* self, PyObject* args) {
    const char *data;
    Py_ssize_t n;
    int stride = 4;
    if (!PyArg_ParseTuple(args, "y#|i", &data, &n, &stride)) return NULL;
    if (n < stride*2) {
        return PyBytes_FromStringAndSize(data, n);
    }
    PyObject *out = PyBytes_FromStringAndSize(NULL, n);
    if (!out) return NULL;
    char *out_buf = PyBytes_AS_STRING(out);
    Py_ssize_t out_idx = 0;
    for (int col = 0; col < stride; col++) {
        Py_ssize_t src = col;
        while (src < n) {
            out_buf[out_idx++] = data[src];
            src += stride;
        }
    }
    return out;
}

static PyMethodDef methods[] = {
    {"shuffle", c_shuffle, METH_VARARGS, "SHUFFLE stride-4 pure C"},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef mod = {
    PyModuleDef_HEAD_INIT, "rissa.c_shuffle", NULL, -1, methods
};

PyMODINIT_FUNC PyInit_c_shuffle(void) {
    return PyModule_Create(&mod);
}
