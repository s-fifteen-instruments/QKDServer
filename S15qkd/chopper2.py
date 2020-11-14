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
from types import SimpleNamespace

from . import qkd_globals
from .qkd_globals import logger, PipesQKD, FoldersQKD

proc_chopper2 = None
first_epoch = None

def start_chopper2(config_file_name: str = qkd_globals.config_file):
    global proc_chopper2, first_epoch, t1logpipe_digest_thread_flag, t1_epoch_count
    
    with open(config_file_name, 'r') as f:
        config = json.load(f, object_hook=lambda d: SimpleNamespace(**d))
    cwd = os.getcwd()
    proc_chopper2 = None
    t1_epoch_count = 0
    t1logpipe_digest_thread_flag = False
    first_epoch = None
    prog_chopper2 = config.program_root + '/chopper2'

    args = f'-i {PipesQKD.RAWEVENTS} \
             -l {PipesQKD.T1LOG} -V 3 \
             -D {FoldersQKD.T1FILES} \
             -U -F -m {config.max_event_diff}'
    t1logpipe_thread = threading.Thread(
        target=_t1logpipe_digest, args=(), daemon=True)
    t1logpipe_thread.start()
    with open(f'{cwd}/{config.data_root}/chopper2error', 'a+') as f:
        proc_chopper2 = subprocess.Popen((prog_chopper2, *args.split()),
                                         stdout=subprocess.PIPE, stderr=f)
    logger.info('Started chopper2.')


def _t1logpipe_digest():
    '''
    Digest the t1log pipe written by chopper2.
    Chopper2 runs on the high-count side.
    Also counts the number of epochs recorded by chopper2.
    '''
    global t1logpipe_digest_thread_flag, t1_epoch_count, first_epoch
    t1_epoch_count = 0
    t1logpipe_digest_thread_flag = True

    while t1logpipe_digest_thread_flag is True:
        for message in _reader(PipesQKD.T1LOG):
            logger.debug(f'[read msg] {message}')
            if t1_epoch_count == 0:
                first_epoch = message.split()[0]
                logger.info(f'First_epoch: {first_epoch}')
            t1_epoch_count += 1
    logger.info(f'Thread finished.')


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


def is_running():
    return not (proc_chopper2 is None or proc_chopper2.poll() is not None)


if __name__ == '__main__':
    import time
    start_chopper2()
    time.sleep(5)
    stop_chopper2()
