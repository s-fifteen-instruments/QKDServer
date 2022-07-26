#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
This module handles the polarization compensation process both during service
and secure operation.

Copyright (c) 2022 S-Fifteen Instruments Pte. Ltd.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

__author__ = 'Syed Abdullah Aljunid'
__copyright__ = 'Copyright 2022, S-Fifteen Instruments Pte. Ltd.'
__credits__ = ['Gan Jun Herng', 'Justin Peh']
__license__ = 'MIT'
__version__ = '0.0.2'
__maintainer__ = ''
__email__ = 'info@s-fifteen.com'
__status__ = 'dev'

import numpy as np
import math
import time
from typing import Tuple, NamedTuple, Any
from dataclasses import dataclass

from S15lib.instruments import LCRDriver
from .utils import HeadT1, ServiceT3, service_T3
from . import qkd_globals
from .qkd_globals import logger, FoldersQKD

class PolComp(object):
    """Class for polarization compensation.
    """

    class LookupTab(NamedTuple):
        id: int
        volt_V: np.ndarray
        ret_V: np.ndarray
        grad_V: np.ndarray

    class LCR_Tab(NamedTuple):
        tab: Any

    #@dataclass
    class LCR_V(NamedTuple):
        target_host: str
        volt_file: str
        V1: float
        V2: float
        V3: float
        V4: float

    def __init__(self, lcr_path: str = '' ):
        self.lcr = LCRDriver(lcr_path)
        self.lcr.all_channels_on()
        LCR_volt_info = qkd_globals.config['LCR_volt_info']
        self.LCR_params = self.LCR_V(qkd_globals.config['target_hostname'],*LCR_volt_info.values())
        self.set_voltage = self.LCR_params[2:6]
        self._set_voltage()
        self.last_voltage_list = self.set_voltage
        self._load_lut()
        self._reset()
        logger.debug(f'pol com initialized')

    def _reset(self):
        self.qber_list = []
        self.last_qber = 1
        self.qber_counter = 0
        self.next_epoch = None
        self.stokes_v = []

    def _load_lut(self):
        file = '../S15qkd/lcvr_callibration.csv'
        #file = qkd_globals.config['LCR_calibration_table']
        self.LUT = [self.LookupTab(0,0,0,0)]
        self.LUT.clear() # Just to get syntax highlighting in VScode
        for i in [0,1,2,3]:
            data = np.genfromtxt(file, delimiter = ',', skip_header=1)
            id = i
            volt_V = data[:,0]
            ret_V = data[:,1]
            grad_V = data[:,2]
            table = self.LookupTab(i,volt_V,ret_V,grad_V)
            self.LUT.append(table)

    def _set_retardance(self, retardances):
        self._calculate_voltages(retardances)
        self._set_voltage()
        return
    
    def _calculate_voltages(self, retardances: list):
        ind = 0
        for i in retardances:
            ind = ind 
            self.set_voltage[i] = self.voltage_lookup(i,ind)
        return


    def _set_voltage(self):
        self.lcr.V1 = self.set_voltage[0]
        self.lcr.V2 = self.set_voltage[1]
        self.lcr.V3 = self.set_voltage[2]
        self.lcr.V4 = self.set_voltage[3]
        return

    def send_epoch(self, epoch_path: str = None):
        logger.debug(f'Received {epoch_path}')
        epoch = epoch_path.split('/')[-1]
        self.diagnosis = service_T3(epoch_path)
        if not self.stokes_v: 
            self.stokes_v, self.dop = self.get_stokes_vector(epoch)
            logger.debug(f'First stokes setting {epoch} {self.next_epoch}')
            return
        if not self.stokes_v[3]:
            self.stokes_v, self.dop = self.get_stokes_vector(epoch) 
            logger.debug(f'Second stokes setting {epoch} {self.next_epoch}')
            return
        logger.debug(f'QBER {self.diagnosis.qber}, epoch {epoch}')
        self.lcvr_instant_find()
        logger.debug(f'QBER {self.diagnosis.qber}, epoch {epoch}')
        return

    def get_stokes_vector(self, epoch):
        """Main measurement loop.

        Measures the individual Stokes vectors and returns them as a list. 
        Also returns the degree of polarization parameter.
        """
        diagnosis=self.diagnosis
        if not self.stokes_v and not self.next_epoch: 
            # Set LCVR to transparent state
            self.set_voltage = [5.5,5.5,5.5,5.5]
            self._set_voltage()
            self.next_epoch = get_current_epoch()
        
        if self.next_epoch and epoch:
            # Compare epochs to see if reached
            epoch_int = int(epoch, 16)
            if epoch_int <= self.next_epoch:
                logger.debug(f'Ignored epoch: {epoch}')
                return self.stokes_v , 0

            # Now at target epoch
            self.next_epoch = None
            if not self.stokes_v: 
                # Measure S0
                S0 = diagnosis.okcount

                # Measure S1
                VH = diagnosis.coinc_matrix[2]
                HV = diagnosis.coinc_matrix[8]
                ADD = diagnosis.coinc_matrix[7]
                DAD = diagnosis.coinc_matrix[13]
                
                VV = diagnosis.coinc_matrix[0]
                HH = diagnosis.coinc_matrix[10]
                ADAD = diagnosis.coinc_matrix[5]
                DD = diagnosis.coinc_matrix[15]
                

                S1 = ((VH + HV + ADD + DAD ) - (VV + HH + ADAD + DD)) \
                   / ((VH + HV + ADD + DAD ) + (VV + HH + ADAD + DD))

                # Measure S2
                VD = diagnosis.coinc_matrix[3]
                HAD = diagnosis.coinc_matrix[9]
                ADH = diagnosis.coinc_matrix[6]
                DV = diagnosis.coinc_matrix[12]

                VAD = diagnosis.coinc_matrix[1]
                HD = diagnosis.coinc_matrix[11]
                ADV = diagnosis.coinc_matrix[4]
                DH = diagnosis.coinc_matrix[14]

                S2 = ((VD + HAD + ADH + DV) - (VAD + HD + ADV + DH)) \
                   / ((VD + HAD + ADH + DV) + (VAD + HD + ADV + DH))
                stokes_vector = [1, S1, S2, None]
            
                # Set horizontal LCVR to phi = pi/4 retardance
                # 2.8V value estimated from Jyh Harng's thesis as a placeholder
                self.set_voltage = [5.5,5.5,5.5,2.8]
                self._set_voltage()
                self.next_epoch = get_current_epoch()
            
                return stokes_vector, 0 
            else:
                # Measure S3
                VH = diagnosis.coinc_matrix[2]
                HV = diagnosis.coinc_matrix[8]
                ADD = diagnosis.coinc_matrix[7]
                DAD = diagnosis.coinc_matrix[13]
                
                VV = diagnosis.coinc_matrix[0]
                HH = diagnosis.coinc_matrix[10]
                ADAD = diagnosis.coinc_matrix[5]
                DD = diagnosis.coinc_matrix[15]
                S3 = ((VH + HV + ADD + DAD ) - (VV + HH + ADAD + DD)) \
                   / ((VH + HV + ADD + DAD ) + (VV + HH + ADAD + DD))
                
                self.stokes_v[3] = S3
                S0 = self.stokes_v[0]
                S1 = self.stokes_v[1]
                S2 = self.stokes_v[2]
                degree_of_polarization = \
                    math.sqrt((S1)**2 + (S2)**2 + (S3)**2)/S0
                stokes_vector = [1, S1, S2, S3]
                return stokes_vector, degree_of_polarization

    def lcvr_instant_find(self):
        """To replace the current random walk method.

        i.e. lcvr_narrow_down()
        """
        stokes_vector = self.stokes_v
        logger.debug(f'Stokes vector is {stokes_vector}')
        phi1, phi2, phi3, phi4 = self.compute_polarization_compensation(stokes_vector)
        logger.debug(f'Angles phi {phi1} {phi2} {phi3} {phi4}')
        retardances = [phi1, phi2, phi3, phi4 ]
        self.set_voltage[2] = self.voltage_lookup(phi3,2)
        self.set_voltage[3] = self.voltage_lookup(phi4,3)
        self._set_voltage()
        #self._set_retardance(retardances) # unused for not cause unsure about voltage at zero retardances yet.


    def compute_polarization_compensation(self,stokes_vector: list):
        """Computes phi rotations from a given Stokes vector.
        Assume only rotations from last 2 LCVRs with theta3=0 and theta4=pi/4.
        theta1=0 and theta2=0 and phi1=0, phi2=0
        In order to correct the input to purely linear polarization.
        """
        assert(len(stokes_vector) == 4)

        s1,s2,s3 = stokes_vector[1], stokes_vector[2], stokes_vector[3]
        phi3 = -math.atan2(s2,s3)
        phi4 = math.acos(s1)
        phi1 = 0
        phi2 = 0

        return phi1, phi2, phi3, phi4

    def voltage_lookup(self, retardance, id: int):
        """For a given retardance value, gets the corresponding LCVR voltage.

        Args:
            Retardance: Desired retardance in radians.
            Table: File path to callibration table of the target LCVR.
        """


        retdiffVector = self.LUT[id].ret_V - retardance
        min_idx = len(retdiffVector[retdiffVector > 0]) - 1
        voltage_raw = self.LUT[id].volt_V[min_idx] + (retdiffVector[min_idx] * self.LUT[id].grad_V[min_idx])
        voltage = float(round(voltage_raw,3))

        # The index that is closest to the target retardance is chosen
        # by looking only at the positive differences between the target
        # and the lookup values.

        return voltage

    
def qber_cost_func(qber: float, desired_qber: float = 0.04, amplitude: float = 6) -> float:
    return amplitude * (qber - desired_qber)**2

def get_current_epoch():
    """Returns the current epoch in integer.

    Hex value of epoch can be checked with 'hex(get_current_epoch())[2:]'.
    """
    return time.time_ns() >> 29


import os

LCR_VOlT_FILENAME = 'latest_LCR_voltages.txt'
VOLT_MIN = 0.9
VOLT_MAX = 5.5
LCVR1_CALLIBRATION_FILEPATH = 'lcvr_callibration.csv'
LCVR2_CALLIBRATION_FILEPATH = 'lcvr_callibration.csv'

# Lookup table to convert retardances to LCVR voltages

class PolarizationDriftCompensation(object):
    def __init__(self, lcr_path: str = '/dev/serial/by-id/usb-S-Fifteen_Instruments_Quad_LCD_driver_LCDD-001-if00',
                 averaging_n: int = 5):
        self.lcr_driver = LCRDriver(lcr_path)
        self.lcr_driver.all_channels_on()
        self.averaging_n = averaging_n
        self.LCRvoltages_file_name = LCR_VOlT_FILENAME
        if not os.path.exists(self.LCRvoltages_file_name):
            #np.savetxt(self.LCRvoltages_file_name, [1.85, 3.01, 2.99, 4.36])
            np.savetxt(self.LCRvoltages_file_name, [4.781, 1.625, 2.104, 3.963])
        self.V1, self.V2, self.V3, self.V4 = np.genfromtxt(
            self.LCRvoltages_file_name).T
        self.lcr_driver.V1 = self.V1
        self.lcr_driver.V2 = self.V2
        self.lcr_driver.V3 = self.V3
        self.lcr_driver.V4 = self.V4
        self.last_voltage_list = [self.V1, self.V2, self.V3, self.V4]
        self.qber_list = []
        self.last_qber = 1
        self.qber_counter = 0
        self.next_epoch = None
        self.stokes_v = []

    def send_diagnosis(self, diagnosis, epoch: str = None):
        if not self.stokes_v: 
            self.stokes_v, self.dop  = self.get_stokes_vector(diagnosis, epoch)
            logger.debug(f'First stokes setting {epoch} {self.next_epoch}')
            return
        if not self.stokes_v[3]:
            self.stokes_v, self.dop = self.get_stokes_vector(diagnosis, epoch) 
            logger.debug(f'Second stokes setting {epoch} {self.next_epoch}')
            return
        logger.debug(f'QBER {diagnosis.quantum_bit_error}, epoch {epoch}')
        self.lcvr_instant_find()
        logger.debug(f'QBER {diagnosis.quantum_bit_error}, epoch {epoch}')

    def update_QBER(self, qber: float, qber_threshold: float = 0.086, epoch: str = None):
        self.qber_counter += 1
        if self.qber_counter < 22: # in case pfind finds a bad match, we don't want to change the lcvr voltage too early
            return

        # 'next_epoch' will be updated when LCVR values are pushed
        # In service mode, all epochs between now (time LCVR values are computed) and 'next_epoch'
        # should be discarded, so that the updated value is properly reflected.
        if not self.next_epoch and not epoch:
            # Compare epochs to see if reached
            epoch_int = int(epoch, 16)
            if epoch_int < self.next_epoch:
                logger.debug(f'Ignored epoch: {epoch}')
                return

            # Now at target epoch
            self.next_epoch = None
            return # start averaging from next epoch onwards

        self.qber_list.append(qber)
        if len(self.qber_list) >= self.averaging_n:
            qber_mean = np.mean(self.qber_list)
            self.qber_list.clear()
            logger.info(
                f'Avg(qber): {qber_mean:.2f} of the last {self.averaging_n} epochs. Voltage search range: {qber_cost_func(qber_mean):.2f}')
            if qber_mean > 0.3:
                self.averaging_n = 2
            if qber_mean < 0.3:
                self.averaging_n = 5
            if qber_mean < 0.15:
                self.averaging_n = 10
            if qber_mean < 0.10:
                self.averaging_n = 15
            logger.info(
                f'Avg(qber): {qber_mean:.2f} averaging over {self.averaging_n} epochs. V_range: {qber_cost_func(qber_mean):.2f}')
            if qber_mean < qber_threshold:
                #np.savetxt(self.LCRvoltages_file_name, [self.V1, self.V2, self.V3, self.V4])
                #controller.stop_key_gen()
                #logger.info('Attempting to start key generation')
                #time.sleep(1)
                #controller.start_key_generation()
                #controller.service_to_BBM92()
                return
            if qber_mean < self.last_qber:
                self.last_voltage_list= [self.V1, self.V2, self.V3, self.V4]
                #self.lcvr_narrow_down(*self.last_voltage_list,
                #                      qber_cost_func(qber_mean))
                self.lcvr_instant_find()
                np.savetxt(self.LCRvoltages_file_name,
                           [*self.last_voltage_list])
            else:
                #self.lcvr_narrow_down(*self.last_voltage_list,
                #                      qber_cost_func(self.last_qber))
                self.lcvr_instant_find()
            self.next_epoch = get_current_epoch()
            logger.debug(f'Next epoch set to "{hex(self.next_epoch)[2:]}".')
            self.last_qber= qber_mean

    def lcvr_narrow_down(self, c1: float, c2: float, c3: float, c4: float, r_narrow: float) -> Tuple[float, float, float, float]:
        self.V1= np.random.uniform(max(c1 - r_narrow, VOLT_MIN),
                                    min(c1 + r_narrow, VOLT_MAX))
        self.V2= np.random.uniform(max(c2 - r_narrow, VOLT_MIN),
                                    min(c2 + r_narrow, VOLT_MAX))
        self.V3= np.random.uniform(max(c3 - r_narrow, VOLT_MIN),
                                    min(c3 + r_narrow, VOLT_MAX))
        self.V4= np.random.uniform(max(c4 - r_narrow, VOLT_MIN),
                                    min(c4 + r_narrow, VOLT_MAX))
        # logger.info(f'{self.V1}, {self.V2}, {self.V3}, {self.V4}')
        self.lcr_driver.V1= self.V1
        self.lcr_driver.V2= self.V2
        self.lcr_driver.V3= self.V3
        self.lcr_driver.V4= self.V4

    def lcvr_instant_find(self):
        """To replace the current random walk method.

        i.e. lcvr_narrow_down()
        """
        stokes_vector, dop = self.get_stokes_vector()
        phi1, phi2 = self.compute_polarization_compensation(stokes_vector)

        # Convert phi1, phi2 to voltages with lookup table
        v1 = self.voltage_lookup(phi1, LCVR1_CALLIBRATION_FILEPATH)
        v2 = self.voltage_lookup(phi2, LCVR2_CALLIBRATION_FILEPATH)

        # Update lcvr voltage list
        self.V1 = v1
        self.V2 = v2
        self.V3 = 5.5
        self.V4 = 5.5

        self.lcr_driver.V1 = self.V1
        self.lcr_driver.V2 = self.V2
        self.lcr_driver.V3 = self.V3
        self.lcr_driver.V4 = self.V4

        # Can return degree of polarization here if needed
        #return dop

    def get_stokes_vector(self, diagnosis, epoch):
        """Main measurement loop.

        Measures the individual Stokes vectors and returns them as a list. 
        Also returns the degree of polarization parameter.
        """
        if not self.stokes_v and not self.next_epoch: 
            # Set LCVR to transparent state
            lcrVoltages = [5.5,5.5,5.5,5.5]
            self.lcr_driver.V1 = lcrVoltages[0]
            self.lcr_driver.V2 = lcrVoltages[1]
            self.lcr_driver.V3 = lcrVoltages[2]
            self.lcr_driver.V4 = lcrVoltages[3]
        
            self.next_epoch = get_current_epoch()
        


        if self.next_epoch and epoch:
            # Compare epochs to see if reached
            epoch_int = int(epoch, 16)
            if epoch_int <= self.next_epoch:
                logger.debug(f'Ignored epoch: {epoch}')
                return self.stokes_v , 0

            # Now at target epoch
            self.next_epoch = None
            # Measure S0
            if not self.stokes_v: 
                total_coincidences = diagnosis.total_coincidences
                S0 = total_coincidences

                # Measure S1
                HH = diagnosis.coincidences_HH
                VV = diagnosis.coincidences_VV
                S1 = (HH-VV)/total_coincidences

                # Measure S2
                ADAD = diagnosis.coincidences_ADAD
                DD = diagnosis.coincidences_DD
                S2 = (ADAD - DD)/total_coincidences
                stokes_vector = [S0, S1, S2, None]
            
                # Set horizontal LCVR to phi = pi/4 retardance
                # 2.8V value estimated from Jyh Harng's thesis as a placeholder
                self.lcr_driver.V4 = 2.8
                self.next_epoch = get_current_epoch()
            
                return stokes_vector, 0 
            else:
                # Measure S3
                S0 = diagnosis.total_coincidences
                HH = diagnosis.coincidences_HH
                VV = diagnosis.coincidences_VV

                RR = diagnosis.coincidences_HH
                LL = diagnosis.coincidences_VV
                S3 = (RR - LL)/S0

                self.stokes_v[3] = S3
                S1 = self.stokes_v[1]
                S2 = self.stokes_v[2]
                degree_of_polarization = \
                    math.sqrt((S1)**2 + (S2)**2 + (S3)**2)/S0
                stokes_vector = [S0, S1, S2, S3]
                return stokes_vector, degree_of_polarization

    def compute_polarization_compensation(self,stokes_vector: list):
        """Computes LCVR retardances from a given Stokes vector.
        
        In order to correct the input to purely linear polarization.
        """
        assert(len(stokes_vector == 4))

        s1,s2,s3 = stokes_vector[1], stokes_vector[2], stokes_vector[3]
        phi1 = -math.atan2(s2,s3)
        phi2 = math.acos(s1)

        return phi1,phi2

    def voltage_lookup(self, retardance, table):
        """For a given retardance value, gets the corresponding LCVR voltage.

        Args:
            Retardance: Desired retardance in radians.
            Table: File path to callibration table of the target LCVR.
        """

        data = np.genfromtxt(table, delimiter = ',', skip_header=1)
        voltageVector = data[:,0]
        retVector = data[:,1]
        gradVector = data[:,2]

        retdiffVector = retVector - retardance
        min_idx = len(retdiffVector[retdiffVector > 0]) - 1
        voltage_raw = voltageVector[min_idx] + (retdiffVector[min_idx] * gradVector[min_idx])
        voltage = float(round(voltage_raw,3))

        # The index that is closest to the target retardance is chosen
        # by looking only at the positive differences between the target
        # and the lookup values.

        return voltage

    def get_qber_4ep(self, dia_file: str = '/tmp/cryptostuff/diagdata'):
        wrong_coinc_index = [0,5,10,15]
        good_coinc_index = [2,7,8,13]
        try:
            with open(dia_file, 'r') as fd:
                last_4_lines = fd.readlines()[-5:-1]
        except:
            return 0.5
        else:
            l1 =list(map(int,last_4_lines[0].strip('\n').split(' ')))
            l2 =list(map(int,last_4_lines[1].strip('\n').split(' ')))
            l3 =list(map(int,last_4_lines[2].strip('\n').split(' ')))
            l4 =list(map(int,last_4_lines[3].strip('\n').split(' ')))
            wrong_coin=sum([l1[i]+ l2[i] + l3[i] +l4[i] for i in wrong_coinc_index])
            good_coin=sum([l1[i]+ l2[i] + l3[i] +l4[i] for i in good_coinc_index])
            qber = wrong_coin /(wrong_coin + good_coin)
            return qber

    def update_qber2(self, qber: float, qber_threshold: float = 0.086):
        r_narrow =  qber_cost_func(qber)
        v_list = self.gen_10_list([self.V1,self.V2,self.V3,self.V4],r_narrow)
        qb = []
        for i in range(0,10):
            v_test = v_list[i]
            self.send_v(v_test)
            time.sleep(0.53*6)
            q = self.get_qber_4ep()
            qb.append(q)
            print(v_test,q)
            in_min = np.argmin(qb)
            min_qb = qb[in_min]
            v_good = v_list[in_min]
            self.send_v(v_good)

    def gen_10_list(self,l: list, r_narrow: float):
        v_list = []
        for i in range(0,10):
            v1 = np.random.uniform(max(l[0] - r_narrow, VOLT_MIN),
                                   min(l[0] + r_narrow, VOLT_MAX))
            v2 = np.random.uniform(max(l[1] - r_narrow, VOLT_MIN),
                                   min(l[1] + r_narrow, VOLT_MAX))
            v3 = np.random.uniform(max(l[2] - r_narrow, VOLT_MIN),
                                   min(l[2] + r_narrow, VOLT_MAX))
            v4 = np.random.uniform(max(l[3] - r_narrow, VOLT_MIN),
                                   min(l[3] + r_narrow, VOLT_MAX))
            v_list.append([v1, v2, v3, v4])
        return v_list
    
    def send_v(self,v: list):
        self.lcr_driver.V1 = v[0]
        self.lcr_driver.V2 = v[1]
        self.lcr_driver.V3 = v[2]
        self.lcr_driver.V4 = v[3]
        self.V1 = v[0]
        self.V2 = v[1]
        self.V3 = v[2]
        self.V4 = v[3]

