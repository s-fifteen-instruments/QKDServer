#!/usr/bin/env python3

import numpy as np
from fast_histogram import histogram1d
try:
    from .delta import delta_loop
    cflag = True
except ImportError:
    print('delta.so module not found, using native option')

    def delta_loop(t1, t2, bins: int=500, bin_width: float= 2):
        """
        Time difference between vectors t1 and t2

        :param t1: event timestamp for channel 1
        :type t1: array of int
        :param t2: event timestamp for channel 2
        :type t2: array of int
        :param max_range: maximum time diference in nsec, defaults to 2000
        :type max_range: int, optional
        :returns: vector with Deltas between t1 and t2
        :rtype: {int}
        """
        histogram = np.zeros(bins)
        idx = 0
        idx2 = 0
        l_t1 = len(t1)
        l_t2 = len(t2)
        max_range = bins * bin_width
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


def _data_extractor(filename, highres_tscard=False):
    """Reads raw timestamp into time and patterns vectors

    :param filename: a python file object open in binary mode
    :param highres_tscard: Flag for the 4ps time resolution card 
    :type filename: _io.BufferedReader
    :returns: Two vectors: timestamps, corresponding pattern
    :rtype: {numpy.ndarray(float), numpy.ndarray(uint32)}
    """
    with open(filename, 'rb') as f:
        data = np.fromfile(file=f, dtype='=I').reshape(-1, 2)
        if highres_tscard:
            t = ((np.uint64(data[:, 0]) << 22) + (data[:, 1] >> 10)) / 256.
        else:
            t = ((np.uint64(data[:, 0]) << 17) + (data[:, 1] >> 15)) / 8.
        p = data[:, 1] & 0xf
        return t, p


def g2_extr(filename: str, bins: int=100, bin_width: float=2, min_range: int=0,
            channel_start: int=0, channel_stop: int=1, c_stop_delay: int=0, highres_tscard: bool=False):
    '''Extract G2 histogram from raw timestamp file

    Arguments:
        filename {str} -- timestamp file containing raw data

    Keyword Arguments:
        bins {int} -- number of bins in for the histogram (default: {100})
        max_range {int} -- upper range of correlation in nsec (default: {2000})
        min_range {int} -- lower range of correlation in nsec (default: {0})
        channel_start {int} -- channel of start events (default: {0})
        channel_stop {int} -- channel of stop events (default: {1})
        c_stop_delay {int} -- introduce a delay in channel_stop (default: {0})
        highres_tscard {bool} -- Setting for timestamp cards with different time resolution (default: {False})

    Returns:
        [int], int, int, int} -- histogram, events in channel_start, events in channel_stop, time at last event
    '''
    if channel_start not in range(4):
        raise ValueError('Selected start channel not in range')
    if channel_stop not in range(4):
        raise ValueError('Selected stop channel not in range')
    t, p = _data_extractor(filename, highres_tscard)
    t1 = t[(p & (0b1 << channel_start)) == (0b1 << channel_start)]
    t2 = t[(p & (0b1 << channel_stop)) == (0b1 << channel_stop)]
    hist = delta_loop(t1, t2 - min_range, bins=bins,
                      bin_width=bin_width)
    try:
        t_max = t[-1]
    except IndexError:
        t_max = 0
    dt = np.arange(0, bins * bin_width, bin_width)
    return hist, dt + min_range, len(t1), len(t2), t_max


def g2_bins(bins=100, max_range=2000, min_range=0, retstep=False):
    """Generates the bin vector for the histogram"""
    return np.linspace(min_range, max_range, bins, retstep=retstep)


if __name__ == '__main__':
    import timeit
    filename = './test.raw'
    _data_extractor(filename)
    # g2_time = timeit.timeit('g2_extr(filename)', number=100, globals=globals())
    # print(g2_time / 100)
