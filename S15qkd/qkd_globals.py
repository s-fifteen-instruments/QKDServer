#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
This modules contains functions and variables used by some of the process modules.


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
import sys
import stat
import os
import psutil
import glob
import logging
import logging.handlers
import time
import json
import shutil
import codecs
from enum import unique, Enum

EPOCH_DURATION = 2**32 / 8 * 1e-9

cwd = os.getcwd()
# root_name, _, _ = __name__.partition('.')
# root_module = sys.modules[root_name]
# MODULE_ROOT_DIR = os.path.dirname(root_module.__file__)


config_file = 'qkd_engine_config.json'
if not os.path.exists(config_file):
    dictionary = {
        "target_ip": "192.168.1.20",
        "data_root": "tmp/cryptostuff",
        "program_root": "bin/remotecrypto",
        "port_num": 4852,
        "identity": "Alice",
        "remote_coincidence_window": 16,
        "tracking_window": 30,
        "track_filter_time_constant": 2000000,
        "FFT_buffer_order": 23,
        "local_detector_skew_correction": {
            "det1corr": 0,
            "det2corr": 0,
            "det3corr": 0,
            "det4corr": 0
        },
        "max_event_time_pause": 20000,
        "autorestart_costream": True,
        "costream_general_log": True,
        "clock_source": "-e",
        "protocol": 1,
        "max_event_diff": 20000,
        "kill_option": "-k -K",
        "pfind_epochs": 5,
        "costream_histo_option": "",
        "costream_histo_number": 10,
        "error_correction_program_path": "bin/errorcorrection",
        "error_correction": True,
        "privacy_amplification": True,
        "errcd_killfile_option": True,
        "QBER_limit": 0.12,
        "default_QBER": 0.05,
        "minimal_block_size": 5000,
        "target_bit_error": 1e-09,
        "servo_blocks": 5,
        "do_polarization_compensation": False,
        "LCR_polarization_compensator_path": "/dev/serial/by-id/usb-Centre_for_Quantum_Technologies_Quad_LCD_driver_QLC-QO05-if00"
    }
    json_object = json.dumps(dictionary, indent=4)
    with open(config_file, "w") as outfile:
        outfile.write(json_object)

with open(config_file, 'r') as f:
    config = json.load(f)

data_root = config['data_root']
program_root = config['program_root']

testing = 0  # CHANGE to 0 if you want to run it with hardware
if testing == 1:
    # this outputs one timestamp file in an endless loop. This is for testing only.
    prog_readevents = '/' + \
        (__file__).strip('/controller.py') + \
        '/timestampsimulator/readevents_simulator.sh'
else:
    prog_readevents = program_root + '/readevents'


# Logging
class MyTimedRotatingFileHandler(logging.handlers.TimedRotatingFileHandler):
    ''' 
    copied from https://stackoverflow.com/questions/338450/timedrotatingfilehandler-changing-file-name
    '''
    timestamp_format = "%Y%m%d_%H%M%S"

    def __init__(self, dir_log: str = 'logs'):
        if os.path.exists(dir_log) is False:
            os.makedirs(dir_log)
        self.dir_log = dir_log
        # dir_log here MUST be with os.sep on the end
        filename = self.dir_log + "/" + \
            time.strftime(self.timestamp_format) + ".log"
        logging.handlers.TimedRotatingFileHandler.__init__(
            self, filename, when='midnight', interval=1,
            backupCount=0, encoding=None)

    def doRollover(self):
        """
        TimedRotatingFileHandler remix -
        rotates logs on daily basis, and filename of current logfile is
        time.strftime("%m%d%Y")+".txt".
        """
        self.stream.close()
        self.baseFilename = self.dir_log + '/' + \
            time.strftime(self.timestamp_format) + ".log"
        if self.encoding:
            self.stream = codecs.open(self.baseFilename, 'w', self.encoding)
        else:
            self.stream = open(self.baseFilename, 'w')
        self.rolloverAt = self.rolloverAt + self.interval





def kill_process_by_name(process_name: str):
    '''
    Get a list of running PIDs named like the given process_name
    '''
    list_of_process_objects = []
    # Iterate over the all the running process
    for proc in psutil.process_iter():
        try:
            pinfo = proc.as_dict(attrs=['pid', 'name', 'create_time'])
            # Check if process name contains the given name string.
            if process_name.lower() in pinfo['name'].lower():
                list_of_process_objects.append(pinfo)
                psutil.Process(pinfo['pid']).kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    return list_of_process_objects


def kill_existing_qcrypto_processes():
    process_list = [
        'transferd', 'chopper', 'chopper2',
        'splicer', 'costream', 'errcd', 'pfind',
        'getrate', 'readevents4a', 'readevents']
    for name in process_list:
        kill_process_by_name(name)


def kill_process(my_process):
    try:
        if my_process is not None:
            logger.info(f'Killing process: {my_process.pid}.')
            process = psutil.Process(my_process.pid)
            for proc in process.children(recursive=True):
                proc.kill()
            process.kill()
    except Exception as a:
        logger.warning(f'{a}.')


class PipesQKD(str, Enum):
    MSGIN = f'{cwd}/tmp/cryptostuff' + '/msgin'
    MSGOUT = f'{cwd}/tmp/cryptostuff' + '/msgout'
    RAWEVENTS = f'{cwd}/tmp/cryptostuff' + '/rawevents'
    T1LOG = f'{cwd}/tmp/cryptostuff' + '/t1logpipe'
    T2LOG = f'{cwd}/tmp/cryptostuff' + '/t2logpipe'
    CMD = f'{cwd}/tmp/cryptostuff' + '/cmdpipe'
    GENLOG = f'{cwd}/tmp/cryptostuff' + '/genlog'
    TRANSFERLOG = f'{cwd}/tmp/cryptostuff' + '/transferlog'
    SPLICER = f'{cwd}/tmp/cryptostuff' + '/splicepipe'
    CNTLOG = f'{cwd}/tmp/cryptostuff' + '/cntlogpipe'
    ECCMD = f'{cwd}/tmp/cryptostuff' + '/eccmdpipe'
    ECS =f'{cwd}/tmp/cryptostuff' + '/ecspipe'
    ECR = f'{cwd}/tmp/cryptostuff' + '/ecrpipe'
    ECNOTE = f'{cwd}/tmp/cryptostuff' + '/ecnotepipe'
    ECQUERY = f'{cwd}/tmp/cryptostuff' + '/ecquery'
    ECRESP = f'{cwd}/tmp/cryptostuff' + '/ecresp'

    @classmethod
    def prepare_pipes(cls):
        for pipe in cls:
            if os.path.exists(pipe):
                if stat.S_ISFIFO(os.stat(pipe).st_mode):
                    os.unlink(pipe)
                else:
                    os.remove(pipe)
            os.mkfifo(pipe)
            os.open(pipe, os.O_RDWR)

    @classmethod
    def drain_all_pipes(cls):
        for fn in cls:
            cls.drain_pipe(fn)

    @staticmethod
    def drain_pipe(pipe_name: str):
        fd = os.open(pipe_name, os.O_RDONLY | os.O_NONBLOCK)
        f = os.fdopen(fd, 'rb', 0)
        f.readall()


class FoldersQKD(str, Enum):
    DATAROOT = cwd + '/' + data_root
    SENDFILES = DATAROOT + '/sendfiles'
    RECEIVEFILES = DATAROOT + '/receivefiles'
    T1FILES = DATAROOT + '/t1'
    T3FILES = DATAROOT + '/t3'
    RAWKEYS = DATAROOT + '/rawkey'
    HISTOS = DATAROOT + '/histos'
    FINALKEYS = DATAROOT + '/finalkey'

    @classmethod
    def prepare_folders(cls):
        for folder in cls:
            if not os.path.exists(folder):
                os.makedirs(folder)

    @classmethod
    def remove_stale_comm_files(cls):
        for folder in [cls.RECEIVEFILES + '/*', cls.SENDFILES + '/*', cls.T1FILES + '/*', cls.T3FILES + '/*']:
            for f in glob.glob(data_root + folder):
                os.remove(f)


def writer(file_name: str, message: str):
    '''Writes message into file given by file_name.
    The write is in binary and ends with a newline.

    Arguments:
        file_name {str} -- Target file
        message {str} -- Message written into the file
    '''
    f = os.open(file_name, os.O_WRONLY)
    os.write(f, f'{message}\n'.encode())
    os.close(f)


@unique
class QKDProtocol(int, Enum):
    SERVICE = 0
    BBM92 = 1


logger = logging.getLogger("QKD logger")
logFormatter = logging.Formatter(
    "%(asctime)s | %(levelname)-5s | %(threadName)-10s | %(module)s | %(funcName)s | %(message)s")

fileHandler = MyTimedRotatingFileHandler('logs')
fileHandler.setFormatter(logFormatter)
consoleHandler = logging.StreamHandler(sys.stdout)
consoleHandler.setFormatter(logFormatter)

logger.addHandler(fileHandler)
logger.addHandler(consoleHandler)
logger.setLevel(logging.DEBUG)
