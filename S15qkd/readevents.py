#!/usr/bin/env python3

import pathlib
import subprocess
import os
import numpy as np

from .utils import Process
from . import qkd_globals
from .qkd_globals import logger, PipesQKD

class Readevents(Process):

    def __init__(self, process):
        super().__init__(process)
        self.blinded = False

    def generate_base_args(self):
        """Returns token list for running readevents with subprocess."""
        # Detector skew in units of 1/256 nsec
        det1corr = Process.config.local_detector_skew_correction.det1corr
        det2corr = Process.config.local_detector_skew_correction.det2corr
        det3corr = Process.config.local_detector_skew_correction.det3corr
        det4corr = Process.config.local_detector_skew_correction.det4corr

        args = [
            '-a', 1,  # always output as binary events
            '-X',     # legacy mode, for compatibility with qcrypto
            '-A',     # absolute time
            '-D', f'{det1corr},{det2corr},{det3corr},{det4corr}',
        ]

        # Fast mode
        use_fast_mode = Process.config.qcrypto.readevents.use_fast_mode
        if use_fast_mode:
            args += ["-f"]

        # Check if reading TTL instead of NIM
        use_ttl_trigger = Process.config.qcrypto.readevents.use_ttl_trigger
        if use_ttl_trigger:
            args += ["-t", 2032]

        return args

    def start(
            self,
            callback_restart=None,    # to restart keygen
        ):
        try:
            assert not self.is_running()
        except AssertionError as msg:
            print(msg)
            callback_restart()

        args = self.generate_base_args()
        args += ["-s"]  # short mode, 49 bits timing info in 1/8 nsec

        # Flush readevents
        super().start(args + ['-q1'])  # With proper termination with sigterm, this should not be necessary anymore.
        self.wait()

        # Persist readevents
        super().start(args, stdout=PipesQKD.RAWEVENTS, stderr="readeventserror", callback_restart=callback_restart)

    def start_sb(
            self,
            callback_restart=None,
            callback_stop=None,
            blindmode=241,
            level1=1080,
            level2=0,
        ):
        try:
            assert not self.is_running()
        except AssertionError as msg:
            print(msg)
            callback_restart()

        self._callback_stop = callback_stop

        args = self.generate_base_args()
        args += ['-b', f'{blindmode},{level1},{level2}']
        # Short mode not enabled - blind bit will be lost

        # Flush readevents
        super().start(args + ['-q1'])  # With proper termination with sigterm, this should not be necessary anymore.
        self.wait()

        args_tee = [
                f'{PipesQKD.RAWEVENTS}',
        ]
        self.t = Process('tee')
        self.t.start(args_tee,stdin=PipesQKD.TEEIN, stdout=PipesQKD.SBIN)

        args_getrate2 = [
                '-n0',
                '-s',
                '-b',
        ]
        self.gr = Process(pathlib.Path(Process.config.program_root) / 'getrate2')
        self.gr.start(args_getrate2, stdin = PipesQKD.SBIN, stdout=PipesQKD.SB )

        # Persist readevents
        super().start(args, stdout=PipesQKD.TEEIN, stderr="readeventserror", callback_restart=callback_restart)

        self.i = 0
        self.sb = []
        self.tt_counts = []
        self.read(PipesQKD.SB,self.self_seed_monitor, 'SB', persist=True)

    def self_seed_monitor(self, pipe):
        """
        Monitors the Self-seeding count rate pipe. Averages over n readings and flags when count rates crosses threshold, indicating a blinded detector.
        """
        n_ave = 5

        lower_th = 500
        higher_th = 90000

        counts = pipe.readline().rstrip('\n').lstrip('\x00')
        if len(counts) == 0:
            return
        (
            total_counts,
            total_sb,
            *_,
        ) = counts.split()

        self.sb.insert(0, int(total_sb))
        self.tt_counts.insert(0, int(total_counts))
        if len(self.sb) < 4:
            return
        else:
            sb_mean = np.mean(self.sb)
            count_mean = np.mean(self.tt_counts)
            self.sb.pop()
            self.tt_counts.pop()

        if count_mean > higher_th and sb_mean < lower_th:
            self.blinded = True
            self._callback_stop()
            logger.warning(f'SB_mean is {sb_mean}. Counts_mean is {count_mean}')
            logger.warning(f'Uh oh, seems like the detector might be blinded')
        else:
            self.blinded = False
        return

    def measure_local_count_rate_system(self):
        """Measure local photon count rate through shell. Done to solve process not terminated nicely for >160000 count rate per epoch.
           Don't need to handle pipes, but harder to recover if things don't work."""
        try:
            assert not self.is_running()
        except AssertionError as msg:
            print(msg)

        # Flush readevents
        # Terminates after single event retrieved
        super().start(['-q1'])
        self.wait()

        command = [ pathlib.Path(Process.config.program_root).absolute().as_posix(),
                    '/readevents -a1 -X | ',
                    pathlib.Path(Process.config.program_root).absolute().as_posix(),
                    '/getrate']
        command = ''.join(command)
        proc = os.popen(command)
        if not proc :
            logger.warning(f'getrate returned error')
        counts = int(proc.read().rstrip('\n'))
        proc.close()

        return counts

    def measure_local_count_rate(self):
        """Measure local photon count rate."""
        try:
            assert not self.is_running()
        except AssertionError as msg:
            print(msg)

        args = [
            '-a', 1,  # outmode 1
            '-X',     # legacy: high/low word swap
        ]

        # Flush readevents
        # Terminates after single event retrieved
        super().start(args + ['-q1'])
        self.wait()

        # TODO(Justin): Problematic if the above just hangs, i.e.
        # wait does nothing. Might consider performing a timeout kill
        # in Process.wait.

        # Retrieve one round of counting events
        # Terminate when getrate terminates
        super().start(args, stdout=subprocess.PIPE)
        proc_getrate = subprocess.Popen(
            pathlib.Path(Process.config.program_root) / 'getrate',
            stdin=self.process.stdout,
            stdout=subprocess.PIPE,
        )
        proc_getrate.wait()
        self.stop()

        # Extract measured local count rate
        return int(proc_getrate.stdout.read().decode())

    def powercycle(self):
        super().stop()
        try:
            assert not self.is_running()
        except AssertionError as msg:
            print(msg)
        super().start(['-q1', '-Z'])
        return

    def stop(self):
        self.empty_seed_pipes()
        if self.process is None:
            return
        try:
            self.t
            self.gr
        except AttributeError:
            pass
        else:
            self.t.stop()
            self.gr.stop()
            self.empty_seed_pipes()
        finally:
            logger.debug('Stopping readevents')
            super().stop()
        return

    def empty_seed_pipes(self):
        PipesQKD.drain_pipe(PipesQKD.TEEIN)
        PipesQKD.drain_pipe(PipesQKD.SBIN)
        PipesQKD.drain_pipe(PipesQKD.SB)
        return
