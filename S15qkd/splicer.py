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

__author__ = 'Mathias Alexander Seidler'
__copyright__ = 'Copyright 2020, S-Fifteen Instruments Pte. Ltd.'
__credits__ = ['Lim Chin Chean']
__license__ = 'MIT'
__version__ = '0.0.1'
__maintainer__ = 'Mathias Seidler'
__email__ = 'mathias.seidler@s-fifteen.com'
__status__ = 'dev'

import json
import sys
import threading
import os
import subprocess
import time
import select
import psutil
from types import SimpleNamespace

from . import qkd_globals
from . import error_correction
from . import rawkey_diagnosis
from . import controller
from .qkd_globals import logger, PipesQKD, FoldersQKD, QKDProtocol, QKDEngineState
from .polarization_compensation import PolarizationDriftCompensation

proc_splicer = None


def _load_splicer_config(config_file_name: str):
    global data_root, program_root, protocol, kill_option
    global prog_splicer

    with open(config_file_name, 'r') as f:
        config = json.load(f)

    data_root = config['data_root']
    protocol = config['protocol']
    program_root = config['program_root']
    kill_option = config['kill_option']
    prog_splicer = program_root + '/splicer'


def initialize(config_file_name: str = qkd_globals.config_file):
    global cwd, proc_splicer
    _load_splicer_config(config_file_name)
    cwd = os.getcwd()
    proc_splicer = None


def start_splicer(qkd_protocol: int = QKDProtocol.BBM92):
    '''
    Starts the splicer process and attaches a thread digesting 
    the splice pipe and the genlog.
    '''
    global data_root, cwd, proc_splicer
    initialize()
    args = f'-d {FoldersQKD.T3FILES} \
             -D {FoldersQKD.RECEIVEFILES} \
             -f {FoldersQKD.RAWKEYS} \
             -E {PipesQKD.SPLICER} \
             {kill_option} \
             -p {qkd_protocol} \
             -m {PipesQKD.GENLOG}'

    proc_splicer = subprocess.Popen([prog_splicer, *args.split()])
    time.sleep(0.1)
    logger.info(f'Started splicer process.')
    thread_splicepipe_digest = threading.Thread(target=_splice_pipe_digest,
                                                args=([qkd_protocol]))
    thread_splicepipe_digest.start()


def _splice_pipe_digest(qkd_protocol, config_file_name: str = qkd_globals.config_file):
    '''
    Digests the text written into splicepipe and genlog.
    Runs until the splicer process closes.
    '''
    logger.info(f'Starting _splice_pipe_digest thread.')
    fd_genlog = os.open(PipesQKD.GENLOG, os.O_RDONLY |
                        os.O_NONBLOCK)  # non-blocking
    f_genlog = os.fdopen(fd_genlog, 'rb', 0)  # non-blocking

    logger.info(f'Thread started.')
    sleep_time = 0.1  # sleep time before next read file attempt
    with open(config_file_name, 'r') as f:
        config = json.load(f, object_hook=lambda d: SimpleNamespace(**d))
    if config.do_polarization_compensation is True:
        polarization_compensator = PolarizationDriftCompensation(
            config.LCR_polarization_compensator_path)
    while is_running():
        time.sleep(sleep_time)
        try:
            message = (f_genlog.readline().decode().rstrip(
                '\n')).lstrip('\x00')
            if len(message) != 0:
                logger.debug(f'[genlog] {message}')
                if qkd_protocol == QKDProtocol.BBM92:
                    logger.debug(f'Add {message} to error correction queue')
                    error_correction.ec_queue.put(message)
                elif qkd_protocol == QKDProtocol.SERVICE:
                    controller.qkd_engine_state = QKDEngineState.SERVICE_MODE
                    diagnosis = rawkey_diagnosis.RawKeyDiagnosis(
                        FoldersQKD.RAWKEYS + '/' + message)
                    logger.debug(
                        f'Service mode, QBER: {diagnosis.quantum_bit_error}, Epoch: {message}')
                    if config.do_polarization_compensation is True:
                        polarization_compensator.update_QBER(
                            diagnosis.quantum_bit_error)
        except OSError:
            pass
        except Exception as a:
            logger.error(a)
    logger.info(f'Thread finished.')


def stop_splicer():
    global proc_splicer
    qkd_globals.kill_process(proc_splicer)
    proc_splicer = None


def is_running():
    return not (proc_splicer is None or proc_splicer.poll() is not None)


def main():
    pass


if __name__ == '__main__':
    main()
