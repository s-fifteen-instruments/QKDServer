#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
This module wraps the error correction process and attaches readers to the process pipes.

The code for the error correction process can be found under: 
https://github.com/kurtsiefer/qcrypto/tree/master/errorcorrection

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
import json
import subprocess
import os
import threading
import sys
import psutil
import time
import queue
import collections

from . import qkd_globals
from .qkd_globals import logger, PipesQKD, FoldersQKD
from . import polarization_compensation

EPOCH_DURATION = 0.536  # seconds

proc_error_correction = None

def _load_error_correction_config(config_file_name: str):
    global config, program_root, data_root
    global privacy_amplification, errcd_killfile_option, target_bit_error
    global minimal_block_size, QBER_limit, default_QBER, servo_blocks
    global program_error_correction, program_diagbb84, ec_note_pipe
    global raw_key_folder, servoed_QBER
    global do_polarization_compensation

    with open(config_file_name, 'r') as f:
        config = json.load(f)

    data_root = config['data_root']
    program_root = config['program_root']
    privacy_amplification = config['privacy_amplification']
    errcd_killfile_option = config['errcd_killfile_option']
    target_bit_error = config['target_bit_error']
    minimal_block_size = config['minimal_block_size']
    QBER_limit = config['QBER_limit']
    default_QBER = config['default_QBER']
    servo_blocks = config['servo_blocks']
    do_polarization_compensation = config['do_polarization_compensation']

    program_error_correction = program_root + '/errcd'
    program_diagbb84 = program_root + '/diagbb84'
    ec_note_pipe = data_root + '/ecnotepipe'
    raw_key_folder = data_root + '/rawkey'
    servoed_QBER = default_QBER


def initialize(config_file_name: str = qkd_globals.config_file):
    global ec_queue, total_ec_key_bits, cwd
    global undigested_epochs_info, init_QBER_info, ec_raw_bits
    global ec_epoch, ec_final_bits, ec_err_fraction, first_epoch_info, ec_key_gen_rate
    global proc_error_correction, ec_err_fraction_history, ec_err_key_length_history
    global polarization_comp
    _load_error_correction_config(config_file_name)
    ec_queue = queue.Queue()  # used to queue raw key files
    total_ec_key_bits = 0  # counts the final error-corrected key bits
    cwd = os.getcwd()
    first_epoch_info = ''
    undigested_epochs_info = 0
    init_QBER_info = 0
    ec_raw_bits = 0
    ec_final_bits = 0
    ec_err_fraction = 0
    ec_epoch = ''
    ec_key_gen_rate = 0
    proc_error_correction = None  # error correction process handle
    ec_err_fraction_history = collections.deque(maxlen=100)
    ec_err_key_length_history = collections.deque(maxlen=100)
    polarization_comp = None
    if do_polarization_compensation is True:
        polarization_comp = polarization_compensation.PolarizationDriftCompensation(
            averaging_n=1)


def start_error_correction(cmd_pipe: str = PipesQKD.ECCMD, send_pipe: str = PipesQKD.ECS,
                           receive_pipe: str = PipesQKD.ECR, raw_keys_folder: str = FoldersQKD.RAWKEYS,
                           final_keys_folder: str = FoldersQKD.FINALKEYS, notification_pipe: str = PipesQKD.ECNOTE,
                           query_pipe: str = PipesQKD.ECQUERY, query_resp_pipe: str = PipesQKD.ECR):
    '''Starts the error correction process.
    '''
    global proc_error_correction
    initialize()
    # create erroroptions from settings
    erropt = ''
    if privacy_amplification is False:
        erropt = '-p'
        logger.info(f'Privacy amplification off.')
    if errcd_killfile_option is True:
        erropt += ' -k'
    erropt += f' -B {target_bit_error}'
    logger.info(f'Error option: {erropt}')

    args = f'-c {cmd_pipe} \
             -s {send_pipe} \
             -r {receive_pipe} \
             -d {raw_keys_folder} \
             -f {final_keys_folder} \
             -l {notification_pipe} \
             -Q {query_pipe} \
             -q {query_resp_pipe} \
             -V 2 {erropt} -T 1'
    with open(f'{FoldersQKD.DATAROOT}/errcd_err', 'a+') as f_err:
        with open(f'{FoldersQKD.DATAROOT}/errcd_log', 'a+') as f_stdout:
            proc_error_correction = subprocess.Popen((program_error_correction,
                                                      *args.split()),
                                                     stdout=f_stdout,
                                                     stderr=f_err)
    # start pipe digests
    ecnotepipe_thread = threading.Thread(
        target=_ecnotepipe_digest, args=(), daemon=True)
    ecnotepipe_thread.start()
    do_ec_thread = threading.Thread(
        target=_do_error_correction, args=(), daemon=True)
    do_ec_thread.start()
    logger.info(f'Started error correction.')


def _ecnotepipe_digest():
    '''
    Digests error correction activities indicated by the 'ecnotepipe' pipe.
    This is getting input from the ec_note_pipe which is updated after an error correction run.
    '''
    global proc_error_correction, total_ec_key_bits, servoed_QBER, ec_note_pipe
    global ec_epoch, ec_raw_bits, ec_final_bits, ec_err_fraction
    global ec_err_fraction_history, ec_err_key_length_history, ec_key_gen_rate
    fd = os.open(ec_note_pipe, os.O_RDONLY | os.O_NONBLOCK)
    f = os.fdopen(fd, 'rb', 0)  # non-blocking

    while proc_error_correction is not None and proc_error_correction.poll() is None:
        time.sleep(0.1)
        try:
            message = (f.readline().decode().rstrip('\n')).lstrip('\x00')
            if len(message) != 0:
                message = message.split()
                ec_epoch = message[0]
                ec_raw_bits = int(message[1])
                ec_final_bits = int(message[2])
                ec_err_fraction = float(message[3])
                ec_key_gen_rate = ec_final_bits / \
                    (int(message[4]) * EPOCH_DURATION)
                total_ec_key_bits += ec_final_bits
                ec_err_fraction_history.append(ec_err_fraction)
                ec_err_key_length_history.append(ec_final_bits)
                if polarization_comp is not None:
                    polarization_comp.update_QBER(ec_err_fraction)
                # servoing QBER
                servoed_QBER += (ec_err_fraction - servoed_QBER) / servo_blocks
                if servoed_QBER < 0.005:
                    servoed_QBER = 0.005
                if servoed_QBER > 1 or servoed_QBER < 0:
                    servoed_QBER = default_QBER
                elif servoed_QBER > QBER_limit:
                    servoed_QBER = QBER_limit

                logger.info(
                    f'{message}. Total generated final bits: {total_ec_key_bits}.')
        except OSError:
            pass
    logger.info(f'Thread finished')


def _do_error_correction():
    '''Executes the error correction on files list in the ec_queue.
    The queue consists of raw key file names generated by costream or splicer.
    Usually runs as a thread.

    This function checks each file for the bit number and once enough bits are available
    it notifies the error correction process by writing into the eccmdpipe.
    '''
    global ec_queue, minimal_block_size, first_epoch_info, undigested_epochs_info, init_QBER_info
    undigested_raw_bits = 0
    first_epoch = ''
    undigested_epochs = 0
    while proc_error_correction is not None and proc_error_correction.poll() is None:
        # Attempt get from queue (FIFO). If no item is available, sleep a while
        # and try again.
        try:
            file_name = ec_queue.get_nowait()
        except queue.Empty:
            time.sleep(0.6)
            continue
        # Use diagbb84 to check for raw key bits
        args = f'{FoldersQKD.RAWKEYS}/{file_name}'
        proc_diagbb84 = subprocess.Popen([program_diagbb84, *args.split()],
                                         stderr=subprocess.PIPE,
                                         stdout=subprocess.PIPE)
        proc_diagbb84.wait()
        diagbb84_result = (proc_diagbb84.stdout.read()).decode().split()
        diagbb84_error = (proc_diagbb84.stderr.read()).decode()
        logger.info(f'diagbb84_result: {file_name} {diagbb84_result}')
        if diagbb84_error != '':
            logger.info(f'diagbb84_error: {diagbb84_error}')

        if int(diagbb84_result[0]) == 0 or int(diagbb84_result[1]) != 1:
            logger.info(f'Not BB84 file type or more than 1 bit per entry.')
            continue

        if undigested_epochs == 0:
            first_epoch = file_name
        undigested_epochs += 1
        undigested_raw_bits += int(diagbb84_result[2])

        # for now I just implement the bit size option.
        # Could be also based on number of epochs.
        if undigested_raw_bits > minimal_block_size:
            # notify the error correction process about the first epoch, number of epochs, and the servoed QBER
            qkd_globals.writer(
                PipesQKD.ECCMD, f'0x{first_epoch} {undigested_epochs} {float("{0:.4f}".format(servoed_QBER))}')
            logger.info(
                f'Started error correction for epoch {first_epoch}, {undigested_epochs}.')
            first_epoch_info = first_epoch
            undigested_epochs_info = undigested_epochs
            init_QBER_info = servoed_QBER
            undigested_raw_bits = 0
            undigested_epochs = 0
        else:
            logger.info(
                f'Undigested raw bits:{undigested_raw_bits}. Undigested epochs: {undigested_epochs}.')
        ec_queue.task_done()
    logger.info(f'Thread finished.')


def stop_error_correction():
    global proc_error_correction
    qkd_globals.kill_process(proc_error_correction)
    proc_error_correction = None


def is_running():
    return not (proc_error_correction is None or proc_error_correction.poll() is not None)


if __name__ == '__main__':
    import time
    start_error_correction()
    time.sleep(1)
    stop_error_correction()
