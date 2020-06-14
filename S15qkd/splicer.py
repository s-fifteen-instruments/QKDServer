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

from . import qkd_globals
from .qkd_globals import logger

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
    global cwd, proc_splicer, sleep_time
    _load_splicer_config(config_file_name)
    cwd = os.getcwd()
    proc_splicer = None
    sleep_time = 0.3  # sleep time before next file read in threads



def start_splicer(splicer_callback):
    '''
    Starts the splicer process and attaches a thread digesting 
    the splice pipe and the genlog.
    '''
    global data_root, cwd, proc_splicer
    method_name = sys._getframe().f_code.co_name
    thread_splicepipe_digest = threading.Thread(target=splice_pipe_digest,
                                                args=([splicer_callback]))
    args = f'-d {cwd}/{data_root}/t3 -D {data_root}/receivefiles \
            -f {cwd}/{data_root}/rawkey \
            -E {cwd}/{data_root}/splicepipe \
            {kill_option} \
            -p {protocol} \
            -m {cwd}/{data_root}/genlog'

    proc_splicer = subprocess.Popen([prog_splicer, *args.split()])
    time.sleep(0.1)
    logger.info(f'[{method_name}] Started splicer process.')
    thread_splicepipe_digest.start()


def splice_pipe_digest(splicer_callback):
    '''
    Digests the text written into splicepipe and genlog.
    Runs until the splicer process closes.
    '''
    global data_root, proc_splicer
    method_name = sys._getframe().f_code.co_name
    logger.info(f'[{method_name}] Starting splice_pipe_digest thread.')
    splice_pipe =f'{data_root}/splicepipe'
    genlog = f'{data_root}/genlog'
    fd_sp = os.open(splice_pipe, os.O_RDONLY | os.O_NONBLOCK)  # non-blocking
    f_sp = os.fdopen(fd_sp, 'rb', 0)  # non-blocking
    fd_genlog = os.open(genlog, os.O_RDONLY | os.O_NONBLOCK)  # non-blocking
    f_genlog = os.fdopen(fd_genlog, 'rb', 0)  # non-blocking

    logger.info(f'[{method_name}] Thread started.')
    while proc_splicer is not None and proc_splicer.poll() is None:
        time.sleep(sleep_time)
        if proc_splicer is None:
            break
        try:
            # read from genlog
            message = (f_genlog.readline().decode().rstrip('\n')).lstrip('\x00')
            if len(message) != 0:
                logger.info(f'[{method_name}:genlog] {message}')
                splicer_callback(message)
            # read from splicepipe
            message = ((f_sp.readline()).rstrip('\n')).lstrip('\x00')
            if len(message) != 0:
                logger.info(f'[{method_name}:splicepipe] {message}')
        except OSError as a:
            pass
    logger.info(f'[{method_name}] Thread finished.')


def stop_splicer():
    global proc_splicer
    qkd_globals.kill_process(proc_splicer)
    proc_splicer = None


initialize()

def main()
    start_splicer()
    time.sleep(2)
    kill_splicer_process()

if __name__ == '__main__':
    main()

