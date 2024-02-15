#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Wraps the splicer executable from
https://github.com/kurtsiefer/qcrypto/tree/master/remotecrypto.


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

from .utils import Process, read_T3_header, HeadT3, read_T4_header, HeadT4
from .qkd_globals import logger, QKDProtocol, PipesQKD, FoldersQKD, QKDEngineState

class Splicer(Process):

    def start(
            self,
            qkd_protocol,
            callback_ecqueue = None,  # message passing of epoch to error correction
            callback_notify = None,  # callback to pass to polarization controller
            callback_restart = None,    # to restart keygen
        ):
        """

        Starts the splicer process and attaches a thread digesting
        the splice pipe and the genlog.
        """
        assert not self.is_running()


        self._qkd_protocol = qkd_protocol
        self._callback_notify = callback_notify
        self._callback_ecqueue = callback_ecqueue
        self._callback_restart = callback_restart
        self._latest_message_time = time.time()

        args = [
            '-d', FoldersQKD.T3FILES,
            '-D', FoldersQKD.RECEIVEFILES,
            '-f', FoldersQKD.RAWKEYS,
            '-E', PipesQKD.SPLICER,
            Process.config.kill_option,
            '-p', qkd_protocol.value,
            '-m', PipesQKD.GENLOG,
        ]
        super().start(args, stdout='splicer_stdout', stderr='splicer_stderr', callback_restart=callback_restart)
        self.read(PipesQKD.GENLOG, self.digest_splice_outpipe, 'GENLOG', persist=True)
        self.read(PipesQKD.PRESPLICER, self.send_splice_inpipe, 'PRESPLICEPIPE', persist=True)
        super().start_thread_method(self._no_message_monitor)

    def digest_splice_outpipe(self, pipe):
        # message = pipe.readline().decode().rstrip('\n').lstrip('\x00')
        message = pipe.readline().rstrip('\n').lstrip('\x00')
        if len(message) == 0:
            return

        self._latest_message_time = time.time()
        qkd_protocol = self._qkd_protocol
        logger.debug(f'[genlog] {message}')
        if qkd_protocol == QKDProtocol.BBM92:
            logger.debug(f'Add {message} to error correction queue')
            self._callback_ecqueue(message)

        if self._callback_notify:
            self._callback_notify(message)

    def send_splice_inpipe(self, pipe):
        headt3 = HeadT3(0,0,0,0) # tag,epoch(int),length_entry,bits_per_entry
        headt4 = HeadT4(0,0,0,0,0) #
        message = pipe.readline().rstrip('\n').lstrip('\x00')
        if len(message) == 0:
            return
        if self.is_running():
            qkd_protocol = self._qkd_protocol
            logger.debug(f'Epoch = {message}')
            epoch = message
            t4_epoch_path = FoldersQKD.RECEIVEFILES + '/' + epoch
            t3_epoch_path = FoldersQKD.T3FILES + '/' + epoch
            headt3 = read_T3_header(t3_epoch_path)
            headt4 = read_T4_header(t4_epoch_path)
            if qkd_protocol == QKDProtocol.BBM92:
                basebit3 = 1
                basebit4 = 0
            elif qkd_protocol == QKDProtocol.SERVICE:
                basebit3 = 4
                basebit4 = 4
            if headt3.bits_per_entry == basebit3 and headt4.base_bits == basebit4:
                Process.write(PipesQKD.SPLICER, epoch)
                logger.debug(f'Sent epoch name {epoch} to splicer.')
            else:
                logger.debug(f'Base bits not proper yet. Protocol: {qkd_protocol}, T3 basebits: {headt3.bits_per_entry} T4 basebits: {headt4.base_bits}')

    def _no_message_monitor(self, stop_event):
        timeout_seconds = 200
        while not stop_event.is_set() and self.is_running():
            if time.time() - self._latest_message_time > timeout_seconds:
                logger.debug(f"Timed out for '{self.program}' received no messages in {timeout_seconds}")
                self._callback_restart()
                return
            time.sleep(timeout_seconds)
        return
