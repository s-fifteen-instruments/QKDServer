cimport cython

@cython.boundscheck(False)  # turn off bounds-checking
@cython.wraparound(False)   # turn off negative index wrapping
@cython.nonecheck(False)
def _delta_loop(double [:] t1 not None,
               double [:] t2 not None,
               int max_range,
               int l_t1, int l_t2):
    """time difference between vectors t1 and t2

    :param t1: event timestamp for channel 1
    :type t1: array of int
    :param t2: event timestamp for channel 2
    :type t2: array of int
    :param max_range: maximum time diference in nsec, defaults to 2000
    :type max_range: int, optional
    :returns: vector with Deltas between t1 and t2
    :rtype: {int}
    """
    retvec = []
    cdef int idx = 0
    cdef int idx2 = 0
    cdef int n, it_b, it_c
    cdef double c, b, k

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
                if k > max_range:
                    break
                retvec.append(k)
    return retvec

def delta_loop(t1,
               t2,
               max_range=2000):
    cdef int l_t1 = len(t1)
    cdef int l_t2 = len(t2)
    return _delta_loop(t1, t2, max_range, l_t1, l_t2)
