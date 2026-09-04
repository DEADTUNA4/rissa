/* rissa/arrow_glue.c — zero-copy Arrow buffer -> c_shuffle, no input copy.
 *
 * Uses the buffer protocol (`y*`), which pyarrow.Buffer supports natively:
 * `view.buf` IS the Arrow data pointer — we read it in place and only
 * allocate the output. Arrow buffers are immutable, so output must be fresh;
 * true zero-copy on both sides is impossible, input-side is the win.
 *
 * Build (same as c_shuffle.c, w64devkit GCC 16.2):
 *   python setup.py build_ext --inplace --compiler=mingw32
 * Test:
 *   python -c "import rissa.arrow_glue, pyarrow as pa; ..."
 */
#include <Python.h>
#include <stdint.h>

/* SHUFFLE stride-N directly from an Arrow buffer pointer. No memcpy of input. */
static PyObject* arrow_shuffle(PyObject* self, PyObject* args) {
    Py_buffer view;
    int stride = 4;
    if (!PyArg_ParseTuple(args, "y*|i", &view, &stride)) return NULL;
    if (stride <= 0) { PyBuffer_Release(&view); PyErr_SetString(PyExc_ValueError, "stride must be > 0"); return NULL; }
    Py_ssize_t n = view.len;
    PyObject *out = PyBytes_FromStringAndSize(NULL, n < stride*2 ? n : n);
    if (!out) { PyBuffer_Release(&view); return NULL; }
    char *out_buf = PyBytes_AS_STRING(out);
    const char *data = (const char*)view.buf;
    if (n < (Py_ssize_t)(stride*2)) {
        /* below threshold: identical to shuffle_encode fallback, byte copy only */
        for (Py_ssize_t i = 0; i < n; i++) out_buf[i] = data[i];
    } else {
        Py_ssize_t out_idx = 0;
        for (int col = 0; col < stride; col++) {
            Py_ssize_t src = col;
            while (src < n) {
                out_buf[out_idx++] = data[src];
                src += stride;
            }
        }
    }
    PyBuffer_Release(&view);
    return out;
}

/* DELTA directly from an Arrow buffer pointer. No memcpy of input. */
static PyObject* arrow_delta(PyObject* self, PyObject* args) {
    Py_buffer view;
    if (!PyArg_ParseTuple(args, "y*", &view)) return NULL;
    Py_ssize_t n = view.len;
    PyObject *out = PyBytes_FromStringAndSize(NULL, n);
    if (!out) { PyBuffer_Release(&view); return NULL; }
    char *o = PyBytes_AS_STRING(out);
    const unsigned char *data = (const unsigned char*)view.buf;
    if (n > 0) {
        o[0] = (char)data[0];
        for (Py_ssize_t i = 1; i < n; i++) o[i] = (char)((data[i] - data[i-1]) & 0xFF);
    }
    PyBuffer_Release(&view);
    return out;
}

static PyMethodDef methods[] = {
    {"shuffle", arrow_shuffle, METH_VARARGS, "SHUFFLE from Arrow buffer, zero-copy input"},
    {"delta", arrow_delta, METH_VARARGS, "DELTA from Arrow buffer, zero-copy input"},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef mod = {PyModuleDef_HEAD_INIT, "rissa.arrow_glue", NULL, -1, methods};
PyMODINIT_FUNC PyInit_arrow_glue(void) { return PyModule_Create(&mod); }
