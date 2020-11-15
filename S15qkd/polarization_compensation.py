#!/usr/bin/env python3

import os
import numpy as np
from typing import Tuple
from S15lib.instruments import LCRDriver
from .qkd_globals import logger
from . import controller

LCR_VOlT_FILENAME = 'latest_LCR_voltages.txt'
VOLT_MIN = 0.5
VOLT_MAX = 4.5


def qber_cost_func(qber: float, desired_qber: float = 0.03, amplitude: float = 16) -> float:
    return amplitude * (qber - desired_qber)**2


class PolarizationDriftCompensation(object):
    def __init__(self, lcr_path: str = '/dev/serial/by-id/usb-Centre_for_Quantum_Technologies_Quad_LCD_driver_QLC-QO05-if00',
                 averaging_n: int = 5):
        self.lcr_driver = LCRDriver(lcr_path)
        self.lcr_driver.all_channels_on()
        self.averaging_n = averaging_n
        self.LCRvoltages_file_name = LCR_VOlT_FILENAME
        if not os.path.exists(self.LCRvoltages_file_name):
            np.savetxt(self.LCRvoltages_file_name, [1.5, 1.5, 1.5, 1.5])
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

    def update_QBER(self, qber: float, qber_threshold: float = 0.1, qber_stop_service_mode: float = 0.08):
        self.qber_counter += 1
        if self.qber_counter < 200:
            return
        self.qber_list.append(qber)
        if len(self.qber_list) >= self.averaging_n:
            qber_mean = np.mean(self.qber_list)
            self.qber_list.clear()
            logger.info(
                f'Avg(qber): {qber_mean:.2f} of the last {self.averaging_n} epochs. Voltage search range: {qber_cost_func(qber_mean):.2f}')
            if qber_mean > 0.3:
                self.averaging_n = 3
            if qber_mean < 0.3:
                self.averaging_n = 10
            if qber_mean < 0.15:
                self.averaging_n = 15
            logger.info(
                f'Avg(qber): {qber_mean:.2f} averaging over {self.averaging_n} epochs. V_range: {qber_cost_func(qber_mean):.2f}')
            if qber_mean < qber_threshold:
                if qber_mean < qber_stop_service_mode:
                    controller.stop_key_gen()
                return
            if qber_mean < self.last_qber:
                self.last_voltage_list = [self.V1, self.V2, self.V3, self.V4]
                self.lcvr_narrow_down(*self.last_voltage_list,
                                      qber_cost_func(qber_mean))
                np.savetxt(self.LCRvoltages_file_name, [*self.last_voltage_list])
            else:
                self.lcvr_narrow_down(*self.last_voltage_list,
                                      qber_cost_func(self.last_qber))
            self.last_qber = qber_mean

    def lcvr_narrow_down(self, c1: float, c2: float, c3: float, c4: float, r_narrow: float) -> Tuple[float, float, float, float]:
        self.V1 = np.random.uniform(max(c1 - r_narrow, VOLT_MIN),
                                    min(c1 + r_narrow, VOLT_MAX))
        self.V2 = np.random.uniform(max(c2 - r_narrow, VOLT_MIN),
                                    min(c2 + r_narrow, VOLT_MAX))
        self.V3 = np.random.uniform(max(c3 - r_narrow, VOLT_MIN),
                                    min(c3 + r_narrow, VOLT_MAX))
        self.V4 = np.random.uniform(max(c4 - r_narrow, VOLT_MIN),
                                    min(c4 + r_narrow, VOLT_MAX))
        # logger.info(f'{self.V1}, {self.V2}, {self.V3}, {self.V4}')
        self.lcr_driver.V1 = self.V1
        self.lcr_driver.V2 = self.V2
        self.lcr_driver.V3 = self.V3
        self.lcr_driver.V4 = self.V4
