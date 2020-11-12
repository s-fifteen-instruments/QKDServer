#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
This modules is a wrapper of the transferd process.
Transferd is reponsible for the communication between the two partnering nodes in a QKD protocol.
It allows us to do messaging and file transfer.


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

import json
import subprocess
import threading
import os
from queue import Queue, Empty
import time
import sys
import psutil
from enum import Enum
from types import SimpleNamespace

from . import qkd_globals
from .qkd_globals import logger, PipesQKD, FoldersQKD


# def _load_transferd_config(config_file_name: str):
#     global data_root, program_root, target_ip, port_num, extclockopt
#     global prog_getrate, prog_transferd

#     with open(config_file_name, 'r') as f:
#         config = json.load(f)
#     data_root = config['data_root']
#     program_root = config['program_root']
#     target_ip = config['target_ip']
#     port_num = config['port_num']
#     extclockopt = config['clock_source']
#     prog_transferd = program_root + '/transferd'
#     prog_getrate = program_root + '/getrate'


def initialize(config_file_name: str = qkd_globals.config_file):
    global cwd, sleep_time, communication_status, low_count_side, remote_count_rate
    global local_count_rate, transferd_proc, first_received_epoch, last_received_epoch
    global prog_readevents, negotiating
    cwd = os.getcwd()
    sleep_time = 1
    communication_status = 0
    low_count_side = ''
    remote_count_rate = -1
    local_count_rate = -1
    transferd_proc = None
    first_received_epoch = ''
    last_received_epoch = ''
    prog_readevents = qkd_globals.prog_readevents
    negotiating = SymmetryNegotiationState.NOTDONE


def _local_callback(msg: str):
    '''
    The transferd process has a msgout pipe which contains received messages.
    Usually we let another script manage the response to these messages, 
    however when no response function is defined this function is used as a default response.


    Arguments:
        msg {str} -- Contains the messages received in the msgout pipe.
    '''
    logger.info(f'The msgout pipe is printed locally by the transferd modul.\n\
          Define a callback function in start_communication to digest the msgout output in your custom function.')
    logger.info(msg)


def start_communication(msg_out_callback=_local_callback, config_file_name: str = qkd_globals.config_file):
    global transferd_proc
    initialize()
    with open(config_file_name, 'r') as f:
        config = json.load(f, object_hook=lambda d: SimpleNamespace(**d))
    if communication_status == 0:
        args = f'-d {FoldersQKD.SENDFILES} -c {PipesQKD.CMD} -t {config.target_ip} \
            -D {FoldersQKD.RECEIVEFILES} -l {PipesQKD.TRANSFERLOG} \
            -m {PipesQKD.MSGIN} -M {PipesQKD.MSGOUT} -p {config.port_num} \
            -k -e {PipesQKD.ECS} -E {PipesQKD.ECR}'
        prog_transferd = config.program_root + '/transferd'
        transferd_proc = subprocess.Popen(
            (prog_transferd, *args.split()),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        # setup read thread for the process stdout
        q = Queue()  # I don't know why I need this but it works
        t = threading.Thread(
            target=_transferd_stdout_digest,
            args=(transferd_proc.stdout, transferd_proc.stderr, q),
            daemon=True)
        t.start()

        # setup read thread for the msgout pipe
        msg_out_thread = threading.Thread(target=_msg_out_digest,
                                          args=[msg_out_callback], daemon=True)
        msg_out_thread.start()

        # setup read thread fro the transferlog
        transferlog_thread = threading.Thread(
            target=_transferlog_digest, args=(), daemon=True)
        transferlog_thread.start()
        time.sleep(0.2)  # give some time to connect to the partnering computer
        return transferd_proc  # returns the process handle


def _transferd_stdout_digest(out, err, queue):
    global transferd_proc, communication_status
    logger.info(f'Thread started.')
    while is_running():
        time.sleep(0.5)
        for line in iter(out.readline, b''):
            line = line.rstrip()
            logger.info(f'[stdout] {line.decode()}')
            if line == b'connected.':
                communication_status = 1
            elif line == b'disconnected.':
                communication_status = 2
        for line in iter(err.readline, b''):
            logger.info(f'[stderr] {line.decode()}')
    communication_status = 0
    logger.info(f'Thread finished')
    # startcommunication() # this is to restart the startcomm process if it crashes


def _msg_out_digest(msg_out_callback):
    global transferd_proc
    fd = os.open(PipesQKD.MSGOUT, os.O_RDONLY | os.O_NONBLOCK)
    f = os.fdopen(fd, 'rb', 0)  # non-blocking
    logger.info(f'Thread started.')
    while is_running():
        time.sleep(0.05)
        try:
            message = f.readline().decode().lstrip('\x00').rstrip('\n')
            if len(message) != 0:
                logger.info(f'[read] {message}')
                if message.split(':')[0] in {'ne1', 'ne2', 'ne3'}:
                    _symmetry_negotiation_messaging(message)
                else:
                    msg_out_callback(message)
        except OSError:
            pass
    logger.info(f'Thread finished')


def _transferlog_digest():
    '''
    Digests the transferlog which is written by the transferd process.

    This function usually runs as a thread and watches the transferlog file. 
    If this is the low count side this function notifies the splicer about file arrival.
    '''
    global first_received_epoch, low_count_side, last_received_epoch
    fd = os.open(PipesQKD.TRANSFERLOG, os.O_RDONLY | os.O_NONBLOCK)
    f = os.fdopen(fd, 'rb', 0)  # non-blocking
    logger.info('Thread started.')
    while is_running():
        time.sleep(0.1)
        try:
            message = f.readline().decode().rstrip()
            if len(message) != 0:
                last_received_epoch = message
                logger.info(f'[read msg] {message}')
                if first_received_epoch == '':
                    first_received_epoch = message
                    logger.info(f'[first_rx_epoch] {first_received_epoch}')
                if low_count_side is True:
                    qkd_globals.writer(PipesQKD.SPLICER, message)
                    logger.info(f'Sent epoch name {message} to splicer.')
        except OSError:
            pass
    logger.info(f'Thread finished.')


def _symmetry_negotiation_messaging(message: str):
    global remote_count_rate, local_count_rate, low_count_side
    global negotiating
    msg_split = message.split(':')[:]
    msg_code = msg_split[0]

    if local_count_rate == -1:
        local_count_rate = measure_local_count_rate()

    if msg_code == 'ne1':
        remote_count_rate = int(msg_split[1])
        send_message(f'ne2:{local_count_rate}:{msg_split[1]}')

    if msg_code == 'ne2':
        remote_count_rate = int(msg_split[1])
        if int(msg_split[2]) == local_count_rate:
            send_message(f'ne3:{local_count_rate}:{remote_count_rate}')
            if local_count_rate <= remote_count_rate:
                low_count_side = True
                logger.info(f'[ne2] This is the low count side.')
            else:
                low_count_side = False
                logger.info(f'[ne2] This the high count side.')
            negotiating = SymmetryNegotiationState.FINISHED
        else:
            logger.info(f'[ne2] Local countrates do not agree. \
                    Symmetry negotiation failed.')
            negotiating = SymmetryNegotiationState.NOTDONE

    if msg_code == 'ne3':
        if int(msg_split[2]) == local_count_rate and int(msg_split[1]) == remote_count_rate:
            if local_count_rate < remote_count_rate:
                low_count_side = True
                logger.info(f'[ne3] This is the low count side.')
            else:
                low_count_side = False
                logger.info(f'[ne3] This is the high count side.')
            logger.info(f'[ne3] Symmetry negotiation succeeded.')
            negotiating = SymmetryNegotiationState.FINISHED
        else:
            logger.info(f'[ne3] Count rates in the messages do not agree. \
                Symmetry negotiation failed')
            negotiating = SymmetryNegotiationState.NOTDONE


def stop_communication():
    global transferd_proc, communication_status
    if is_running():
        qkd_globals.kill_process(transferd_proc)
        communication_status = 0
        transferd_proc = None


def send_message(message: str):
    qkd_globals.writer(PipesQKD.MSGIN, message)
    logger.info(message)
    time.sleep(sleep_time)


def symmetry_negotiation():
    global transferd_proc
    global negotiating, local_count_rate
    if negotiating != SymmetryNegotiationState.FINISHED:
        if local_count_rate == -1:
            local_count_rate = measure_local_count_rate()
        if transferd_proc.poll() is None:
            send_message(f'ne1:{local_count_rate}')
            negotiating = SymmetryNegotiationState.PENDING
        else:
            logger.info(f'Transferd process not running.')


def measure_local_count_rate(config_file_name: str = qkd_globals.config_file):
    '''
    Measure local photon count rate.
    '''
    global localcountrate
    with open(config_file_name, 'r') as f:
        config = json.load(f, object_hook=lambda d: SimpleNamespace(**d))
    localcountrate = -1
    cmd = prog_readevents
    args = f'-a 1 -F -u {config.clock_source} -S 20'
    p1 = subprocess.Popen([cmd, *args.split()],
                          stdout=subprocess.PIPE)
    logger.info('started readevents')
    prog_getrate = config.program_root + '/getrate'
    p2 = subprocess.Popen(prog_getrate,
                          stdin=p1.stdout,
                          stdout=subprocess.PIPE)
    p2.wait()
    try:
        qkd_globals.kill_process(p1)
        qkd_globals.kill_process(p2)
    except psutil.NoSuchProcess:
        pass
    localcountrate = int((p2.stdout.read()).decode())
    return localcountrate


def is_running():
    return not (transferd_proc is None or transferd_proc.poll() is not None)


def main():
    logger.info('start communication')
    start_communication()
    time.sleep(10)
    stop_communication()


def __del__():
    print('closing module')


class SymmetryNegotiationState(int, Enum):
    NOTDONE = 0
    PENDING = 1
    FINISHED = 2


if __name__ == '__main__':
    main()
