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

# Built-in/Generic Imports
import json
import subprocess
import os
import threading
import sys
import psutil
import select

from . import qkd_globals
from .qkd_globals import logger

def _load_chopper2_config(config_file_name: str):
    '''
    Reads a JSON config file and stores the relevant information in
    global variables.

    Arguments:
        config_file_name {str} -- file name of the JSON formatted configuration file
    '''
    global dataroot, programroot, max_event_diff, prog_chopper2
    with open(config_file_name, 'r') as f:
        config = json.load(f)
    dataroot = config['data_root']
    max_event_diff = config['max_event_diff']
    programroot = config['program_root']
    prog_chopper2 = programroot + '/chopper2'


def initialize(config_file_name: str = qkd_globals.config_file):
    global cwd, proc_chopper2, t1_epoch_count, t1logpipe_digest_thread_flag
    global first_epoch
    _load_chopper2_config(config_file_name)
    cwd = os.getcwd()
    proc_chopper2 = None
    t1_epoch_count = 0
    t1logpipe_digest_thread_flag = False
    first_epoch = None


def start_chopper2(rawevents_pipe: str='rawevents', t1_log_pipe: str='t1logpipe', t1_file_folder: str='t1'):
    global proc_chopper2, max_event_diff
    method_name = sys._getframe().f_code.co_name
    args = f'-i {cwd}/{dataroot}/{rawevents_pipe} \
            -l {cwd}/{dataroot}/{t1_log_pipe} -V 3 \
            -D {cwd}/{dataroot}/{t1_file_folder} \
            -U -F -m {max_event_diff}'
    t1logpipe_thread = threading.Thread(target=_t1logpipe_digest, args=(), daemon=True)
    t1logpipe_thread.start()
    with open(f'{cwd}/{dataroot}/chopper2error', 'a+') as f:
        proc_chopper2 = subprocess.Popen((prog_chopper2, *args.split()),
                                         stdout=subprocess.PIPE, stderr=f)
    logger.info(f'[{method_name}] Started chopper2.')


def _t1logpipe_digest():
    '''
    Digest the t1log pipe written by chopper2.
    Chopper2 runs on the high-count side.
    Also counts the number of epochs recorded by chopper2.
    '''
    global t1logpipe_digest_thread_flag, t1_epoch_count, first_epoch
    method_name = sys._getframe().f_code.co_name
    t1_epoch_count = 0
    t1logpipe_digest_thread_flag = True
    pipe_name = f'{dataroot}/t1logpipe'

    while t1logpipe_digest_thread_flag is True:
        for message in _reader(pipe_name):
            logger.info(f'[{method_name}:read] {message}')
            if t1_epoch_count == 0:
                first_epoch = message.split()[0]
                logger.info(f'[{method_name}:first_epoch] {first_epoch}')
            t1_epoch_count += 1
    logger.info(f'[{method_name}] Thread finished.')


def stop_chopper2():
    global proc_chopper2, t1logpipe_digest_thread_flag
    qkd_globals.kill_process(proc_chopper2)
    proc_chopper2 = None
    t1logpipe_digest_thread_flag = False


def _reader(file_name: str):
    fd = os.open(file_name, os.O_RDWR)
    f = os.fdopen(fd, 'r')  # non-blocking
    readers = select.select([f], [], [], 3)[0]
    for r in readers:
        if f == r:
            yield ((f.readline()).rstrip('\n')).lstrip('\x00')

initialize()

if __name__ == '__main__':
    import time
    start_chopper2()
    time.sleep(5)
    kill_chopper2_process()
