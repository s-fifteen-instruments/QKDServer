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
from collections import deque
from xmlrpc.client import Boolean
import numpy as np
import math
import time
from typing import Tuple, NamedTuple, Any
from dataclasses import dataclass

from S15lib.instruments.lcr_driver import LCRDriver, MockLCRDriver
from .utils import HeadT1, ServiceT3, service_T3
from . import qkd_globals
from .qkd_globals import logger, FoldersQKD
from .utils import Process

VOLT_MIN = 0.9
VOLT_MAX = 5.5
RETARDANCE_MAX = 4.58
RETARDANCE_MIN = 1.18
EPOCH_DURATION = 0.537
#QBER_THRESHOLD = 0.085
MAX_UPDATE_NUM = 1100 # ~ 10 minutes

DESIRED_QBER = Process.config.qcrypto.polarization_compensation.target_qber
LOSS_COEFFICIENT = Process.config.qcrypto.polarization_compensation.loss_coefficient
LOSS_EXPONENT = Process.config.qcrypto.polarization_compensation.loss_exponent
QBER_HISTLEN = Process.config.qcrypto.polarization_compensation.qber_history_length

def qber_cost_func(
        qber: float,
        desired_qber: float = DESIRED_QBER,
        amplitude: float = LOSS_COEFFICIENT,
        exponent: float = LOSS_EXPONENT,
    ) -> float:
    """Returns a measure of distance to desired QBER.

    Used in polarization compensation to tune the search range of the LCVRs.

    Note:
        This is not formally a metric since triangle inequality not satisfied.
    """
    return amplitude * (max(qber,desired_qber)-desired_qber)**exponent

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
        self.LCR_params = self.LCR_V(*LCR_volt_info.values())
        self.set_voltage = [self.LCR_params.V1, self.LCR_params.V2,
                            self.LCR_params.V3, self.LCR_params.V4]
        self._load_lut()

        # Apply parameters
        self._reset()
        self._set_voltage()
        self.last_voltage_list = self.set_voltage.copy()
        self._calculate_retardances()
        self._callback = callback_service_to_BBM92
        self.qber_threshold = qkd_globals.config['QBER_threshold'] # threshold to start BBM92
        self.qber_threshold_2 = self.qber_threshold + 0.10 # threshold to go from do_walks(1-D walk) to update QBER (n-D walk)
        logger.debug(f'pol com initialized')

    def save_config(self):
        """Writes current LCVR voltages to configuration of current connection."""
        curr_conn = Process.config.remote_connection_id
        Process.config.connections.__dict__[curr_conn].LCR_volt_info = SimpleNamespace()
        Process.config.connections.__dict__[curr_conn].LCR_volt_info.V1 = self.lcr.V1
        Process.config.connections.__dict__[curr_conn].LCR_volt_info.V2 = self.lcr.V2
        Process.config.connections.__dict__[curr_conn].LCR_volt_info.V3 = self.lcr.V3
        Process.config.connections.__dict__[curr_conn].LCR_volt_info.V4 = self.lcr.V4
        logger.debug(f"Current Polarization is: {self.lcr.V1}, {self.lcr.V2}, {self.lcr.V3}, {self.lcr.V4}. Config saved")

    def load_config(self):
        """Loads LCVR voltages from configuration of current connection."""
        config = Process.config
        self.set_voltage = [
            config.LCR_volt_info.V1,
            config.LCR_volt_info.V2,
            config.LCR_volt_info.V3,
            config.LCR_volt_info.V4,
        ]
        self._set_voltage()
        self.last_voltage_list = self.set_voltage.copy()

    def _reset(self):
        self.qber_list = []
        self.S1_list = []
        self.S2_list = []
        self.S3_list = []
        self.S4_list = []
        self.counter = 0
        self._last_qber = 1
        self._last_qbers = deque(maxlen=QBER_HISTLEN)
        self.qber_counter = 0
        self.qber_current = 1
        self.averaging_n = 2000
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
        logger.debug(f'self.retardances : {self.retardances}')
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
            logger.debug(f'Ignored epoch: {epoch}. Next epoch is {hex(self.next_epoch)[2:]}')
            return False
        logger.debug(f'Good epoch: {epoch}. Next epoch is {hex(self.next_epoch)[2:]}')
        return True

    def epoch_match(self, epochstr:str ,epochint: int) -> Boolean:
        epoch1_int = int(epochstr,16)
        if epoch1_int <= epochint:
            return False
        return True

    def start_walk(self):
        """Triggers initial strategy of searching for rough minima."""
        thread = threading.Thread(target=self.do_walks) # defaults to lcvr_idx=0
        thread.start()
        logger.debug(f'do walk started')

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
        voltage_list.append(self.last_voltage_list[lcvr_idx])
        if self.first_pass and self.next_id == 0:
            retardance_list = np.linspace(self.retardance_lookup(VOLT_MIN, lcvr_idx),
                                          self.retardance_lookup(VOLT_MAX, lcvr_idx),
                                          num=11)
        else:
            del_ret = self.qber_current * 5 # walking range is dependent on current qber
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
            time.sleep(EPOCH_DURATION*1.5)
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

    def find_diagnosis_from_epoch(self, epoch_path):
        diagnosis = service_T3(epoch_path)
        return diagnosis

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
                self._last_qber = qber_min
        self._voltage_list = []
        self.last_voltage_list = self.set_voltage.copy() # for update qber later on

        logger.debug(f'Minimum QBER {qber_min} at {self.set_voltage}')
        self._set_voltage()
        self._calculate_retardances()
        self.last_retardances = self.retardances.copy()
        self.qber_current = qber_min
        self.next_epoch = get_current_epoch()
        if qber_min < self.qber_threshold: # minimum qber applied is low enough. Start BBM92.
            self.last_voltage_list = self.set_voltage.copy()
            self.last_retardances = self.retardances.copy()
            self._last_qber= qber_min
            # Flush QBER history with lowest QBER value
            self._last_qbers.extend([qber_min]*QBER_HISTLEN)
            self.qber_counter=0
            self._callback()
            logger.info(f'BBM92 called')
            return False
        elif qber_min < self.qber_threshold_2: # minimum qber applied is low enough. .
            return False
        return True

    def narrow_down(self, qber: float, epoch: str):
        """From the current set_voltages and qber,
        narrow down to below threshold qber."""
        if not self.narrow_down_list: #first entry
            self._last_qber = self.qber_current
            self._set_voltage()
            self.next_epoch = get_current_epoch()
            return
        if not self.epoch_passed(epoch):
            return
        if qber > self.qber_current:
            return

    def send_epoch(self, epoch: str = None):
        """Receives the epoch from controller and performs
           polarization compensation. Only done in
           SERVICE mode.
           The function name makes more sense from the
           controller side. This script is actually
           receiving the epoch.
        """
        epoch_path = FoldersQKD.RAWKEYS + '/' + epoch
        if self.walks_array:
            self.process_qber(self.find_qber_from_epoch(epoch_path), epoch)
        else:
            self.update_QBER_from_diagnosis(
                self.find_diagnosis_from_epoch(epoch_path),
                self.qber_threshold,
                epoch,
            )

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

    def update_QBER_secure(self, qber: float, epoch:str = None):
        """Feedback for polarization compensation algorithm.

        Typically called from error correction module, in order to update
        the QBER obtained after error correction. In order to avoid
        latching onto a low QBER borne from statistical fluctuations, a
        sliding mean of historical QBER is used. This history will be
        flushed with the lowest measured QBER to allow initial attempts to
        improve the QBER.
        """
        if not self.epoch_passed(epoch):
            return  # polcomp results not present in this epoch

        # Use current settings as new reference, if current QBER is lower
        target_qber = np.mean(self._last_qbers)
        voltages = list(map(lambda v: round(v,3), self.set_voltage.copy()))
        logger.debug("Current QBER %.3f, target QBER %.3f, voltages %s", qber, target_qber, voltages)
        if qber < target_qber:
            self.last_voltage_list = self.set_voltage.copy()
            self.last_retardances = self.retardances.copy()
            self.lcvr_narrow_down2(qber)
            self._last_qber= qber
            # Flush QBER history with lowest value and retry
            self._last_qbers.extend([qber]*QBER_HISTLEN)

        else:
            # Update new target
            self._last_qbers.append(qber)
            target_qber = np.mean(self._last_qbers)

            self.set_voltage = self.last_voltage_list.copy()
            self.retardances = self.last_retardances.copy()
            self.lcvr_narrow_down2(target_qber)
        self.next_epoch = get_current_epoch()
        logger.debug(f'Next epoch set to "{hex(self.next_epoch)[2:]}".')

    def update_QBER_from_diagnosis(self, diagnosis, qber_threshold: float = 0.085, epoch: str = None):
        self.qber_counter += 1
        if self.qber_counter < 10: # in case pfind finds a bad match, we don't want to change the lcvr voltage too early
            return

        # 'next_epoch' will be updated when LCVR values are pushed
        # In service mode, all epochs between now (time LCVR values are computed) and 'next_epoch'
        # should be discarded, so that the updated value is properly reflected.
        if not self.epoch_passed(epoch):
            return # start averaging from next epoch onwards

        self.qber_list.append(diagnosis)
        total_bits = sum([d.okcount for d in self.qber_list])
        # Note: 'averaging_n' represents the number of bits to calculate the averaged QBER over
        logger.info("Accumulating bits for QBER calculation: %d / %d", total_bits, self.averaging_n)
        if total_bits >= self.averaging_n:

            # Compute QBER from set of diagnosis in each epoch
            matrices = np.array([d.coinc_matrix for d in self.qber_list])
            coinc_matrix = np.sum(matrices, axis=0)
            er_coin = sum(coinc_matrix[[0, 5, 10, 15]])  # VV, AA, HH, DD
            gd_coin = sum(coinc_matrix[[2, 7, 8, 13]])  # VH, AD, HV, DA
            if er_coin + gd_coin == 0:
                qber_mean = 1.0
            else:
                qber_mean = round(er_coin / (er_coin + gd_coin), 3)

            self.qber_list.clear()
            logger.info(
                f'Avg(qber): {qber_mean:.2f} of the last {total_bits} bits at voltages {self.set_voltage}. Phi search range: {qber_cost_func(qber_mean):.2f}')
            if qber_mean > 0.3:
                self.averaging_n = 400
            if qber_mean < 0.3:
                self.averaging_n = 800
            if qber_mean < 0.15:
                self.averaging_n = 1000
            if qber_mean < 0.12:
                self.averaging_n = 4000
            if qber_mean < qber_threshold:
                logger.debug("Ready to call BBM92")
                self.last_voltage_list = self.set_voltage.copy()
                self.last_retardances = self.retardances.copy()
                self._callback()
                self._last_qber = qber_mean
                logger.info('BBM92 called')
                self.qber_counter=0
                return
            if qber_mean < self._last_qber:
                self.last_voltage_list = self.set_voltage.copy()
                self.last_retardances = self.retardances.copy()
                self.lcvr_narrow_down(qber_mean)
            else:
                self.set_voltage = self.last_voltage_list.copy()
                self.retardances = self.last_retardances.copy()
                self.lcvr_narrow_down(self._last_qber)

            self.next_epoch = get_current_epoch()
            logger.debug(f'Next epoch set to "{hex(self.next_epoch)[2:]}".')
            self._last_qber= qber_mean

        # Update QBER is stuck in some range that has not converged for MAX_UPDATE_NUM.
        # Kick it out by doing something different instead of calling lcvr_narrow_down
        if self.qber_counter > MAX_UPDATE_NUM:
            self.kickout()
            self.next_epoch = get_current_epoch()
            self.qber_counter = 10
            self.averaging_n = 2000
            self.qber_list.clear()
            self._last_qber = 1 # Set to one to not go back to last voltage values
            self.do_walks(0)

    def kickout(self):
        lcvr_to_kick = [0, 1]
        for i in lcvr_to_kick:
            self.set_voltage[i] = np.random.uniform(VOLT_MIN + 0.2,VOLT_MAX - 0.2)
        self._set_voltage()
        self._calculate_retardances()
        logger.debug(f'Kicked to new voltage.')

    def lcvr_narrow_down(self,  curr_qber: float):
        ret_range = qber_cost_func(curr_qber)
        delta_phis = [0]*4
        phis = [0]*4
        lcvr_to_adjust = [0, 1, 2, 3] # only adjust these lcvr in n-D search
        lcvr_to_fix = [] # keep these lcvr phase fixed
        for i in lcvr_to_fix:
            phis[i] = self.retardances[i]
        for i in lcvr_to_adjust:
            delta_phis[i] = np.random.uniform(-ret_range, ret_range)
            phis[i] = self.retardances[i] + delta_phis[i]
        phis = self.bound_retardance(phis)
        volt_ret,phi_ret = self._calculate_voltages(phis)
        logger.debug(f'qber {curr_qber:.3f}, ret_range {ret_range:.6f}, old_voltage {self.set_voltage}, new_voltage {volt_ret}')
        for i in lcvr_to_adjust:
            self.set_voltage[i] = volt_ret[i]
            self.retardances[i] = phi_ret[i]
        self._set_voltage()
        logger.debug(f'Phis are {phis},self.retardances {self.retardances}, delta_phis {delta_phis},voltage {self.set_voltage}')

    def lcvr_narrow_down2(self,  curr_qber: float):
        ret_range = qber_cost_func(curr_qber)
        delta_phis = [0]*4
        phis = [0]*4
        lcvr_to_adjust = [1, 2, 3] # only adjust these lcvr in n-D search
        lcvr_to_fix = [0] # keep these lcvr phase fixed
        logger.debug(f'Phis began with {phis},self.retardances {self.retardances}, delta_phis {delta_phis},voltage {self.set_voltage}')
        for i in lcvr_to_fix:
            phis[i] = self.retardances[i]
        for i in lcvr_to_adjust:
            delta_phis[i] = np.random.uniform(-ret_range, ret_range)
            phis[i] = self.retardances[i] + delta_phis[i]
        phis = self.bound_retardance(phis)
        volt_ret,phi_ret = self._calculate_voltages(phis)
        logger.debug(f'qber {curr_qber:.3f}, ret_range {ret_range:.6f}, old_voltage {self.set_voltage}, new_voltage {volt_ret}')
        for i in lcvr_to_adjust:
            self.set_voltage[i] = volt_ret[i]
            self.retardances[i] = phi_ret[i]
        self._set_voltage()
        logger.debug(f'Phis are {phis},self.retardances {self.retardances}, delta_phis {delta_phis},voltage {self.set_voltage}')

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

    @property
    def last_qber(self) -> float:
        return self._last_qber


class MockPolComp:
    """Enumerates interface exposed to Controller.

    Does no actual polarization compensation, but instead monitors and writes out
    to file at 'QBER_READOUT_PATH' for external service to handle.
    """

    QBER_READOUT_PATH = "/tmp/cryptostuff/mockpolcomp_qber_epoch.txt"

    #==========  PUBLIC METHODS  ==========

    def __init__(self, lcr_path, callback_service_to_BBM92=None):  # Controller::__init__
        self.lcr = MockLCRDriver(lcr_path)  # Controller::update_config
        self.set_voltage = [0, 0, 0, 0]  # Controller::reload_configuration
        self.last_voltage_list = self.set_voltage.copy()  # Controller::reload_configuration
        self._callback = callback_service_to_BBM92
        self._last_qber = 1
        self.averaging_n = 2000
        self.qber_counter = 0
        self.qber_list = []
        self.qber_threshold = qkd_globals.config['QBER_threshold']

    def _set_voltage(self):  # Controller::reload_configuration
        """Commits voltages."""
        (
            self.lcr.V1,
            self.lcr.V2,
            self.lcr.V3,
            self.lcr.V4,
        ) = self.set_voltage

    def send_epoch(self, epoch_path):  # Controller::send_epoch_notification
        """Responsible for extracting QBER and calling SERVICE->BBM92.

        SERVICE mode only.
        """
        epoch = epoch_path.split('/')[-1]
        self.update_QBER_from_diagnosis(
            self.find_diagnosis_from_epoch(epoch_path),
            self.qber_threshold,
            epoch,
        )

    def update_QBER_secure(self, qber, epoch):  # Controller::drift_secure_comp
        """
        BBM92 mode only.
        """
        self._last_qber = qber
        self._write_qber_epoch(qber, epoch)

    def do_walks(self):  # Controller::pol_com_walk
        pass

    @property
    def last_qber(self) -> float:  # Controller::get_status_info
        return self._last_qber


    #==========  INTERNAL METHODS  ==========

    def _write_qber_epoch(self, qber, epoch):
        with open(self.QBER_READOUT_PATH, "w") as f:
            f.write(f"{qber} {epoch}")

    def find_diagnosis_from_epoch(self, epoch_path):
        diagnosis = service_T3(epoch_path)
        return diagnosis

    def update_QBER_from_diagnosis(self, diagnosis, qber_threshold: float = 0.085, epoch: str = None):
        self.qber_counter += 1
        if self.qber_counter < 10: # in case pfind finds a bad match, we don't want to change the lcvr voltage too early
            return

        self.qber_list.append(diagnosis)
        total_bits = sum([d.okcount for d in self.qber_list])
        logger.info("Accumulating bits for QBER calculation: %d / %d", total_bits, self.averaging_n)
        if total_bits >= self.averaging_n:

            # Compute QBER from set of diagnosis in each epoch
            matrices = np.array([d.coinc_matrix for d in self.qber_list])
            coinc_matrix = np.sum(matrices, axis=0)
            er_coin = sum(coinc_matrix[[0, 5, 10, 15]])  # VV, AA, HH, DD
            gd_coin = sum(coinc_matrix[[2, 7, 8, 13]])  # VH, AD, HV, DA
            if er_coin + gd_coin == 0:
                qber_mean = 1.0
            else:
                qber_mean = round(er_coin / (er_coin + gd_coin), 3)

            self.qber_list.clear()
            logger.info(
                f'Avg(qber): {qber_mean:.2f} of the last {total_bits} bits.')

            qber = qber_mean
            self._last_qber = qber
            self._write_qber_epoch(qber, epoch)

            if qber_mean > 0.3:
                self.averaging_n = 400
            if qber_mean < 0.3:
                self.averaging_n = 800
            if qber_mean < 0.15:
                self.averaging_n = 1000
            if qber_mean < 0.12:
                self.averaging_n = 4000
            if qber_mean < qber_threshold:
                self._callback()
                return


class PaddlePolComp(MockPolComp):
    pass
