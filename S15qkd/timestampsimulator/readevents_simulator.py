import os
import numpy as np
import argparse
import sys
import math
import time

import os

def time_pattern_to_byte_timestamp(time, pattern, dt_units_ps=125):
    """
    time in units of ps
    retrieve time and pattern with:
        time = (b << 17) + (c >> 15)
        pattern = c & 0xf
    """
    assert type(pattern) is int, print(type(pattern))
    time = math.ceil(time / dt_units_ps)
    ts = ((time << 15) + pattern)  # & 0xffffffffffffffff
    # not so sure why I need little but it works
    return ((ts >> 32) + ((ts & 0xFFFFFFFF) << 32)).to_bytes(8, 'little')


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


def write_to_stdout(time_list: list, pattern_list: list):
    diff_time_list = np.diff(time_list)
    diff_time_list = np.append(time_list[0], diff_time_list)
    t_running = 0

    with os.fdopen(sys.stdout.fileno(), "wb", 0, closefd=False) as stdout:
        while True:
            for dt, p in zip(diff_time_list, pattern_list):
                # The sleep slows down the printing. However sleep is not very precies on a micro second scale.
                # Adjust denominator until it works for you. This is ugly and I know it.
                t_running += dt
                time.sleep(dt * 1e-9 / 2.5)
                stdout.write(time_pattern_to_byte_timestamp(
                    t_running * 1e3, int(p)))
                stdout.flush()


def main(file_name):
    t, p = _data_extractor(file_name)
    start = time.time()
    write_to_stdout(t, p)
    # print(f'\nRun time: {time.time() - start}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Optional app description')
    parser.add_argument('-infile', type=str,
                        help='input file which is written to the stdout')
    args = parser.parse_args()
    if args.infile:
        main(args.infile)

    else:
        main('../data/simulated_timestamps/bob_correlated.ts')
