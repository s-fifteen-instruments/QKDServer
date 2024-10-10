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
import codecs
import contextlib
from enum import unique, Enum, auto

EPOCH_DURATION = 2**32 / 8 * 1e-9

config_file = '/root/code/QKDServer/S15qkd/qkd_engine_config.json'

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





def kill_process_by_cmdline(process_name: str):
    '''
    Searches processes by cmdline arg and kills them.
    '''
    list_of_process_objects = []
    # Iterate over the all the running process
    for proc in psutil.process_iter():
        try:
            pinfo = proc.as_dict(attrs=['pid', 'name', 'create_time','cmdline'])
            # Check if process name contains the given name string.
            if any(process_name.lower() in ext.lower() for ext in pinfo['cmdline']):
                list_of_process_objects.append(pinfo)
                psutil.Process(pinfo['pid']).kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    return list_of_process_objects

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
        'fpfind', 'freqcd', 'freqservo',
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
    MSGIN = data_root + '/msgin'
    MSGOUT = data_root + '/msgout'
    RAWEVENTS = data_root + '/rawevents'
    T1LOG = data_root + '/t1logpipe'
    T2LOG = data_root + '/t2logpipe'
    CMD = data_root + '/cmdpipe'
    GENLOG = data_root + '/genlog'
    TRANSFERLOG = data_root + '/transferlog'
    SPLICER = data_root + '/splicepipe'
    PRESPLICER = data_root + '/presplicepipe'
    CNTLOG = data_root + '/cntlogpipe'
    ECCMD = data_root + '/eccmdpipe'
    ECS = data_root + '/ecspipe'
    ECR = data_root + '/ecrpipe'
    ECNOTE = data_root + '/ecnotepipe'
    ECQUERY = data_root + '/ecquery'
    ECRESP = data_root + '/ecresp'
    SB = data_root + '/SB'
    TEEIN = data_root + '/TEEIN'
    SBIN = data_root + '/SBIN'
    FRAWEVENTS = data_root + '/frawevents'  # freq corrected raw events
    FREQIN = data_root + '/freqin'  # pass freq correction to readevents.freqcd

    # NB: FoldersQKD.prepare_folders *must* be called prior to
    #     pipe initialization, which is done so in controller.start_communication
    ECNOTE_GUARDIAN = '/epoch_files/notify.pipe'

    @classmethod
    def prepare_pipes(cls):
        os.makedirs(data_root, exist_ok=True)
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

    @classmethod
    def flush_all_pipes(cls):
        for fn in cls:
            cls.flush_pipe(fn)

    @staticmethod
    def flush_pipe(pipe_name: str):
        fd = os.open(pipe_name, os.O_WRONLY | os.O_NONBLOCK)
        f = os.fdopen(fd, 'wb', 0)
        f.write("\n".encode())

    def __str__(self):
        """Allows implicit conversion to value.

        See mixin effect on str(v) vs f'{v}' [1].
        In particular, subclassing as class(str,Enum) allows certain
        libraries (e.g. os, f-strings), to interpret the enum member
        as a string directly, while the __str__ method allows implicit
        conversion of the enum to a string.

        [1]: https://docs.python.org/3/library/enum.html#others
        """
        return self.value


class FoldersQKD(str, Enum):
    DATAROOT = data_root
    SENDFILES = data_root + '/sendfiles'
    RECEIVEFILES = data_root + '/receivefiles'
    T1FILES = data_root + '/t1'
    T3FILES = data_root + '/t3'
    RAWKEYS = data_root + '/rawkey'
    HISTOS = data_root + '/histos'
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
                try:
                    os.remove(f)
                except FileNotFoundError:
                    logger.debug(f"File {f} removed by another process")

    def __str__(self):
        """See FoldersQKD.__str__ for documentation."""
        return self.value

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
    PEAK_FINDING = auto()
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
