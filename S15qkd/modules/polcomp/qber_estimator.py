#!/usr/bin/env python3

import numpy as np

from S15qkd.qkd_globals import FoldersQKD, logger
from S15qkd.utils import service_T3


class QberEstimator:
    """Provides an estimation of QBER depending on the available bits.

    Note:
        Note that this class is not thread-safe, but should work under the assumption
        that QBER computation should take much less than the epoch separation time, i.e.
        0.536s. If thread-safety is desired, one could use 'threading.Lock'.
    """

    MINIMUM_BITS = 400

    def __init__(self):
        self.qber = 1.0
        self.reset()

    def reset(self):
        self.diagnoses = []

    def handle_epoch(self, epoch) -> float:
        epoch_path = FoldersQKD.RAWKEYS + "/" + epoch
        return self.handle_epoch_path(epoch_path)

    def handle_epoch_path(self, epoch_path) -> float:
        diagnosis = service_T3(epoch_path)
        return self.handle_diagnosis(diagnosis)

    def handle_diagnosis(self, diagnosis):
        """Aggregates bits for dynamic QBER calculation.

        Returns 'None' if accumulated bits are insufficient to make a precise
        estimation of QBER, otherwise a float value [0,1] will be returned.
        """
        self.diagnoses.append(diagnosis)

        # Do nothing if insufficient bits
        qber, accumulated_bits = self._calculate_qber()
        desired_bits = self._get_desired_bits(qber)
        if accumulated_bits < desired_bits:
            logger.info(
                "Accumulating more bits for QBER calculation: "
                f"{accumulated_bits} / {desired_bits}"
            )
            return None
        else:
            self.qber = qber  # commit QBER since sufficient bits
            self.reset()
            return self.qber

    def _calculate_qber(self) -> float:
        """Computes QBER from the accumulated set of diagnosis.

        TODO:
            Integrate this into 'handle_diagnosis()' to avoid aggressive
            recomputation of QBER. This currently behaves poorly when the
            number of coincidences per epoch is low.
        """
        # Compute QBER from set of diagnosis in each epoch
        matrices = np.array([d.coinc_matrix for d in self.diagnoses])
        coinc_matrix = np.sum(matrices, axis=0)
        er_coin = sum(coinc_matrix[[0, 5, 10, 15]])  # VV, AA, HH, DD
        gd_coin = sum(coinc_matrix[[2, 7, 8, 13]])  # VH, AD, HV, DA
        tt_coin = er_coin + gd_coin
        qber = round(er_coin / tt_coin, 3) if tt_coin != 0 else 1.0
        logger.info(f"Avg(QBER): {qber:.3f} of the last {tt_coin} bits.")
        return qber, tt_coin

    def _get_desired_bits(self, qber) -> int:
        if qber < 0.12:
            return 4000
        if qber < 0.15:
            return 1000
        if qber < 0.30:
            return 800
        else:
            return QberEstimator.MINIMUM_BITS
