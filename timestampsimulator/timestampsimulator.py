#!/usr/local/bin/python3
import os
from random import randint
import math
import numpy as np
import argparse

# Instantiate the parser


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
    mask = np.random.binomial(1, heralding_efficiency, len(times_channel_1)).astype(bool)  # selects randomly events to create pairs
    pair_times = times_channel_1[mask] + pair_delay  # add photon pair time delay
    c = np.concatenate((times_channel_2, pair_times))

    # stack all the events and sort them with respect to time
    time_and_pattern_channel1 = np.vstack([times_channel_1, np.repeat(pattern_photon_1, len(times_channel_1))]).T
    time_and_pattern_channel2 = np.vstack([c, np.repeat(pattern_photon_2, len(c))]).T
    tmp = np.vstack([time_and_pattern_channel1, time_and_pattern_channel2])
    tmp = tmp[tmp[:, 0].argsort()]

    # write to file
    with open(file_name, "wb") as f:
        for row in tmp:
            f.write(time_pattern_to_byte_timestamp(row[0] * 1e12, int(row[1])))


def simulate_pair_source_timestamps_write_into_two_files(file_name_ph1, file_name_ph2, rate_photon_1, rate_photon_2, rate_pairs, tot_time, pattern_photon_1=int('0001', 2), pattern_photon_2=int('0001', 2), pair_delay=1e-6):

    # create photon waiting times from an exponential distribution
    # simulates exponential distribution for waiting times
    times_photon_1 = np.random.exponential(1 / rate_photon_1, int(rate_photon_1 * tot_time)).cumsum()
    times_photon_2 = np.random.exponential(1 / (rate_photon_2 - rate_pairs),
                                                 int((rate_photon_2 - rate_pairs) * tot_time)).cumsum()  # simulates exponential distribution for waiting times

    # select random events in the channel 1 and add a partner photon in channel 2
    heralding_efficiency = rate_pairs / rate_photon_1
    mask = np.random.binomial(1, heralding_efficiency, len(times_photon_1)).astype(bool)  # selects randomly events to create pairs
    pair_times = times_photon_1[mask] + pair_delay  # add photon pair time delay
    c = np.concatenate((times_photon_2, pair_times))

    # stack all the events and sort them with respect to time
    time_and_pattern_photon1 = np.vstack([times_photon_1, np.repeat(pattern_photon_1, len(times_photon_1))]).T
    time_and_pattern_photon2 = np.vstack([c, np.repeat(pattern_photon_2, len(c))]).T
    # sorting times
    time_and_pattern_photon1 = time_and_pattern_photon1[time_and_pattern_photon1[:, 0].argsort()]
    time_and_pattern_photon2 = time_and_pattern_photon2[time_and_pattern_photon2[:, 0].argsort()]

    # write to file
    with open(file_name_ph1, "wb") as f:
        for row in time_and_pattern_photon1:
            f.write(time_pattern_to_byte_timestamp(row[0] * 1e12, int(row[1])))

    with open(file_name_ph2, "wb") as f:
        for row in time_and_pattern_photon2:
            f.write(time_pattern_to_byte_timestamp(row[0] * 1e12, int(row[1])))


def simulate_entangled_pair_source(file_name_ph1, file_name_ph2, rate_photon_1, rate_photon_2, rate_pairs, tot_time, pair_delay=1e-6):
    # create random photon arrival times following an exponential distribution
    arrival_times_photon_1 = np.random.exponential(1 / rate_photon_1, int(rate_photon_1 * tot_time)).cumsum()
    arrivals_times_photon_2 = np.random.exponential(1 / (rate_photon_2 - rate_pairs), int((rate_photon_2 - rate_pairs) * tot_time)).cumsum()
    # select random events in the channel 1 and add a partner photon in channel 2
    heralding_efficiency = rate_pairs / rate_photon_1
    mask_pair_events = np.random.binomial(1, heralding_efficiency, len(arrival_times_photon_1)).astype(bool)  # selects randomly events to create pairs

    # create uncorreclated photons for photon 1 they end up on a random detector equally distributed
    uncorr_detections_photon_1 = arrival_times_photon_1[np.logical_not(mask_pair_events)]
    random_channel = 0b1 << np.random.randint(0, 4, len(uncorr_detections_photon_1))
    uncorr_time_pattern_photon1 = np.vstack([uncorr_detections_photon_1, random_channel]).T

    random_channel = 0b1 << np.random.randint(0, 4, len(arrivals_times_photon_2))
    uncorr_time_pattern_photon_2 = np.vstack([arrivals_times_photon_2, random_channel]).T

    # simulate photon pairs
    pair_times_photon1 = arrival_times_photon_1[mask_pair_events]
    # simulating a beam splitter with a splitratio of 50:50 (R/T), basis 1 is H/V, basis 2 is D/AD
    mask_basis1_meas = np.random.binomial(
        1, 1 / 2, len(pair_times_photon1)).astype(bool)
    pair_times_photons_basis1 = pair_times_photon1[mask_basis1_meas]
    pair_times_photons_basis2 = pair_times_photon1[np.logical_not(mask_basis1_meas)]

    # BASIS 1 (H/V basis) measurements
    # 50% of the photons are H and the others a V
    mask_H = np.random.binomial(1, 1 / 2, len(pair_times_photons_basis1)).astype(bool)
    H_times = pair_times_photons_basis1[mask_H]  # NOTE: photon 1 times
    V_times = pair_times_photons_basis1[np.logical_not(mask_H)]  # NOTE: photon 1 times
    # BASIS 2 (A/AD) measurements: photon 1 goes into the basis 2 arm. The photon pair state is HH + VV = DD + AD AD
    mask_D = np.random.binomial(1, 1 / 2, len(pair_times_photons_basis2)).astype(bool)
    # NOTE: photon 1 arrival time, store later
    D_times = pair_times_photons_basis2[mask_D] 
    AD_times = pair_times_photons_basis2[np.logical_not(mask_D)]

    # Create the partnering photons on the other side
    # first when they are measured in the same basis
    mask_H_H = np.random.binomial(1, 1 / 2, len(H_times)).astype(bool)
    H_H_times = H_times[mask_H_H] + pair_delay  # NOTE: photon 2 times

    mask_V_V = np.random.binomial(1, 1 / 2, len(V_times)).astype(bool)
    V_V_times = V_times[mask_V_V] + pair_delay  # NOTE: photon 2 times

    # second when the second photons is measured in the other basis (D/AD)
    H_basis2_times = H_times[np.logical_not(mask_H_H)]
    # they are split 50/50 onto A/AD
    mask_H_D = np.random.binomial(1, 1 / 2, len(H_basis2_times)).astype(bool)
    H_D_times = H_basis2_times[mask_H_D] + pair_delay  # NOTE: photon 2 times
    H_AD_times = H_basis2_times[np.logical_not(mask_H_D)] + pair_delay  # NOTE: photon 2 times

    # the same for V photon 1
    # measuremnt in the same basis
    V_basis2_times = V_times[np.logical_not(mask_V_V)]
    mask_V_D = np.random.binomial(1, 1 / 2, len(V_basis2_times)).astype(bool)
    V_D_times = V_basis2_times[mask_V_D] + pair_delay  # NOTE: photon 2 times
    V_AD_times = V_basis2_times[np.logical_not(mask_V_D)] + pair_delay  # NOTE: photon 2 times

    # 50% photons of the photons are D the othes are AD
    # half of them are measured in the same basis
    mask_D_D = np.random.binomial(1, 1 / 2, len(D_times)).astype(bool)
    D_D_times = D_times[mask_D_D] + pair_delay  # NOTE: photon 2 times
    # half of them are measured in the same basis
    mask_AD_AD = np.random.binomial(1, 1 / 2, len(AD_times)).astype(bool)
    AD_AD_times = AD_times[mask_AD_AD] + pair_delay  # NOTE: photon 2 times

    D_basis1_times = D_times[np.logical_not(mask_D_D)]
    mask_D_H = np.random.binomial(1, 1 / 2, len(D_basis1_times)).astype(bool)
    mask_D_V = np.logical_not(mask_D_H)
    D_H_times = D_basis1_times[mask_D_H] + pair_delay  # NOTE: photon 2 times
    D_V_times = D_basis1_times[mask_D_V] + pair_delay  # NOTE: photon 2 times

    AD_basis1_times = AD_times[np.logical_not(mask_AD_AD)]
    mask_AD_H = np.random.binomial(1, 1 / 2, len(AD_basis1_times)).astype(bool)
    AD_H_times = AD_basis1_times[mask_AD_H] + pair_delay  # NOTE: photon 2 times
    AD_V_times = AD_basis1_times[np.logical_not(mask_AD_H)] + pair_delay  # NOTE: photon 2 times

    # next step stack up everything and sort it
    a = np.vstack([H_times, np.repeat(H_PATTERN, len(H_times))]).T
    b = np.vstack([V_times, np.repeat(V_PATTERN, len(V_times))]).T
    c = np.vstack([D_times, np.repeat(D_PATTERN, len(D_times))]).T
    d = np.vstack([AD_times, np.repeat(AD_PATTERN, len(AD_times))]).T

    # final stack for arrival times on one side of the detectors
    time_pattern_photon1 = np.vstack([uncorr_time_pattern_photon1, a, b, c, d])
    time_pattern_photon1 = time_pattern_photon1[time_pattern_photon1[:, 0].argsort()]


    a = np.vstack([H_H_times, np.repeat(H_PATTERN, len(H_H_times))]).T
    b = np.vstack([D_H_times, np.repeat(H_PATTERN, len(D_H_times))]).T
    c = np.vstack([AD_H_times, np.repeat(H_PATTERN, len(AD_H_times))]).T

    d = np.vstack([V_V_times, np.repeat(V_PATTERN, len(V_V_times))]).T
    e = np.vstack([D_V_times, np.repeat(V_PATTERN, len(D_V_times))]).T
    f = np.vstack([AD_V_times, np.repeat(V_PATTERN, len(AD_V_times))]).T

    g = np.vstack([D_D_times, np.repeat(D_PATTERN, len(D_D_times))]).T
    h = np.vstack([V_D_times, np.repeat(D_PATTERN, len(V_D_times))]).T
    i = np.vstack([H_D_times, np.repeat(D_PATTERN, len(H_D_times))]).T

    j = np.vstack([AD_AD_times, np.repeat(AD_PATTERN, len(AD_AD_times))]).T
    k = np.vstack([V_AD_times, np.repeat(AD_PATTERN, len(V_AD_times))]).T
    l = np.vstack([H_AD_times, np.repeat(AD_PATTERN, len(H_AD_times))]).T
 

    time_pattern_photon2 = np.vstack([uncorr_time_pattern_photon_2, a, b, c, d, e, f, g, h, i, j, k, l])
    time_pattern_photon2 = time_pattern_photon2[time_pattern_photon2[:, 0].argsort()]


    with open(file_name_ph1, "wb") as f:
        for row in time_pattern_photon1:
            f.write(time_pattern_to_byte_timestamp(row[0] * 1e12, int(row[1])))

    with open(file_name_ph2, "wb") as f:
        for row in time_pattern_photon2:
            f.write(time_pattern_to_byte_timestamp(row[0] * 1e12, int(row[1])))



def read_file_write_to_stdout(file_name):
    with open(file_name, 'rb') as f:
        while(1):
            byte_s = f.read()
            if not byte_s:
                break
            os.write(1, byte_s)


# ts = time_pattern_to_timestamp(100, 2)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Optional app description')
    parser.add_argument('-infile', type=str, help='input file which is written to the stdout')
    args = parser.parse_args()
    if args.infile:
        read_file_write_to_stdout(args.infile)
    else:
    # time = 0
    # for i in range(0, 10):     # random time between 0 and 10 us
    #     ts = time_pattern_to_byte_timestamp(time, 1)
    #     ts2 = time_pattern_to_byte_timestamp(time + 80, int("0010", 2))
    #     os.write(1, ts)
    #     os.write(1, ts2)
    #     # write to file
    #     # with open("test.bnr", "wb") as f:
    #   #   f.write(ts.to_bytes(8, 'little'))
    #     time += randint(80, 800)
        print('starting to create timestamp files')
        acq_time = 10 * 1
        file_name = 'time_corelated_photons.ts'
        simulate_pair_source_timestamps(file_name, 40000, 20000, 1000, acq_time)
        simulate_pair_source_timestamps_write_into_two_files('alice_correlated.ts', 'bob_correlate.ts', 40e3, 20000, 1000, acq_time)
        simulate_entangled_pair_source('alice_entangled.ts', 'bob_entangled.ts', 40e3, 20000, 1000, acq_time)