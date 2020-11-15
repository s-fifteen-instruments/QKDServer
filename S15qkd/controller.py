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
from .qkd_globals import logger, QKDProtocol, PipesQKD, FoldersQKD
from .transferd import SymmetryNegotiationState

# configuration file contains the most important paths and the target ip and port number
config_file = qkd_globals.config_file


def _load_config(config_file_name: str):
    with open(config_file_name, 'r') as f:
        config = json.load(f)
    global det1corr, det2corr, det3corr, det4corr
    global dataroot, programroot, extclockopt, periode_count, fft_buffer_order
    global with_error_correction, qkd_protocol, identity
    det1corr = config['local_detector_skew_correction']['det1corr']
    det2corr = config['local_detector_skew_correction']['det2corr']
    det3corr = config['local_detector_skew_correction']['det3corr']
    det4corr = config['local_detector_skew_correction']['det4corr']
    dataroot = config['data_root']
    programroot = config['program_root']
    qkd_protocol = QKDProtocol(config['protocol'])
    extclockopt = config['clock_source']
    periode_count = config['pfind_epochs']
    fft_buffer_order = config['FFT_buffer_order']
    with_error_correction = config['error_correction']
    identity = config['identity']


def initialize(config_file_name: str = config_file):
    global prog_readevents, prog_pfind, proc_readevents, proc_pfind
    global cwd, localcountrate, remote_count_rate
    global low_count_side, first_epoch, time_diff, sig_long, sig_short
    _load_config(config_file_name)
    cwd = os.getcwd()
    prog_readevents = qkd_globals.prog_readevents
    prog_pfind = programroot + '/pfind'
    proc_readevents = None
    proc_pfind = None
    localcountrate = -1
    remote_count_rate = -1
    low_count_side = None
    first_epoch = ''
    time_diff = 0
    sig_long = 0
    sig_short = 0
    qkd_globals.kill_existing_qcrypto_processes()


def msg_response(message):
    global low_count_side, first_epoch, time_diff, sig_long, sig_short
    global with_error_correction
    msg_split = message.split(':')[:]
    msg_code = msg_split[0]
    low_count_side = transferd.low_count_side

    if msg_code == 'st1':  # Start key generation Step 1
        qkd_globals.FoldersQKD.remove_stale_comm_files()
        if low_count_side is None:
            logger.info(f'{msg_code} Symmetry negotiation not completed yet. \
                Key generation was not started.')
            return
        elif low_count_side is True:
            chopper.start_chopper(QKDProtocol.BBM92)
            splicer.start_splicer()
            if with_error_correction == True:
                error_correction.start_error_correction()
            _start_readevents()
        elif low_count_side is False:
            chopper2.start_chopper2()
            _start_readevents()
        transferd.send_message("st2")

    if msg_code == 'st2':
        qkd_globals.FoldersQKD.remove_stale_comm_files()
        if low_count_side is None:
            logger.info(f'{msg_code} Symmetry negotiation not completed yet. \
                Key generation was not started.')
            return
        elif low_count_side is True:
            _start_readevents()
            chopper.start_chopper(QKDProtocol.BBM92)
            splicer.start_splicer()
            if with_error_correction == True:
                error_correction.start_error_correction()
            transferd.send_message('st3')  # High count side starts pfind
        elif low_count_side is False:
            _start_readevents()
            chopper2.start_chopper2()
            time_diff, sig_long, sig_short = time_difference_find()
            costream.start_costream(time_diff, first_epoch,
                                    qkd_protocol=QKDProtocol.BBM92)
            if with_error_correction == True:
                error_correction.start_error_correction()

    if msg_code == 'st3':
        if low_count_side is False:
            time_diff, sig_long, sig_short = time_difference_find()
            costream.start_costream(time_diff, first_epoch,
                                    qkd_protocol=QKDProtocol.BBM92)
            if with_error_correction == True:
                error_correction.start_error_correction()
        else:
            logger.error(f'{msg_code} Not the high count side or symmetry \
                negotiation not completed.')

    if msg_code == 'stop_key_gen':
        _stop_key_gen_processes()

    if msg_code == 'start_service_mode':
        _stop_key_gen_processes()
        transferd.send_message('start_service_mode_step2')
        print(low_count_side)
        if low_count_side is False:
            _start_readevents()
            chopper2.start_chopper2()
            # wait_for_epoch_files(2)
            # if costream.initial_time_difference != None:
            #     curr_time_diff = costream.latest_deltat + costream.initial_time_difference
            # else:
            curr_time_diff, sig_long, sig_short = time_difference_find()
            costream.start_costream(curr_time_diff, first_epoch, 
                                    qkd_protocol=QKDProtocol.SERVICE)
        else:
            _start_readevents()
            chopper.start_chopper(QKDProtocol.SERVICE)
            splicer.start_splicer(qkd_protocol=QKDProtocol.SERVICE)

    if msg_code == 'start_service_mode_step2':
        _stop_key_gen_processes()
        if low_count_side is False:
            _start_readevents()
            chopper2.start_chopper2()
            # wait_for_epoch_files(2)
            # if costream.initial_time_difference != None:
            #     curr_time_diff = costream.latest_deltat + costream.initial_time_difference
            # else:
            curr_time_diff, sig_long, sig_short = time_difference_find()
            costream.start_costream(curr_time_diff, first_epoch, 
                                    qkd_protocol=QKDProtocol.SERVICE)
        else:
            _start_readevents()
            chopper.start_chopper(QKDProtocol.SERVICE)
            splicer.start_splicer(qkd_protocol=QKDProtocol.SERVICE)


def wait_for_epoch_files(number_of_epochs):
    global first_epoch
    transferd.first_received_epoch = None
    if not transferd.is_running():
        logger.error(f'Transferd process has not been started.' +
                     ' time_difference_find aborted.')
        return
    if transferd.transferd_proc.poll() is not None:
        logger.error(f'Transferd process was started but is not running. \
            time_difference_find aborted.')
        return
    start_time = time.time()
    timeout = (number_of_epochs + 2) * qkd_globals.EPOCH_DURATION 
    while transferd.first_received_epoch is None or chopper2.first_epoch is None:
        if (time.time() - start_time) > timeout:
            logger.error(
                f'Timeout: not enough data within {timeout}s')
            raise Exception(
                f'Notenough data within {timeout}s')
        time.sleep(0.2)

    # make sure there is enough epochs available
    while chopper2.t1_epoch_count < number_of_epochs:
        logger.debug(f'Waiting for more epochs.')
        time.sleep(1)

    epoch_diff = int(transferd.first_received_epoch, 16) - \
        int(chopper2.first_epoch, 16)
    if epoch_diff < 0 or epoch_diff == 0:
        first_epoch = chopper2.first_epoch
    elif epoch_diff > 0:
        first_epoch = transferd.first_received_epoch
    return first_epoch, epoch_diff


def time_difference_find():
    '''
    Starts pfind and searches for the photon coincidence peak
    in the combined timestamp files.
    '''
    global periode_count, fft_buffer_order
    global prog_pfind, first_epoch

    first_epoch, epoch_diff = wait_for_epoch_files(periode_count)

    if epoch_diff > 0:
        use_periods = periode_count - epoch_diff  # less periodes are available
    else:
        # Not sure why minus 2, but I'm following what was done in crgui_ec.
        use_periods = periode_count - 2

    args = f'-d {cwd}/{dataroot}/receivefiles \
            -D {cwd}/{dataroot}/t1 \
            -e 0x{first_epoch} \
            -n {use_periods} -V 1 \
            -q {fft_buffer_order}'
    logger.info(f'pfind {args}')
    with open(f'{cwd}/{dataroot}/pfinderror', 'a+') as f:
        proc_pfind = subprocess.Popen([prog_pfind, *args.split()],
                                      stderr=f,
                                      stdout=subprocess.PIPE)
    proc_pfind.wait()
    pfind_result = (proc_pfind.stdout.read()).decode()
    logger.info(f'Pfind result: {pfind_result.split()}')
    return [float(i) for i in pfind_result.split()]


def _do_symmetry_negotiation():
    if transferd.is_running():
        transferd.symmetry_negotiation()
        if transferd.low_count_side == '':
            # logger.degug(f'Symmetry negotiation not finished.')
            start_time = time.time()
            while True:
                if transferd.negotiating == SymmetryNegotiationState.PENDING:
                    if (time.time() - start_time) > 3:
                        logger.error(
                            f'Symmetry negotiation timeout.')
                        return
                    continue
                elif transferd.negotiating == SymmetryNegotiationState.FINISHED:
                    break
                elif transferd.negotiating == SymmetryNegotiationState.NOTDONE:
                    logger.error(
                        f'No network connection established.')
                    return
    else:
        logger.error(
            'Symmetry negotiation failed because transferd is not running.')


def start_key_generation():
    # global protocol
    if transferd.is_running() is False:
        start_communication()
    transferd.send_message('stop_key_gen')
    _stop_key_gen_processes()
    if transferd.is_running():
        _do_symmetry_negotiation()
        transferd.send_message('st1')


def start_service_mode():
    if transferd.is_running() is False:
        start_communication()
    transferd.send_message('stop_key_gen')
    _stop_key_gen_processes()
    _do_symmetry_negotiation()
    transferd.send_message('start_service_mode')


def _stop_key_gen_processes():
    global proc_readevents
    chopper.stop_chopper()
    chopper2.stop_chopper2()
    splicer.stop_splicer()
    costream.stop_costream()
    error_correction.stop_error_correction()
    qkd_globals.kill_process(proc_readevents)
    qkd_globals.PipesQKD.drain_all_pipes()

def stop_key_gen():
    transferd.send_message('stop_key_gen')
    _stop_key_gen_processes()


def start_communication():
    '''Establishes network connection between computers.
    '''
    if not transferd.is_running():
        qkd_globals.FoldersQKD.prepare_folders()
        qkd_globals.PipesQKD.prepare_pipes()
        transferd.start_communication(msg_response)


def get_process_states():
    return {'transferd': transferd.is_running(),
            'readevents': not (proc_readevents is None or proc_readevents.poll() is not None),
            'chopper': chopper.is_running(),
            'chopper2': chopper2.is_running(),
            'costream': costream.is_running(),
            'splicer': splicer.is_running(),
            'error_correction': error_correction.is_running()
            }


def get_status_info():
    stats = {'connection_status': transferd.communication_status,
             'protocol': qkd_protocol,
             'last_received_epoch': transferd.last_received_epoch,
             'init_time_diff': time_diff,
             'sig_long': sig_long,
             'sig_short': sig_short,
             'tracked_time_diff': costream.latest_deltat,
             'symmetry': transferd.low_count_side,
             'coincidences': costream.latest_coincidences,
             'accidentals': costream.latest_accidentals,
             }
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


def _start_readevents(det_dead_time: int = 30000):
    '''
    Start readevents
    '''
    global proc_readevents, prog_readevents
    fd = os.open(PipesQKD.RAWEVENTS, os.O_RDWR)  # non-blocking
    f_stdout = os.fdopen(fd, 'w')  # non-blocking
    args = f'-a 1 -A {extclockopt} -S 20 \
             -Y {det_dead_time},{det_dead_time},{det_dead_time},{det_dead_time} \
             -d {det1corr},{det2corr},{det3corr},{det4corr}'
    logger.info(f'readevents started with these arguments: {args}')
    with open(f'{cwd}/{dataroot}/readeventserror', 'a+') as f_stderr:
        proc_readevents = subprocess.Popen((prog_readevents, *args.split()),
                                           stdout=f_stdout,
                                           stderr=f_stderr)
    logger.info(f'Started readevents.')


class ProcessWatchDog(threading.Thread):
    '''Monitors all processes neccessary to generate QKD keys.

    Basic logging of events and restart processes in case they crash.
    '''

    def __init__(self, log_file_name: str = 'process_watchdog.log'):
        super(ProcessWatchDog, self).__init__()
        self._running = True
        self._logger = logging.getLogger('processes_watchdog')
        self._logger.setLevel(logging.DEBUG)
        self._fh = logging.FileHandler(log_file_name, mode="a+")
        self._fh.setLevel(logging.DEBUG)
        self._fh.setFormatter(logging.Formatter(
            '%(asctime)s | %(process)d | %(levelname)s | %(module)s | %(message)s'))
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
