/* rissa Huffman bit-packing — w64devkit GCC 16.2, pure C.
 *
 * The slow part of deep_compress/huffman.py is per-bit Python: building a
 * '0'/'1' str per byte ("".join over the whole block) and walking the tree
 * one CHARACTER at a time on decode. Tree construction (256 symbols) stays
 * in Python — zero divergence risk. These two helpers take the already-built
 * `codes` (list of 256 '0'/'1' strs, "" for absent) and do the bit loops.
 *
 * pack(data, codes) -> (encoded: bytes, padding: int)
 * unpack(encoded, codes, padding, original_len) -> bytes
 * Bit order MSB-first, zero padding — identical to the Python version.
 */
#include <Python.h>
#include <stdint.h>
#include <string.h>

static int load_codes(PyObject *codes, const char *cstr[256], Py_ssize_t clen[256]) {
    if (!PyList_Check(codes) || PyList_Size(codes) != 256) return -1;
    for (int i = 0; i < 256; i++) {
        PyObject *s = PyList_GetItem(codes, i); /* borrowed */
        if (!PyUnicode_Check(s)) return -1;
        Py_ssize_t L = 0;
        const char *p = PyUnicode_AsUTF8AndSize(s, &L);
        if (!p && L != 0) return -1;
        cstr[i] = p ? p : "";
        clen[i] = L;
    }
    return 0;
}

/* real pack: (bytes, list) */
static PyObject* h_pack_bytes(PyObject* self, PyObject* args) {
    const char *data;
    Py_ssize_t n;
    PyObject *codes;
    if (!PyArg_ParseTuple(args, "y#O", &data, &n, &codes)) return NULL;
    const unsigned char *d = (const unsigned char *)data;
    const char *cstr[256];
    Py_ssize_t clen[256];
    if (load_codes(codes, cstr, clen) < 0) return NULL;

    unsigned long long total = 0;
    for (Py_ssize_t k = 0; k < n; k++) total += (unsigned long long)clen[d[k]];
    Py_ssize_t out_len = (Py_ssize_t)((total + 7) / 8);
    int padding = (int)((8 - (total % 8)) % 8);
    PyObject *out = PyBytes_FromStringAndSize(NULL, out_len);
    if (!out) return NULL;
    unsigned char *o = (unsigned char *)PyBytes_AS_STRING(out);
    if (out_len) memset(o, 0, (size_t)out_len);
    unsigned long long bit = 0;
    for (Py_ssize_t k = 0; k < n; k++) {
        const char *s = cstr[d[k]];
        for (Py_ssize_t j = 0; j < clen[d[k]]; j++) {
            if (s[j] == '1') o[bit >> 3] |= (unsigned char)(0x80 >> (bit & 7));
            bit++;
        }
    }
    PyObject *ret = PyTuple_New(2);
    if (!ret) { Py_DECREF(out); return NULL; }
    PyTuple_SetItem(ret, 0, out); /* steals */
    PyTuple_SetItem(ret, 1, PyLong_FromLong(padding));
    return ret;
}

/* decoding tree node pool */
typedef struct { int child[2]; int sym; } DNode;

static PyObject* h_unpack(PyObject* self, PyObject* args) {
    const char *data;
    Py_ssize_t n;
    PyObject *codes;
    int padding;
    Py_ssize_t orig_len;
    if (!PyArg_ParseTuple(args, "y#Oin", &data, &n, &codes, &padding, &orig_len))
        return NULL;
    const unsigned char *d = (const unsigned char *)data;
    if (orig_len == 0) return PyBytes_FromStringAndSize("", 0);
    if (padding < 0 || padding > 7) {
        PyErr_Format(PyExc_ValueError, "huffman padding %d out of range 0..7", padding);
        return NULL;
    }
    if ((unsigned long long)n * 8 < (unsigned long long)padding) {
        PyErr_SetString(PyExc_ValueError, "huffman padding exceeds payload bits");
        return NULL;
    }
    const char *cstr[256];
    Py_ssize_t clen[256];
    if (load_codes(codes, cstr, clen) < 0) return NULL;

    /* count nodes needed */
    Py_ssize_t need = 1;
    for (int i = 0; i < 256; i++) need += clen[i];
    DNode *t = (DNode *)malloc((need ? (size_t)need : 1) * sizeof(DNode));
    if (!t) return PyErr_NoMemory();
    t[0].child[0] = t[0].child[1] = -1;
    t[0].sym = -1;
    int nn = 1;
    for (int i = 0; i < 256; i++) {
        if (clen[i] == 0) continue;
        int cur = 0;
        for (Py_ssize_t j = 0; j < clen[i]; j++) {
            int b = (cstr[i][j] == '1') ? 1 : 0;
            if (t[cur].child[b] < 0) {
                t[cur].child[b] = nn;
                t[nn].child[0] = t[nn].child[1] = -1;
                t[nn].sym = -1;
                nn++;
            }
            cur = t[cur].child[b];
        }
        t[cur].sym = i;
    }

    PyObject *out = PyBytes_FromStringAndSize(NULL, orig_len);
    if (!out) { free(t); return NULL; }
    unsigned char *o = (unsigned char *)PyBytes_AS_STRING(out);
    unsigned long long total_bits = (unsigned long long)n * 8 - (unsigned)padding;
    unsigned long long bit = 0;
    Py_ssize_t w = 0;
    int cur = 0;
    while (bit < total_bits && w < orig_len) {
        int b = (d[bit >> 3] >> (7 - (bit & 7))) & 1;
        bit++;
        cur = t[cur].child[b];
        if (cur < 0) break; /* malformed: match Python (stops short) */
        if (t[cur].sym >= 0) {
            o[w++] = (unsigned char)t[cur].sym;
            cur = 0;
        }
    }
    free(t);
    if (w < orig_len) _PyBytes_Resize(&out, w);
    return out;
}

static PyMethodDef methods[] = {
    {"pack", h_pack_bytes, METH_VARARGS, "pack bits MSB-first -> (bytes, padding)"},
    {"unpack", h_unpack, METH_VARARGS, "unpack bits via code table -> bytes"},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef mod = {PyModuleDef_HEAD_INIT, "rissa.c_huff", NULL, -1, methods};
PyMODINIT_FUNC PyInit_c_huff(void) { return PyModule_Create(&mod); }
