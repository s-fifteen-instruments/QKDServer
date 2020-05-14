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
__credits__ = ['']
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


def load_error_correction_config(config_file_name: str):
    global dataroot, config, error_correction_program_path, program_root, data_root
    global privacy_amplification, errcd_killfile_option, target_bit_error
    global minimal_block_size, QBER_limit, default_QBER
    with open(config_file_name, 'r') as f:
        config = json.load(f)
    data_root = config['data_root']
    program_root = config['program_root']
    error_correction_program_path = config['error_correction_program_path']
    privacy_amplification = config['privacy_amplification']
    errcd_killfile_option = config['errcd_killfile_option']
    target_bit_error = config['target_bit_error']
    minimal_block_size = config['minimal_block_size']
    QBER_limit = config['QBER_limit']
    default_QBER = config['default_QBER']
    servo_blocks = config['servo_blocks']


load_error_correction_config('config/config.json')

program_error_correction = error_correction_program_path + '/errcd'
program_diagbb84 = program_root + '/diagbb84'
proc_error_correction = None  # error correction process handle
ec_queue = queue.Queue()  # used to queue raw key files
servoed_QBER = default_QBER
# counts the final key bits produced by the error correction process
total_ec_key_bits = 0
cwd = os.getcwd()


def start_error_correction():
    '''Starts the error correction process.
    '''
    global proc_error_correction
    method_name = sys._getframe().f_code.co_name  # used for logging
    ecnotepipe_thread = threading.Thread(target=_ecnotepipe_digest, args=())
    do_ec_thread = threading.Thread(target=_do_error_correction, args=())

    erropt = ''
    if privacy_amplification is False:
        erropt = '-p'
    if errcd_killfile_option is True:
        erropt += ' -k'
    erropt += f' -B {target_bit_error}'

    args = f'-c {data_root}/eccmdpipe \
             -s {data_root}/ecspipe \
             -r {data_root}/ecrpipe \
             -d {data_root}/rawkey -f {data_root}/finalkey \
             -l {data_root}/ecnotepipe \
             -Q {data_root}/ecquery -q {data_root}/ecresp \
             -V 2 {erropt} -T 1'

    with open(f'{cwd}/{data_root}/errcd_log', 'a+') as f_stdout:
        with open(f'{cwd}/{data_root}/errcd_err', 'a+') as f_err:
            proc_error_correction = subprocess.Popen((program_error_correction,
                                                      *args.split()),
                                                     stdout=f_stdout,
                                                     stderr=f_err)
    ecnotepipe_thread.start()
    do_ec_thread.start()
    print(f'[{method_name}] Started error correction.')


def _ecnotepipe_digest():
    '''
    Digests error correction activities indicated by the 'ecnotepipe' pipe
    '''
    global proc_error_correction, total_ec_key_bits, servoed_QBER
    method_name = sys._getframe().f_code.co_name
    pipe_name = f'{dataroot}/ecnotepipe'
    fd = os.open(pipe_name, os.O_RDONLY | os.O_NONBLOCK)
    f = os.fdopen(fd, 'rb', 0)  # non-blocking

    while proc_error_correction.poll() is None:
        time.sleep(0.05)
        try:
            message = (f.readline().decode().rstrip('\n')).lstrip('\x00')
            if len(message) == 0:
                # print('.')
                continue
            message = message.split()
            ec_epoch = message[0]
            ec_raw_bits = int(message[1])
            ec_final_bits = int(message[2])
            ec_err_fraction = float(message[3])
            total_ec_key_bits += ec_final_bits

            # servoing QBER
            servoed_QBER += (ec_err_fraction - servoed_QBER) / servo_blocks
            if servoed_QBER > 1 or servoed_QBER < 0:
                servoed_QBER = default_QBER
            elif servoed_QBER > QBER_limit:
                servoed_QBER = QBER_limit

            print(f'[{method_name}] {message}')
        except OSError as a:
            pass
    print(f'[{method_name}] Thread finished')


def _do_error_correction():
    '''Executes the error correction on files in the ec_queue.
    The queue consists of raw key file names generated by costream or splicer.
    Usually runs as a thread.

    This function checks each file for the bit number and once enough bits are available
    it notifies the error correction process by writing into the eccmdpipe.
    '''
    global ec_queue, minimal_block_size
    method_name = sys._getframe().f_code.co_name
    ec_cmd_pipe = f'{dataroot}/eccmdpipe'
    undigested_raw_bits = 0
    first_epoch = None
    undigested_epochs = 0
    while proc_error_correction.poll() is None:
        # Attempt get from queue (FIFO). If no item is available, sleep a while
        # and try again.
        try:
            file_name = ec_queue.get_nowait()
        except queue.Empty as a:
            print(f'{method_name:Exception} {a}')
            time.sleep(0.5)
            continue
        # Use diagbb84 to check for raw key bits
        args = f'{file_name}'
        proc_diagbb84 = subprocess.Popen([program_diagbb84, *args.split()],
                                         stderr=subprocess.PIPE,
                                         stdout=subprocess.PIPE)
        proc_diagbb84.wait()
        diagbb84_result = (proc_diagbb84.stdout.read()).decode().split()
        diagbb84_error = (proc_diagbb84.stderr.read()).decode()
        print(f'[{method_name}:diagbb84_result] {diagbb84_result}')
        print(f'[{method_name}:diagbb84_result] {diagbb84_error}')
        # If no BB84 type OR more than one bit per entry
        # Check diagbb84 for the return values meanings
        if int(diagbb84_result[0]) == 0 or int(diagbb84_result[1]) != 1:
            continue

        if undigested_epochs == 0:
            first_epoch = file_name
        undigested_epochs += 1
        undigested_raw_bits += int(diagbb84_result[2])
        # for now I just implement the bit size option
        if undigested_raw_bits > minimal_block_size:
            # notify the error correction process about the first epoch, number of epochs, and the servoed QBER
            _writer(ec_cmd_pipe, f'0x{first_epoch} {undigested_epochs} {float("{0:.4f}".format(servoed_QBER))}')
            undigested_raw_bits = 0
            undigested_epochs = 0
            print(print(f'[{method_name}] Started error correction for epoch {first_epoch}, {undigested_epochs}.'))


def _writer(file_name, message):
    f = os.open(file_name, os.O_WRONLY)
    os.write(f, f'{message}\n'.encode())
    os.close(f)


def _kill_process(my_process):
    if my_process is not None:
        method_name = sys._getframe().f_code.co_name
        print(f'[{method_name}] Killing process: {my_process.pid}.')
        process = psutil.Process(my_process.pid)
        for proc in process.children(recursive=True):
            proc.kill()
        process.kill()


def stop_error_correction():
    global proc_error_correction
    _kill_process(proc_error_correction)
    proc_error_correction = None


if __name__ == '__main__':
    import time
    start_error_correction()
    time.sleep(1)
    stop_error_correction()
