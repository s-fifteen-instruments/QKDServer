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

# TODO(Justin): Remove these when instantiation parked under main loop,
#               and use callbacks instead.
from . import error_correction
from . import controller

class Splicer(Process):

    def __init__(self, program):
        super().__init__(program)
        self._qkd_protocol = None
        self._polarization_compensator = None
        
    def start(
            self,
            qkd_protocol: int = QKDProtocol.BBM92,
            callback_ecqueue = None,  # message passing of epoch to error correction
            callback_servicemode=None,  # message passing to mark as service mode 
        ):
        """

        Starts the splicer process and attaches a thread digesting 
        the splice pipe and the genlog.
        """
        assert not self.is_running()
        self._protocol = qkd_protocol
        self._callback_ecqueue = callback_ecqueue
        self._callback_servicemode = callback_servicemode

        self.read(PipesQKD.GENLOG, self.digest_splicepipe, 'GENLOG')

        args = [
            '-d', FoldersQKD.T3FILES,
            '-D', FoldersQKD.RECEIVEFILES,
            '-f', FoldersQKD.RAWKEYS,
            '-E', PipesQKD.SPLICER,
            Process.config.kill_option,
            '-p', qkd_protocol,
            '-m', PipesQKD.GENLOG,
        ]

        super().start(args, stdout='splicer_stdout', stderr='splicer_stderr')

        if Process.config.do_polarization_compensation:
            self._polarization_compensator = PolarizationDriftCompensation(
                Process.config.LCR_polarization_compensator_path
            )

    def digest_splicepipe(self, pipe):
        message = pipe.readline().decode().rstrip('\n').lstrip('\x00')
        if len(message) == 0:
            return
        
        qkd_protocol = self._qkd_protocol
        logger.debug(f'[genlog] {message}')
        if qkd_protocol == QKDProtocol.BBM92:
            logger.debug(f'Add {message} to error correction queue')
            self._callback_ecqueue(message)
            
        elif qkd_protocol == QKDProtocol.SERVICE:
            self._callback_servicemode()
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


# Wrapper
Process.load_config()
splicer = Splicer(Process.config.program_root + '/splicer')

def callback_ecqueue(message):
    error_correction.ec_queue.put(message)

# Conflicting states between qkd_protocol and controller.qkd_engine_state...
def callback_servicemode():
    controller.qkd_engine_state = QKDEngineState.SERVICE_MODE

# Original interface
proc_splicer = None

def start_splicer(qkd_protocol: int = QKDProtocol.BBM92):
    global proc_splicer
    splicer.start(qkd_protocol, callback_ecqueue, callback_servicemode)
    proc_splicer = splicer.process

def stop_splicer():
    global proc_splicer
    splicer.stop()
    proc_splicer = None

def is_running():
    return splicer.is_running()
