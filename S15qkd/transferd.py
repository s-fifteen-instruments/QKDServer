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

from . import qkd_globals
from .qkd_globals import logger

def _load_transferd_config(config_file_name: str):
    global data_root, program_root, target_ip, port_num, extclockopt
    global prog_getrate, prog_transferd

    with open(config_file_name, 'r') as f:
        config = json.load(f)
    data_root = config['data_root']
    program_root = config['program_root']
    target_ip = config['target_ip']
    port_num = config['port_num']
    extclockopt = config['clock_source']
    prog_transferd = program_root + '/transferd'
    prog_getrate = program_root + '/getrate'


def initialize(config_file_name: str = qkd_globals.config_file):
    _load_transferd_config(config_file_name)
    global cwd, sleep_time, communication_status, low_count_side, remote_count_rate
    global local_count_rate, commhandle, first_received_epoch, last_received_epoch
    global prog_readevents, negotiating
    cwd = os.getcwd()
    sleep_time = 1
    communication_status = 0
    low_count_side = ''
    remote_count_rate = -1
    local_count_rate = -1
    commhandle = None
    first_received_epoch = ''
    last_received_epoch = ''
    prog_readevents = qkd_globals.prog_readevents
    negotiating = 0


def _local_callback(msg: str):
    '''
    The transferd process has a msgout pipe which contains received messages.
    Usually we let another script manage the response to theses messages, 
    however when no response function is defined this function is used as a default response.


    Arguments:
        msg {str} -- Contains the messages received in the msgout pipe.
    '''
    method_name = sys._getframe().f_code.co_name
    logger.info(f'[{method_name}] The msgout pipe is printed locally by the transferd modul.\n\
          Define a callback function in start_communication to digest the msgout output in your custom function.')
    logger.info(msg)


def start_communication(msg_out_callback=_local_callback):
    global commhandle, program_root, data_root

    if communication_status == 0:
        args = f'-d {cwd}/{data_root}/sendfiles -c {cwd}/{data_root}/cmdpipe -t {target_ip} \
            -D {cwd}/{data_root}/receivefiles -l {cwd}/{data_root}/transferlog \
            -m {cwd}/{data_root}/msgin -M {cwd}/{data_root}/msgout -p {port_num} \
            -k -e {cwd}/{data_root}/ecspipe -E {cwd}/{data_root}/ecrpipe'


        commhandle = subprocess.Popen((prog_transferd, *args.split()),
                                      stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE)

        # setup read thread for the process stdout
        q = Queue()  # I don't know why I need this but it works
        t = threading.Thread(
                target=_transferd_stdout_digest,
                args=(commhandle.stdout, commhandle.stderr, q), 
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
        return commhandle  # returns the process handle


def _transferd_stdout_digest(out, err, queue):
    global commhandle, communication_status
    method_name = sys._getframe().f_code.co_name
    logger.info(f'[{method_name}] Thread started.')
    while commhandle.poll() is None:
        time.sleep(0.5)
        for line in iter(out.readline, b''):
            line = line.rstrip()
            logger.info(f'[transferd:stdout] {line.decode()}')
            if line == b'connected.':
                communication_status = 1
            elif line == b'disconnected.':
                communication_status = 2
        for line in iter(err.readline, b''):
            logger.info(f'[transferd:stderr] {line.decode()}')
    communication_status = 0
    logger.info(f'[{method_name}] Thread finished')
    # startcommunication() # this is to restart the startcomm process if it crashes


def _msg_out_digest(msg_out_callback):
    global commhandle
    method_name = sys._getframe().f_code.co_name
    pipe_name = f'{data_root}/msgout'
    fd = os.open(pipe_name, os.O_RDONLY | os.O_NONBLOCK)
    f = os.fdopen(fd, 'rb', 0)  # non-blocking
    logger.info(f'[{method_name}] Thread started.')
    while is_running():
        time.sleep(0.05)
        try:
            message = f.readline().decode().lstrip('\x00').rstrip('\n')
            if len(message) != 0:
                logger.info(f'[{method_name}:read] {message}')
                if message.split(':')[0] in {'ne1', 'ne2', 'ne3'}:
                    _symmetry_negotiation_messaging(message)
                else:
                    msg_out_callback(message)
        except OSError:
            pass
    logger.info(f'[{method_name}] Thread finished')


def _transferlog_digest():
    '''
    Digests the transferlog which is written by the transferd process.

    This function usually runs as a thread and
    watches the transferlog file.
    '''
    global first_received_epoch, low_count_side, last_received_epoch
    method_name = sys._getframe().f_code.co_name
    log_file_name = f'{data_root}/transferlog'
    splicer_pipe = f'{data_root}/splicepipe'
    fd = os.open(log_file_name, os.O_RDONLY | os.O_NONBLOCK)
    f = os.fdopen(fd, 'rb', 0)  # non-blocking
    logger.info(f'[{method_name}] Thread started.')
    while is_running():
        time.sleep(0.1)
        try:
            message = f.readline().decode().rstrip()
            if len(message) != 0:
                last_received_epoch = message
                logger.info(f'[{method_name}:read] {message}')
                if first_received_epoch == '':
                    first_received_epoch = message
                    logger.info(f'[{method_name}:first_rx_epoch] {first_received_epoch}')
                if low_count_side is True:
                    qkd_globals.writer(splicer_pipe, message)
                    logger.info(f'[{method_name}] Sent epoch name {message} to splicer.')
        except OSError:
            pass
    logger.info(f'[{method_name}] Thread finished.')


def _symmetry_negotiation_messaging(message):
    global remote_count_rate, local_count_rate, low_count_side
    global negotiating
    method_name = sys._getframe().f_code.co_name
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
                logger.info(f'[{method_name}:ne2] This is the low count side.')
            else:
                low_count_side = False
                logger.info(f'[{method_name}:ne2] This the high count side.')
            negotiating = 2
        else:
            logger.info(f'[{method_name}:ne2] Local countrates do not agree. \
                    Symmetry negotiation failed.')
            negotiating = 0

    if msg_code == 'ne3':
        if int(msg_split[2]) == local_count_rate and int(msg_split[1]) == remote_count_rate:
            if local_count_rate < remote_count_rate:
                low_count_side = True
                logger.info(f'[{method_name}:ne3] This is the low count side.')
            else:
                low_count_side = False
                logger.info(f'[{method_name}:ne3] This is the high count side.')
            logger.info(f'[{method_name}:ne3] Symmetry negotiation succeeded.')
            negotiating = 2
        else:
            logger.info(f'[{method_name}:ne3] Count rates in the messages do not agree. \
                Symmetry negotiation failed')
            negotiating = 0


def stop_communication():
    global commhandle
    if is_running():
        qkd_globals.kill_process(commhandle)
        commhandle = None


def send_message(message):
    method_name = sys._getframe().f_code.co_name
    qkd_globals.writer(f'{data_root}/msgin', message)
    logger.info(f'[{method_name}:write] {message}')
    time.sleep(sleep_time)


def symmetry_negotiation():
    # global commhandle
    global negotiating, local_count_rate
    method_name = sys._getframe().f_code.co_name
    if local_count_rate == -1:
        local_count_rate = measure_local_count_rate()
    if commhandle.poll() is None:
        send_message(f'ne1:{local_count_rate}')
        negotiating = 1
    else:
        logger.info(f'[{method_name}] Transferd process not running.')


def measure_local_count_rate():
    '''
    Measure local photon count rate.
    '''
    global program_root, data_root, localcountrate, extclockopt
    localcountrate = -1
    cmd = prog_readevents
    args = f'-a 1 -F -u {extclockopt} -S 20'
    p1 = subprocess.Popen([cmd, *args.split()],
                          stdout=subprocess.PIPE)
    logger.info('started readevents')
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
    return not (commhandle is None or commhandle.poll() is not None)


def main():
    logger.info('start communication')
    start_communication()
    time.sleep(10)
    stop_communication()


initialize()

if __name__ == '__main__':
    main()
