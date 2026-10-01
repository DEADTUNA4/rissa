/* rissa batch-1 C ports — w64devkit GCC 16.2, pure C, no deps beyond Python C-API.
 *
 * Ports of the slow pure-Python paths in deep_compress/transforms_v2.py:
 *   shuffle (generic stride 2/4/8) + shuffle_decode (had NO C path),
 *   float_split (+decode), delta2 (+decode), xor (+decode), order2 (+decode),
 *   delta2_zigzag (+decode), mtf (+decode), rle (+decode), rle_zero (+decode).
 * Already C elsewhere (do NOT duplicate): stride-4 shuffle (c_shuffle),
 * bit_transpose (c_bit), delta/delta_decode/zigzag/zigzag_decode (c_delta).
 *
 * Every function replicates the Python semantics byte-for-byte INCLUDING
 * edge cases (n < stride*2 passthrough, len%4!=0 passthrough, run caps,
 * rle_decode trailing-byte rule). Bit-identical output is verified by
 * test vs the Python implementations before wiring in.
 */
#include <Python.h>
#include <stdint.h>
#include <string.h>

/* ---------- shuffle generic ---------- */
static PyObject* t_shuffle(PyObject* self, PyObject* args) {
    const char *data;
    Py_ssize_t n;
    int stride = 4;
    if (!PyArg_ParseTuple(args, "y#|i", &data, &n, &stride)) return NULL;
    if (stride <= 0) stride = 4;
    if (n < (Py_ssize_t)stride * 2) return PyBytes_FromStringAndSize(data, n);
    PyObject *out = PyBytes_FromStringAndSize(NULL, n);
    if (!out) return NULL;
    char *o = PyBytes_AS_STRING(out);
    Py_ssize_t idx = 0;
    for (int col = 0; col < stride; col++) {
        Py_ssize_t src = col;
        while (src < n) { o[idx++] = data[src]; src += stride; }
    }
    return out;
}

/* shuffle_decode: inverse of t_shuffle. Python builds cols with
 * first 'rem' cols holding base+1, then interleaves row-major. */
static PyObject* t_shuffle_decode(PyObject* self, PyObject* args) {
    const char *data;
    Py_ssize_t n;
    int stride = 4;
    if (!PyArg_ParseTuple(args, "y#|i", &data, &n, &stride)) return NULL;
    if (stride <= 0) stride = 4;
    if (n < (Py_ssize_t)stride * 2) return PyBytes_FromStringAndSize(data, n);
    PyObject *out = PyBytes_FromStringAndSize(NULL, n);
    if (!out) return NULL;
    unsigned char *o = (unsigned char *)PyBytes_AS_STRING(out);
    const unsigned char *d = (const unsigned char *)data;
    Py_ssize_t base = n / stride;
    Py_ssize_t rem = n % stride;
    /* column j starts at: sum over k<j of (base + (k<rem)) */
    Py_ssize_t max_col = base + (rem > 0 ? 1 : 0);
    Py_ssize_t idx = 0;
    for (Py_ssize_t row = 0; row < max_col; row++) {
        for (int col = 0; col < stride; col++) {
            Py_ssize_t col_len = base + (col < rem ? 1 : 0);
            if (row < col_len) {
                /* start offset of column col */
                Py_ssize_t start = col * base + (col < rem ? col : rem);
                o[idx++] = d[start + row];
                if (idx >= n) break;
            }
        }
        if (idx >= n) break;
    }
    return out;
}

/* ---------- float_split (== shuffle-4 when len%4==0, else passthrough) ---------- */
static PyObject* t_fsplit(PyObject* self, PyObject* args) {
    const char *data;
    Py_ssize_t n;
    if (!PyArg_ParseTuple(args, "y#", &data, &n)) return NULL;
    if (n < 8 || (n % 4) != 0) return PyBytes_FromStringAndSize(data, n);
    Py_ssize_t m = n / 4;
    PyObject *out = PyBytes_FromStringAndSize(NULL, n);
    if (!out) return NULL;
    char *o = PyBytes_AS_STRING(out);
    for (Py_ssize_t i = 0; i < m; i++) {
        const char *base = data + i * 4;
        o[i] = base[0];
        o[m + i] = base[1];
        o[2 * m + i] = base[2];
        o[3 * m + i] = base[3];
    }
    return out;
}

static PyObject* t_fsplit_decode(PyObject* self, PyObject* args) {
    const char *data;
    Py_ssize_t n;
    if (!PyArg_ParseTuple(args, "y#", &data, &n)) return NULL;
    if (n < 8 || (n % 4) != 0) return PyBytes_FromStringAndSize(data, n);
    Py_ssize_t m = n / 4;
    PyObject *out = PyBytes_FromStringAndSize(NULL, n);
    if (!out) return NULL;
    char *o = PyBytes_AS_STRING(out);
    for (Py_ssize_t i = 0; i < m; i++) {
        char *base = o + i * 4;
        base[0] = data[i];
        base[1] = data[m + i];
        base[2] = data[2 * m + i];
        base[3] = data[3 * m + i];
    }
    return out;
}

/* ---------- delta2 ---------- */
static PyObject* t_delta2(PyObject* self, PyObject* args) {
    const char *data;
    Py_ssize_t n;
    if (!PyArg_ParseTuple(args, "y#", &data, &n)) return NULL;
    const unsigned char *d = (const unsigned char *)data;
    if (n < 2) return PyBytes_FromStringAndSize(data, n);
    /* d1[i] = d[i]-d[i-1] computed on the fly; out[0]=d[0], out[1]=d1[1] */
    PyObject *out = PyBytes_FromStringAndSize(NULL, n);
    if (!out) return NULL;
    unsigned char *o = (unsigned char *)PyBytes_AS_STRING(out);
    unsigned char prev_d1 = (d[1] - d[0]) & 0xFF;
    o[0] = d[0];
    o[1] = prev_d1;
    for (Py_ssize_t i = 2; i < n; i++) {
        unsigned char cur_d1 = (d[i] - d[i - 1]) & 0xFF;
        o[i] = (cur_d1 - prev_d1) & 0xFF;
        prev_d1 = cur_d1;
    }
    return out;
}

static PyObject* t_delta2_decode(PyObject* self, PyObject* args) {
    const char *data;
    Py_ssize_t n;
    if (!PyArg_ParseTuple(args, "y#", &data, &n)) return NULL;
    const unsigned char *d = (const unsigned char *)data;
    if (n < 2) return PyBytes_FromStringAndSize(data, n);
    unsigned char *d1 = (unsigned char *)malloc(n ? (size_t)n : 1);
    if (!d1) return PyErr_NoMemory();
    d1[0] = d[0];
    d1[1] = d[1];
    for (Py_ssize_t i = 2; i < n; i++) d1[i] = (d[i] + d1[i - 1]) & 0xFF;
    PyObject *out = PyBytes_FromStringAndSize(NULL, n);
    if (!out) { free(d1); return NULL; }
    unsigned char *o = (unsigned char *)PyBytes_AS_STRING(out);
    o[0] = d1[0];
    for (Py_ssize_t i = 1; i < n; i++) o[i] = (d1[i] + o[i - 1]) & 0xFF;
    free(d1);
    return out;
}

/* ---------- xor ---------- */
static PyObject* t_xor(PyObject* self, PyObject* args) {
    const char *data;
    Py_ssize_t n;
    if (!PyArg_ParseTuple(args, "y#", &data, &n)) return NULL;
    const unsigned char *d = (const unsigned char *)data;
    if (n == 0) return PyBytes_FromStringAndSize("", 0);
    PyObject *out = PyBytes_FromStringAndSize(NULL, n);
    if (!out) return NULL;
    unsigned char *o = (unsigned char *)PyBytes_AS_STRING(out);
    o[0] = d[0];
    for (Py_ssize_t i = 1; i < n; i++) o[i] = d[i] ^ d[i - 1];
    return out;
}

static PyObject* t_xor_decode(PyObject* self, PyObject* args) {
    const char *data;
    Py_ssize_t n;
    if (!PyArg_ParseTuple(args, "y#", &data, &n)) return NULL;
    const unsigned char *d = (const unsigned char *)data;
    if (n == 0) return PyBytes_FromStringAndSize("", 0);
    PyObject *out = PyBytes_FromStringAndSize(NULL, n);
    if (!out) return NULL;
    unsigned char *o = (unsigned char *)PyBytes_AS_STRING(out);
    o[0] = d[0];
    for (Py_ssize_t i = 1; i < n; i++) o[i] = d[i] ^ o[i - 1];
    return out;
}

/* ---------- order2 ---------- */
static PyObject* t_order2(PyObject* self, PyObject* args) {
    const char *data;
    Py_ssize_t n;
    if (!PyArg_ParseTuple(args, "y#", &data, &n)) return NULL;
    const unsigned char *d = (const unsigned char *)data;
    if (n < 2) return PyBytes_FromStringAndSize(data, n);
    PyObject *out = PyBytes_FromStringAndSize(NULL, n);
    if (!out) return NULL;
    unsigned char *o = (unsigned char *)PyBytes_AS_STRING(out);
    o[0] = d[0];
    o[1] = d[1];
    for (Py_ssize_t i = 2; i < n; i++) {
        unsigned char pred = (2 * d[i - 1] - d[i - 2]) & 0xFF;
        o[i] = (d[i] - pred) & 0xFF;
    }
    return out;
}

static PyObject* t_order2_decode(PyObject* self, PyObject* args) {
    const char *data;
    Py_ssize_t n;
    if (!PyArg_ParseTuple(args, "y#", &data, &n)) return NULL;
    const unsigned char *d = (const unsigned char *)data;
    if (n < 2) return PyBytes_FromStringAndSize(data, n);
    PyObject *out = PyBytes_FromStringAndSize(NULL, n);
    if (!out) return NULL;
    unsigned char *o = (unsigned char *)PyBytes_AS_STRING(out);
    o[0] = d[0];
    o[1] = d[1];
    for (Py_ssize_t i = 2; i < n; i++) {
        unsigned char pred = (2 * o[i - 1] - o[i - 2]) & 0xFF;
        o[i] = (d[i] + pred) & 0xFF;
    }
    return out;
}

/* ---------- delta2_zigzag ---------- */
static PyObject* t_d2zz(PyObject* self, PyObject* args) {
    const char *data;
    Py_ssize_t n;
    if (!PyArg_ParseTuple(args, "y#", &data, &n)) return NULL;
    const unsigned char *d = (const unsigned char *)data;
    if (n < 2) return PyBytes_FromStringAndSize(data, n);
    PyObject *out = PyBytes_FromStringAndSize(NULL, n);
    if (!out) return NULL;
    unsigned char *o = (unsigned char *)PyBytes_AS_STRING(out);
    unsigned char prev_d1 = (d[1] - d[0]) & 0xFF;
    o[0] = d[0];
    o[1] = prev_d1;
    for (Py_ssize_t i = 2; i < n; i++) {
        unsigned char cur_d1 = (d[i] - d[i - 1]) & 0xFF;
        unsigned char delta = (cur_d1 - prev_d1) & 0xFF;
        int s = delta < 128 ? delta : delta - 256;
        o[i] = (unsigned char)(((s << 1) ^ (s >> 7)) & 0xFF);
        prev_d1 = cur_d1;
    }
    return out;
}

static PyObject* t_d2zz_decode(PyObject* self, PyObject* args) {
    const char *data;
    Py_ssize_t n;
    if (!PyArg_ParseTuple(args, "y#", &data, &n)) return NULL;
    const unsigned char *d = (const unsigned char *)data;
    if (n < 2) return PyBytes_FromStringAndSize(data, n);
    unsigned char *d1 = (unsigned char *)malloc(n ? (size_t)n : 1);
    if (!d1) return PyErr_NoMemory();
    d1[0] = d[0];
    d1[1] = d[1];
    for (Py_ssize_t i = 2; i < n; i++) {
        int zz = d[i];
        int s = (zz >> 1) ^ (-(zz & 1));
        d1[i] = (d1[i - 1] + (unsigned char)(s & 0xFF)) & 0xFF;
    }
    PyObject *out = PyBytes_FromStringAndSize(NULL, n);
    if (!out) { free(d1); return NULL; }
    unsigned char *o = (unsigned char *)PyBytes_AS_STRING(out);
    o[0] = d1[0];
    for (Py_ssize_t i = 1; i < n; i++) o[i] = (d1[i] + o[i - 1]) & 0xFF;
    free(d1);
    return out;
}

/* ---------- mtf ---------- */
static PyObject* t_mtf(PyObject* self, PyObject* args) {
    const char *data;
    Py_ssize_t n;
    if (!PyArg_ParseTuple(args, "y#", &data, &n)) return NULL;
    const unsigned char *d = (const unsigned char *)data;
    PyObject *out = PyBytes_FromStringAndSize(NULL, n);
    if (!out) return NULL;
    unsigned char *o = (unsigned char *)PyBytes_AS_STRING(out);
    unsigned char alpha[256];
    int pos[256];
    for (int i = 0; i < 256; i++) { alpha[i] = (unsigned char)i; pos[i] = i; }
    for (Py_ssize_t k = 0; k < n; k++) {
        unsigned char c = d[k];
        int idx = pos[c];
        o[k] = (unsigned char)idx;
        if (idx != 0) {
            /* move alpha[idx] to front, shift [0,idx) right by one */
            memmove(alpha + 1, alpha, (size_t)idx);
            alpha[0] = c;
            for (int i = 0; i < 256; i++)
                if (pos[i] < idx) pos[i]++;
            pos[c] = 0;
        }
    }
    return out;
}

static PyObject* t_mtf_decode(PyObject* self, PyObject* args) {
    const char *data;
    Py_ssize_t n;
    if (!PyArg_ParseTuple(args, "y#", &data, &n)) return NULL;
    const unsigned char *d = (const unsigned char *)data;
    PyObject *out = PyBytes_FromStringAndSize(NULL, n);
    if (!out) return NULL;
    unsigned char *o = (unsigned char *)PyBytes_AS_STRING(out);
    unsigned char alpha[256];
    for (int i = 0; i < 256; i++) alpha[i] = (unsigned char)i;
    for (Py_ssize_t k = 0; k < n; k++) {
        int idx = d[k];
        unsigned char c = alpha[idx];
        o[k] = c;
        if (idx != 0) {
            memmove(alpha + 1, alpha, (size_t)idx);
            alpha[0] = c;
        }
    }
    return out;
}

/* ---------- rle generic: >BH pairs, runs split at 65535 ---------- */
static PyObject* t_rle(PyObject* self, PyObject* args) {
    const char *data;
    Py_ssize_t n;
    if (!PyArg_ParseTuple(args, "y#", &data, &n)) return NULL;
    const unsigned char *d = (const unsigned char *)data;
    /* worst case: every byte its own run -> 3 bytes each */
    PyObject *out = PyBytes_FromStringAndSize(NULL, n * 3);
    if (!out) return NULL;
    unsigned char *o = (unsigned char *)PyBytes_AS_STRING(out);
    Py_ssize_t w = 0, i = 0;
    while (i < n) {
        unsigned char k = d[i];
        Py_ssize_t j = i + 1;
        while (j < n && d[j] == k) j++;
        Py_ssize_t run = j - i;
        while (run > 0) {
            unsigned c = run > 65535 ? 65535 : (unsigned)run;
            o[w++] = k;
            o[w++] = (unsigned char)(c >> 8);
            o[w++] = (unsigned char)(c & 0xFF);
            run -= c;
        }
        i = j;
    }
    _PyBytes_Resize(&out, w);
    return out;
}

static PyObject* t_rle_decode(PyObject* self, PyObject* args) {
    const char *data;
    Py_ssize_t n;
    if (!PyArg_ParseTuple(args, "y#", &data, &n)) return NULL;
    const unsigned char *d = (const unsigned char *)data;
    /* first pass: total length (cap: Python equivalent has no cap issue; sum fits) */
    Py_ssize_t lim = n - (n % 3), total = 0;
    for (Py_ssize_t i = 0; i < lim; i += 3)
        total += ((Py_ssize_t)d[i + 1] << 8) | d[i + 2];
    PyObject *out = PyBytes_FromStringAndSize(NULL, total);
    if (!out) return NULL;
    unsigned char *o = (unsigned char *)PyBytes_AS_STRING(out);
    Py_ssize_t w = 0;
    for (Py_ssize_t i = 0; i < lim; i += 3) {
        Py_ssize_t c = ((Py_ssize_t)d[i + 1] << 8) | d[i + 2];
        memset(o + w, d[i], (size_t)c);
        w += c;
    }
    return out;
}

/* ---------- rle_zero: 4-zero marker [0,0,0,0,N-4], runs split at 259 ---------- */
static PyObject* t_rle0(PyObject* self, PyObject* args) {
    const char *data;
    Py_ssize_t n;
    if (!PyArg_ParseTuple(args, "y#", &data, &n)) return NULL;
    const unsigned char *d = (const unsigned char *)data;
    if (n == 0) return PyBytes_FromStringAndSize("", 0);
    PyObject *out = PyBytes_FromStringAndSize(NULL, n + 16);
    if (!out) return NULL;
    unsigned char *o = (unsigned char *)PyBytes_AS_STRING(out);
    Py_ssize_t cap = n + 16, w = 0, i = 0;
#define RLE0_PUSH(b) do { \
    if (w >= cap) { cap *= 2; if (_PyBytes_Resize(&out, cap) < 0) return NULL; o = (unsigned char *)PyBytes_AS_STRING(out); } \
    o[w++] = (unsigned char)(b); } while (0)
    while (i < n) {
        if (d[i] == 0) {
            Py_ssize_t run = 1;
            while (i + run < n && d[i + run] == 0 && run < 259) run++;
            if (run >= 4) {
                RLE0_PUSH(0); RLE0_PUSH(0); RLE0_PUSH(0); RLE0_PUSH(0);
                RLE0_PUSH(run - 4);
                i += run;
            } else {
                for (Py_ssize_t k = 0; k < run; k++) RLE0_PUSH(0);
                i += run;
            }
        } else {
            RLE0_PUSH(d[i]);
            i++;
        }
    }
#undef RLE0_PUSH
    _PyBytes_Resize(&out, w);
    return out;
}

static PyObject* t_rle0_decode(PyObject* self, PyObject* args) {
    const char *data;
    Py_ssize_t n;
    if (!PyArg_ParseTuple(args, "y#", &data, &n)) return NULL;
    const unsigned char *d = (const unsigned char *)data;
    /* worst case: every 5-byte marker -> 259 zeros: over-alloc n + markers*259 */
    PyObject *out = PyBytes_FromStringAndSize(NULL, n * 2 + 300);
    if (!out) return NULL;
    unsigned char *o = (unsigned char *)PyBytes_AS_STRING(out);
    Py_ssize_t cap = n * 2 + 300, w = 0, i = 0;
    while (i < n) {
        /* NOTE: replicates Python quirk exactly: marker only if i+4 < n (strict) */
        if (i + 4 < n && d[i] == 0 && d[i + 1] == 0 && d[i + 2] == 0 && d[i + 3] == 0) {
            Py_ssize_t run = d[i + 4] + 4;
            while (w + run > cap) { cap *= 2; _PyBytes_Resize(&out, cap); o = (unsigned char *)PyBytes_AS_STRING(out); }
            memset(o + w, 0, (size_t)run);
            w += run;
            i += 5;
        } else {
            if (w >= cap) { cap *= 2; _PyBytes_Resize(&out, cap); o = (unsigned char *)PyBytes_AS_STRING(out); }
            o[w++] = d[i];
            i++;
        }
    }
    _PyBytes_Resize(&out, w);
    return out;
}

/* ---------- BWT: cyclic prefix-doubling ----------
 * Sorts length-n rotations exactly like transforms_v2.bwt_encode's Python
 * radix/naive sorts (both compute the same order): full-rotation ascending,
 * ties (periodic data) broken by rotation index ascending. Counting sorts
 * are stable and the initial order is index-ascending, so equal rotations
 * keep index order — matching Python's stable sorted().
 * O(n log n) time, O(n) memory, no degeneration on repetitive input
 * (where the naive Python sort would OOM building n full-size slices).
 * Returns (bwt_bytes|None, primary|None) just like the Python version.
 */
static PyObject* t_bwt_encode(PyObject* self, PyObject* args) {
    const char *data;
    Py_ssize_t n;
    if (!PyArg_ParseTuple(args, "y#", &data, &n)) return NULL;
    const unsigned char *d = (const unsigned char *)data;
    if (n == 0) {
        PyObject *r = PyTuple_New(2);
        if (!r) return NULL;
        PyTuple_SetItem(r, 0, PyBytes_FromStringAndSize("", 0));
        PyTuple_SetItem(r, 1, PyLong_FromLong(0));
        return r;
    }
    if (n > 256 * 1024) {
        PyObject *r = PyTuple_New(2);
        if (!r) return NULL;
        Py_INCREF(Py_None); PyTuple_SetItem(r, 0, Py_None);
        Py_INCREF(Py_None); PyTuple_SetItem(r, 1, Py_None);
        return r;
    }
    int N = (int)n;
    int *rank = (int *)malloc((size_t)N * sizeof(int));
    int *nrank = (int *)malloc((size_t)N * sizeof(int));
    int *ord = (int *)malloc((size_t)N * sizeof(int));
    int *nord = (int *)malloc((size_t)N * sizeof(int));
    /* cnt must cover 256 byte-ranks on early passes AND N+1 later: take max */
    size_t ncnt = (size_t)(N + 1) > 256 ? (size_t)(N + 1) : 256;
    int *cnt = (int *)malloc(ncnt * sizeof(int));
    if (!rank || !nrank || !ord || !nord || !cnt) {
        free(rank); free(nrank); free(ord); free(nord); free(cnt);
        return PyErr_NoMemory();
    }
    for (int i = 0; i < N; i++) { rank[i] = d[i]; ord[i] = i; }
    /* init: stable counting sort by first byte */
    {
        int c0[256] = {0};
        for (int i = 0; i < N; i++) c0[d[i]]++;
        int s = 0;
        for (int i = 0; i < 256; i++) { int t = c0[i]; c0[i] = s; s += t; }
        for (int i = 0; i < N; i++) nord[c0[d[i]]++] = i;
        memcpy(ord, nord, (size_t)N * sizeof(int));
    }
    int maxr = 255;
    for (long k = 1; ; k *= 2) {
        int kk = (int)(k % N);
        /* LSD pass 1: key2 = rank[(i+k)%N], stable */
        memset(cnt, 0, (size_t)(maxr + 1) * sizeof(int));
        for (int t = 0; t < N; t++) cnt[rank[(ord[t] + kk) % N]]++;
        int s = 0;
        for (int i = 0; i <= maxr; i++) { int t = cnt[i]; cnt[i] = s; s += t; }
        for (int t = 0; t < N; t++) {
            int idx = ord[t];
            nord[cnt[rank[(idx + kk) % N]]++] = idx;
        }
        /* LSD pass 2: key1 = rank[i], stable */
        memset(cnt, 0, (size_t)(maxr + 1) * sizeof(int));
        for (int t = 0; t < N; t++) cnt[rank[nord[t]]]++;
        s = 0;
        for (int i = 0; i <= maxr; i++) { int t = cnt[i]; cnt[i] = s; s += t; }
        for (int t = 0; t < N; t++) {
            int idx = nord[t];
            ord[cnt[rank[idx]]++] = idx;
        }
        /* recompute ranks */
        int nr = 0;
        nrank[ord[0]] = 0;
        for (int t = 1; t < N; t++) {
            int a = ord[t - 1], b = ord[t];
            if (rank[a] != rank[b] || rank[(a + kk) % N] != rank[(b + kk) % N]) nr++;
            nrank[b] = nr;
        }
        { int *sw = rank; rank = nrank; nrank = sw; }
        maxr = nr;
        if (nr == N - 1 || 2 * k >= N) break;
    }
    int primary = 0;
    PyObject *out = PyBytes_FromStringAndSize(NULL, n);
    if (!out) { free(rank); free(nrank); free(ord); free(nord); free(cnt); return NULL; }
    unsigned char *o = (unsigned char *)PyBytes_AS_STRING(out);
    for (int r = 0; r < N; r++) {
        int sa = ord[r];
        if (sa == 0) primary = r;
        o[r] = d[(sa - 1 + N) % N];
    }
    free(rank); free(nrank); free(ord); free(nord); free(cnt);
    rank = nrank = ord = nord = cnt = NULL; /* freed above; error path below must not re-free */
    PyObject *ret = PyTuple_New(2);
    if (!ret) { Py_DECREF(out); return NULL; }
    PyTuple_SetItem(ret, 0, out);
    PyTuple_SetItem(ret, 1, PyLong_FromLong(primary));
    return ret;
}

static PyObject* t_bwt_decode(PyObject* self, PyObject* args) {
    const char *data;
    Py_ssize_t n;
    long primary;
    if (!PyArg_ParseTuple(args, "y#l", &data, &n, &primary)) return NULL;
    const unsigned char *d = (const unsigned char *)data;
    if (n == 0) return PyBytes_FromStringAndSize("", 0);
    if (primary < 0 || primary >= n) {
        PyErr_Format(PyExc_ValueError, "BWT primary %ld out of range for length %zd", primary, n);
        return NULL;
    }
    long counts[256] = {0};
    for (Py_ssize_t i = 0; i < n; i++) counts[d[i]]++;
    long starts[256];
    long s = 0;
    for (int i = 0; i < 256; i++) { starts[i] = s; s += counts[i]; }
    int *occ = (int *)malloc((n ? (size_t)n : 1) * sizeof(int));
    long *cur = (long *)calloc(256, sizeof(long));
    if (!occ || !cur) { free(occ); free(cur); return PyErr_NoMemory(); }
    for (Py_ssize_t i = 0; i < n; i++) {
        occ[i] = (int)cur[d[i]];
        cur[d[i]]++;
    }
    free(cur);
    PyObject *out = PyBytes_FromStringAndSize(NULL, n);
    if (!out) { free(occ); return NULL; }
    unsigned char *o = (unsigned char *)PyBytes_AS_STRING(out);
    long row = primary;
    for (Py_ssize_t i = n - 1; i >= 0; i--) {
        unsigned char c = d[row];
        o[i] = c;
        row = starts[c] + occ[row];
    }
    free(occ);
    return out;
}

static PyMethodDef methods[] = {
    {"shuffle", t_shuffle, METH_VARARGS, "generic-stride SHUFFLE"},
    {"shuffle_decode", t_shuffle_decode, METH_VARARGS, "SHUFFLE decode"},
    {"float_split", t_fsplit, METH_VARARGS, "FLOAT_SPLIT"},
    {"float_split_decode", t_fsplit_decode, METH_VARARGS, "FLOAT_SPLIT decode"},
    {"delta2", t_delta2, METH_VARARGS, "DELTA2"},
    {"delta2_decode", t_delta2_decode, METH_VARARGS, "DELTA2 decode"},
    {"xor_enc", t_xor, METH_VARARGS, "XOR_DELTA"},
    {"xor_dec", t_xor_decode, METH_VARARGS, "XOR_DELTA decode"},
    {"order2", t_order2, METH_VARARGS, "ORDER2"},
    {"order2_decode", t_order2_decode, METH_VARARGS, "ORDER2 decode"},
    {"d2zz", t_d2zz, METH_VARARGS, "DELTA2_ZIGZAG"},
    {"d2zz_decode", t_d2zz_decode, METH_VARARGS, "DELTA2_ZIGZAG decode"},
    {"mtf", t_mtf, METH_VARARGS, "MTF"},
    {"mtf_decode", t_mtf_decode, METH_VARARGS, "MTF decode"},
    {"rle", t_rle, METH_VARARGS, "RLE"},
    {"rle_decode", t_rle_decode, METH_VARARGS, "RLE decode"},
    {"rle_zero", t_rle0, METH_VARARGS, "RLE_ZERO"},
    {"rle_zero_decode", t_rle0_decode, METH_VARARGS, "RLE_ZERO decode"},
    {"bwt_encode", t_bwt_encode, METH_VARARGS, "BWT radix"},
    {"bwt_decode", t_bwt_decode, METH_VARARGS, "BWT LF decode"},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef mod = {PyModuleDef_HEAD_INIT, "rissa.c_trans", NULL, -1, methods};
PyMODINIT_FUNC PyInit_c_trans(void) { return PyModule_Create(&mod); }
