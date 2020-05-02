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
__credits__ = ['']
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
import psutil
import asyncio  # for concurrent processes
import glob  # for file system access
import stat
import shutil  # can delete complete folders with everything underneath
import sys
import threading
import select
from queue import Queue, Empty
import json

# Own modules
import transferd
import splicer
import chopper
import chopper2

# configuration file contains the most important paths and the target ip and port number
with open('config/config.json', 'r') as f:
    config = json.load(f)


for key, value in config['local_detector_skew_correction'].items():
    vars()[key] = value
dataroot = config['data_root']
programroot = config['program_root']
protocol = config['protocol']
max_event_diff = config['max_event_diff']
targetmachine = config['target_ip']
portnum = config['port_num']
kill_option = config['kill_option']
extclockopt = config['clock_source']
periode_count = config['periode_count']
AKF_buffer_order = config['AKF_buffer_order']

cwd = os.getcwd()
localcountrate = -1
remote_count_rate = -1
testing = 1  # CHANGE to 0 if you want to run it with hardware
if testing == 1:
    # this outputs one timestamp file in an endless loop. This is for testing only.
    prog_readevents = 'timestampsimulator/readevents_simulator.sh'
else:
    prog_readevents = programroot + '/readevents3'

prog_pfind = programroot + '/pfind'

proc_readevents = proc_pfind = None
low_count_side = None
t2logpipe_digest_thread_flag = False
t1logpipe_digest_thread_flag = False
t1logcount = 0
first_epoch = first_received_epoch = None


def kill_process(my_process):
    if my_process is not None:
        method_name = sys._getframe().f_code.co_name
        print(f'[{method_name}] Killing process: {my_process.pid}.')
        process = psutil.Process(my_process.pid)
        for proc in process.children(recursive=True):
            proc.kill()
        process.kill()


def _prepare_folders():
    global dataroot
    if os.path.exists(dataroot):
        shutil.rmtree(dataroot)
    folder_list = ('/sendfiles', '/receivefiles', '/t1',
                   '/t3', '/rawkey', '/histos', '/finalkey')
    for i in folder_list:
        if os.path.exists(i):
            print('error')
        os.makedirs(dataroot + i)

    fifo_list = ('/msgin', '/msgout', '/rawevents',
                 '/t1logpipe', '/t2logpipe', '/cmdpipe', '/genlog',
                 '/transferlog', '/splicepipe', '/cntlogpipe',
                 '/eccmdpipe', '/ecspipe', '/ecrpipe', '/ecnotepipe',
                 '/ecquery', '/ecresp')
    for i in fifo_list:
        fifo_path = dataroot + i
        if os.path.exists(fifo_path):
            if stat.S_ISFIFO(os.stat(fifo_path).st_mode):
                os.unlink(fifo_path)
            else:
                os.remove(fifo_path)
        os.mkfifo(dataroot + i)
        os.open(dataroot + i, os.O_RDWR)


def _remove_stale_comm_files():
    files = glob.glob(dataroot + '/receivefiles/*')
    for f in files:
        os.remove(f)
    files = glob.glob(dataroot + '/sendfiles/*')
    for f in files:
        os.remove(f)



def msg_response(message):
    global low_count_side
    method_name = sys._getframe().f_code.co_name
    msg_split = message.split(':')[:]
    msg_code = msg_split[0]
    low_count_side = transferd.low_count_side

    if msg_code == 'st1':
        _remove_stale_comm_files()
        if low_count_side is None:
            print(f'[{method_name}:st1] Symmetry negotiation not completed yet. \
                Key generation was not started.')
            return
        elif low_count_side is True:
            chopper.start_chopper()
            splicer.start_splicer()
            _start_readevents()
        elif low_count_side is False:
            chopper2.start_chopper2()
            _start_readevents()
        transferd.send_message("st2")

    if msg_code == 'st2':
        _remove_stale_comm_files()
        if low_count_side is None:
            print(f'[{method_name}:st2] Symmetry negotiation not completed yet. \
                Key generation was not started.')
            return
        elif low_count_side is True:
            chopper.start_chopper()
            _start_readevents()
            splicer.start_splicer()
            transferd.send_message('st3')  # High count side starts pfind
        elif low_count_side is False:
            chopper2.start_chopper2()
            _start_readevents()
            periode_find()

    if msg_code == 'st3':
        if low_count_side is False:
            periode_find()
            return
        else:
            print(f'[{method_name}:st3] Not the high count side or symmetry \
                negotiation not completed.')


def periode_find():
    '''Starts pfind and costream

    '''
    method_name = sys._getframe().f_code.co_name
    global periode_count, t1logcount, AKF_buffer_order, prog_pfind, first_epoch, first_received_epoch

    if transferd.commhandle is None:
        print(f'[{method_name}] transferd process has not been started.' +
              ' periode_find aborted.')
        return
    if transferd.commhandle.poll() is not None:
        print(f'[{method_name}] transferd process was started but is not running. \
            periode_find aborted.')
        return

    while transferd.first_received_epoch is None or chopper2.first_epoch is None:
        print('waiting for more data')
        time.sleep(1)

    while chopper2.t1_epoch_count < periode_count:
        print(f'[{method_name}] Not enough epochs available to execute pfind.')
        time.sleep(1)



    print('!!!!', transferd.first_received_epoch, chopper2.first_epoch)
    # if chopper2.t1_epoch_count < periode_count:
    #     print(f'[{method_name}] Not enough epochs available to execute pfind.')
    # use_periods = periode_count - 2

    # delete this here later. this is for testing
    use_periods = 5
    first_epoch = transferd.first_received_epoch
    time.sleep(10)
    args = f'-d {cwd}/{dataroot}/receivefiles \
            -D {cwd}/{dataroot}/t1 \
            -e 0x{first_epoch} \
            -n {use_periods} -V 1 \
            -q {AKF_buffer_order}'

    with open(f'{cwd}/{dataroot}/pfinderror', 'a+') as f:
        proc_pfind = subprocess.Popen([prog_pfind, *args.split()],
                                      stderr=f,
                                      stdout=subprocess.PIPE)
    proc_pfind.wait()
    pfind_result = (proc_pfind.stdout.read()).decode()
    print(f'[{method_name}:pfind_result] {pfind_result}')


def _reader(file_name):
    fd = os.open(file_name, os.O_RDWR)
    f = os.fdopen(fd, 'r')  # non-blocking
    readers = select.select([f], [], [], 3)[0]
    for r in readers:
        if f == r:
            yield ((f.readline()).rstrip('\n')).lstrip('\x00')


def _writer(file_name, message):
    f = os.open(file_name, os.O_WRONLY)
    os.write(f, f'{message}\n'.encode())
    os.close(f)


def symmetry_negotiation():
    count_rate = measure_local_count_rate()
    send_message(f'ne1:{count_rate}')


def initiate_proto_negotiation():
    global wantprotocol, protocol
    protocol = 0  # disable protocol on asking
    sendmsg(f'pr1:{protocol}')


def start_raw_key_generation():
    global protocol
    method_name = sys._getframe().f_code.co_name
    
    if transferd.low_count_side is None:
        print(f'[{method_name}] Symmetry negotiation not finished.')
    else:
        transferd.send_message('st1')


def start_communication():
    _prepare_folders()
    _remove_stale_comm_files()
    transferd.start_communication(msg_response)

def stop_communication():
    transferd.stop_communication()
    chopper.stop_chopper()
    chopper2.stop_chopper2()
    splicer.stop_splicer()

# def symmetry_negotiation():
#     global low_count_side


def _start_readevents():
    '''
    Start reader and chopper on sender side (low-count side)
    '''
    method_name = sys._getframe().f_code.co_name  # used for logging
    global proc_readevents, prog_readevents
    args = f'-a 1 -R -A {extclockopt} -S 20 \
            -d {det1corr},{det2corr},{det3corr},{det4corr}'
    fd = os.open(f'{dataroot}/rawevents', os.O_RDWR)  # non-blocking
    f_stdout = os.fdopen(fd, 'w')  # non-blocking

    with open(f'{cwd}/{dataroot}/readeventserror', 'a+') as f_stderr:
        proc_readevents = subprocess.Popen((prog_readevents, *args.split()),
                                           stdout=f_stdout,
                                           stderr=f_stderr)
    print(f'[{method_name}] Started readevents.')


if __name__ == '__main__':
    start_communication()
    time.sleep(10)
    stop_communication()
    # kill_process(commhandle)
