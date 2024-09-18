#!/usr/bin/env python3

import pathlib
import subprocess
import os
import numpy as np

from fpfind.lib import parse_epochs as eparser

from .utils import Process
from . import qkd_globals
from .qkd_globals import logger, PipesQKD, EPOCH_DURATION

class Readevents(Process):

    def __init__(self, process):
        super().__init__(process)
        self.blinded = False
        # Frequency correction value for freqcd
        self.freqcorr = Process.config.qcrypto.frequency_correction.initial_correction

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

        # Set self blinding parameters
        use_blinding_countermeasure = Process.config.qcrypto.use_blinding_countermeasure
        if use_blinding_countermeasure:
            test_mode = Process.config.qcrypto.blinding_parameters.test_mode
            density = Process.config.qcrypto.blinding_parameters.density
            timebase = Process.config.qcrypto.blinding_parameters.timebase
            level1 = Process.config.qcrypto.blinding_parameters.level1
            level2 = Process.config.qcrypto.blinding_parameters.level2
            self.mon_ave = Process.config.qcrypto.blinding_parameters.monitor_ave
            self.mon_lower_thresh = Process.config.qcrypto.blinding_parameters.monitor_lower_thresh
            self.mon_higher_thresh = Process.config.qcrypto.blinding_parameters.monitor_higher_thresh
            blindmode = timebase * (1<<5) + density * (1<<2) + test_mode
            args += ["-b", f'{blindmode},{level1},{level2}']

        return args

    def start(
            self,
            callback_restart=None,    # to restart keygen
            callback_stop=None,       # to stop when blinded
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

        if use_blinding_countermeasure:
            self._callback_stop = callback_stop

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

            self.sb = []
            self.tt_counts = []
            self.read(PipesQKD.SB,self.self_seed_monitor, 'SB', persist=True)
        else:
            # Persist readevents
            super().start(args, stdout=PipesQKD.RAWEVENTS, stderr="readeventserror", callback_restart=callback_restart)

    def start_fc(
            self,
            callback_restart=None,
            callback_stop=None,       # to stop when blinded
        ):
        """Starts readevents together with frequency correction.

        'freqcd' is injected here instead of a separate process to minimize
        external changes to architecture, i.e. 'chopper' still only ever sees
        one RAWEVENTS pipe coming out from 'readevents', regardless of whether
        'freqcd' is enabled.
        """
        try:
            assert not self.is_running()
        except AssertionError as msg:
            print(msg)
            callback_restart()

        # Start freqcd first
        args_freqcd = [
            '-i', PipesQKD.FRAWEVENTS,
            '-o', PipesQKD.RAWEVENTS,
            '-x',
            '-f', int(round(self.freqcorr * 2**34)),
            '-F', PipesQKD.FREQIN,
        ]
        self._dt_history = []  # maintain an array of historical dt values
        self._ignore = Process.config.qcrypto.frequency_correction.ignore_first_epochs
        self._average = Process.config.qcrypto.frequency_correction.averaging_length
        self._separation = Process.config.qcrypto.frequency_correction.separation_length
        self._cap = Process.config.qcrypto.frequency_correction.limit_correction

        # TODO(2024-02-08):
        #   Type-checking should be performed during config import,
        #   according to some schema.
        assert isinstance(self._ignore, int) and self._ignore > 0
        assert isinstance(self._average, int) and self._average > 0
        assert isinstance(self._separation, int) and self._separation > 0
        assert isinstance(self._cap, float)
        self._required = self._ignore + self._average + self._separation

        self.freqcd = Process('freqcd')
        self.freqcd.start(args_freqcd, callback_restart=callback_restart)

        # Setup readevents as usual
        args = self.generate_base_args() + ["-s"]
        super().start(args + ['-q1'])  # flush
        self.wait()

        if use_blinding_countermeasure:
            self._callback_stop = callback_stop

            args_tee = [
                    f'{PipesQKD.FRAWEVENTS}',
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

            self.sb = []
            self.tt_counts = []
            self.read(PipesQKD.SB,self.self_seed_monitor, 'SB', persist=True)
        else:
            super().start(args, stdout=PipesQKD.FRAWEVENTS, stderr="readeventserror", callback_restart=callback_restart)

    def commit_freqcorr(self, freq: float):
        """Commits frequency correction to 'freqcd'.

        Magnitude of 'freq' should not be larger than 2^-13.

        Args:
            freq: Frequency correction value, in absolute units.
        """
        assert abs(freq) < 2**-13  # maximum range, see fpfind#6
        self.freqcorr = freq

        # Convert to 2**-34 units before writing
        freq_u34 = int(round(freq * 2**34))
        Process.write(PipesQKD.FREQIN, str(freq_u34), "FREQIN")

    def update_freqcorr(self, freq: float):
        """Updates frequency correction value relative to previous.

        Args:
            freq: Frequency correction value, in absolute units.
        """
        old_freq = self.freqcorr
        new_freq = (1 + old_freq) * (1 + freq) - 1
        logger.debug(
            "freq update, curr: %5.1f ppb, new: %5.1f ppb",
            old_freq*1e9, new_freq*1e9,
        )
        self.commit_freqcorr(new_freq)

    def send_epoch(self, epoch, dt):
        """Receives epoch information from costream to calculate clock skew.

        This function accumulates the dt values, and performs some degree of
        averaging (low-pass) to smoothen the frequency correction adjustment.

        Note:
            Assuming a bimodal clock skew, the algorithm used should not be a
            sliding mean, since the coincidence matching requires an accurate
            frequency compensation value. We instead collect a set of samples,
            then calculate the frequency difference.

            Race condition may be possible - no guarantees on the continuity
            of epochs. This is resolved with continuity check during every
            function call.
        """
        # Verify epochs are contiguous
        # Needed because costream may terminate prematurely, and no calls to
        # flush the dt history is made, resulting in large time gaps.
        if len(self._dt_history) > 0:
            # self._dt_history format: [(epoch:str, dt:float),...]
            prev_epoch = self._dt_history[-1][0]
            if eparser.epoch2int(prev_epoch) + 1 != eparser.epoch2int(epoch):
                self._dt_history.clear()

        # Collect epochs
        self._dt_history.append((epoch, dt))
        if len(self._dt_history) < self._required:
            return

        # Ignore first few epochs to allow freqcorr to propagate
        history = self._dt_history[self._ignore:]  # make a copy
        epochs, dts = list(zip(*history))
        logger.debug("Triggering active frequency correction, with measurements: %s", dts)

        # Calculate averaged frequency difference
        dt_early = np.mean(dts[:self._average])
        dt_late = np.mean(dts[-self._average:])
        dt_change = (dt_late - dt_early) * (1e-9 / 8)  # convert 1/8ns -> 1s units
        df = dt_change / (self._separation * EPOCH_DURATION)
        df_toapply = 1/(1 + df) - 1
        self._dt_history.clear()  # restart collection

        # Cap correction if positive value supplied
        df_applied = df_toapply
        if self._cap > 0:
            df_applied = max(-self._cap, min(self._cap, df_toapply))

        logger.debug(
            "freq log, epoch: %s, freqcorr: %5.1f ppb, capped: %.1f ppb",
            epochs[-1], df_toapply*1e9, df_applied*1e9,
        )
        self.update_freqcorr(df_applied)

    def self_seed_monitor(self, pipe):
        """
        Monitors the Self-seeding count rate pipe. Averages over n readings and flags when count rates crosses threshold, indicating a blinded detector.
        """
        n_ave = self.mon_ave
        lower_th = self.mon_lower_thresh
        higher_th = self.mon_higher_thresh

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
        if hasattr(self, "t") and hasattr(self, "gr"):
            self.t.stop()
            self.gr.stop()
            self.empty_seed_pipes()
        if hasattr(self, "freqcd"):
            self.freqcd.stop()
        logger.debug('Stopping readevents')
        super().stop()
        return

    def empty_seed_pipes(self):
        PipesQKD.drain_pipe(PipesQKD.TEEIN)
        PipesQKD.drain_pipe(PipesQKD.SBIN)
        PipesQKD.drain_pipe(PipesQKD.SB)
        return
