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

from .utils import Process
from .qkd_globals import logger, PipesQKD, FoldersQKD, config_file

class Chopper2(Process):

    def __init__(self, program):
        super().__init__(program)
        self._t1_epoch_count = 0
        self._first_epoch = None
    
    def start(self):
        assert not self.is_running()
        
        self.read(PipesQKD.T1LOG, self.digest_t1logpipe, 'T1LOG')

        args = [
            '-i', PipesQKD.RAWEVENTS,
            '-D', FoldersQKD.T1FILES,
            '-l', PipesQKD.T1LOG,
            '-V', 3,
            '-U',
            '-F',
            '-m', Process.config.max_event_diff,
        ]
        super().start(args, stderr="chopper2error")
        logger.info('Started chopper2.')

    def digest_t1logpipe(self, pipe):
        """Digest the t1log pipe written by chopper2.

        Chopper2 runs on the high-count side.
        Also counts the number of epochs recorded by chopper2.
        """
        message = pipe.readline().decode().rstrip('\n').lstrip('\x00')
        if len(message) == 0:
            return
        
        logger.debug(f'[read msg] {message}')
        if self._t1_epoch_count == 0:
            self._first_epoch = message.split()[0]
            logger.info(f'First_epoch: {self._first_epoch}')
        self._t1_epoch_count += 1

    @property
    def t1_epoch_count(self):
        return self._t1_epoch_count

    @property
    def first_epoch(self):
        return self._first_epoch


# Wrapper
Process.load_config()
chopper2 = Chopper2(Process.config.program_root + '/chopper2')

# Original interface
proc_chopper2 = None
first_epoch = None
t1_epoch_count = 0

def start_chopper2(config_file_name: str = config_file):
    global proc_chopper2, first_epoch, t1_epoch_count
    Process.load_config(config_file_name)
    chopper2.start()
    proc_chopper2 = chopper2.process

def stop_chopper2():
    global proc_chopper2
    chopper2.stop()
    proc_chopper2 = None

def is_running():
    return chopper2.is_running()
