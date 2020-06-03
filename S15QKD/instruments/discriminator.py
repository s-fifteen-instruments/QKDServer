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

def volt2power(volt, wave_length, resistance):
    alpha = np.interp(wave_length, wl, eff)
    return volt / resistance / alpha



class Discriminator():
    """Module for communicating with the power meter"""

    DEVICE_IDENTIFIER = 'Programmable discriminator'
    NIM = 0
    TTL = 1
    

    def __init__(self, device_path=''):
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

    def set_polarity(self, channel, polarity):
        """Returns the voltage accross the resistor.

        Returns:
            number -- Voltage in V
        """
        assert type(self._com) is serialconnection.SerialConnection
        cmd = ('polarity {} {}\n'.format(channel, polarity)).encode()
        self._com.write(cmd)

    def set_threshold(self, channel, voltage_V)
        cmd = (f'threshold {channel} {voltage_V}\n').encode()
        self._com.write(cmd)   

    def help(self):
        return self._com.help()


if __name__ == '__main__':
    print('nothing implemented yet. Please change this.')
