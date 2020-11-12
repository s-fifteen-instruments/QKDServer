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
from types import SimpleNamespace

from . import qkd_globals
from .qkd_globals import logger, PipesQKD, FoldersQKD


def start_chopper(qkd_protocol, config_file_name: str = qkd_globals.config_file):
    '''Starts the chopper process.

    Keyword Arguments:
        rawevents_pipe {str} -- The pipe it reads to acquire timestamps. (default: {'rawevents'})
    '''
    global proc_chopper
    with open(config_file_name, 'r') as f:
        config = json.load(f, object_hook=lambda d: SimpleNamespace(**d))
    prog_chopper = config.program_root + '/chopper'
    cwd = os.getcwd()
    proc_chopper = None
    t2logpipe_thread = threading.Thread(target=_t2logpipe_digest, args=())
    args = f'-i {PipesQKD.RAWEVENTS} \
             -D {FoldersQKD.SENDFILES} \
             -d {FoldersQKD.T3FILES} \
             -l {PipesQKD.T2LOG} \
             -V 4 -U -p {qkd_protocol} -Q 5 -F \
             -y 20 -m {config.max_event_diff}'

    t2logpipe_thread.start()
    with open(f'{cwd}/{config.data_root}/choppererror', 'a+') as f:
        proc_chopper = subprocess.Popen((prog_chopper, *args.split()),
                                        stdout=subprocess.PIPE,
                                        stderr=f)
    logger.info(f'Started chopper.')


def _t2logpipe_digest():
    '''Digests chopper activities.

    Watches t2logpipe for new epoch files and writes the epoch name into the transferd cmdpipe.
    Transferd copies the corresponding epoch file to the partnering computer.
    '''
    global t2logpipe_digest_thread_flag
    t2logpipe_digest_thread_flag = True
    fd = os.open(PipesQKD.T2LOG, os.O_RDONLY | os.O_NONBLOCK)
    f = os.fdopen(fd, 'rb', 0)  # non-blocking

    while t2logpipe_digest_thread_flag is True:
        time.sleep(0.1)
        try:
            message = (f.readline().decode().rstrip('\n')).lstrip('\x00')
            if len(message) == 0:
                continue
            epoch = message.split()[0]
            qkd_globals.writer(PipesQKD.CMD, epoch)
            logger.info(f'Msg: {message}')
        except OSError:
            pass
    logger.info(f'Thread finished')


def stop_chopper():
    global proc_chopper, t2logpipe_digest_thread_flag
    qkd_globals.kill_process(proc_chopper)
    proc_chopper = None
    t2logpipe_digest_thread_flag = False


def is_running():
    return not (proc_chopper is None or proc_chopper.poll() is not None)


if __name__ == '__main__':
    import time
    start_chopper(0)
    time.sleep(1)
    stop_chopper()
