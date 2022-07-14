#!/usr/bin/env python3

import pathlib
import subprocess

from .utils import Process
from .qkd_globals import logger, PipesQKD

class Readevents(Process):

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
        #super().start(args + ['-q2'])  # With proper termination with sigterm, this is not necessary anymore.
        #self.wait()

        # Persist readevents
        # TODO(Justin): Check default default directory
        #               and pipe O_APPEND.
        super().start(args, stdout=PipesQKD.RAWEVENTS, stderr="readeventserror", callback_restart=callback_restart)

    def measure_local_count_rate(self):
        """Measure local photon count rate."""
        assert not self.is_running()
        args = [
            '-a', 1,  # outmode 1
            '-X',     # legacy: high/low word swap
        ]

        # Flush readevents
        # Terminates after single event retrieved
        #super().start(args + ['-q1'])
        #self.wait()

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
