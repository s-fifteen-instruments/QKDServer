#!/usr/bin/env python3
import subprocess

from .utils import Process
from .qkd_globals import logger, FoldersQKD

class Pfind(Process):

    def measure_time_diff(self, first_epoch, use_periods) -> list:
        assert not self.is_running()
        logger.info("pfind: %s / %s", Process.config.qcrypto.pfind.number_of_epochs, use_periods)
        args = [
            '-d', FoldersQKD.RECEIVEFILES,
            '-D', FoldersQKD.T1FILES,
            '-e', f'0x{first_epoch}',
            '-n', Process.config.qcrypto.pfind.number_of_epochs,
            '-V', 1,
            '-q', Process.config.FFT_buffer_order,
            '-R', Process.config.qcrypto.pfind.coarse_resolution,
            '-r', Process.config.qcrypto.pfind.fine_resolution,
        ]
        super().start(args, stdout=subprocess.PIPE, stderr="pfinderror")
        self.wait()

        output = self.process.stdout.read().decode()
        if len(output) == 0:
            logger.error("pfind did not return anything")
            raise RuntimeError  # TODO: Subclass this.

        result = output.split()
        logger.info(f'Pfind result: {result}')
        return list(map(float, result))

    def measure_time_freq_diff(self, first_epoch, use_periods) -> list:
        assert not self.is_running()
        args = [
            '-d', FoldersQKD.RECEIVEFILES,
            '-D', FoldersQKD.T1FILES,
            '-e', f'0x{first_epoch}',
            '-q', Process.config.FFT_buffer_order,
            '-R', Process.config.qcrypto.pfind.coarse_resolution,
            '-r', Process.config.qcrypto.pfind.fine_resolution,
            '-s', 5,
            '--freq-threshold', 10,
            '--convergence-rate', 0.1,
            '-P',
            '--precomp-stop', 1e-6,
            '-V', 0b1001,
            '-vvv',
        ]
        super().start(args, stdout=subprocess.PIPE, stderr="fpfinderror")
        self.wait()

        output = self.process.stdout.read().decode()
        if len(output) == 0:
            logger.error("fpfind did not return anything")
            raise RuntimeError  # TODO: Subclass this.

        result = output.strip().split("\t")
        logger.info(f'Fpfind result: {result}')
        fd, td = list(map(float, result))
        return fd, td
