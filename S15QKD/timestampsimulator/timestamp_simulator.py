#!/usr/local/bin/python3
import os
from random import randint
import math
import numpy as np
import argparse


H_PATTERN = 0b1 << 0
V_PATTERN = 0b1 << 1
D_PATTERN = 0b1 << 2
AD_PATTERN = 0b1 << 3


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


def simulate_pair_source_timestamps(file_name, rate_photon_1, rate_photon_2, rate_pairs, tot_time, pattern_photon_1=int('0001', 2), pattern_photon_2=int('0010', 2), pair_delay=1e-6):

    # create photon waiting times from an exponential distribution
    # simulates exponential distribution for waiting times
    times_channel_1 = np.random.exponential(
        1 / rate_photon_1, rate_photon_1 * tot_time).cumsum()
    times_channel_2 = np.random.exponential(1 / (rate_photon_2 - rate_pairs),
                                            (rate_photon_2 - rate_pairs) * tot_time).cumsum()  # simulates exponential distribution for waiting times

    # select random events in the channel 1 and add a partner photon in channel 2
    heralding_efficiency = rate_pairs / rate_photon_1
    mask = np.random.binomial(1, heralding_efficiency, len(times_channel_1)).astype(
        bool)  # selects randomly events to create pairs
    pair_times = times_channel_1[mask] + \
        pair_delay  # add photon pair time delay
    c = np.concatenate((times_channel_2, pair_times))

    # stack all the events and sort them with respect to time
    time_and_pattern_channel1 = np.vstack(
        [times_channel_1, np.repeat(pattern_photon_1, len(times_channel_1))]).T
    time_and_pattern_channel2 = np.vstack(
        [c, np.repeat(pattern_photon_2, len(c))]).T
    tmp = np.vstack([time_and_pattern_channel1, time_and_pattern_channel2])
    tmp = tmp[tmp[:, 0].argsort()]

    # write to file
    with open(file_name, "wb") as f:
        for row in tmp:
            f.write(time_pattern_to_byte_timestamp(row[0] * 1e12, int(row[1])))


def simulate_pair_source_timestamps_write_into_two_files(file_name_ph1, file_name_ph2,
                                                         rate_photon_1, rate_photon_2,
                                                         rate_pairs, tot_time, pattern_photon_1=int(
                                                             '0001', 2),
                                                         pattern_photon_2=int('0001', 2), pair_delay=1e-6):
    '''Generates two timestamp streams which contain photon pairs and coherent light statistics.

    The streams are written into two files.
    '''
    # create photon waiting times from an exponential distribution
    # simulates exponential distribution for waiting times
    times_photon_1 = np.random.exponential(
        1 / rate_photon_1, int(rate_photon_1 * tot_time)).cumsum()
    times_photon_2 = np.random.exponential(1 / (rate_photon_2 - rate_pairs),
                                           int((rate_photon_2 - rate_pairs) * tot_time)).cumsum()  # simulates exponential distribution for waiting times

    # select random events in the channel 1 and add a partner photon in channel 2
    heralding_efficiency = rate_pairs / rate_photon_1
    mask = np.random.binomial(1, heralding_efficiency, len(times_photon_1)).astype(
        bool)  # selects randomly events to create pairs
    pair_times = times_photon_1[mask] + \
        pair_delay  # add photon pair time delay
    c = np.concatenate((times_photon_2, pair_times))

    # stack all the events and sort them with respect to time
    time_and_pattern_photon1 = np.vstack(
        [times_photon_1, np.repeat(pattern_photon_1, len(times_photon_1))]).T
    time_and_pattern_photon2 = np.vstack(
        [c, np.repeat(pattern_photon_2, len(c))]).T
    # sorting times
    time_and_pattern_photon1 = time_and_pattern_photon1[time_and_pattern_photon1[:, 0].argsort(
    )]
    time_and_pattern_photon2 = time_and_pattern_photon2[time_and_pattern_photon2[:, 0].argsort(
    )]

    # write to file
    with open(file_name_ph1, "wb") as f:
        for row in time_and_pattern_photon1:
            f.write(time_pattern_to_byte_timestamp(row[0] * 1e12, int(row[1])))

    with open(file_name_ph2, "wb") as f:
        for row in time_and_pattern_photon2:
            f.write(time_pattern_to_byte_timestamp(row[0] * 1e12, int(row[1])))


def simulated_entangled_pair_source(rate_pairs, tot_time, photon_delay=1e-6, file_alice='alice_entangled.ts', file_bob='bob_entangled.ts'):
    H_PATTERN_Alice = 0b1 << 2
    H_PATTERN_Bob = 0b1 << 0
    V_PATTERN_Alice = 0b1 << 0
    V_PATTERN_Bob = 0b1 << 2
    D_PATTERN_Alice = 0b1 << 1
    D_PATTERN_Bob = 0b1 << 3
    AD_PATTERN_Alice = 0b1 << 3
    AD_PATTERN_Bob = 0b1 << 1

    time_stamp_Alice = []
    time_stamp_Bob = []
    running_time = 0
    while running_time < tot_time:
        running_time += np.random.exponential(1 / rate_pairs, 1)[0]
        # print(running_time)
        basis_choice_Alice = np.random.binomial(1, 0.5, 1).astype(bool)
        basis_choice_Bob = np.random.binomial(1, 0.5, 1).astype(bool)
        if basis_choice_Alice and basis_choice_Bob:
            if np.random.binomial(1, 0.5, 1).astype(bool):
                time_stamp_Alice.append([running_time, H_PATTERN_Alice])
                time_stamp_Bob.append([running_time, H_PATTERN_Bob])
            else:
                time_stamp_Alice.append([running_time, V_PATTERN_Alice])
                time_stamp_Bob.append([running_time, V_PATTERN_Bob])
        elif (not basis_choice_Alice) and (not basis_choice_Bob):
            if np.random.binomial(1, 0.5, 1).astype(bool):
                time_stamp_Alice.append([running_time, D_PATTERN_Alice])
                time_stamp_Bob.append([running_time, D_PATTERN_Bob])
            else:
                time_stamp_Alice.append([running_time, AD_PATTERN_Alice])
                time_stamp_Bob.append([running_time, AD_PATTERN_Bob])

        elif basis_choice_Alice and (not basis_choice_Bob):
            if np.random.binomial(1, 0.5, 1).astype(bool):
                time_stamp_Alice.append([running_time, H_PATTERN_Alice])
            else:
                time_stamp_Alice.append([running_time, V_PATTERN_Alice])
            if np.random.binomial(1, 0.5, 1).astype(bool):
                time_stamp_Bob.append([running_time, D_PATTERN_Bob])
            else:
                time_stamp_Bob.append([running_time, AD_PATTERN_Bob])

        elif (not basis_choice_Alice) and basis_choice_Bob:
            if np.random.binomial(1, 0.5, 1).astype(bool):
                time_stamp_Alice.append([running_time, D_PATTERN_Alice])
            else:
                time_stamp_Alice.append([running_time, AD_PATTERN_Alice])
            if np.random.binomial(1, 0.5, 1).astype(bool):
                time_stamp_Bob.append([running_time, H_PATTERN_Bob])
            else:
                time_stamp_Bob.append([running_time, V_PATTERN_Bob])


    with open(file_alice, "wb") as f:
        for row in time_stamp_Alice:
            f.write(time_pattern_to_byte_timestamp(row[0] * 1e12, int(row[1])))

    with open(file_bob, "wb") as f:
        for row in time_stamp_Bob:
            f.write(time_pattern_to_byte_timestamp((row[0] + photon_delay) * 1e12, int(row[1])))




def read_file_write_to_stdout(file_name):
    with open(file_name, 'rb') as f:
        while(1):
            byte_s = f.read()
            if not byte_s:
                break
            os.write(1, byte_s)



if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Optional app description')
    parser.add_argument('-infile', type=str,
                        help='input file which is written to the stdout')
    args = parser.parse_args()
    if args.infile:
        read_file_write_to_stdout(args.infile)
    else:
        print('starting to create timestamp files')
        acq_time = 10 * 1
        # file_name = 'time_corelated_photons.ts'
        simulated_entangled_pair_source(10000, 10)
        # simulate_pair_source_timestamps(
        #     file_name, 40000, 20000, 1000, acq_time)
        # simulate_pair_source_timestamps_write_into_two_files(
        #     'alice_correlated.ts', 'bob_correlated.ts', 40e3, 20000, 1000, acq_time)
        # simulate_entangled_pair_source(
        #     'alice_entangled.ts', 'bob_entangled.ts', 40e3, 20000, 1000, acq_time)
