#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
This module wraps the chopper process and attaches readers to the process pipes.

Copyright (c) 2020 S-Fifteen Instruments Pte. Ltd.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

import threading
import time
from .utils import Process
from .qkd_globals import logger, PipesQKD, FoldersQKD, config_file

class Chopper(Process):

    def __init__(self, program):
        super().__init__(program)
        self._reset()

    def _reset(self):
        self._det_counts = [0, 0, 0, 0, 0]

    def start(
            self,
            qkd_protocol,
            callback_restart=None,    # to restart keygen
        ):
        """
        
        Needs to know current protocol (SERVICE or KEYGEN) to change up verbosity
        of transmission from low count to high count side.
        """
        assert not self.is_running()
        
        # T2LOG pipe must be opened before starting chopper!
        # Might be some premature writing to T2LOG in chopper.c
        self.read(PipesQKD.T2LOG, self.digest_t2logpipe, 'T2LOG', persist=True)

        args = [
            '-i', PipesQKD.RAWEVENTS,
            '-D', FoldersQKD.SENDFILES,
            '-d', FoldersQKD.T3FILES,
            '-l', PipesQKD.T2LOG,
            '-V', 4,
            '-U',
            '-p', qkd_protocol.value,
            '-Q', 5,
            '-F',
            '-y', 20,
            '-m', Process.config.max_event_diff,
        ]
        super().start(args, stderr="choppererror", callback_restart=callback_restart)
        self.monitor_counts(callback_restart)
        logger.info('Started chopper.')

    def digest_t2logpipe(self, pipe):
        """Digests chopper activities.

        Watches t2logpipe for new epoch files and writes the epoch name into the transferd cmdpipe.
        Transferd copies the corresponding epoch file to the partnering computer.
        """
        # message = pipe.readline().decode().rstrip('\n').lstrip('\x00')
        message = pipe.readline().rstrip('\n').lstrip('\x00')
        if len(message) == 0:
            return
        
        epoch = message.split()[0]
        self._det_counts = list(map(int,message.split()[1:6]))
        Process.write(PipesQKD.CMD, epoch)
        logger.debug(f'Msg: {message}')


    @property
    def det_counts(self):
        """ Returns (total_counts, d1, d2, d3, d4)
        """
        return self._det_counts

    def monitor_counts(self, callback_restart):
        """Restarts keygen if detector counts goes to zero.
        Polls performed every 1 second.
        """

        def monitor_daemon():
            time.sleep(1)
            while self._expect_running:
                for counts in self.det_counts:
                    if counts == 0:
                        logger.debug(f"Counts monitor for '{self.program}' ('{self.process}') reported zero")
                        callback_restart()
                        return
                time.sleep(1)
            logger.debug(f"Terminated counts monitor for '{self.program}' ('{self.process}')")

        logger.debug(f"Starting counts monitor for '{self.program}' ('{self.process}')")
        thread = threading.Thread(target=monitor_daemon)
        thread.daemon = True
        thread.start()


