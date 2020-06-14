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
import os
import psutil
import glob
import logging
import logging.handlers
import time
import json
import shutil

root_name, _, _ = __name__.partition('.')
root_module = sys.modules[root_name]
MODULE_ROOT_DIR = os.path.dirname(root_module.__file__)

config_file = MODULE_ROOT_DIR + '/config/config.json'

with open(config_file, 'r') as f:
    config = json.load(f)

data_root = config['data_root']

# Logging
class MyTimedRotatingFileHandler(logging.handlers.TimedRotatingFileHandler):
    ''' copied from https://stackoverflow.com/questions/338450/timedrotatingfilehandler-changing-file-name
    '''
    timestamp_format = "%Y%d%m_%H%M%S"
    def __init__(self, dir_log: str='logs'):
        if os.path.exists(dir_log) is False:
            os.makedirs(dir_log)
        self.dir_log = dir_log
        # dir_log here MUST be with os.sep on the end
        filename = self.dir_log + "/" + time.strftime(self.timestamp_format) + ".log"
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
        self.baseFilename = self.dir_log + time.strftime(self.timestamp_format) + ".log"
        if self.encoding:
            self.stream = codecs.open(self.baseFilename, 'w', self.encoding)
        else:
            self.stream = open(self.baseFilename, 'w')
        self.rolloverAt = self.rolloverAt + self.interval



logger = logging.getLogger("QKD logger")
logFormatter = logging.Formatter(
    "%(asctime)s [%(threadName)-12.12s]  [%(module)s] [%(levelname)-5.5s]  %(message)s")

fileHandler = MyTimedRotatingFileHandler('logs')
fileHandler.setFormatter(logFormatter)
consoleHandler = logging.StreamHandler(sys.stdout)
consoleHandler.setFormatter(logFormatter)

logger.addHandler(fileHandler)
logger.addHandler(consoleHandler)
logger.setLevel(logging.DEBUG)





def kill_process(my_process):
    if my_process is not None:
        method_name = sys._getframe().f_code.co_name
        logger.info(f'[{method_name}] Killing process: {my_process.pid}.')
        process = psutil.Process(my_process.pid)
        for proc in process.children(recursive=True):
            proc.kill()
        process.kill()


def prepare_folders():
    # global data_root
    if os.path.exists(data_root):
        shutil.rmtree(data_root)
    folder_list = ('/sendfiles', '/receivefiles', '/t1',
                   '/t3', '/rawkey', '/histos', '/finalkey')
    for i in folder_list:
        if os.path.exists(i):
            print('error')
        os.makedirs(data_root + i)

    fifo_list = ('/msgin', '/msgout', '/rawevents',
                 '/t1logpipe', '/t2logpipe', '/cmdpipe', '/genlog',
                 '/transferlog', '/splicepipe', '/cntlogpipe',
                 '/eccmdpipe', '/ecspipe', '/ecrpipe', '/ecnotepipe',
                 '/ecquery', '/ecresp')
    for i in fifo_list:
        fifo_path = data_root + i
        if os.path.exists(fifo_path):
            if stat.S_ISFIFO(os.stat(fifo_path).st_mode):
                os.unlink(fifo_path)
            else:
                os.remove(fifo_path)
        os.mkfifo(data_root + i)
        os.open(data_root + i, os.O_RDWR)


def remove_stale_comm_files():
    files = glob.glob(data_root + '/receivefiles/*')
    for f in files:
        os.remove(f)
    files = glob.glob(data_root + '/sendfiles/*')
    for f in files:
        os.remove(f)


def writer(file_name: str, message: str):
    '''Writes message into file given by file_name.
    The write is in binary and ends with a newline.

    Arguments:
        file_name {str} -- Target file
        message {str} -- Message to write
    '''
    f = os.open(file_name, os.O_WRONLY)
    os.write(f, f'{message}\n'.encode())
    os.close(f)
