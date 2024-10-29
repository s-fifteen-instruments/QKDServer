#!/usr/bin/env python3
"""Provides the MockPolComp class."""

import time

from S15qkd import qkd_globals
from S15qkd.modules.polcomp.qber_estimator import QberEstimator


class MockPolComp:
    """Enumerates interface exposed to Controller."""

    def __init__(
        self, lcr_path, callback_service_to_BBM92=None
    ):  # Controller.__init__()
        self._callback = callback_service_to_BBM92
        self.estimator = QberEstimator()
        self.qber = self.estimator.qber
        self.qber_threshold = qkd_globals.config["QBER_threshold"]

    def send_epoch(self, epoch):  # Controller.send_epoch_notification()
        """Process notification of epoch provided by costream/splicer.

        Responsible for extracting QBER and calling SERVICE->BBM92.
        """
        self.qber = self.estimator.handle_epoch(epoch)
        if self.qber < self.qber_threshold:
            self._callback()

    def update_QBER_secure(self, qber, epoch):  # Controller.drift_secure_comp()
        """Process notification of QBER @ epoch provided by error correction.

        Direct counterpart to PolComp.send_epoch().
        """
        self.qber = qber

    def start_walk(self):  # Controller.pol_com_walk()
        pass

    def save_config(self):  # Controller.reload_configuration()
        pass

    def load_config(self):  # Controller.reload_configuration()
        pass

    @property
    def last_qber(self) -> float:  # Controller.get_status_info()
        return self.qber


class ProxyPolComp(MockPolComp):
    """Proxies the QBER information to a writable file, for handling by other interfaces."""

    READOUT_FILE = "/tmp/cryptostuff/mockpolcomp_qber_epoch.txt"

    def send_epoch(self, epoch):
        super().send_epoch(epoch)
        self._write_qber(self.qber, epoch)

    def update_QBER_secure(self, qber, epoch):
        super().update_QBER_secure(qber, epoch)
        self._write_qber(qber, epoch)

    def _write_qber(self, qber, epoch):
        """Writes QBER and corresponding epoch to temporary file for message passing."""
        with open(ProxyPolComp.READOUT_FILE, "w") as f:
            f.write(f"{qber} {epoch}")

    def _read_qber(self):
        with open(ProxyPolComp.READOUT_FILE) as f:
            data = f.read()
        qber, epoch = data.strip().split(" ")
        qber = float(qber)
        return qber, epoch

    def _read_qber_after(self, epoch):
        """Monitors and returns the QBER after specified epoch."""
        from fpfind.lib import parse_epochs as parser

        epochint = parser.epoch2int(epoch)
        while True:
            qber, _epoch = self._read_qber()
            _epochint = parser.epoch2int(_epoch)
            if _epochint > epochint:
                return qber
            time.sleep(0.5)  # wait for next epoch
