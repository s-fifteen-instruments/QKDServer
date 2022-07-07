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

from .utils import Process
from .qkd_globals import logger, QKDProtocol, PipesQKD, FoldersQKD, QKDEngineState
from .polarization_compensation import PolarizationDriftCompensation
from .rawkey_diagnosis import RawKeyDiagnosis

class Splicer(Process):
        
    def start(
            self,
            qkd_protocol,
            callback_ecqueue = None,  # message passing of epoch to error correction
            callback_start_keygen=None,  # callback to pass to polarization controller
            callback_restart=None,    # to restart keygen
        ):
        """

        Starts the splicer process and attaches a thread digesting 
        the splice pipe and the genlog.
        """
        assert not self.is_running()

        self.read(PipesQKD.GENLOG, self.digest_splicepipe, 'GENLOG', persist=True)

        self._qkd_protocol = qkd_protocol
        self._polarization_compensator = None
        self._callback_ecqueue = callback_ecqueue

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

        if Process.config.do_polarization_compensation:
            self._polarization_compensator = PolarizationDriftCompensation(
                Process.config.LCR_polarization_compensator_path
            ) # TODO(Justin): Pass 'callback_start_keygen'

    def digest_splicepipe(self, pipe):
        # message = pipe.readline().decode().rstrip('\n').lstrip('\x00')
        message = pipe.readline().rstrip('\n').lstrip('\x00')
        if len(message) == 0:
            return
        
        qkd_protocol = self._qkd_protocol
        logger.debug(f'[genlog] {message}')
        if qkd_protocol == QKDProtocol.BBM92:
            logger.debug(f'Add {message} to error correction queue')
            self._callback_ecqueue(message)
            
        elif qkd_protocol == QKDProtocol.SERVICE:
            diagnosis = RawKeyDiagnosis(
                pathlib.Path(FoldersQKD.RAWKEYS) / message
            )
            logger.debug(
                f'Service mode, QBER: {diagnosis.quantum_bit_error}, Epoch: {message}'
            )

            # Perform polarization compensation while still in SERVICE mode
            if self._polarization_compensator:
                self._polarization_compensator.update_QBER(
                    diagnosis.quantum_bit_error, epoch=message,
                )
