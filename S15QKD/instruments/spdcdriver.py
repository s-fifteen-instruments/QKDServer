"""
Created on Mon Feb 9 2020
by Mathias Seidler
"""

import glob
from . import serialconnection
import time
import numpy as np


class SPDCDriver():
    """Module for communicating with the power meter"""

    DEVICE_IDENTIFIER = 'SPDC driver'

    def __init__(self, device_path=''):
        # if no path is indicated it tries to init the first power_meter device
        if device_path == '':
            device_path = (serialconnection.search_for_serial_devices(
                self.DEVICE_IDENTIFIER))[0]
            print('Connected to', device_path)
        self._com = serialconnection.SerialConnection(device_path)
        self._com._reset_buffers()
        self._com.write(b'power 3\n')

    def reset(self):
        '''Resets the device.

        Returns:
            str -- Response of the device after.
        '''
        return self._com.write(b'*RST')

    def heater_loop_on(self):
        self._com.write(b'HLOOP 1\n')

    def heater_loop_off(self):
        self._com.write(b'HLOOP 0\n')

    def peltier_loop_on(self):
        self._com.write(b'PLOOP 1\n')

    def peltier_loop_off(self):
        self._com.write(b'PLOOP 0\n')

    @property
    def peltier_loop(self):
        return int(self._com._getresponse_1l('PLOOP?'))

    @property
    def heater_loop(self):
        return int(self._com._getresponse_1l('HLOOP?'))

    @property
    def laser_current(self):
        assert type(self._com) is serialconnection.SerialConnection
        return float(self._com._getresponse_1l('lcurrent?'))

    @laser_current.setter
    def laser_current(self, current):
        assert type(self._com) is serialconnection.SerialConnection and (
            type(current) is float or type(current) is int)
        cmd = ('lcurrent {}\n'.format(current)).encode()
        self._com.write(cmd)

    def laser_on(self, current):
        if self.laser_current == 0:
            self.peltier_temp = 25
            self._com.write(b'LCURRENT 0\n')
            cmd = 'on\n'.encode()
            self._com.write(b'on\n')
            # laser current ramp
            for i in range(1, current + 1):
                cmd = ('LCURRENT {}\n'.format(i)).encode()
                self._com.write(cmd)
                time.sleep(0.1)
        else:
            print('Laser is on already.')

    def laser_off(self):
        if self.laser_current != 0:
            for i in range(int(self.laser_current), -1, -1):
                cmd = ('LCURRENT {}\n'.format(i)).encode()
                # print(cmd)
                self._com.write(cmd)
                time.sleep(0.05)
        self._com.write('off\n'.encode())

    @property
    def heater_temp(self):
        """Returns the temperature at the crystal.

        Returns:
            number -- Temperture at the crystal
        """
        assert type(self._com) is serialconnection.SerialConnection
        return float(self._com._getresponse_1l('HTEMP?'))

    @heater_temp.setter
    def heater_temp(self, temperature: float):
        '''Sets the temperature of the crystal heater


        Decorators:
                heater_temp.setter

        Arguments:
                temperature {float} -- set point for the heater temperature
        '''
        assert type(self._com) is serialconnection.SerialConnection
        cmd_setPID = b'HCONSTP 0.13;HCONSTI 0.008\n'
        self._com.write(cmd_setPID)
        now_temp = self.heater_temp
        cmd = ('HSETTEMP {}\n'.format(now_temp)).encode()
        self.heater_loop_on()
        if now_temp < temperature:
            for t in range(int(now_temp) + 1, temperature + 1):
                cmd = ('HSETTEMP {}\n'.format(t)).encode()
                print(cmd)
                self._com.write(cmd)
                time.sleep(6)
        else:
            cmd = ('HSETTEMP {}\n'.format(temperature)).encode()
            print('lowering temp', cmd)
            self._com.write(cmd)

    @property
    def peltier_temp(self):
        """Measures the temperature close to the peltier, where the laser diode is cooled.

        Returns:
            number -- Current temperature of the peltier temp
        """
        assert type(self._com) is serialconnection.SerialConnection
        return float(self._com._getresponse_1l('PTEMP?'))

    @peltier_temp.setter
    def peltier_temp(self, temperature):
        assert temperature > 20 and temperature < 50
        assert type(self._com) is serialconnection.SerialConnection
        assert type(temperature) is float or type(temperature) is int
        cmd_setPID = b'PCONSTP 0.5;PCONSTI 0.035\n'
        self._com.write(cmd_setPID)
        cmd = ('PSETTEMP {}\n'.format(temperature)).encode()
        self._com.write(cmd)
        self.peltier_loop_on()  # switch feedback loop on

    @property
    def device_identifier(self):
        return self._com._getresponse_1l('*idn?')

    @device_identifier.setter
    def device_identifier(self, value):
        print('Serial number can not be changed.')

    def help(self):
        return self._com.help()


if __name__ == '__main__':
    spdc_driver = SPDCDriver()
    start = time.time()
    print(spdc_driver.heater_temp)
    Dt = time.time() - start

    print("Waktu {}".format(Dt))
