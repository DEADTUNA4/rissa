#include <Python.h>
#include <stdint.h>
#include <string.h>

// BIT_TRANSPOSE 8x8 - pure C, 8 int ops, uint8
// For 8-byte chunks: transpose bits so that bit planes are grouped
// Input 8 bytes: each byte has 8 bits, output 8 bytes where output[bit] has bit `bit` from all 8 input bytes
// Matches transforms_v2.py bit_transpose_encode

static PyObject* c_bit_transpose(PyObject* self, PyObject* args) {
    const char *data;
    Py_ssize_t n;
    if (!PyArg_ParseTuple(args, "y#", &data, &n)) return NULL;
    if (n < 8) {
        return PyBytes_FromStringAndSize(data, n);
    }
    PyObject *out = PyBytes_FromStringAndSize(NULL, n);
    if (!out) return NULL;
    char *out_buf = PyBytes_AS_STRING(out);
    Py_ssize_t chunks = n / 8;
    for (Py_ssize_t c = 0; c < chunks; c++) {
        const unsigned char *chunk = (const unsigned char*)data + c*8;
        unsigned char transposed[8] = {0};
        for (int i = 0; i < 8; i++) {
            unsigned char b = chunk[i];
            for (int bit = 0; bit < 8; bit++) {
                if (b & (1 << bit)) {
                    transposed[bit] |= (1 << i);
                }
            }
        }
        memcpy(out_buf + c*8, transposed, 8);
    }
    // remainder
    Py_ssize_t rem = n % 8;
    if (rem) {
        memcpy(out_buf + chunks*8, data + chunks*8, rem);
    }
    return out;
}

static PyMethodDef methods[] = {
    {"bit_transpose", c_bit_transpose, METH_VARARGS, "BIT_TRANSPOSE 8x8 pure C"},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef mod = {
    PyModuleDef_HEAD_INIT, "rissa.c_bit", NULL, -1, methods
};

PyMODINIT_FUNC PyInit_c_bit(void) {
    return PyModule_Create(&mod);
}
