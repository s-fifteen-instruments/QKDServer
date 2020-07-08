"""
Created on Mon Feb 9 2020
by Mathias Seidler
"""

from . import serial_connection
import time
import numpy as np


class LCDDriver(object):
    """Module for communicating with the power meter"""

    DEVICE_IDENTIFIER = 'LCD Driver'

    def __init__(self, device_path=''):
        # if no path is indicated it tries to init the first power_meter device
        if device_path == '':
            device_path = (serialconnection.search_for_serial_devices(
                self.DEVICE_IDENTIFIER))[0]
            print('Connected to', device_path)
        self._com = serialconnection.SerialConnection(device_path)
        self._com._getresponse_1l('*idn?')

    def reset(self):
        '''Resets the device.

        Returns:
            str -- Response of the device after.
        '''
        return self._com.write(b'*RST')

    def all_channels_on(self, voltage):
        if start_voltage < 10:
            self._com.write(b'ON\r\n')
            self._com.write(b'DARK\r\n')
            self._com.write(b'FREQ 2000\r\n')
            self._com.write((f'AMPLITUDE 1 {voltage}\r\n').encode())
            self._com.write((f'AMPLITUDE 2 {voltage}\r\n').encode())
            self._com.write((f'AMPLITUDE 3 {voltage}\r\n').encode())
            self._com.write((f'AMPLITUDE 4 {voltage}\r\n').encode())
        else:
            print('voltage invalid'.format(position))

    def set_voltage(self, channel, voltage):
        if voltage < 10 and voltage >= 0:
            self.write((f'AMPLITUDE {channel} {voltage}\r\n').encode())
        else:
            raise Exception('Voltage to high')

    @property
    def identity(self):
        return self._com._getresponse_1l('*idn?')

    def help(self):
        return self._com.help()


if __name__ == '__main__':
    spdc_driver = SPDCDriver()
    start = time.time()
    print(spdc_driver.heater_temp)
    Dt = time.time() - start

    print("Waktu {}".format(Dt))
