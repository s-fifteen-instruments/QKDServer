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
import signal
import time
import sys
import threading
from queue import Queue, Empty
import json
import logging

# Own modules
from . import transferd
from . import splicer
from . import chopper
from . import chopper2
from . import costream
from . import error_correction
from . import qkd_globals
from .qkd_globals import logger

# configuration file contains the most important paths and the target ip and port number
config_file = qkd_globals.config_file

with open(config_file, 'r') as f:
    config = json.load(f)


for key, value in config['local_detector_skew_correction'].items():
    vars()[key] = value
dataroot = config['data_root']
programroot = config['program_root']
protocol = config['protocol']
extclockopt = config['clock_source']
periode_count = config['pfind_epochs']
FFT_buffer_order = config['FFT_buffer_order']

cwd = os.getcwd()
localcountrate = -1
remote_count_rate = -1

# program paths for processes used in this module
prog_readevents = qkd_globals.prog_readevents
prog_pfind = programroot + '/pfind'

proc_readevents = None
proc_pfind = None
low_count_side = None
t2logpipe_digest_thread_flag = False
t1logpipe_digest_thread_flag = False
t1logcount = 0
first_epoch = ''
time_diff = 0
sig_long = 0
sig_short = 0



def msg_response(message):
    global low_count_side, first_epoch, time_diff, sig_long, sig_short
    method_name = sys._getframe().f_code.co_name
    msg_split = message.split(':')[:]
    msg_code = msg_split[0]
    low_count_side = transferd.low_count_side

    if msg_code == 'st1':
        qkd_globals.remove_stale_comm_files()
        if low_count_side is None:
            logger.info(f'[{method_name}:st1] Symmetry negotiation not completed yet. \
                Key generation was not started.')
            return
        elif low_count_side is True:
            chopper.start_chopper()
            splicer.start_splicer(_splicer_callback_start_error_correction)
            error_correction.start_error_correction()
            _start_readevents()
        elif low_count_side is False:
            chopper2.start_chopper2()
            _start_readevents()
        transferd.send_message("st2")

    if msg_code == 'st2':
        qkd_globals.remove_stale_comm_files()
        if low_count_side is None:
            logger.info(f'[{method_name}:st2] Symmetry negotiation not completed yet. \
                Key generation was not started.')
            return
        elif low_count_side is True:
            _start_readevents()
            chopper.start_chopper()
            splicer.start_splicer(_splicer_callback_start_error_correction)
            error_correction.start_error_correction()
            transferd.send_message('st3')  # High count side starts pfind
        elif low_count_side is False:
            _start_readevents()
            chopper2.start_chopper2()
            time_diff, sig_long, sig_short = periode_find()
            costream.start_costream(time_diff, first_epoch)
            error_correction.start_error_correction()

    if msg_code == 'st3':
        if low_count_side is False:
            time_diff, sig_long, sig_short = periode_find()
            costream.start_costream(time_diff, first_epoch)
            error_correction.start_error_correction()
        else:
            logger.info(f'[{method_name}:st3] Not the high count side or symmetry \
                negotiation not completed.')


def _splicer_callback_start_error_correction(epoch_name: str):
    '''
    This function is used as a call back for the splicer process.
    Whenever the splicer generates a raw key, we notify the error correction process to
    convert the keys to error-corrected privacy-amplified keys.
    '''
    method_name = sys._getframe().f_code.co_name
    logger.info(f'[{method_name}] Add {epoch_name} to error correction queue')
    error_correction.ec_queue.put(epoch_name)


def periode_find():
    '''
    Starts pfind and searches for the photon coincidence peak
    in the combined timestamp files.
    '''
    method_name = sys._getframe().f_code.co_name
    global periode_count, t1logcount, FFT_buffer_order
    global prog_pfind, first_epoch

    if transferd.commhandle is None:
        logger.info(f'[{method_name}] Transferd process has not been started.' +
              ' periode_find aborted.')
        return
    if transferd.commhandle.poll() is not None:
        logger.info(f'[{method_name}] transferd process was started but is not running. \
            periode_find aborted.')
        return

    while transferd.first_received_epoch is None or chopper2.first_epoch is None:
        logger.info(f'[{method_name}] Waiting for data.')
        time.sleep(1)

    # make sure there is enough epochs available
    while chopper2.t1_epoch_count < periode_count:
        logger.info(f'[{method_name}] Not enough epochs available to execute pfind.')
        time.sleep(1)

    # Not sure why minus 2, but I'm following what was done in crgui_ec.
    use_periods = periode_count - 2

    epoch_diff = int(transferd.first_received_epoch, 16) - \
        int(chopper2.first_epoch, 16)
    if epoch_diff < 0 or epoch_diff == 0:
        first_epoch = chopper2.first_epoch
    elif epoch_diff > 0:
        first_epoch = transferd.first_received_epoch
        use_periods = periode_count - epoch_diff  # less periodes are available

    args = f'-d {cwd}/{dataroot}/receivefiles \
            -D {cwd}/{dataroot}/t1 \
            -e 0x{first_epoch} \
            -n {use_periods} -V 1 \
            -q {FFT_buffer_order}'

    with open(f'{cwd}/{dataroot}/pfinderror', 'a+') as f:
        proc_pfind = subprocess.Popen([prog_pfind, *args.split()],
                                      stderr=f,
                                      stdout=subprocess.PIPE)
    proc_pfind.wait()
    pfind_result = (proc_pfind.stdout.read()).decode()
    logger.info(f'[{method_name}:pfind_result] {pfind_result.split()}')
    return [float(i) for i in pfind_result.split()]


def start_raw_key_generation():
    # global protocol
    method_name = sys._getframe().f_code.co_name
    if transferd.is_running() is False:
        qkd_globals.prepare_folders()
        transferd.start_communication(msg_response)
    qkd_globals.drain_all_pipes()
    transferd.symmetry_negotiation()
    if transferd.low_count_side == '':
        logger.info(f'[{method_name}] Symmetry negotiation not finished.')
        while True:
            if transferd.negotiating == 1:
                continue
            elif transferd.negotiating == 2:
                break
            elif transferd.negotiating == 0:
                return
    transferd.send_message('st1')


def start_communication():
    '''Establishes network connection between computers.

    [description]
    '''
    if not transferd.is_running():
        stop_all_processes()
        qkd_globals.prepare_folders()
        transferd.start_communication(msg_response)


def get_process_states():
    return {'transferd': not (transferd.commhandle is None or transferd.commhandle.poll() is not None),
            'readevents': not (proc_readevents is None or proc_readevents.poll() is not None),
            'chopper': not (chopper.proc_chopper is None or chopper.proc_chopper.poll() is not None),
            'chopper2': not (chopper2.proc_chopper2 is None or chopper2.proc_chopper2.poll() is not None),
            'costream': not (costream.proc_costream is None or costream.proc_costream.poll() is not None),
            'splicer': not (splicer.proc_splicer is None or splicer.proc_splicer.poll() is not None),
            'error_correction': not (error_correction.proc_error_correction is None or error_correction.proc_error_correction.poll() is not None)
            }


def get_status_info():
    stats = {'connection_status': transferd.communication_status,
             'protocol': protocol,
             'last_received_epoch': transferd.last_received_epoch,
             'init_time_diff': time_diff,
             'sig_long': sig_long,
             'sig_short': sig_short,
             'tracked_time_diff': 'where is this info?',
             'symmetry':transferd.low_count_side}
    return stats


def get_error_corr_info():
    stats = {'first_epoch': error_correction.first_epoch_info,
             'undigested_epochs': error_correction.undigested_epochs_info,
             'ec_raw_bits': error_correction.ec_raw_bits,
             'ec_final_bits': error_correction.ec_final_bits,
             'ec_err_fraction': error_correction.ec_err_fraction,
             'key_file_name': error_correction.ec_epoch,
             'total_ec_key_bits': error_correction.total_ec_key_bits,
             'init_QBER': error_correction.init_QBER_info}
    return stats


def stop_all_processes():
    global proc_readevents
    transferd.stop_communication()
    chopper.stop_chopper()
    chopper2.stop_chopper2()
    splicer.stop_splicer()
    costream.stop_costream()
    error_correction.stop_error_correction()
    qkd_globals.kill_process(proc_readevents)


def _start_readevents():
    '''
    Start reader and chopper on sender side (low-count side)
    '''
    method_name = sys._getframe().f_code.co_name  # used for logging
    global proc_readevents, prog_readevents
    
    fd = os.open(f'{dataroot}/rawevents', os.O_RDWR)  # non-blocking
    f_stdout = os.fdopen(fd, 'w')  # non-blocking
    logger.info('starting_readevents:' + prog_readevents)
    args = f'-a 1 -A {extclockopt} -S 20 \
             -d {det1corr},{det2corr},{det3corr},{det4corr}'
    with open(f'{cwd}/{dataroot}/readeventserror', 'a+') as f_stderr:
        proc_readevents = subprocess.Popen((prog_readevents, *args.split()),
                                           stdout=f_stdout,
                                           stderr=f_stderr)
    logger.info(f'[{method_name}] Started readevents.')


class ProcessWatchDog(threading.Thread):
    '''Monitors all processes neccessary to generate QKD keys.

    Basic logging of events and restart processes in case they crash.
    
    Arguments:
        log_file_name {str}
    '''
    def __init__(self, log_file_name: str = 'process_watchdog.log'): 
        super(ProcessWatchDog, self).__init__()
        self._running = True
        self._logger = logging.getLogger('processes_watchdog')
        self._logger.setLevel(logging.DEBUG)
        self._fh = logging.FileHandler(log_file_name, mode="a+")
        self._fh.setLevel(logging.DEBUG)
        self._fh.setFormatter(logging.Formatter('%(asctime)s - %(process)d - %(levelname)s - %(module)s - %(message)s'))
        self._logger.addHandler(self._fh)
        self._logger.info('Initialized watchdog.')
        # store process states to obsrver changes
        self.prev_proc_states = get_process_states()
        self.prev_status = get_status_info()
        self._logger.info(self.prev_proc_states)
        # print(self.prev_proc_states)

    def terminate(self):
        self._running = False

    def run(self):
        global proc_readevents
        while self._running:
            time.sleep(0.5)
            proc_states = get_process_states()
            status = get_status_info()
            for key in proc_states:
                if self.prev_proc_states[key] != proc_states[key]:
                    if proc_states[key]:
                        self._logger.info(f'{key} started.')
                    else:
                        self._logger.info(f'{key} stopped.')
            if status['connection_status'] == 2 and self.prev_status['connection_status'] == 1:
                self._logger.info('Disconnected.')
                self._logger.info('Stopping all key generation processes')
                chopper.stop_chopper()
                chopper2.stop_chopper2()
                splicer.stop_splicer()
                costream.stop_costream()
                error_correction.stop_error_correction()
                qkd_globals.kill_process(proc_readevents)
            self.prev_proc_states = proc_states
            self.prev_status = status


def initialize():
    qkd_globals.kill_existing_qcrypto_processes()

def main():
    start_communication()
    # error_correction.raw_key_folder = 'data/ec_test_data/rawkeyB'
    # error_correction.errcd_killfile_option = ''
    error_correction.start_error_correction()
    time.sleep(10)
    stop_all_processes()
    # kill_process(commhandle))

initialize()
watchdog = ProcessWatchDog()
watchdog.daemon = True
watchdog.start()


if __name__ == '__main__':
    main()

