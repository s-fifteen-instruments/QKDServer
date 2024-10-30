#!/usr/bin/env python3
"""Provides the PaddlePolComp class."""

import numpy as np
from fpfind.lib import parse_epochs as parser

from S15qkd.modules.polcomp import optimizers
from S15qkd.modules.polcomp.mock.mockpolcomp import ProxyPolComp
from S15qkd.modules.polcomp.paddles.mpc320 import ThorlabsMPC320
from S15qkd.qkd_globals import QKDProtocol, logger
from S15qkd.utils import get_current_epoch


class PaddlePolComp(ProxyPolComp):
    """Wraps Thorlabs MPC320 for polarization compensation."""

    ABSOLUTE_BOUND = (ThorlabsMPC320.MIN_RANGE, ThorlabsMPC320.MAX_RANGE)
    ABSOLUTE_BOUNDS = [ABSOLUTE_BOUND] * 3
    DEFAULT_ANGLES = (40, 40, 40)
    MIN_THRESHOLD = 2 * ThorlabsMPC320.MIN_STEP

    def __init__(self, device_path, callback_service_to_BBM92=None):
        super().__init__(None, callback_service_to_BBM92)
        self.motor = ThorlabsMPC320(device_path, suppress_errors=True)
        self.protocol = QKDProtocol.SERVICE
        self.optimizer = None
        self._disable_till_protocol_switch = False

        self.load_config()  # single connection ignored
        self._refresh_optimizer()

    def save_config(self):
        """Writes current LCVR voltages to configuration of current connection."""
        pass

    def load_config(self):  # use 'get' instead
        self._commit_angles(PaddlePolComp.DEFAULT_ANGLES)

    def send_epoch(self, epoch):
        # Check for protocol transition
        if self.protocol != QKDProtocol.SERVICE:
            self.protocol = QKDProtocol.SERVICE
            self._disable_till_protocol_switch = False
            self._refresh_optimizer()

        # Ignore if protocol due for switching
        if self._disable_till_protocol_switch:
            return

        # Proxy epoch only if specified epoch has passed
        epochint = parser.epoch2int(epoch)
        if epochint <= self.prev_epochint:
            logger.debug(
                f"Ignored epoch {epoch}: "
                f"waiting for epoch {parser.int2epoch(self.prev_epochint)}"
            )
            return

        # Proxy QBER only if estimator returns a QBER estimate
        qber = self.estimator.handle_epoch(epoch)
        if qber is None:
            return

        # Update QBER and handle BBM92 trigger
        self.qber = qber
        self._write_qber(self.qber, epoch)
        if self.qber < self.qber_threshold:
            self._disable_till_protocol_switch = True
            self._callback()
            return

        # Check if angle difference too small => optimization failed
        angles = self.optimizer(self.qber)
        logger.debug(
            f"Adjusting {self._format_angles(self.prev_angles)} "
            f"-> {self._format_angles(angles)} "
            f"for QBER {self.qber*100:.1f}% @ epoch {epoch}"
        )
        dx = np.array(angles) - np.array(self.prev_angles)
        if np.all(np.abs(dx) < PaddlePolComp.MIN_THRESHOLD):
            self._refresh_optimizer()
            angles = self.optimizer(self.qber)

        # Send epochs only after specified epoch has passed
        self._commit_angles(angles)

    def update_QBER_secure(self, qber, epoch):
        # Check for protocol transition
        if self.protocol != QKDProtocol.BBM92:
            self.protocol = QKDProtocol.BBM92
            self._disable_till_protocol_switch = False
            self._refresh_optimizer()

        # Ignore if protocol due for switching
        if self._disable_till_protocol_switch:
            return

        # Update QBER
        super().update_QBER_secure(qber, epoch)

    ######################
    #  INTERNAL METHODS  #
    ######################

    def _commit_angles(self, angles):
        self.prev_angles = angles
        self.motor.angles = angles
        self.prev_epochint = get_current_epoch()  # motor takes time to rotate

    def _refresh_optimizer(self):
        """Resets and assigns new optimizer based on current protocol.

        Be careful: this method has two side-effects, affecting 'optimizer'
        and 'estimator'.
        """
        # Terminates existing optimizations
        if self.optimizer:
            self.optimizer(None)  # graceful connection close
            self.optimizer = None

        # Restart QBER calculation
        self.estimator.reset()

        # Create new optimizer
        kwargs = {
            "x0": self.motor.angles,  # start from current position
            "step": 80 if self.protocol is QKDProtocol.SERVICE else 30,
            "bounds": PaddlePolComp.ABSOLUTE_BOUNDS,
        }
        self.optimizer = optimizers.run_manual_optimizer(
            optimizers.minimize_neldermead,
            kwargs=kwargs,
        )

    def _format_angles(self, angles) -> str:
        """For pretty-printing 3-tuple 'angles'."""
        angles = [f"{a:.2f}" for a in angles]
        return f"({' '.join(angles)})"
