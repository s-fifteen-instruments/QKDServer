#!/usr/bin/env python3

import os
import numpy as np
import time
from typing import Tuple
from S15lib.instruments import LCRDriver
from .qkd_globals import logger
from . import controller

LCR_VOlT_FILENAME = 'latest_LCR_voltages.txt'
VOLT_MIN = 0.9
VOLT_MAX = 5.5


def qber_cost_func(qber: float, desired_qber: float = 0.04, amplitude: float = 6) -> float:
    return amplitude * (qber - desired_qber)**2

def get_current_epoch():
    """Returns the current epoch in integer.

    Hex value of epoch can be checked with 'hex(get_current_epoch())[2:]'.
    """
    return time.time_ns() >> 29

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
                np.savetxt(self.LCRvoltages_file_name, [self.V1, self.V2, self.V3, self.V4])
                controller.stop_key_gen()
                logger.info('Attempting to start key generation')
                controller.start_key_generation()
                return
            if qber_mean < self.last_qber:
                self.last_voltage_list= [self.V1, self.V2, self.V3, self.V4]
                self.lcvr_narrow_down(*self.last_voltage_list,
                                      qber_cost_func(qber_mean))
                np.savetxt(self.LCRvoltages_file_name,
                           [*self.last_voltage_list])
            else:
                self.lcvr_narrow_down(*self.last_voltage_list,
                                      qber_cost_func(self.last_qber))
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

    def get_qber_4ep(self, dia_file: str = '/tmp/cryptostuff/diagdata'):
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

