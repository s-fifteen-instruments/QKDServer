#!/usr/bin/env python3

import os
import numpy as np
from typing import Tuple
from S15lib.instruments import LCRDriver

LCR_VOlT_FILENAME = 'latest_LCR_voltages.txt'
LCVR_0 = 1
LCVR_1 = 2
LCVR_2 = 3
LCVR_3 = 4
VOLT_MIN = 0.5
VOLT_MAX = 4.5


def qber_cost_func(qber: float) -> float:
    return 8 * (qber - 0.05)**2


class PolarizationDriftCompensation(object):
    def __init__(self, lcr_path: str = '/dev/serial/by-id/usb-Centre_for_Quantum_Technologies_Quad_LCD_driver_QLC-QO05-if00', averaging_n: int = 2, monte_carlo_n: int = 10):
        self.lcr_driver = LCRDriver(lcr_path)
        self.lcr_driver.all_channels_on()
        self.averaging_n = averaging_n
        self.monte_carlo_n = monte_carlo_n
        self.LCRvoltages_file_name = LCR_VOlT_FILENAME
        if not os.path.exists(self.LCRvoltages_file_name):
            np.savetxt(self.LCRvoltages_file_name, [1.5, 1.5, 1.5, 1.5])
        self.V1, self.V2, self.V3, self.V4 = np.genfromtxt(
            self.LCRvoltages_file_name).T
        print(self.V1, self.V2, self.V3, self.V4)
        self.lcr_driver.set_voltage(LCVR_0, self.V1)
        self.lcr_driver.set_voltage(LCVR_1, self.V2)
        self.lcr_driver.set_voltage(LCVR_2, self.V3)
        self.lcr_driver.set_voltage(LCVR_3, self.V4)
        self.latest_qber_list = []
        self.monte_carlo_qber_list = []
        self.monte_carlo_voltages_list = []
        self.curr_voltages_for_search = []

    def update_QBER(self, QBER: float):
        self.latest_qber_list.append(QBER)
        if len(self.latest_qber_list) >= self.averaging_n:
            self.monte_carlo_qber_list.append(np.mean(self.latest_qber_list))
            self.latest_qber_list = []
            self.monte_carlo_voltages_list.append(
                self.curr_voltages_for_search)

            if len(self.monte_carlo_qber_list) >= self.monte_carlo_n:
                min_idx = np.argmin(self.monte_carlo_qber_list)
                r_narrow = qber_cost_func(self.monte_carlo_qber_list[min_idx])
                self.V1, self.V2, self.V3, self.V4 = self.monte_carlo_voltages_list[min_idx]
                np.savetxt(self.LCRvoltages_file_name,
                           [self.V1, self.V2, self.V3, self.V4])
                self.monte_carlo_voltages_list = []
                self.monte_carlo_qber_list = []

            self.curr_voltages_for_search = self.lcvr_narrow_down(
                self.V1, self.V2, self.V3, self.V4, r_narrow)

    def lcvr_narrow_down(self, c1: float, c2: float, c3: float, c4: float, r_narrow: float) -> Tuple[float, float, float, float]:
        r1 = np.random.uniform(max(c1 - r_narrow, VOLT_MIN),
                               min(c1 + r_narrow, VOLT_MAX))
        r2 = np.random.uniform(max(c2 - r_narrow, VOLT_MIN),
                               min(c2 + r_narrow, VOLT_MAX))
        r3 = np.random.uniform(max(c3 - r_narrow, VOLT_MIN),
                               min(c3 + r_narrow, VOLT_MAX))
        r4 = np.random.uniform(max(c4 - r_narrow, VOLT_MIN),
                               min(c4 + r_narrow, VOLT_MAX))
        self.lcr_driver.set_voltage(LCVR_0, r1)
        self.lcr_driver.set_voltage(LCVR_1, r2)
        self.lcr_driver.set_voltage(LCVR_2, r3)
        self.lcr_driver.set_voltage(LCVR_3, r4)
        return r1, r2, r3, r4
