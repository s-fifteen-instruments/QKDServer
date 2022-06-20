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
import contextlib
from enum import unique, Enum, auto

EPOCH_DURATION = 2**32 / 8 * 1e-9

cwd = os.getcwd()
# root_name, _, _ = __name__.partition('.')
# root_module = sys.modules[root_name]
# MODULE_ROOT_DIR = os.path.dirname(root_module.__file__)


config_file = 'qkd_engine_config.json'
if not os.path.exists(config_file):
    dictionary = {
        "target_hostname": "a.qkd.internal",
        "remote_cert": "authd.qkda.crt",
        "local_cert": "authd.qkdb.crt",
        "local_key": "authd.qkdb.key",
        "port_authd": 55555,
        "port_transd": 4855,
        "local_authd_ip": "b.qkd.internal",
        "data_root": "tmp/cryptostuff",
        "program_root": "bin/remotecrypto",
        "identity": "QKD-B (Pol Comp)",
        "remote_coincidence_window": 6,
        "tracking_window": 30,
        "track_filter_time_constant": 2000000,
        "FFT_buffer_order": 22,
        "local_detector_skew_correction": {
            "det1corr": 64,
            "det2corr": -78,
            "det3corr": -15,
            "det4corr": 0
        },
        "max_event_time_pause": 20000,
        "autorestart_costream": True,
        "costream_general_log": True,
        "clock_source": "-e",
        "protocol": 1,
        "max_event_diff": 20000,
        "kill_option": "-k -K",
        "pfind_epochs": 10,
        "costream_histo_option": "",
        "costream_histo_number": 10,
        "error_correction_program_path": "bin/errorcorrection",
        "error_correction": True,
        "privacy_amplification": True,
        "errcd_killfile_option": False,
        "QBER_limit": 0.11,
        "default_QBER": 0.07,
        "minimal_block_size": 5000,
        "target_bit_error": 1e-09,
        "servo_blocks": 5,
        "do_polarization_compensation": True,
        "LCR_polarization_compensator_path": "/dev/serial/by-id/usb-S-Fifteen_Instruments_Quad_LCD_driver_LCDD-001-if00"
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
    Searches processes by name and kills them.
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
        'getrate', 'readevents']
    for name in process_list:
        kill_process_by_name(name)


def kill_process(my_process):
    try:
        if my_process is not None:
            logger.debug(f'Killing process: {my_process.pid}.')
            process = psutil.Process(my_process.pid)
            for proc in process.children(recursive=True):
                proc.kill()
            process.kill()
    except Exception as a:
        logger.debug(f'{a}.')


class PipesQKD(str, Enum):
    MSGIN = f'/tmp/cryptostuff' + '/msgin'
    MSGOUT = f'/tmp/cryptostuff' + '/msgout'
    RAWEVENTS = f'/tmp/cryptostuff' + '/rawevents'
    T1LOG = f'/tmp/cryptostuff' + '/t1logpipe'
    T2LOG = f'/tmp/cryptostuff' + '/t2logpipe'
    CMD = f'/tmp/cryptostuff' + '/cmdpipe'
    GENLOG = f'/tmp/cryptostuff' + '/genlog'
    TRANSFERLOG = f'/tmp/cryptostuff' + '/transferlog'
    SPLICER = f'/tmp/cryptostuff' + '/splicepipe'
    CNTLOG = f'/tmp/cryptostuff' + '/cntlogpipe'
    ECCMD = f'/tmp/cryptostuff' + '/eccmdpipe'
    ECS =f'/tmp/cryptostuff' + '/ecspipe'
    ECR = f'/tmp/cryptostuff' + '/ecrpipe'
    ECNOTE = f'/tmp/cryptostuff' + '/ecnotepipe'
    ECQUERY = f'/tmp/cryptostuff' + '/ecquery'
    ECRESP = f'/tmp/cryptostuff' + '/ecresp'

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
    DATAROOT = '/' + data_root
    SENDFILES = DATAROOT + '/sendfiles'
    RECEIVEFILES = DATAROOT + '/receivefiles'
    T1FILES = DATAROOT + '/t1'
    T3FILES = DATAROOT + '/t3'
    RAWKEYS = DATAROOT + '/rawkey'
    HISTOS = DATAROOT + '/histos'
    FINALKEYS = '/epoch_files'

    @classmethod
    def prepare_folders(cls):
        for folder in cls:
            if not os.path.exists(folder):
                os.makedirs(folder)
        cls.remove_stale_comm_files()

    @classmethod
    def remove_stale_comm_files(cls):
        for folder in [cls.RECEIVEFILES + '/*', cls.SENDFILES + '/*', cls.T1FILES + '/*', cls.T3FILES + '/*']:
            for f in glob.glob(folder):
                os.remove(f)

@contextlib.contextmanager
def my_open(file_name: str):
     fd = os.open(file_name, os.O_WRONLY)
     try:
         yield fd
     finally:
         os.close(fd)


def writer(file_name: str, message: str):
    '''Writes message into file given by file_name.
    The write is in binary and ends with a newline.

    Arguments:
        file_name {str} -- Target file
        message {str} -- Message written into the file
    '''
    with my_open(file_name) as f:
        os.write(f, f'{message}\n'.encode())


@unique
class QKDProtocol(int, Enum):
    SERVICE = 0
    BBM92 = 1


@unique
class QKDEngineState(Enum):
    SERVICE_MODE = auto()
    KEY_GENERATION = auto()
    ONLY_COMMUNICATION = auto()
    OFF = auto()
    # TRANSITIONING_TO_KEY_GENERATION = auto()
    

logger = logging.getLogger("QKD logger")
logger.setLevel(logging.DEBUG)
logFormatter = logging.Formatter(
    "%(asctime)s | %(levelname)-5s | %(threadName)-10s | %(module)s | %(funcName)s | %(message)s")

fileHandler = MyTimedRotatingFileHandler('logs')
fileHandler.setFormatter(logFormatter)
fileHandler.setLevel(logging.DEBUG)
consoleHandler = logging.StreamHandler(sys.stdout)
consoleHandler.setFormatter(logFormatter)
consoleHandler.setLevel(logging.DEBUG)

logger.addHandler(fileHandler)
logger.addHandler(consoleHandler)
