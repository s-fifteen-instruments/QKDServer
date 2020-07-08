#!/usr/bin/env python3

###############################################################################
#
# Script for Polarisation Compensation Using 4 LCVRs
# Modified to a minimum finding algorithm using a "Monte carlo guessing" method
#
# Author: Tan Jyh Harng, Shi Yicheng, Poh Hou Shun
# Created: 2019.02.19
#
#
#
# Added feature: pressing ctrl+C to stop the locking process and press enter to
# resume locking.
# Changed: 2019.07.16
#
#
#
################################################################################

import os
import time
import datetime
import numpy as np
import random
import subprocess
import math
import signal

# usbcounter is not used here, just ignore
import devices.USBcounter as USBcounter

# rampgenerator for generating the 2kHz AC control voltages of the LCVRs
import devices.rampgenerator as rampgenerator

###############################################################################

# Prepare the folder to store the data

data_folder = '/home/qitlab/programs/fibre-compensation/data/'
today_folder = time.strftime('%Y%m%d') + '_qber_lock'

data_path = data_folder + today_folder
if not os.path.exists(data_path):
    os.makedirs(data_path)

###############################################################################

PERIOD = 0.0005  # 2kHz frequency, specified in specs
VOLT_START = 3.5  # starts in middle of voltage range
VOLT_STEP = 0.2  # in volt
VOLT_MIN = 1.0  # in volt
VOLT_MAX = 6.0  # in volt
SLEEP_INTERVAL = 0.1  # waiting time in seconds after setting lcvr
COIN_TOL_RATE = 120  # coincidence tolerance per seconds, not useful here, ignore

# we use 2 ramp generators, each with 2 output channels, so a total of 4 LCVR channels
LCVR_0 = 0
LCVR_1 = 1
LCVR_2 = 2
LCVR_3 = 3

# set initial voltage amplitude, all 3.5V
lcvr_0_volt = VOLT_START
lcvr_1_volt = VOLT_START
lcvr_2_volt = VOLT_START
lcvr_3_volt = VOLT_START

# usbcounter integration time
INT_TIME = 1000  # in milliseconds

#COIN_TOL = COIN_TOL_RATE*INT_TIME/1000
COIN_TOL = 0.01


MONTE_CARLO_N = 10  # number of guesses in each monte-carlo iteration
AVERAGE_N = 4  # number of actual QBER data points averaged to get one QBER reading
###############################################################################

# script control via receiving a keyboard interruption


def signal_handler(signal, frame):
    print("ctrl+c detected")
    return 0


###############################################################################
# connect to two ramp generators
DEVICE_PATH_0 = '/dev/serial/by-id/usb-Centre_for_Quantum_Technologies_Ramp_Generator_RG-QO03-if00'
DEVICE_PATH_1 = '/dev/serial/by-id/usb-Centre_for_Quantum_Technologies_Ramp_Generator_RG-QO06-if00'
DEVICE_PATH_2 = '/dev/serial/by-id/usb-Centre_for_Quantum_Technologies_USB_Counter_UC2-QO13-if00'

#------------------------------------------------------------------------------

# initialize the function generators

rg_0 = rampgenerator.RampGenerator(DEVICE_PATH_0)
rg_1 = rampgenerator.RampGenerator(DEVICE_PATH_1)

###############################################################################

# switch all the LCVRs to the starting 3.5V voltage, 2kHz square wave


def lcvr_all_on():
    rg_0.rectangle(0, -VOLT_START, VOLT_START, PERIOD)
    rg_0.rectangle(1, -VOLT_START, VOLT_START, PERIOD)
    rg_1.rectangle(0, -VOLT_START, VOLT_START, PERIOD)
    rg_1.rectangle(1, -VOLT_START, VOLT_START, PERIOD)

# switch off all LCVRs


def lcvr_all_off():
    rg_0.off(0)
    rg_0.off(1)
    rg_1.off(0)
    rg_1.off(1)

# assign each LCVR with a random amplitude between 1V and 6V


def lcvr_all_random():
    global r1, r2, r3, r4
    r1 = random.uniform(VOLT_MIN, VOLT_MAX)
    r2 = random.uniform(VOLT_MIN, VOLT_MAX)
    r3 = random.uniform(VOLT_MIN, VOLT_MAX)
    r4 = random.uniform(VOLT_MIN, VOLT_MAX)
    rg_0.rectangle(0, -r1, r1, PERIOD)
    rg_0.rectangle(1, -r2, r2, PERIOD)
    rg_1.rectangle(0, -r3, r3, PERIOD)
    rg_1.rectangle(1, -r4, r4, PERIOD)

# Given the LCVRs are currently driven by amplitudes c1..c4, randomly generate 4 new amplitudes
# between the range (c1...c4 +- r_narrow) and set the new amplitude to that. If the new amplitude
# is smaller than VOLT_MIN or larger than VOLT_MAX, then use the min/max value as boundaries


def lcvr_narrow_down(c1, c2, c3, c4, r_narrow):
    global r1, r2, r3, r4
    r1 = random.uniform(max(c1 - r_narrow, VOLT_MIN),
                        min(c1 + r_narrow, VOLT_MAX))
    r2 = random.uniform(max(c2 - r_narrow, VOLT_MIN),
                        min(c2 + r_narrow, VOLT_MAX))
    r3 = random.uniform(max(c3 - r_narrow, VOLT_MIN),
                        min(c3 + r_narrow, VOLT_MAX))
    r4 = random.uniform(max(c4 - r_narrow, VOLT_MIN),
                        min(c4 + r_narrow, VOLT_MAX))
    rg_0.rectangle(0, -r1, r1, PERIOD)
    rg_0.rectangle(1, -r2, r2, PERIOD)
    rg_1.rectangle(0, -r3, r3, PERIOD)
    rg_1.rectangle(1, -r4, r4, PERIOD)

# randomly select (MONTE_CARLO_N=10) amplitude settings (10 sets of r1...r4) withing the r_narrow range and centered at c1...c4, measure QBER for each settings, find the amplitude setting with the minimum QBER as the new center (c1...c4) with a new range (r_narrow) and repeat until QBER is below threshold


def monte_carlo_minimum():
    global lcvr_0_volt, lcvr_1_volt, lcvr_2_volt, lcvr_3_volt
    global r1, r2, r3, r4
    random_list = []
    r_narrow = (VOLT_MAX - VOLT_MIN) / 2
    c1 = (VOLT_MAX + VOLT_MIN) / 2
    c2 = (VOLT_MAX + VOLT_MIN) / 2
    c3 = (VOLT_MAX + VOLT_MIN) / 2
    c4 = (VOLT_MAX + VOLT_MIN) / 2
    k = 0
    while 1:
        try:
            random_list = []
            for i in range(1, MONTE_CARLO_N):
                lcvr_narrow_down(c1, c2, c3, c4, r_narrow)
                result = get_qber(AVERAGE_N)
                curr_time = datetime.datetime.now()
                print "k =", k, " result:", result, r1, r2, r3, r4
                random_list.append([r1, r2, r3, r4, result])
                f.write('{0:.3e}\t{1:.3e}\t{2:.3e}\t{3:.3e}\t{4:.3e}\t{5}\t{6:.3e}\n'.format(
                    r1, r2, r3, r4, result, curr_time, r_narrow))
            column = []
            for row in random_list:
                column.append(row[4])
            min_qber = min(column)
            min_index = column.index(min(column))
            print "min QBER is:", min_qber, "index is:", min_index
            # print random_list
            r1 = random_list[min_index][0]
            r2 = random_list[min_index][1]
            r3 = random_list[min_index][2]
            r4 = random_list[min_index][3]
            c1 = r1
            c2 = r2
            c3 = r3
            c4 = r4
            rg_0.rectangle(0, -r1, r1, PERIOD)
            rg_0.rectangle(1, -r2, r2, PERIOD)
            rg_1.rectangle(0, -r3, r3, PERIOD)
            rg_1.rectangle(1, -r4, r4, PERIOD)

            MAX_VOLT_RANGE = 2
            MAX_QBER = 0.5
            R = 0.2
            #r_narrow = MAX_VOLT_RANGE*(1 - math.exp(-get_qber(AVERAGE_N)/MAX_QBER/R))
            r_narrow = 8 * (get_qber(AVERAGE_N) - 0.04)**2
            print "now the qber is:", get_qber(AVERAGE_N), "voltage center:", r1, r2, r3, r4, "search range:", r_narrow
            while (get_qber(AVERAGE_N) < 1 * COIN_TOL):
                print "QBER:", get_qber(AVERAGE_N), "compensation inactive"
            k = k + 1
        except KeyboardInterrupt:
            print "\n"
            print "QBER locking paused via Ctrl-c"
            raw_input('Press ENTER to continue: ')


# define a new function to directly feed a selected lcvr with a given voltage input
def lcvr_feed(channel, voltage):
    global lcvr_0_volt, lcvr_1_volt, lcvr_2_volt, lcvr_3_volt
    global VOLT_STEP, VOLT_MIN, VOLT_MAX, PERIOD, SLEEP_INTERVAL
    if channel == 0:
        rg_0.rectangle(0, -voltage, voltage, PERIOD)
    elif channel == 1:
        rg_0.rectangle(1, -voltage, voltage, PERIOD)
    elif channel == 2:
        rg_1.rectangle(0, -voltage, voltage, PERIOD)
    elif channel == 3:
        rg_1.rectangle(1, -voltage, voltage, PERIOD)
    time.sleep(SLEEP_INTERVAL)

#------------------------------------------------------------------------------
# function to read QBER from the costream_glog file (by calling another script "read-QBER.sh")


def get_qber(nsamples):
    bla = 0
    # nsamples=3
    for i in range(nsamples):
        str = subprocess.check_output('./read-QBER.sh')
        bla = bla + float(str)
        # print i
    # print float(bla)/nsamples
    return float(bla) / nsamples

#------------------------------------------------------------------------------

###############################################################################


lcvr_all_on()
time.sleep(1)

###############################################################################

# locking

output_file = time.strftime("%Y%m%d_%H%M_stat_lock.dat")
output_file = data_path + '/' + output_file

with open(output_file, 'wb') as f:
    monte_carlo_minimum()


###############################################################################
