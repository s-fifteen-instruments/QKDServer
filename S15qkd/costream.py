#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
This module wraps the costream process.


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
import time
import threading
import json
import sys
import psutil

# Own modules
from . import qkd_globals
from .qkd_globals import logger


def _load_costream_config(config_file_name: str):
    '''
    Reads a JSON config file and stores the relevant information in
    global variables.

    Arguments:
        config_file_name {str} -- file name of the JSON formatted configuration file
    '''
    global data_root, program_root, kill_option, protocol
    global remote_coincidence_window, tracking_window, track_filter_time_constant
    global costream_histo_number, costream_histo_option, program_costream
    global config

    with open(config_file_name, 'r') as f:
        config = json.load(f)

    data_root = config['data_root']
    program_root = config['program_root']
    kill_option = config['kill_option']
    protocol = config['protocol']
    remote_coincidence_window = config['remote_coincidence_window']
    tracking_window = config['tracking_window']
    track_filter_time_constant = config['track_filter_time_constant']
    costream_histo_number = config['costream_histo_number']
    costream_histo_option = config['costream_histo_option']


def initialize(config_file_name: str = qkd_globals.config_file):
    global program_costream, proc_costream, cwd
    global latest_coincidences, latest_accidentals, latest_deltat, latest_sentevents
    global latest_compress, latest_rawevents, latest_outepoch
    _load_costream_config(config_file_name)
    program_costream = program_root + '/costream'
    proc_costream = None
    cwd = os.getcwd()
    latest_coincidences = costream_info[6]
    latest_accidentals = costream_info[5]
    latest_deltat = costream_info[4]
    latest_compress = costream_info[3]
    latest_sentevents = costream_info[2]
    latest_rawevents = costream_info[1]
    latest_outepoch = costream_info[0]


def start_costream(time_difference: int, begin_epoch: str):
    method_name = sys._getframe().f_code.co_name
    global proc_costream
    logger.info(f'[{method_name}] {begin_epoch}')
    args = f'-d {data_root}/receivefiles \
             -D {data_root}/t1 \
             -f {data_root}/rawkey \
             -F {data_root}/sendfiles \
             -e 0x{begin_epoch} \
             {kill_option} \
             -t {time_difference} \
             -p {protocol} \
             -T 2 \
             -m {data_root}/rawpacketindex \
             -M {data_root}/cmdpipe \
             -n {data_root}/genlog \
             -V 5 \
             -G 2 -w {remote_coincidence_window} \
             -u {tracking_window} \
             -Q {int(-track_filter_time_constant)} \
             -R 5 \
             {costream_histo_option} \
             -h {costream_histo_number}'

    with open(f'{cwd}/{data_root}/costreamerror', 'a+') as f:
        proc_costream = subprocess.Popen((program_costream, *args.split()),
                                            stdout=subprocess.PIPE, stderr=f)
    costream_thread = threading.Thread(target=_genlog_digest, args=())
    costream_thread.start()


def _genlog_digest():
    '''
    Digests the genlog pipe written by costream.
    '''
    global latest_coincidences, latest_accidentals, latest_deltat, latest_sentevents
    global latest_compress, latest_rawevents, latest_outepoch
    method_name = sys._getframe().f_code.co_name
    pipe_name = f'{data_root}/genlog'
    fd = os.open(pipe_name, os.O_RDONLY | os.O_NONBLOCK)
    f = os.fdopen(fd, 'rb', 0)  # non-blocking
    logger.info(f'[{method_name}] Thread started.')
    while is_running():
        time.sleep(0.1)
        try:
            message = (f.readline().decode().rstrip('\n')).lstrip('\x00')
            if len(message) != 0:
                logger.info(f'[{method_name}] {message}')
                costream_info = message.split()
                latest_coincidences = costream_info[6]
                latest_accidentals = costream_info[5]
                latest_deltat = costream_info[4]
                latest_compress = costream_info[3]
                latest_sentevents = costream_info[2]
                latest_rawevents = costream_info[1]
                latest_outepoch = costream_info[0]
        except OSError:
            pass
    logger.info(f'[{method_name}] Thread finished.')


def stop_costream():
    global proc_costream
    qkd_globals.kill_process(proc_costream)
    proc_costream = None


def is_running():
    return not (proc_costream is None or proc_costream.poll() is not None)

initialize()
