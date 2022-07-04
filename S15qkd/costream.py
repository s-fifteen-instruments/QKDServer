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

__author__ = 'Mathias Alexander Seidler'
__copyright__ = 'Copyright 2020, S-Fifteen Instruments Pte. Ltd.'
__credits__ = ['Lim Chin Chean']
__license__ = 'MIT'
__version__ = '0.0.1'
__maintainer__ = 'Mathias Seidler'
__email__ = 'mathias.seidler@s-fifteen.com'
__status__ = 'dev'


# Built-in/Generic Imports
import subprocess
import os
import time
import threading
import json
import sys
import psutil
from types import SimpleNamespace

# Own modules
from . import qkd_globals
from .rawkey_diagnosis import RawKeyDiagnosis
from .qkd_globals import logger, QKDProtocol, PipesQKD, FoldersQKD, QKDEngineState
from .polarization_compensation import PolarizationDriftCompensation
from . import controller, transferd

proc_costream = None


def _initialize(config_file_name: str = qkd_globals.config_file):
    global proc_costream
    global latest_coincidences, latest_accidentals, latest_deltat, latest_sentevents
    global latest_compress, latest_rawevents, latest_outepoch, initial_time_difference

    proc_costream = None
    latest_coincidences = -1
    latest_accidentals = -1
    latest_deltat = -1
    initial_time_difference = None
    latest_compress = ''
    latest_sentevents = ''
    latest_rawevents = ''
    latest_outepoch = ''


def start_costream(time_difference: int,
                   begin_epoch: str,
                   qkd_protocol: int = QKDProtocol.BBM92,
                   config_file_name: str = qkd_globals.config_file):
    global proc_costream, initial_time_difference, protocol
    initial_time_difference = time_difference
    with open(config_file_name, 'r') as f:
        config = json.load(f, object_hook=lambda d: SimpleNamespace(**d))
    _initialize()
    protocol = qkd_protocol
    logger.info(f'{begin_epoch}')
    args = f'-d {FoldersQKD.RECEIVEFILES} \
             -D {FoldersQKD.T1FILES} \
             -f {FoldersQKD.RAWKEYS} \
             -F {FoldersQKD.SENDFILES} \
             -e 0x{begin_epoch} \
             {config.kill_option} \
             -t {time_difference} \
             -p {qkd_protocol} \
             -T 2 \
             -m /{config.data_root}/rawpacketindex \
             -M {PipesQKD.CMD} \
             -n {PipesQKD.GENLOG} \
             -V 5 \
             -G 2 -w {config.remote_coincidence_window} \
             -u {config.tracking_window} \
             -Q {int(-config.track_filter_time_constant)} \
             -R 5 \
             {config.costream_histo_option} \
             -h {config.costream_histo_number}'
    program_costream = config.program_root + '/costream'
    logger.info(f'costream starts with the following arguments: {args}')
    with open(f'/{config.data_root}/costreamerror', 'a+') as f:
        proc_costream = subprocess.Popen((program_costream, *args.split()),
                                         stdout=subprocess.PIPE, stderr=f)
    costream_thread = threading.Thread(
        target=_genlog_digest, args=([qkd_protocol]))
    costream_thread.start()


def _genlog_digest(qkd_protocol, config_file_name: str = qkd_globals.config_file):
    '''
    Digests the genlog pipe written by costream.
    '''
    global latest_coincidences, latest_accidentals, latest_deltat, latest_sentevents
    global latest_compress, latest_rawevents, latest_outepoch
    fd = os.open(PipesQKD.GENLOG, os.O_RDONLY | os.O_NONBLOCK)
    f = os.fdopen(fd, 'rb', 0)  # non-blocking
    logger.info('Thread started.')
    with open(config_file_name, 'r') as f_config:
        config = json.load(f_config, object_hook=lambda d: SimpleNamespace(**d))
    if config.do_polarization_compensation is True and qkd_protocol == QKDProtocol.SERVICE:
        polarization_compensator = PolarizationDriftCompensation(
            config.LCR_polarization_compensator_path)
    pairs_over_accidentals_avg = 10
    while is_running():
        time.sleep(0.1)
        try:
            message = (f.readline().decode().rstrip('\n')).lstrip('\x00')
            if len(message) != 0:
                logger.debug(message)
                costream_info = message.split()
                latest_coincidences = costream_info[6]
                latest_accidentals = costream_info[5]
                latest_deltat = costream_info[4]
                latest_compress = costream_info[3]
                latest_sentevents = costream_info[2]
                latest_rawevents = costream_info[1]
                latest_outepoch = costream_info[0]
                # restart time difference finder if pairs to accidentals is too low
                pairs_over_accidentals = int(
                    latest_coincidences) / (int(latest_accidentals) + 1) #incase of divide by zero
                pairs_over_accidentals_avg = (pairs_over_accidentals_avg * 19 + pairs_over_accidentals) / 20
                if pairs_over_accidentals_avg < 2.5:
                    logger.error(
                        f'Pairs to accidental ratio bad: avg(p/a) = {pairs_over_accidentals_avg:.2f}')
                    controller.stop_key_gen()
                    if qkd_protocol == QKDProtocol.SERVICE:
                        controller.start_service_mode()
                    elif qkd_protocol == QKDProtocol.BBM92:
                        controller.start_key_generation()
                    continue
                if qkd_protocol == QKDProtocol.SERVICE:
                    controller.qkd_engine_state = QKDEngineState.SERVICE_MODE
                    logger.debug(message)
                    diagnosis = RawKeyDiagnosis(
                        FoldersQKD.RAWKEYS + '/' + message)
                    logger.debug(
                        f'Service mode, QBER: {diagnosis.quantum_bit_error}, Epoch: {costream_info[0]}')
                    if config.do_polarization_compensation is True:
                        if pairs_over_accidentals > 2.5:
                            #polarization_compensator.update_qber2(diagnosis.quantum_bit_error)
                            polarization_compensator.update_QBER(
                            diagnosis.quantum_bit_error, epoch=message)

        except OSError:
            pass
        except Exception as a:
            logger.error(a)
    logger.info('Thread finished.')


def stop_costream():
    global proc_costream
    qkd_globals.kill_process(proc_costream)
    proc_costream = None


def is_running():
    return not (proc_costream is None or proc_costream.poll() is not None)


_initialize()
