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


def load_splicer_config(config_file_name: str):
    global dataroot, programroot, protocol, kill_option
    with open(config_file_name, 'r') as f:
        config = json.load(f)
    dataroot = config['data_root']
    protocol = config['protocol']
    programroot = config['program_root']
    kill_option = config['kill_option']


load_splicer_config('config/config.json')
cwd = os.getcwd()
proc_splicer = None
sleep_time = 0.3  # sleep time before next file read in threads
prog_splicer = programroot + '/splicer'


def _kill_process(my_process):
    if my_process is not None:
        method_name = sys._getframe().f_code.co_name
        print(f'[{method_name}] Killing process: {my_process.pid}.')
        process = psutil.Process(my_process.pid)
        for proc in process.children(recursive=True):
            proc.kill()
        process.kill()


def start_splicer(splicer_callback):
    '''
    Starts the splicer process and attaches a thread digesting 
    the splice pipe and the genlog.
    '''
    global dataroot, cwd, proc_splicer
    method_name = sys._getframe().f_code.co_name
    thread_splicepipe_digest = threading.Thread(target=splice_pipe_digest,
                                                args=([splicer_callback]))
    args = f'-d {cwd}/{dataroot}/t3 -D {dataroot}/receivefiles \
            -f {cwd}/{dataroot}/rawkey \
            -E {cwd}/{dataroot}/splicepipe \
            {kill_option} \
            -p {protocol} \
            -m {cwd}/{dataroot}/genlog'

    proc_splicer = subprocess.Popen([prog_splicer, *args.split()])
    time.sleep(0.1)
    print(f'[{method_name}] Started splicer process.')
    thread_splicepipe_digest.start()


def splice_pipe_digest(splicer_callback):
    '''
    Digests the text written into splicepipe and genlog.
    Runs until the splicer process closes.
    '''
    global dataroot, proc_splicer
    method_name = sys._getframe().f_code.co_name
    print(f'[{method_name}] Starting splice_pipe_digest thread.')
    splice_pipe =f'{dataroot}/splicepipe'
    genlog = f'{dataroot}/genlog'
    fd_sp = os.open(splice_pipe, os.O_RDONLY | os.O_NONBLOCK)  # non-blocking
    f_sp = os.fdopen(fd_sp, 'rb', 0)  # non-blocking
    fd_genlog = os.open(genlog, os.O_RDONLY | os.O_NONBLOCK)  # non-blocking
    f_genlog = os.fdopen(fd_genlog, 'rb', 0)  # non-blocking

    print(f'[{method_name}] Thread started.')
    while proc_splicer is not None and proc_splicer.poll() is None:
        time.sleep(sleep_time)
        if proc_splicer is None:
            break
        try:
            # read from genlog
            message = (f_genlog.readline().decode().rstrip('\n')).lstrip('\x00')
            if len(message) == 0:
                continue
            else:
                print(f'[{method_name}:genlog] {message}')
                splicer_callback(message)
            # read from splicepipe
            message = ((f_sp.readline()).rstrip('\n')).lstrip('\x00')
            if len(message) == 0:
                continue
            else:
                print(f'[{method_name}:splicepipe] {message}')
        except OSError as a:
            pass
    print(f'[{method_name}] Thread finished.')


def stop_splicer():
    global proc_splicer
    _kill_process(proc_splicer)
    proc_splicer = None

if __name__ == '__main__':
    start_splicer()
    time.sleep(2)
    kill_splicer_process()
