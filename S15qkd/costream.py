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

from .utils import Process
from .qkd_globals import logger, QKDProtocol, PipesQKD, FoldersQKD, QKDEngineState, config_file
from .polarization_compensation import PolarizationDriftCompensation
from .rawkey_diagnosis import RawKeyDiagnosis

# TODO(Justin): To eventually remove reference to global controller,
#               when instances are created in the main control loop.
from . import controller

class Costream(Process):

    def __init__(self, program):
        super().__init__(program)
        self._latest_coincidences = -1
        self._latest_accidentals = -1
        self._latest_deltat = -1
        self._initial_time_difference = None
        self._latest_compress = ''
        self._latest_sentevents = ''
        self._latest_rawevents = ''
        self._latest_outepoch = ''
        self._protocol = None

        # Polarization compensation
        self._polarization_compensator = None
        self._pairs_over_accidentals_avg = 10
        self._callback_restart = None
    
    def start(
            self,
            time_difference: int,
            begin_epoch: str,
            qkd_protocol=QKDProtocol.BBM92,
            callback_restart=None,  # message passing back to controller to restart keygen,
            callback_servicemode=None,  # message passing to mark as service mode
        ):
        assert not self.is_running()

        self._initial_time_difference = time_difference
        self._protocol = qkd_protocol
        self._callback_restart = callback_restart
        self._callback_servicemode = callback_servicemode
        
        self.read(PipesQKD.GENLOG, self.digest_genlog, 'GENLOG')

        args = [
            '-d', FoldersQKD.RECEIVEFILES,
            '-D', FoldersQKD.T1FILES,
            '-f', FoldersQKD.RAWKEYS,
            '-F', FoldersQKD.SENDFILES,
            '-e', f'0x{begin_epoch}',
            Process.config.kill_option,
            '-t', time_difference,
            '-p', qkd_protocol,
            '-T', 2,
            '-m', f'/{Process.config.data_root}/rawpacketindex',
            '-M', PipesQKD.CMD,
            '-n', PipesQKD.GENLOG,
            '-V', 5,
            '-G', 2,
            '-w', Process.config.remote_coincidence_window,
            '-u', Process.config.tracking_window,
            '-Q', int(-config.track_filter_time_constant),
            '-R', 5,
            Process.config.costream_histo_option,
            '-h', config.costream_histo_number,
        ]
        logger.info(f'costream starts with the following arguments: {args}')
        super().start(args, stderr="costreamerror")

        # Enable polarization compensation
        if Process.config.do_polarization_compensation is True \
                and qkd_protocol == QKDProtocol.SERVICE:
            self._polarization_compensator = PolarizationDriftCompensation(
                Process.config.LCR_polarization_compensator_path,
            )


    def digest_genlog(self, pipe):
        """Digests the genlog pipe written by costream."""
        message = pipe.readline().decode().rstrip('\n').lstrip('\x00')
        if len(message) == 0:
            return

        logger.debug(message)
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
        pairs_over_accidentals = int(latest_coincidences) / (int(latest_accidentals) + 1) #incase of divide by zero
        self._pairs_over_accidentals_avg = (self._pairs_over_accidentals_avg * 19 + pairs_over_accidentals) / 20
        if self._pairs_over_accidentals_avg < 2.5:
            logger.error(
                f'Pairs to accidental ratio bad: avg(p/a) = {self._pairs_over_accidentals_avg:.2f}'
            )

            # Be careful of potential race condition.
            # In current implementation, termination condition for this thread
            # evaluated only after this function returns, so no conflict.
            self._callback_restart()
            return

        # If in SERVICE mode, mark as SERVICE mode in QKD engine
        if qkd_protocol == QKDProtocol.SERVICE:
            self._callback_servicemode()
            logger.debug(message)
            diagnosis = RawKeyDiagnosis(
                pathlib.Path(FoldersQKD.RAWKEYS) / message
            )
            logger.debug(
                f'Service mode, QBER: {diagnosis.quantum_bit_error}, Epoch: {self._latest_outepoch}'
            )

            # Perform polarization compensation while still in SERVICE mode
            if self._polarization_compensator and pairs_over_accidentals > 2.5:
                self._polarization_compensator.update_QBER(
                    diagnosis.quantum_bit_error, epoch=message,
                )

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
    def protocol(self):
        return self._protocol


# Wrapper
Process.load_config()
costream = Costream(Process.config.program_root + '/costream')

def callback_restart():
    """Callback to controller to restart keygen."""
    protocol = costream.protocol
    # TODO(Justin): Abstract into single command to controller, e.g.
    #               controller.restart_keygen(protocol)
    controller.stop_key_gen()
    if qkd_protocol == QKDProtocol.SERVICE:
        controller.start_service_mode()
    elif qkd_protocol == QKDProtocol.BBM92:
        controller.start_key_generation()

# Conflicting states between qkd_protocol and controller.qkd_engine_state...
def callback_servicemode():
    controller.qkd_engine_state = QKDEngineState.SERVICE_MODE

# Original interface
proc_costream = None

def start_costream(
        time_difference: int,
        begin_epoch: str,
        qkd_protocol: int = QKDProtocol.BBM92,
        config_file_name: str = config_file,
    ):
    global proc_costream
    Process.load_config(config_file_name)
    costream.start(time_difference, begin_epoch, qkd_protocol, callback_restart, callback_servicemode)
    proc_costream = costream.process

def stop_costream():
    global proc_costream
    costream.stop()
    proc_costream = None

def is_running():
    return costream.is_running()

# Exposes class properties as global variables
# using module-level __getattr__ available in Python 3.7+
def __getattr__(name):
    return getattr(costream, name)
