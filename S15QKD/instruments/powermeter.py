"""
Created on Mon Feb 9 2020
by Mathias Seidler
"""

import glob
from . import serialconnection
import time
import numpy as np


# Used to search the serial devices for power meters

"""
Calibration table for Hamamatsu S5107 [http://qoptics.quantumlah.org/wiki/index.php/Hamamatsu_S5107]
"""
wl = [351.1, 390.0, 404., 405., 425., 532., 632.8,
      660., 702., 761., 770., 776., 780., 795.,
      808., 810., 850., 1064.]

eff = [0.149, 0.156, 0.1753, 0.1766, 0.1991, 0.3198, 0.4376,
       0.4681, 0.5131, 0.5718, 0.5802, 0.5863, 0.59, 0.6027,
       0.6155, 0.6179, 0.6508, 0.3519]

eff_err = [0.002682, 0.003588, 0.00154264, 0.00155408, 0.00109505,
           0.00153504, 0.00188168, 0.00182559, 0.0020524, 0.00268746,
           0.00237882, 0.0023452, 0.002419, 0.00265188, 0.0025851,
           0.00259518, 0.00247304, 0.0063342]


def volt2power(volt, wave_length, resistance):
    alpha = np.interp(wave_length, wl, eff)
    return volt / resistance / alpha



class PowerMeter():
    """Module for communicating with the power meter"""

    DEVICE_IDENTIFIER = 'power meter'

    def __init__(self, device_path='', resistors=[1e6, 1 / (1 / 110e3 + 1 / 1e6), 10e3, 1e3, 20]):
        # if no path is indicated it tries to init the first power_meter device
        self._resistors = resistors
        if device_path == '':
            device_path = (serialconnection.search_for_serial_devices(
                DEVICE_IDENTIFIER))[0]
            print('Connected to',  device_path)
        self._com = serialconnection.SerialConnection(device_path)

    def reset(self):
        '''Resets the device.

        Returns:
            str -- Response of the device after.
        '''
        return self._com._getresponse_1l(b'*RST')

    def get_voltage(self):
        """Returns the voltage accross the resistor.

        Returns:
            number -- Voltage in V
        """
        assert type(self._com) is serialconnection.SerialConnection
        return float(self._com._getresponse_1l('VOLT?'))

    def get_power(self, wave_length):
        """Get optical power (Watts).

        It automatically selects the correct range.

        Keyword Arguments:
            wave_length {number} -- Wave length of the light in nm

        Returns:
            (number) -- optical power in Watt

        Raises:
            Exception -- Raises an exception when the optical power is higher than the device can measure (A higher resistor may be necessary).
        """
        assert wave_length > 350 and wave_length < 1100, 'wave length out of range of a silicon diode'
        volt = 0
        range = self.range
        while True:
            volt = self.get_voltage()
            if volt > 2.45:
                if range == 5:
                    raise Exception('Optical power out of range')
                else:
                    self.range = range = range + 1
                    continue
            if volt < 0.01:
                if range == 1:
                    break
                else:
                    self.range = range = range - 1
                    continue
            break
        return volt2power(volt, wave_length, self._resistors[range - 1])

    def get_avg_power(self, wave_length, samples=10):
        """Returns the mean and the standard deviation of the optical power
            after sampling it for "samples" times.

        Keyword Arguments:
            samples (number) -- number of samples to average from (default: 10)
            wave_length (number) -- wave length of the light in nm 

        Returns:
            (number, number) -- mean and standard deviation of optical power
        """
        avg_value = []
        for _ in range(samples):
            avg_value.append(self.get_power(wave_length))
        return np.mean(avg_value), np.std(avg_value)

    @property
    def range(self):
        return int(self._com._getresponse_1l('RANGE?'))

    @range.setter
    def range(self, value):
        cmd = ('RANGE {}\n'.format(value)).encode()
        self._com.write(cmd)

    @property
    def serial_number(self):
        return self._com._getresponse_1l('*idn?')

    @serial_number.setter
    def serial_number(self, value):
        print('Serial number can not be changed.')

    def help(self):
        return self._com.help()


if __name__ == '__main__':
    powermeter = PowerMeter()
    start = time.time()
    print(powermeter.get_voltage())
    Dt = time.time() - start

    print("Waktu {}".format(Dt))
