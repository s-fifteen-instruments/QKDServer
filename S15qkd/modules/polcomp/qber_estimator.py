#!/usr/bin/env python3

import numpy as np

from S15qkd.utils import service_T3
from S15qkd.qkd_globals import logger, FoldersQKD


class QberEstimator:
    """Provides an estimation of QBER depending on the available bits.

    Note:
        Note that this class is not thread-safe, but should work under the assumption
        that QBER computation should take much less than the epoch separation time, i.e.
        0.536s. If thread-safety is desired, one could use 'threading.Lock'.
    """

    def __init__(self):
        self.qber = 1.0
        self.reset()

    def reset(self, desired_bits: int = 0):
        self.desired_bits = desired_bits
        self.accumulated_bits = 0
        self.diagnoses = []

    def handle_epoch(self, epoch) -> float:
        epoch_path = FoldersQKD.RAWKEYS + '/' + epoch
        return self.handle_epoch_path(epoch_path)

    def handle_epoch_path(self, epoch_path) -> float:
        diagnosis = service_T3(epoch_path)
        return self.handle_diagnosis(diagnosis)

    def handle_diagnosis(self, diagnosis) -> float:
        self.diagnoses.append(diagnosis)
        self.accumulated_bits += diagnosis.okcount
        logger.info(
            f"Accumulating bits for QBER calculation: {self.accumulated_bits} / {self.desired_bits}"
        )
        if self.accumulated_bits >= self.desired_bits:
            self.qber = self.calculate_qber()
            self.reset(self._get_desired_bits(self.qber))
        return self.qber

    def calculate_qber(self) -> float:
        # Compute QBER from set of diagnosis in each epoch
        matrices = np.array([d.coinc_matrix for d in self.diagnoses])
        coinc_matrix = np.sum(matrices, axis=0)
        er_coin = sum(coinc_matrix[[0, 5, 10, 15]])  # VV, AA, HH, DD
        gd_coin = sum(coinc_matrix[[2, 7, 8, 13]])  # VH, AD, HV, DA
        qber = round(er_coin / (er_coin + gd_coin), 3) if er_coin + gd_coin != 0 else 1.0
        logger.info(f"Avg(qber): {qber:.2f} of the last {self.accumulated_bits} bits.")
        return qber

    def _get_desired_bits(self, qber) -> int:
        if qber < 0.12:
            return 4000
        if qber < 0.15:
            return 1000
        if qber < 0.3:
            return 800
        else:
            return 400
