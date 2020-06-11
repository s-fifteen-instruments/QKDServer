#!/usr/bin/env python

"""
USB mini counter based on FPGA

Collection of functions to simplify the integration of the USB counter in
Python scripts.
The device is described `here
<http://qoptics.quantumlah.org/wiki/index.php/FPGA-based_USB_counter_unit>`_

"""

import glob
import numpy as np
import subprocess

import time

from ..g2lib import g2lib


from os.path import exists, expanduser
from tempfile import NamedTemporaryFile

from . import serialconnection

READEVENTS_PROG = expanduser("~")+"/programs/usbcntfpga/apps/readevents4a"

class TimeStampTDC1(object):
    """
    The usb counter is seen as an object through this class,
    inherited from the generic serial one.
    """
    DEVICE_IDENTIFIER = 'TDC1'

    def __init__(self, device_path=None,
                 integration_time=1000,
                 mode='singles',
                 level='NIM'):
        """
        Function to initialize the counter device.
        It requires the full path to the serial device as arguments,
        otherwise it will
        initialize the first counter found in the system
        """
        if device_path is None:
            device_path = (serialconnection.search_for_serial_devices(
                self.DEVICE_IDENTIFIER))[0]
            print('Connected to', device_path)
        self._device_path = device_path
        self._com = serialconnection.SerialConnection(device_path)
        # timestamp readevents program path
        self._prog = READEVENTS_PROG
        if not exists(self._prog):
            print('No readevents4 program installed!')
        self._com.write(b'mode?\r\n'); self._com.readline()
        self.mode = mode
        self.level = level

        # default set of parameters. the order is important
        self._binwidth = 2
        self._maxbins = 500
        self._max_range = self._binwidth * self._maxbins
        self._t_min, self._t_max = [40, 50]
        self._acc_t_min, self._acc_t_max = [100, 300]
        self._g2bins_setter()
        self._acc_correction()
        self._int_time = integration_time


    @property
    def int_time(self):
        """
        Controls the integration time set in the counter

        :getter: returns integration time in ms
        :setter: Set integration
        :param value: integration time in ms
        :type value: int
        :returns: integration time in ms
        :rtype: int
        """
        self._int_time = int(self._com._getresponse_1l('TIME?'))
        return self._int_time

    @int_time.setter
    def int_time(self, value):
        if value < 1:
            print('Invalid integration time.')
        else:
            self._com.write('time {:d};time?\r\n'.format(int(value)).encode())
            self._int_time = int(self._com.readline().decode().strip())

    @property
    def counts(self):
        """
        Return the actual number of count read from the device buffer.
        :return: a three-element array
        :rtype: {int}
        """
        if self._mode == 3:
            self.mode = 'singles'
        return [int(x) 
                for x 
                in self._com._getresponse_1l('counts?', self._int_time + 0.05).split()]

    @property
    def mode(self):
        self._mode = int(self._com._getresponse_1l('MODE?'))
        return self._mode

    @mode.setter
    def mode(self, value):
        if value.lower() == 'singles':
            self._mode = 0
            self._com.write(b'singles\r\n')
        if value.lower() == 'pairs':
            self._mode = 1
            self._com.write(b'pairs\r\n')
        if value.lower() == 'timestamp':
            self._mode = 3
            self._com.write(b'timestamp\r\n')
        time.sleep(0.1)

    @property
    def level(self):
        """ Set the kind of pulses to count"""
        return self._com._getresponse_1l('LEVEL?')

    @level.setter
    def level(self, value):
        if value.lower() == 'nim':
            self._com.write(b'NIM\r\n')
        elif value.lower() == 'ttl':
            self._com.write(b'TTL\r\n')
        else:
            print('Acceptable input is either \'TTL\' or \'NIM\'')
        time.sleep(0.1)

    @property
    def clock(self):
        """ Choice of clock"""
        return self._com._getresponse_1l('REFCLK?')

    @clock.setter
    def clock(self, value):
        self._com.write('REFCLK {}\r\n'.format(value).encode())

    """ Functions for the timestamp mode"""

    def _timestamp_acq(self, t_acq, out_file_buffer):
        """ Write the binary output to a buffer"""
        if self._mode != 3:
            self.mode = 'timestamp'
        # for short acquisition times (<65 s) we can reply on the FPGA timer
        if t_acq > 65:
            self._timestamp_acq_LT(t_acq, out_file_buffer)
        else:
            self._timestamp_acq_ST(t_acq, out_file_buffer)

    def _timestamp_acq_LT(self, t_acq, out_file_buffer):
        """ Write the binary output to a buffer for total measurement
        times longer than 65 seconds"""
        p1 = subprocess.Popen([self._prog,
                               '-U', self._device_path,
                               '-a', '1',
                               '-g', '{}'.format(int(0)),
                               '-X'],
                              stdout=out_file_buffer,
                              stderr=subprocess.PIPE)
        time.sleep(t_acq)
        p1.kill()

    def _timestamp_acq_ST(self, t_acq, out_file_buffer):
        """ Write the binary output to a buffer for total measurement
        times longer than 65 seconds"""
        subprocess.check_call([self._prog,
                               '-U', self._device_path,
                               '-a', '1',
                               '-g', '{}'.format(int(t_acq * 1000)),
                               '-X'],
                              stdout=out_file_buffer,
                              stderr=subprocess.PIPE)

    def timestamp_acq(self, t_acq, out_file):
        """ Write the binary output to a file"""
        with open(out_file, 'wb') as of:
            self._timestamp_acq(t_acq, of)

    @property
    def maxbins(self):
        """ Set the number of bins for the g2"""
        return self._maxbins

    @maxbins.setter
    def maxbins(self, value):
        self._maxbins = int(value)
        self._max_range = self._maxbins * self._binwidth
        self._g2bins_setter()

    @property
    def g2bins(self):
        return self._g2bins

    def _g2bins_setter(self):
        self._g2bins = np.linspace(0, self._max_range - self._binwidth,
                                   self._maxbins)
        self._mask_acc = [(self._g2bins > self._acc_t_min) &
                          (self._g2bins < self._acc_t_max)]
        self._mask_coinc = [(self._g2bins > self._t_min) &
                            (self._g2bins < self._t_max)]

    @property
    def binwidth(self):
        """ set the bin size for the g2"""
        return self._binwidth

    @binwidth.setter
    def binwidth(self, value):
        self._binwidth = int(value)
        self._g2bins_setter()


    def _acc_correction(self):
        try:
            self._acc_corr = ((self._t_max - self._t_min) / (self._acc_t_max - self._acc_t_min))
        except ZeroDivisionError:
            self._acc_corr = 1

    @property
    def coincidence_range(self):
        return [self._t_min, self._t_max]

    @coincidence_range.setter
    def coincidence_range(self, value):
        if len(value) != 2:
            print('Range should be an array [t_min, t_max]')
            return -1
        self._t_min, self._t_max = value
        self._g2bins_setter()
        self._acc_correction()

    @property
    def acc_range(self):
        return [self._acc_t_min, self._acc_t_max]

    @acc_range.setter
    def acc_range(self, value):
        if len(value) != 2:
            print('Range should be an array [t_min, t_max]')
            return -1
        self._acc_t_min, self._acc_t_max = value
        self._g2bins_setter()
        self._acc_correction()

    def count_g2(self, t_acq):
        """Returns pairs and singles counts from usbcounter timestamp data.

        Computes g2 between channels 1 and 2 of timestamp
        and sum the coincidences within specified window

        :param t_acq: acquisition time in seconds
        :type t_acq: float
        :returns: Ch1 counts, Ch2 counts, Pairs, estimated accidentals,
                  actual acq time
        :rtype: {int, int, int, float, float}
        """

        # open a temporary file to store the processed g2
        with NamedTemporaryFile() as f_raw:
            self._timestamp_acq(t_acq, f_raw)
            f_raw.seek(0)
            g2, t_bins, s1, s2, time_total = g2lib.g2_extr(f_raw.name,
                                                           bins=self._maxbins,
                                                   bin_width=self._binwidth)
        # calculates the pairs from the processed g2
        pairs = np.sum(g2 * self._mask_coinc)

        # estimates accidentals for the integration time-window
        acc = np.sum(g2 * self._mask_acc) * self._acc_corr
        return {'channel1': s1, 'channel2': s2, 'pairs': pairs,
                'accidentals': acc, 'total_time': time_total}, t_bins, g2


if __name__ == '__main__':
    fpga = TimeStampTDC1()

    # record events for 1s and store it in test.raw
    fpga.timestamp_acq(1, 'test.raw')

    # generates the conincidence histogram from data stored in test.raw
    histogram, dt, s1, s2, time_total = g2lib.g2_extr('test.raw', 1000, 2000)
    print(s1, s2, time_total)

    # Counts singles, pairs, coincidences, and estimates accidentals
    fpga.binwidth = 16
    fpga.maxbins = 500
    fpga.range = [48, 54]
    fpga.acc_range = [100, 300]
    output = fpga.counts(5)
    print(output)
    rate1 = output['channel1'] / output['total_time']
    rate2 = output['channel2'] / output['total_time']
    print('rate ch1: {0:.3e} counts/s\n'
          'rate ch2: {1:.3e} counts/s'.format(rate1, rate2))
