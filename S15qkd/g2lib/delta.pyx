cimport cython
import numpy as np
cimport numpy as np

DTYPE = np.int
ctypedef np.int_t DTYPE_t

@cython.boundscheck(False)  # turn off bounds-checking
@cython.wraparound(False)   # turn off negative index wrapping
@cython.nonecheck(False)
def _delta_loop(double [:] t1 not None,
                double [:] t2 not None,
                int bins,
                double bin_width,
                int l_t1, int l_t2):

    cdef np.ndarray histogram = np.zeros(bins, dtype=DTYPE)
    cdef int idx = 0
    cdef int idx2 = 0
    cdef int n, it_b, it_c
    cdef double c, b, k
    cdef double max_range = bins * bin_width
    for it_b in range(l_t1):
        b = t1[it_b]
        n = 0
        idx = idx2
        while True:
            if idx + n >= l_t2:
                break
            c = t2[idx + n]
            n += 1
            if c < b:
                idx2 = idx + n
                continue
            else:
                k = c - b
                if k >= max_range:
                    break
                histogram[int(k // bin_width)] += 1
    return histogram



def delta_loop(t1,
               t2,
               bins=500,
               bin_width=2):
    cdef int l_t1 = len(t1)
    cdef int l_t2 = len(t2)
    return _delta_loop(t1, t2, bins, bin_width, l_t1, l_t2)
