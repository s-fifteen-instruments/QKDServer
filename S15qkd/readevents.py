#!/usr/bin/env python3

import pathlib
import subprocess
import os

from .utils import Process
from . import qkd_globals
from .qkd_globals import logger, PipesQKD

class Readevents(Process):

    def __init__(self, process):
        super().__init__(process)
        self.blinded = False

    def start(
            self, 
            callback_restart=None,    # to restart keygen
        ):
        assert not self.is_running()

        det1corr = Process.config.local_detector_skew_correction.det1corr
        det2corr = Process.config.local_detector_skew_correction.det2corr
        det3corr = Process.config.local_detector_skew_correction.det3corr
        det4corr = Process.config.local_detector_skew_correction.det4corr
        args = [
            '-a', 1,  # outmode 1
            '-X',
            '-A',     # absolute time
            '-s',     # short mode, 49 bits timing info in 1/8 nsec
            # Detector skew in units of 1/256 nsec
            '-D', f'{det1corr},{det2corr},{det3corr},{det4corr}',
        ]

        # Flush readevents
        super().start(args + ['-q1'])  # With proper termination with sigterm, this should not be necessary anymore.
        self.wait()

        # Persist readevents
        # TODO(Justin): Check default default directory
        #               and pipe O_APPEND.
        super().start(args, stdout=PipesQKD.RAWEVENTS, stderr="readeventserror", callback_restart=callback_restart)

    def start_sb(
            self,
            callback_restart=None,
            callback_stop=None,
            blindmode=241,
            level1=880,
            level2=0,
        ):
        assert not self.is_running()
        self._callback_stop = callback_stop
        det1corr = Process.config.local_detector_skew_correction.det1corr
        det2corr = Process.config.local_detector_skew_correction.det2corr
        det3corr = Process.config.local_detector_skew_correction.det3corr
        det4corr = Process.config.local_detector_skew_correction.det4corr
        args = [
            '-a', 1,  # outmode 1
            '-X',
            '-A',     # absolute time
            #'-s',     # short mode, blind bit lost in short mode
            # Detector skew in units of 1/256 nsec
            '-D', f'{det1corr},{det2corr},{det3corr},{det4corr}',
            '-b', f'{blindmode},{level1},{level2}',
        ]

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
        self.gr = Process( pathlib.Path(Process.config.program_root) / 'getrate2')
        self.gr.start(args_getrate2, stdin = PipesQKD.SBIN, stdout=PipesQKD.SB )

        # Persist readevents
        # TODO(Justin): Check default default directory
        #               and pipe O_APPEND.
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
            sb_mean = sum(self.sb)/n_ave
            count_mean = sum(self.tt_counts)/n_ave
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
        assert not self.is_running()
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
        assert not self.is_running()
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
        assert not self.is_running()
        super().start(['-q1', '-Z'])
        return

    def stop(self):
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
        super().stop()
        return
