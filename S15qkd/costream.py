#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
This module wraps the costream process.


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

import pathlib
import time

from .utils import Process
from .qkd_globals import logger, QKDProtocol, PipesQKD, FoldersQKD

class Costream(Process):

    def __init__(self, process):
        super().__init__(process)
        self._reset()  # for initial display on status page

    def _reset(self):
        self._latest_coincidences = None
        self._latest_accidentals = None
        self._latest_deltat = None
        self._initial_time_difference = None
        self._latest_compress = None
        self._latest_sentevents = None
        self._latest_rawevents = None
        self._latest_outepoch = None
        self._initial_time_difference = None

    def start(
            self,
            time_difference: int,
            begin_epoch: str,
            qkd_protocol,
            callback_notify = None,  # pass information about epoch back to Controller
            callback_restart = None,  # allow costream to force keygen restart,
            epochnum = 0, # default (0) converts forever
        ):
        assert not self.is_running()

        self._reset()
        self._initial_time_difference = time_difference
        self._qkd_protocol = qkd_protocol

        # Polarization compensation
        self._callback_notify = callback_notify
        self._pairs_over_accidentals_avg = 10
        self._callback_restart = callback_restart
        self._latest_message_time = time.time()

        args = [
            '-d', FoldersQKD.RECEIVEFILES,
            '-D', FoldersQKD.T1FILES,
            '-f', FoldersQKD.RAWKEYS,
            '-F', FoldersQKD.SENDFILES,
            '-e', f'0x{begin_epoch}',
            Process.config.kill_option,
            '-t', time_difference,
            '-p', qkd_protocol.value,
            '-T', 2,
            '-m', f'{Process.config.data_root}/rawpacketindex',
            '-M', PipesQKD.CMD,
            '-n', PipesQKD.GENLOG,
            '-V', 5,
            '-G', 2,
            '-w', Process.config.remote_coincidence_window,
            '-u', Process.config.tracking_window,
            '-Q', int(-Process.config.track_filter_time_constant),
            '-R', 5,
            Process.config.costream_histo_option,
            '-h', Process.config.costream_histo_number,
            '-q', f'{epochnum}',
        ]
        logger.info(f'costream starts with the following arguments: {args}')
        super().start(args, stderr="costreamerror", callback_restart=callback_restart)

        self.read(PipesQKD.GENLOG, self.digest_genlog, 'GENLOG', persist=True)
        super().start_thread_method(self._no_message_monitor)

    def digest_genlog(self, pipe):
        """Digests the genlog pipe written by costream."""
        # message = pipe.readline().decode().rstrip('\n').lstrip('\x00')
        message = pipe.readline().rstrip('\n').lstrip('\x00')
        if len(message) == 0:
            return

        self._latest_message_time = time.time()
        logger.debug(message)
        self._previous_latest_outepoch = self._latest_outepoch
        self._previous_latest_deltat = self._latest_deltat
        (
            self._latest_outepoch,
            self._latest_rawevents,
            self._latest_sentevents,
            self._latest_compress,
            self._latest_deltat,
            self._latest_accidentals,
            self._latest_coincidences,
            *_,
         ) = message.split()  # costream_info

        # restart time difference finder if pairs to accidentals is too low
        pairs_over_accidentals = int(self._latest_coincidences) / (int(self._latest_accidentals) + 1) #incase of divide by zero
        avg_num = 5
        self._pairs_over_accidentals_avg = (self._pairs_over_accidentals_avg * (avg_num - 1) + pairs_over_accidentals) / avg_num
        if self._pairs_over_accidentals_avg < 2.5:
            logger.error(
                f'Pairs to accidental ratio bad: avg(p/a) = {self._pairs_over_accidentals_avg:.2f}'
            )

            # Be careful of potential race condition.
            # In current implementation, termination condition for this thread
            # evaluated only after this function returns, so no conflict.
            self._callback_restart()
            return

        if self._callback_notify:
            self._callback_notify(self._latest_outepoch, int(self._latest_deltat))

    def _no_message_monitor(self, stop_event):
        """ Monitor restarts the engine if costream is started and receives no updates in timeout seconds.
        """
        timeout_seconds = 200
        while not stop_event.is_set() and self.is_running():
            if time.time() - self._latest_message_time > timeout_seconds:
                logger.info(f"Timed out for '{self.program}' received no messages in {timeout_seconds}")
                self._callback_restart()
                return
            time.sleep(timeout_seconds)
        return

    def _no_message_monitor(self, stop_event):
        """ Monitor restarts the engine if costream is started and receives no updates in timeout seconds.
        """
        timeout_seconds = 200
        while not stop_event.is_set() and self.is_running():
            if time.time() - self._latest_message_time > timeout_seconds:
                logger.info(f"Timed out for '{self.program}' received no messages in {timeout_seconds}")
                self._callback_restart()
                return
            time.sleep(timeout_seconds)
        return

    # Coding defensively... ensure these properties are not
    # modified outside class.

    @property
    def latest_coincidences(self):
        return self._latest_coincidences

    @property
    def latest_accidentals(self):
        return self._latest_accidentals

    @property
    def latest_deltat(self):
        return self._latest_deltat

    @property
    def initial_time_difference(self):
        return self._initial_time_difference

    @property
    def latest_compress(self):
        return self._latest_compress

    @property
    def latest_sentevents(self):
        return self._latest_sentevents

    @property
    def latest_rawevents(self):
        return self._latest_rawevents

    @property
    def latest_outepoch(self):
        return self._latest_outepoch

    @property
    def latest_drift_rate(self):
        try:
            delta_epoch = int(self._latest_outepoch,16) - int(self._previous_latest_outepoch,16)
            delta_deltat = int(self._latest_deltat) - int(self._previous_latest_deltat)
            return int(delta_deltat/delta_epoch)
        except TypeError:
            return 0
