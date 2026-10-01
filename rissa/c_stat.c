/* rissa stats helpers — w64devkit GCC 16.2, pure C.
 *
 * Ports of per-file/per-block Python counting loops that are NOT in the
 * hot transform path but still cost seconds on multi-MB inputs:
 *   hist_entropy(data)          <- huffman.shannon_entropy (Counter + log2 loop)
 *   rank_ngrams(data, window, min_count, max_count)
 *                               <- build_lzma_dict 8-gram Counter (compressor_v4)
 *                               <- build_shared_dict 6-gram fallback (compressor_v3)
 *   cdc_bounds(...)             <- rabin_karp_cdc byte loop (cdc_dict) and the
 *                                  inline cdc_chunks variant (compressor_v4)
 *
 * Ordering matches Python exactly: counts desc, ties by FIRST-SEEN order
 * (Counter.most_common stability / sorted() stability). Dict CONTENT only
 * affects ratio, never correctness (dict is stored in the header).
 */
#include <Python.h>
#include <stdint.h>
#include <string.h>
#include <math.h>

static PyObject* s_hist_entropy(PyObject* self, PyObject* args) {
    const char *data;
    Py_ssize_t n;
    if (!PyArg_ParseTuple(args, "y#", &data, &n)) return NULL;
    const unsigned char *d = (const unsigned char *)data;
    unsigned long long cnt[256] = {0};
    for (Py_ssize_t i = 0; i < n; i++) cnt[d[i]]++;
    PyObject *hist = PyTuple_New(256);
    if (!hist) return NULL;
    for (int i = 0; i < 256; i++) {
        PyObject *v = PyLong_FromUnsignedLongLong(cnt[i]);
        if (!v) { Py_DECREF(hist); return NULL; }
        PyTuple_SetItem(hist, i, v);
    }
    double ent = 0.0;
    if (n > 0) {
        double dn = (double)n;
        for (int i = 0; i < 256; i++) {
            if (cnt[i]) {
                double p = (double)cnt[i] / dn;
                ent -= p * (log(p) / log(2.0));
            }
        }
    }
    PyObject *ret = PyTuple_New(2);
    if (!ret) { Py_DECREF(hist); return NULL; }
    PyTuple_SetItem(ret, 0, hist);
    PyTuple_SetItem(ret, 1, PyFloat_FromDouble(ent));
    return ret;
}

typedef struct { uint64_t key; int first; } PosRec;
typedef struct { uint64_t key; int count; int first; } GrpRec;

static int cmp_pos(const void *a, const void *b) {
    const PosRec *x = (const PosRec *)a, *y = (const PosRec *)b;
    if (x->key < y->key) return -1;
    if (x->key > y->key) return 1;
    return (x->first < y->first) ? -1 : (x->first > y->first);
}

static int cmp_grp(const void *a, const void *b) {
    const GrpRec *x = (const GrpRec *)a, *y = (const GrpRec *)b;
    if (x->count != y->count) return (x->count > y->count) ? -1 : 1;
    return (x->first < y->first) ? -1 : (x->first > y->first);
}

static PyObject* s_rank_ngrams(PyObject* self, PyObject* args) {
    const char *data;
    Py_ssize_t n;
    int window = 8, min_count = 3, max_count = 4096;
    if (!PyArg_ParseTuple(args, "y#|iii", &data, &n, &window, &min_count, &max_count))
        return NULL;
    const unsigned char *d = (const unsigned char *)data;
    if (window <= 0 || window > 8 || n < window) return PyList_New(0);
    Py_ssize_t m = n - window + 1;

    PosRec *arr = (PosRec *)malloc((m ? (size_t)m : 1) * sizeof(PosRec));
    if (!arr) return PyErr_NoMemory();
    for (Py_ssize_t i = 0; i < m; i++) {
        uint64_t k = 0;
        memcpy(&k, d + i, (size_t)window);
        arr[i].key = k;
        arr[i].first = (int)i;
    }
    qsort(arr, (size_t)m, sizeof(PosRec), cmp_pos);

    GrpRec *gr = (GrpRec *)malloc((m ? (size_t)m : 1) * sizeof(GrpRec));
    if (!gr) { free(arr); return PyErr_NoMemory(); }
    Py_ssize_t ng = 0;
    Py_ssize_t i = 0;
    while (i < m) {
        Py_ssize_t j = i + 1;
        int first = arr[i].first;
        while (j < m && arr[j].key == arr[i].key) {
            if (arr[j].first < first) first = arr[j].first;
            j++;
        }
        if ((j - i) >= min_count) {
            gr[ng].key = arr[i].key;
            gr[ng].count = (int)(j - i);
            gr[ng].first = first;
            ng++;
        }
        i = j;
    }
    free(arr);
    qsort(gr, (size_t)ng, sizeof(GrpRec), cmp_grp);
    if (ng > max_count) ng = max_count;

    PyObject *out = PyList_New(ng);
    if (!out) { free(gr); return NULL; }
    for (Py_ssize_t k = 0; k < ng; k++) {
        PyObject *b = PyBytes_FromStringAndSize((const char *)(d + gr[k].first), window);
        if (!b) { free(gr); Py_DECREF(out); return NULL; }
        PyList_SetItem(out, k, b);
    }
    free(gr);
    return out;
}

static PyObject* s_cdc_bounds(PyObject* self, PyObject* args) {
    const char *data;
    Py_ssize_t n;
    int min_chunk = 1024, max_chunk = 8192, max_chunks = 1024;
    unsigned mask = 0xFFF, poly = 0xBF;
    if (!PyArg_ParseTuple(args, "y#|iiiII", &data, &n, &min_chunk, &max_chunk,
                          &max_chunks, &mask, &poly))
        return NULL;
    const unsigned char *d = (const unsigned char *)data;
    PyObject *out = PyList_New(0);
    if (!out) return NULL;
    uint32_t h = 0;
    Py_ssize_t start = 0;
    Py_ssize_t nch = 0;
    for (Py_ssize_t k = 0; k < n; k++) {
        h = (h * poly + d[k]) & 0xFFFFFFFFu;
        if ((h & mask) == 0 || k - start >= max_chunk) {
            if (k - start >= min_chunk) {
                PyObject *t = PyTuple_New(2);
                if (!t) { Py_DECREF(out); return NULL; }
                PyTuple_SetItem(t, 0, PyLong_FromLongLong(start));
                PyTuple_SetItem(t, 1, PyLong_FromLongLong(k + 1));
                if (PyList_Append(out, t) < 0) { Py_DECREF(t); Py_DECREF(out); return NULL; }
                Py_DECREF(t);
                start = k + 1;
                nch++;
            }
            /* NOTE: replicates Python quirk — when the length guard fails,
             * start is NOT reset (bytes re-scan into the next chunk). */
        }
        if (nch > max_chunks) break;
    }
    if (start < n) {
        PyObject *t = PyTuple_New(2);
        if (!t) { Py_DECREF(out); return NULL; }
        PyTuple_SetItem(t, 0, PyLong_FromLongLong(start));
        PyTuple_SetItem(t, 1, PyLong_FromLongLong(n));
        if (PyList_Append(out, t) < 0) { Py_DECREF(t); Py_DECREF(out); return NULL; }
        Py_DECREF(t);
    }
    return out;
}

static PyMethodDef methods[] = {
    {"hist_entropy", s_hist_entropy, METH_VARARGS, "(hist_tuple, entropy) in one pass"},
    {"rank_ngrams", s_rank_ngrams, METH_VARARGS, "ranked n-gram substrings"},
    {"cdc_bounds", s_cdc_bounds, METH_VARARGS, "content-defined chunk bounds"},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef mod = {PyModuleDef_HEAD_INIT, "rissa.c_stat", NULL, -1, methods};
PyMODINIT_FUNC PyInit_c_stat(void) { return PyModule_Create(&mod); }
