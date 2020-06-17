#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
This module wraps the chopper process and attaches readers to the process pipes.


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

from . import qkd_globals
from .qkd_globals import logger


def _load_chopper_config(config_file_name: str):
    '''Loads configuration from config file
    '''
    global dataroot, protocol, kill_option, config, prog_chopper, programroot, max_event_diff
    global prog_chopper
    with open(config_file_name, 'r') as f:
        config = json.load(f)
    dataroot = config['data_root']
    protocol = config['protocol']
    max_event_diff = config['max_event_diff']
    programroot = config['program_root']
    prog_chopper = programroot + '/chopper'


def initialize(config_file_name: str = qkd_globals.config_file):
    '''Initializes all variables necessary to run the chopper
    
    Keyword Arguments:
        config_file_name {str} -- config file to read from (default: {'config/config.json'})
    '''
    global cwd, proc_chopper
    _load_chopper_config(config_file_name)
    cwd = os.getcwd()
    proc_chopper = None


initialize()


def start_chopper(
        rawevents_pipe: str='rawevents',
        sendfiles_folder: str='sendfiles',
        t3_files_folder: str='t3',
        t2_log_pipe: str='t2logpipe'):
    '''Starts the chopper process.

    Keyword Arguments:
        rawevents_pipe {str} -- The pipe it reads to acquire timestamps. (default: {'rawevents'})
    '''
    global proc_chopper, protocol, max_event_diff
    method_name = sys._getframe().f_code.co_name  # used for logging
    t2logpipe_thread = threading.Thread(target=_t2logpipe_digest, args=())
    args = f'-i {cwd}/{dataroot}/{rawevents_pipe} \
            -D {cwd}/{dataroot}/{sendfiles_folder} \
            -d {cwd}/{dataroot}/{t3_files_folder} \
            -l {cwd}/{dataroot}/{t2_log_pipe} \
            -V 4 -U -p {protocol} -Q 5 -F \
            -y 20 -m {max_event_diff}'

    t2logpipe_thread.start()
    with open(f'{cwd}/{dataroot}/choppererror', 'a+') as f:
        proc_chopper = subprocess.Popen((prog_chopper, *args.split()),
                                        stdout=subprocess.PIPE,
                                        stderr=f)
    logger.info(f'[{method_name}] Started chopper.')


def _t2logpipe_digest():
    '''Digests chopper activities.

    Watches t2logpipe for new epoch files and writes the epoch name into the transferd cmdpipe.
    Transferd copies the corresponding epoch-file to the partnering computer.
    '''
    global t2logpipe_digest_thread_flag
    method_name = sys._getframe().f_code.co_name
    t2logpipe_digest_thread_flag = True
    pipe_name = f'{dataroot}/t2logpipe'
    fd = os.open(pipe_name, os.O_RDONLY | os.O_NONBLOCK)
    f = os.fdopen(fd, 'rb', 0)  # non-blocking
    cmd_pipe_name = f'{dataroot}/cmdpipe'

    while t2logpipe_digest_thread_flag is True:
        time.sleep(0.1)
        try:
            message = (f.readline().decode().rstrip('\n')).lstrip('\x00')
            if len(message) == 0:
                continue
            epoch = message.split()[0]
            qkd_globals.writer(cmd_pipe_name, epoch)
            logger.info(f'[{method_name}] {message}')
        except OSError as a:
            pass
    logger.info(f'[{method_name}] Thread finished')


def stop_chopper():
    global proc_chopper, t2logpipe_digest_thread_flag
    qkd_globals.kill_process(proc_chopper)
    proc_chopper = None
    t2logpipe_digest_thread_flag = False


def is_running():
    return not (proc_chopper is None or proc_chopper.poll() is not None)

# def _writer(file_name: str, message: str):
#     f = os.open(file_name, os.O_WRONLY)
#     os.write(f, f'{message}\n'.encode())
#     os.close(f)

if __name__ == '__main__':
    import time
    start_chopper()
    time.sleep(1)
    stop_chopper()
