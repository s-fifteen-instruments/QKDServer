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

from asyncio import QueueEmpty
from xmlrpc.client import Boolean
import numpy as np
import math
import time
from typing import Tuple, NamedTuple, Any
from dataclasses import dataclass

from S15lib.instruments import LCRDriver
from .utils import HeadT1, ServiceT3, service_T3
from . import qkd_globals
from .qkd_globals import logger, FoldersQKD

VOLT_MIN = 0.9
VOLT_MAX = 5.5
RETARDANCE_MAX = 4.58
RETARDANCE_MIN = 1.18
EPOCH_DURATION = 0.537
QBER_THRESHOLD = 0.082

def qber_cost_func(qber: float, desired_qber: float = 0.05, amplitude: float = 2, exponent: float = 1.34) -> float:
    return amplitude * (qber - desired_qber)**exponent

def get_current_epoch():
    """Returns the current epoch in integer.

    Hex value of epoch can be checked with 'hex(get_current_epoch())[2:]'.
    """
    return time.time_ns() >> 29



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

    def __init__(self, lcr_path: str = '', callback_service_to_BBM92 = None ):
        # Get device
        self.lcr = LCRDriver(lcr_path)
        self.lcr.all_channels_on()
        # Load parameters from config
        LCR_volt_info = qkd_globals.config['LCR_volt_info']
        self.LCR_params = self.LCR_V(qkd_globals.config['target_hostname'],*LCR_volt_info.values())
        self.set_voltage = [self.LCR_params.V1, self.LCR_params.V2,
                            self.LCR_params.V3, self.LCR_params.V4]
        self._load_lut()
        
        # Apply parameters
        self._set_voltage()
        self.last_voltage_list = self.set_voltage
        self._reset()
        self._calculate_retardances()
        self._callback = callback_service_to_BBM92
        self.qber_threshold = QBER_THRESHOLD # threshold to start BBM92
        self.qber_threshold_2 = QBER_THRESHOLD+0.04 # threshold to go from do_walks(1-D walk) to update QBER (n-D walk)
        logger.debug(f'pol com initialized')


    def _reset(self):
        self.qber_list = []
        self.S1_list = []
        self.S2_list = []
        self.S3_list = []
        self.S4_list = []
        self.counter = 0
        self.last_qber = 1
        self.qber_counter = 0
        self.qber_current = 1
        self.averaging_n = 4
        self.next_epoch = 0
        self.next_equator = True
        self.S3_swap = None
        self.stokes_v = []
        self.retardances = [0]*4
        self.last_retardances = self.retardances.copy()
        self.cur_stokes_vector = [None]*4
        self.walks_array = []
        self._voltage_list = []
        self.narrow_down_list = []
        self.next_id = 0
        self.first_pass = True


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
        voltage_ret, actual_ret = self._calculate_voltages(retardances)
        self.set_voltage = voltage_ret.copy()
        self.retardances = actual_ret.copy()
        self._set_voltage()
        return
    
    def _calculate_voltages(self, retardances: list):
        assert(len(retardances)==4)
        ind = 0
        actual_ret = [0]*4
        voltage_ret  = [0]*4
        for retardance in retardances:
            voltage_ret[ind], actual_ret[ind] = self.voltage_lookup(retardance,ind)
            ind += 1 
        return voltage_ret, actual_ret

    def _calculate_retardances(self):
        ind = 0
        for volt in self.set_voltage:
            self.retardances[ind] = self.retardance_lookup(volt,ind)
            ind +=1
        return 

    def _set_voltage(self):
        self.lcr.V1 = self.set_voltage[0]
        self.lcr.V2 = self.set_voltage[1]
        self.lcr.V3 = self.set_voltage[2]
        self.lcr.V4 = self.set_voltage[3]
        return

    def _set_one_voltage(self,volt: float, id: int):
        self.lcr.set_voltage(id + 1, volt)
        return

    def send_qber(self, qber: float, epoch: str):
        logger.debug(f'Received {qber}')
        # i-th LCVR
        for i in range(4):
            #walks_array = self.do_walks(i)
            qber_list = []
            for row in self.walks_array:
                epoch = row[-1]
                qber = self.find_qber_from_epoch(epoch)
                qber_list.append(qber)
            min_idx = qber_list.index(min(qber_list))
            self.set_voltage[i] = qber_list[min_idx]
        return

    def epoch_passed(self, epoch:str) -> Boolean:
        epoch_int = int(epoch, 16)
        if self.next_epoch and epoch_int <= self.next_epoch:
            #logger.debug(f'Ignored epoch: {epoch}. Next epoch is {hex(self.next_epoch)[2:]}')
            return False
        #logger.debug(f'Good epoch: {epoch}. Next epoch is {hex(self.next_epoch)[2:]}')
        return True

    def epoch_match(self, epochstr:str ,epochint: int) -> Boolean:
        epoch1_int = int(epochstr,16)
        if epoch1_int <= epochint:
            return False
        return True

    def do_walks(self, lcvr_idx: int = 0):
        """Performs walking in the LCVR space.
        Generates an array (nested list) of LCVR settings 
        and the corresponding epoch.
        [[*voltages1, epoch1],
         [*voltages2, epoch2],
         ...
        ] 
        """
        self.walks_array = []
        voltage_list = []
        if self.first_pass and self.next_id == 0:
            retardance_list = np.linspace(self.retardance_lookup(VOLT_MIN, lcvr_idx),
                                          self.retardance_lookup(VOLT_MAX, lcvr_idx),
                                          num=9)
        else:
            del_ret = self.qber_current * 4 # walking range is dependent on current qber
            retardance_list = np.linspace(-del_ret,
                                          del_ret,
                                          num=7)
            retardance_list += self.retardance_lookup(self.set_voltage[lcvr_idx], lcvr_idx)
            retardance_list = self.bound_retardance(retardance_list)
        for retardance in retardance_list:
            voltage, act_ret = self.voltage_lookup(retardance, 0)
            voltage_list.append(voltage)
            # Try a range of voltages
        for voltage in voltage_list:
            self.set_voltage[lcvr_idx] = voltage
            # Change LCVR setting
            self._set_voltage()
            # Get epoch when LCVR setting was changed
            curr_epoch = get_current_epoch()
            voltages = self.set_voltage.copy()
            voltages.append(curr_epoch)
            self.walks_array.append(voltages)
            time.sleep(EPOCH_DURATION*1.9)

        logger.debug(f'walks_array is {self.walks_array}')
        if self.next_id < 3:
            self.next_id += 1
        else:
            self.next_id = 0
            self.first_pass = False
        #return walks_array
                    
    def find_qber_from_epoch(self, epoch_path):
        diagnosis = service_T3(epoch_path)
        # Pull relevant qber value
        qber = diagnosis.qber
        return qber

    def process_qber(self, qber: float, epoch: str):
        """Process the received qber from epoch"""
        if self.walks_array:
            earliest_val = self.walks_array[0].copy()
            earliest_epoch = earliest_val.pop()
            if not self.epoch_match(epoch, earliest_epoch):
                return
            self.walks_array.remove(self.walks_array[0])
            earliest_val.append(epoch)
            earliest_val.append(qber)
            self._voltage_list.append(earliest_val)
            logger.info(f'{self._voltage_list}')

        if not self.walks_array:
            if self.apply_minimum_qber():
                self.do_walks(self.next_id)
        return

    def apply_minimum_qber(self):
        qber_min = 1.
        for row in self._voltage_list:
            qber = float(row[-1])
            if qber < qber_min:
                qber_min = qber
                voltage_min = row[0:4]
                self.set_voltage = voltage_min
        self._voltage_list = []
        self.last_voltage_list = self.set_voltage.copy() # for update qber later on
        
        logger.debug(f'Minimum QBER {qber_min} at {self.set_voltage}')
        self._set_voltage()
        self._calculate_retardances()
        self.qber_current = qber_min
        if qber_min < self.qber_threshold_2: # minimum qber applied is low enough. Don't do_walk anymore.
            #self._callback()
            #logger.info(f'BBM92 called')
            #self.first_pass = False
            #logger.debug(f'do_walks ended')
            return False
        elif qber_min < self.qber_threshold: # minimum qber applied is low enough. Don't do_walk anymore.
            self._callback()
            logger.info(f'BBM92 called')
            return False
        return True

    def narrow_down(self, qber: float, epoch: str):
        """From the current set_voltages and qber,
        narrow down to below threshold qber."""
        if not self.narrow_down_list: #first entry
            self.last_qber = self.qber_current
            self._set_voltage()
            self.next_epoch = get_current_epoch()
            return
        if not self.epoch_passed(epoch):
            return
        if qber > self.qber_current:
            return

    def send_epoch(self, epoch_path: str = None):
        """Receives the epoch from controller and performs
           polarization compensation. Only done in 
           SERVICE mode.
           The function name makes more sense from the
           controller side. This script is actually
           receiving the epoch.
        """
        
        epoch = epoch_path.split('/')[-1]
        
        if self.walks_array:
            self.process_qber(self.find_qber_from_epoch(epoch_path), epoch)
        else:
            self.update_QBER(self.find_qber_from_epoch(epoch_path), QBER_THRESHOLD, epoch)
        
        ''' #Code to measure current stokes vector
        self.diagnosis = service_T3(epoch_path)
        if self.first_pass:
            self.get_current_stokes_vector(epoch)
            return
        if self.cur_stokes_vector[3]:
            logger.debug(f'Stokes V {self.cur_stokes_vector} {epoch} {self.next_epoch}') 
            self.counter += 1
            if self.counter > self.averaging_n:
                self.rotate_stokes_v_to_S1()
                self.counter = 0
                self.cur_stokes_vector = [None]*4
                self.first_pass = True
        logger.debug(f'QBER {self.diagnosis.qber}, epoch {epoch}')
        
        return
        '''
        """ # code to measure stokes vector at some voltage
        logger.debug(f'Received {epoch_path} QBER {self.diagnosis.qber}, epoch {epoch}')
        if not self.stokes_v: 
            self.get_stokes_vector(epoch)
            logger.debug(f'First stokes setting {epoch} {self.next_epoch}')
            return
        if not self.stokes_v[3]:
            self.get_stokes_vector(epoch) 
            logger.debug(f'Second stokes setting {epoch} {self.next_epoch}')
            return
        self.lcvr_instant_find()
        logger.debug(f'QBER {self.diagnosis.qber}, epoch {epoch}')
        return
        """

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
                return

            # Now at target epoch
            self.next_epoch = None
            if not self.stokes_v: 
                S0, S1, S2 = self.get_S0_S1_S2(diagnosis)
                stokes_vector = [1, S1, S2, None]
            
                # Set horizontal LCVR to phi = pi/4 retardance
                # 2.8V value estimated from Jyh Harng's thesis as a placeholder
                self.set_voltage = [5.5,5.5,5.5,2.8]
                self._set_voltage()
                self.next_epoch = get_current_epoch()
            
                return 
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
                S3 = float(round(((VH + HV + ADD + DAD ) - (VV + HH + ADAD + DD)) \
                   / ((VH + HV + ADD + DAD ) + (VV + HH + ADAD + DD)),3))
                
                self.stokes_v[3] = S3
                S0 = self.stokes_v[0]
                S1 = self.stokes_v[1]
                S2 = self.stokes_v[2]
                degree_of_polarization = \
                    math.sqrt((S1)**2 + (S2)**2 + (S3)**2)/S0
                stokes_vector = [1, S1, S2, S3]
                return #stokes_vector, degree_of_polarization

    def get_S0_S1_S2(self,diagnosis: ServiceT3):
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
        
        if ((VH + HV + ADD + DAD ) + (VV + HH + ADAD + DD)) == 0:
            S1 = 0
        else:
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

        if ((VD + HAD + ADH + DV) + (VAD + HD + ADV + DH)) == 0: 
            S2 = 0
        else:
            S2 = ((VD + HAD + ADH + DV) - (VAD + HD + ADV + DH)) \
                / ((VD + HAD + ADH + DV) + (VAD + HD + ADV + DH))
        return S0, S1, S2

    def get_stokes_vector_redux(self, epoch):
        """Main measurement loop. Ver 2.

        Trying an alernate method of calculating stokes' vectors.
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
                HH = diagnosis.coinc_matrix[10]
                HV = diagnosis.coinc_matrix[8]
                HAD = diagnosis.coinc_matrix[9]
                HD = diagnosis.coinc_matrix[11]

                # 2*HH - (HH + HV + HD + HAD)
                S1 = HH - HV - HD - HAD

                # 2*HD - (HH + HV + HD + HAD)
                S2 = HD - HH - HV - HAD
                
                stokes_vector = [S0, S1, S2, None]
            
                # Set horizontal LCVR to phi = pi/4 retardance
                # 2.8V value estimated from Jyh Harng's thesis as a placeholder
                self.set_voltage = [5.5,5.5,5.5,2.8]
                self._set_voltage()
                self.next_epoch = get_current_epoch()
            
                return stokes_vector, 0
            else:
                # Measure S3
                HH = diagnosis.coinc_matrix[10]
                HV = diagnosis.coinc_matrix[8]
                HAD = diagnosis.coinc_matrix[9]
                HD = diagnosis.coinc_matrix[11]

                # 2*HAD - (HH + HV + HD + HAD)
                S3 = HAD - HH - HV - HD

                self.stokes_v[3] = S3
                S0 = self.stokes_v[0]
                S1 = self.stokes_v[1]
                S2 = self.stokes_v[2]
                degree_of_polarization = \
                    math.sqrt((S1)**2 + (S2)**2 + (S3)**2)/S0
                stokes_vector = [S0, S1, S2, S3]
                return stokes_vector, degree_of_polarization

    def get_current_stokes_vector(self, epoch: str):
        """Find S0 S1 and S2 of current setting of LCVR voltage.
        Rotate Last LCVR by pi/4 and find S3.
        """
        diagnosis=self.diagnosis
        if not self.epoch_passed(epoch):
            return
        if self.next_equator:
            S0, S1, S2 = self.get_S0_S1_S2(diagnosis)
            self.S1_list.append(S1)
            self.S2_list.append(S2)
            if len(self.S1_list) >= self.averaging_n:
                S1 = np.mean(self.S1_list)
                S2 = np.mean(self.S2_list)
                logger.debug(f'S1 {self.S1_list} {S1}, S2 {self.S2_list} {S2}')
                self.S1_list.clear()
                self.S2_list.clear()
                self.cur_stokes_vector = [1, S1, S2, None]
                phi4 = self.rotate_poles()
                self.last_retardances = self.retardances.copy()
                self.previous_voltage = self.set_voltage.copy()
                volt, phi4 = self.voltage_lookup(phi4,3)
                self.set_voltage[3] = volt
                self.retardances[3] = phi4
                self._set_one_voltage(volt, 3)
                self.next_epoch = get_current_epoch()
                self.next_equator = False
            return
        else:
            # Now at target epoch
            S0, S4, S3 = self.get_S0_S1_S2(diagnosis)
            self.S3_list.append(S3)
            self.S4_list.append(S4)
            if len(self.S3_list) >= self.averaging_n:
                S3 = np.mean(self.S3_list)
                S4 = np.mean(self.S4_list)
                logger.debug(f'S3 {self.S3_list} {S3},S4 {self.S4_list} {S4}')
                self.S3_list.clear()
                self.S4_list.clear()
                self.cur_stokes_vector[3] = S3 * self.S3_swap
                self.retardances = self.last_retardances.copy()
                self.set_voltage = self.previous_voltage.copy()
                self._set_voltage()
                self.next_epoch = None
                self.S3_swap = None
                self.next_equator = True
                self.first_pass = False
            return

    def rotate_stokes_v_to_S1(self):
        stokes_vector = self.cur_stokes_vector.copy()
        curr_ret = self.retardances.copy()
        new_ret = []
        phis = self.compute_polarization_compensation(stokes_vector)
        phis = list(phis)
        for i in range(0,len(curr_ret)):
            new_ret.append(curr_ret[i] + phis[i])
            if phis[i] != 0:
                new_voltage, act_ret = self.voltage_lookup(new_ret[i],i)
                self.set_voltage[i] = new_voltage
                self.retardances[i] = act_ret
        self._set_voltage()

    def lcvr_instant_find(self):
        """To replace the current random walk method.

        i.e. lcvr_narrow_down()
        """
        stokes_vector = self.stokes_v
        logger.debug(f'Stokes vector is {stokes_vector}')
        phi1, phi2, phi3, phi4 = self.compute_polarization_compensation(stokes_vector)
        logger.debug(f'Angles phi {phi1} {phi2} {phi3} {phi4}')
        self.set_voltage[2], phi3 = self.voltage_lookup(phi3,2)
        self.set_voltage[3], phi4 = self.voltage_lookup(phi4,3)
        self.retardances = [phi1, phi2, phi3, phi4]
        self._set_voltage()
        #self._set_retardance(self.retardances) # unused for not cause unsure about voltage at zero retardances yet.
        return

    def compute_polarization_compensation(self,stokes_vector: list):
        """Computes phi rotations from a given Stokes vector.
        Assume only rotations from last 2 LCVRs with theta3=0 and theta4=pi/4.
        theta1=0 and theta2=0 and phi1=0, phi2=0
        In order to correct the input to purely linear polarization.
        """
        s1,s2,s3 = stokes_vector[1], stokes_vector[2], stokes_vector[3]
        phi3 = -math.atan2(s2,s3)
        phi4 = math.acos(s1)
        phi1 = 0
        phi2 = 0

        return phi1, phi2, phi3, phi4

    def voltage_lookup(self, retardance: float, id: int) -> float:
        """For a given retardance value, gets the corresponding LCVR voltage.

        Args:
            Retardance: Desired retardance in radians.
            id: Column index of LookUpTab (LUT) to pull data from.
        """

        retdiffVector = self.LUT[id].ret_V - retardance
        min_idx = len(retdiffVector[retdiffVector > 0]) - 1
        voltage_raw = self.LUT[id].volt_V[min_idx] + (retdiffVector[min_idx] / self.LUT[id].grad_V[min_idx])
        voltage = float(round(voltage_raw,3))
        
        if voltage > VOLT_MAX:
            voltage = self.LUT[id].volt_V[-1]
            actual_ret = self.LUT[id].ret_V[-1]
        elif voltage < VOLT_MIN:
            voltage = self.LUT[id].volt_V[0]
            actual_ret = self.LUT[id].ret_V[0]
        else:
            actual_ret = retardance
        
        return voltage, actual_ret
        # The index that is closest to the target retardance is chosen
        # by looking only at the positive differences between the target
        # and the lookup values.


    def retardance_lookup(self, volt: float, id: int = 3 ) -> float:
        """For a given voltage value, get the retardance in radians
        
        Args:
            Voltage: Voltage in Volts.
            id: Column index of LookUpTab (LUT) to pull data from.
        """
        voltdiffVector = self.LUT[id].volt_V - volt
        min_idx = np.argmin(np.abs(voltdiffVector))
        retardance_raw = self.LUT[id].ret_V[min_idx] - (voltdiffVector[min_idx] * self.LUT[id].grad_V[min_idx])
        retardance = float(round(retardance_raw,3))
        logger.debug(f'voltage is {volt}, ret is {retardance}')
        return retardance

    def rotate_poles(self):
        """Looks at self.retardance[3] and add/minus pi/2 depending on the value
        Set a marker"""
        pi_2 = 3.142/2
        if (self.retardances[3] + pi_2) > RETARDANCE_MAX:
            phi4 = self.retardances[3] - pi_2
            self.S3_swap = -1.
            return phi4
        else:
            phi4 = self.retardances[3] + pi_2
            self.S3_swap = 1.
            return phi4

    def bound_retardance(self, retardance_list: list):
        return_val = []
        for ret in retardance_list:
            if ret > RETARDANCE_MAX:
                return_val.append(RETARDANCE_MAX)
            elif ret < RETARDANCE_MIN:
                return_val.append(RETARDANCE_MIN)
            else:
                return_val.append(ret)
        return return_val

    def update_QBER(self, qber: float, qber_threshold: float = QBER_THRESHOLD, epoch: str = None):
        self.qber_counter += 1
        if self.qber_counter < 10: # in case pfind finds a bad match, we don't want to change the lcvr voltage too early
            return

        # 'next_epoch' will be updated when LCVR values are pushed
        # In service mode, all epochs between now (time LCVR values are computed) and 'next_epoch'
        # should be discarded, so that the updated value is properly reflected.
        if not self.epoch_passed(epoch):
            return # start averaging from next epoch onwards

        self.qber_list.append(qber)
        if len(self.qber_list) >= self.averaging_n:
            qber_mean = np.mean(self.qber_list)
            self.qber_list.clear()
            logger.info(
                f'Avg(qber): {qber_mean:.2f} of the last {self.averaging_n} epochs at voltages {self.set_voltage}. Phi search range: {qber_cost_func(qber_mean):.2f}')
            if qber_mean > 0.3:
                self.averaging_n = 2
            if qber_mean < 0.3:
                self.averaging_n = 2
            if qber_mean < 0.15:
                self.averaging_n = 5
            if qber_mean < 0.12:
                self.averaging_n = 10
            if qber_mean < qber_threshold:
                np.savetxt(self.LCR_params.volt_file, [self.set_voltage])
                self._callback()
                logger.info(f'BBM92 called')
                return
            if qber_mean < self.last_qber:
                self.last_voltage_list = self.set_voltage.copy()
                self.last_retardances = self.retardances.copy()
                self.lcvr_narrow_down(qber_mean)
                #np.savetxt(self.LCR_params.LCR_volt_file,
                #           [*self.last_voltage_list])
            else:
                self.set_voltage = self.last_voltage_list.copy()
                self.retardances = self.last_retardances.copy()
                self.lcvr_narrow_down(self.last_qber)
                
            self.next_epoch = get_current_epoch()
            logger.debug(f'Next epoch set to "{hex(self.next_epoch)[2:]}".')
            self.last_qber= qber_mean

    def lcvr_narrow_down(self,  curr_qber: float):
        
        ret_range = qber_cost_func(curr_qber)
        delta_phis = [0]*4
        phis = [0]*4
        lcvr_to_adjust = [ 2, 3] # only adjust these lcvr in n-D search
        lcvr_to_fix = [0, 1] # keep these lcvr phase fixed
        for i in lcvr_to_fix:
            phis[i] = self.retardances[i]
        for i in lcvr_to_adjust:
            delta_phis[i] = np.random.uniform(-ret_range, ret_range)
            phis[i] = self.retardances[i] + delta_phis[i]
        phis = self.bound_retardance(phis)
        logger.debug(f'Phis are {phis}, delta_phis {delta_phis},voltage {self.set_voltage}')
        volt_ret,phi_ret = self._calculate_voltages(phis)
        for i in lcvr_to_adjust:
            self.set_voltage[i] = volt_ret[i]
            self.retardances[i] = phi_ret[i]
        self._set_voltage()
        #self._set_retardance(phis)

    @property
    def voltage(self) -> list:
        return self._voltage

    @voltage.setter
    def voltage(self, value: list):
        assert(len(value) == 4)
        for i in value:
            if i > VOLT_MAX:
                value[i] = VOLT_MAX
                raise ValueError("Set value exceeded Max volt of " + {VOLT_MAX})
            elif i < VOLT_MIN:
                value[i] = VOLT_MIN
                raise ValueError("Set value subceded Min volt of " + {VOLT_MIN})
        self._voltage = value  



import os

LCR_VOLT_FILENAME = 'latest_LCR_voltages.txt'

LCVR1_CALLIBRATION_FILEPATH = 'lcvr_callibration.csv'
LCVR2_CALLIBRATION_FILEPATH = 'lcvr_callibration.csv'

# Lookup table to convert retardances to LCVR voltages

class PolarizationDriftCompensation(object):
    def __init__(self, lcr_path: str = '/dev/serial/by-id/usb-S-Fifteen_Instruments_Quad_LCD_driver_LCDD-001-if00',
                 averaging_n: int = 5):
        self.lcr_driver = LCRDriver(lcr_path)
        self.lcr_driver.all_channels_on()
        self.averaging_n = averaging_n
        self.LCRvoltages_file_name = LCR_VOLT_FILENAME
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


