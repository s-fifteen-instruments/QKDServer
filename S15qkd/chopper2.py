#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
This module implements the QKD business logic. It manages and coordinates all
releveant processes to generate encryption keys.


Copyright (c) 2020 Mathias A. Seidler, S-Fifteen Instruments Pte. Ltd.

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

import time

from .utils import Process
from .qkd_globals import logger, PipesQKD, FoldersQKD, config_file

class Chopper2(Process):

    def __init__(self, program):
        super().__init__(program)
        self._reset()
    
    def _reset(self):
        self._det_counts = [0, 0, 0, 0, 0]
        self._t1_epoch_count = 0
        self._first_epoch = None
        self._latest_message_time = time.time()
    
    def start(
            self,
            callback_restart=None,    # to restart keygen
            callback_reset_timestamp=None,
        ):
        try:
            assert not self.is_running()
        except AssertionError:
            callback_restart()
            return
        self._reset()
        self._callback_restart = callback_restart
        self._callback_reset_timestamp = callback_reset_timestamp
        self._latest_message_time = time.time()

        args = [
            '-i', PipesQKD.RAWEVENTS,
            '-D', FoldersQKD.T1FILES,
            '-l', PipesQKD.T1LOG,
            '-V', 3,
            '-U',
            '-F',
            '-m', Process.config.max_event_diff,
            '-4', # Force four detector option
        ]
        super().start(args, stderr="chopper2error", callback_restart=callback_restart)
        self.read(PipesQKD.T1LOG, self.digest_t1logpipe, wait=0.1, name="T1LOG", persist=True)
        logger.info('Started chopper2.')
        super().start_thread_method(self._no_message_monitor)

    def digest_t1logpipe(self, pipe):
        """Digest the t1log pipe written by chopper2.

        Chopper2 runs on the high-count side.
        Also counts the number of epochs recorded by chopper2.
        """
        # message = pipe.readline().decode().rstrip('\n').lstrip('\x00')
        message = pipe.readline().rstrip('\n').lstrip('\x00')
        if len(message) == 0:
            return
        
        self._latest_message_time = time.time()
        logger.debug(f'[read msg] {message}')
        if self._t1_epoch_count == 0:
            self._first_epoch = message.split()[0]
            logger.info(f'First_epoch: {self._first_epoch}')
        self._t1_epoch_count += 1
        self._det_counts = list(map(int,message.split()[1:6]))
        self._monitor_counts()

    @property
    def t1_epoch_count(self):
        return self._t1_epoch_count

    @property
    def first_epoch(self):
        return self._first_epoch

    @property
    def det_counts(self):
        """ Returns (total_counts, d1, d2, d3, d4)
        """
        return self._det_counts

    def _monitor_counts(self):
        """Restarts keygen if detector counts goes to zero.
        """

        for counts in self.det_counts:
            if counts == 0:
                logger.debug(f"Counts monitor for '{self.program}' ('{self.process}') reported zero")
                self._callback_restart()
                return
        return

    def _no_message_monitor(self):
        timeout_seconds = 5
        while self.is_running():
            if time.time() - self._latest_message_time > timeout_seconds:
                logger.debug(f"Timed out for '{self.program}' received no messages in {timeout_seconds}")
                self._callback_reset_timestamp()
                return
            time.sleep(timeout_seconds)
        return



