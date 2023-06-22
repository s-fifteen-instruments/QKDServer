#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
This module wraps the error correction process and attaches readers to the process pipes.

The code for the error correction process can be found under: 
https://github.com/kurtsiefer/qcrypto/tree/master/errorcorrection

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

import threading
import struct
import time
import queue
import collections
from statistics import mean

# from . import qkd_globals, controller
from .utils import Process, read_T3_header, HeadT3, epoch_after
from .qkd_globals import logger, PipesQKD, FoldersQKD, QKDEngineState

EPOCH_DURATION = 0.536  # seconds

proc_error_correction = None

class ErrorCorr(Process):

    _total_ec_key_bits = None
    _ec_err_fraction_history = collections.deque(maxlen=100)
    _ec_err_key_length_history = collections.deque(maxlen=100)

    @property
    def total_ec_key_bits(self):
        return type(self)._total_ec_key_bits

    @total_ec_key_bits.setter
    def total_ec_key_bits(self,val):
        type(self)._total_ec_key_bits = val

    def __init__(self, process):
        super().__init__(process)
        self._reset()
        #self.do_errc = Process(self.do_error_correction)

    def _reset(self):
        self._first_epoch_info = None
        self._undigested_epochs_info = None
        self._init_QBER_info = None
        self._ec_raw_bits = None
        self._ec_final_bits = None
        self._ec_err_fraction = None
        self._ec_epoch = None
        self._ec_key_gen_rate = None
        self._ec_nr_of_epochs = None
        self._ec_thread_on = None
        self.ec_queue = queue.Queue()

        self._servoed_QBER = Process.config.default_QBER
        self._servo_blocks = Process.config.servo_blocks
        self.QBER_limit = Process.config.QBER_limit
        self.QBER_servo_history = collections.deque(maxlen=self._servo_blocks)

    def empty(self):
        if self.do_ec_thread.is_alive():
            self._ec_thread_on = False
            time.sleep(EPOCH_DURATION)
            self._servoed_QBER = Process.config.default_QBER
        self.do_ec_thread = threading.Thread(target=self.do_error_correction, args=(), daemon=True, name="errcd")
        self._ec_thread_on = True
        self.do_ec_thread.start()

    def start(
            self,
            callback_guardian_note = None,
            callback_restart = None,
            callback_qber_exceed = None,
            callback_pol_comp_qber = None, #Note: For passive polarization compensation, not implemented yet.
        ):
        """

        If 'remote_connection_id' is supplied in the global configuration file, then the notification
        pipe will automatically append remote connection ID as well as (an alternating) direction to
        switch between the bidirectional tables where the keys will be inserted. Resolution for which
        table inserts the first key is performed by determining the output of the string comparison
        "'local_connection_id' < 'remote_connection_id'".

        Note:
            The remote connection id is cached upon starting error correction, to avoid
            race condition when configuration reload is triggered while errcd is still
            running. If no remote connection id is available, the notification pipe format
            will follow the original specification, i.e. newline-delimited epoch filenames.
        """
        assert not self.is_running()
        self._reset()

        self.read(PipesQKD.ECNOTE, self.ecnotepipe_digest, 'ECNOTE', persist=True)
        self._callback_guardian_note = callback_guardian_note
        self._callback_pol_comp = callback_pol_comp_qber
        self._callback_restart = callback_restart
        self._callback_qber_exceed = callback_qber_exceed
        self.remote_connection_id = getattr(Process.config, "remote_connection_id", None)
        local_connection_id = getattr(Process.config, "local_connection_id", "")
        self.key_direction = int(local_connection_id < self.remote_connection_id)  # {0, 1}

        args = [
            '-c', PipesQKD.ECCMD,
            '-s', PipesQKD.ECS,
            '-r', PipesQKD.ECR,
            '-d', FoldersQKD.RAWKEYS,
            '-f', FoldersQKD.FINALKEYS,
            '-l', PipesQKD.ECNOTE,
            '-Q', PipesQKD.ECQUERY,
            '-q', PipesQKD.ECRESP,
            '-V 2',
            '-T 1', #Handling behaviour ignore errors on wrong packets
            Process.config.errcd_killfile_option, # Remove used rawkeys
            Process.config.privacy_amplification # For switching off pa.
        ]
        super().start(args, stdout='errcd_stdout', stderr='errcd_stderr', callback_restart=callback_restart)
        self.do_ec_thread = threading.Thread(target=self.do_error_correction, args=(), daemon=True, name="errcd")
        self._ec_thread_on = True
        self.do_ec_thread.start()
        # To move to class
        # self.do_errc.start_py_thread()

    def ecnotepipe_digest(self, pipe):
        '''
        Digests error correction activities indicated by the 'ecnotepipe' pipe.
        This is getting input from the ec_note_pipe which is updated after an error correction run.
        '''
        message = pipe.readline().rstrip('\n').lstrip('\x00')
        if len(message) == 0:
            return

        # ECNOTE message intercepted to populate results on web interface
        logger.debug(f'[ecnote] {message}')
        (
            self._ec_epoch,
            self._ec_raw_bits,
            self._ec_final_bits,
            self._ec_err_fraction,
            self._ec_nr_of_epochs,
            *_,
        ) = message.split()

        if self.ec_final_bits > 0:
            if self.remote_connection_id is not None:
                notification = f"{self._ec_epoch} {self.remote_connection_id} {self.key_direction}"
            else:
                notification = self._ec_epoch
            self.write(self._callback_guardian_note, message=notification)
            with open("/epoch_files/notified", "a+") as file:
                file.write(f"{notification}\n")
            logger.info(f'Sent {notification} to notify.pipe.')

            # Flip key direction
            self.key_direction = 1 - self.key_direction

        self._ec_key_gen_rate = self.ec_final_bits / (self.ec_nr_of_epochs * EPOCH_DURATION)
        logger.debug(f'Rate is {self.ec_key_gen_rate} bps.')
        if not self.total_ec_key_bits:
            self.total_ec_key_bits = 0
        self.total_ec_key_bits += self.ec_final_bits
        type(self)._ec_err_fraction_history.append(self.ec_err_fraction)
        type(self)._ec_err_key_length_history.append(self.ec_final_bits)
        self.QBER_servo_history.append(self.ec_err_fraction)
        self._servoed_QBER = mean(self.QBER_servo_history)
        logger.debug(f'Servoed QBER is {self.servoed_QBER}.')
        ###
        # servoing QBER
        if self.servoed_QBER < 0.005:
            self._servoed_QBER = 0.005
        elif self.servoed_QBER > 1 or self.servoed_QBER < 0:
            self._servoed_QBER = Process.config.default_QBER
        elif self._callback_qber_exceed and self.ec_err_fraction > 0.15: #if more than 15% restart immediately and don't need to average over self._servo_blocks.
            logger.error(f'QBER: {self.ec_err_fraction} above {0.15}. Restarting polarization compensation.')
            self._servoed_QBER = self.ec_err_fraction
            self.QBER_servo_history.clear()
            self._callback_qber_exceed()
        elif self._callback_qber_exceed and self.servoed_QBER > self.QBER_limit:
            logger.error(f'QBER: {self.servoed_QBER} above {self.QBER_limit}. Restarting polarization compensation.')
            self.QBER_servo_history.clear()
            self._callback_qber_exceed()
        else:
            self._callback_pol_comp(qber=self.ec_err_fraction,epoch=epoch_after(self._ec_epoch,int(self._ec_nr_of_epochs,10)))

        try:
            1+1
        except OSError:
            pass
        except Exception as a:
            logger.error(a)
        logger.info(f'Thread finished')

    def do_error_correction(self):
        '''
        Executes error correction based on the files in the ec_queue.
        The queue consists of raw key file names generated by costream or splicer.
        This function usually runs as a thread waiting for pipe input.

        This function checks each file for the number of bits and once enough bits are available
        it notifies the error correction process by writing into the eccmdpipe.
        '''
        undigested_raw_bits = 0
        first_epoch = ''
        undigested_epochs = 0
        

        while self.is_running() and self._ec_thread_on :
            # Attempt get from queue (FIFO). If no item is available, sleep a while
            # and try again.
            try:
                file_name = self.ec_queue.get_nowait()
            except queue.Empty:
                time.sleep(EPOCH_DURATION)
                continue

            logger.debug(f'Attempting to send file_name = {file_name}')
            file_path = f'{FoldersQKD.RAWKEYS}/{file_name}'
            headt3 = HeadT3(0,0,0,0) # tag,epoch(int),length_entry,bits_per_entry
            headt3 = read_T3_header(file_path)
            if (headt3.bits_per_entry != 1):
                logger.warning(f'Entry in rawkey consists of more than 1 bit per entry. Discarding epoch')
                continue
            if undigested_epochs == 0:
                first_epoch = file_name
                logger.debug(f'First epoch is {first_epoch}')
            undigested_epochs += 1
            undigested_raw_bits += headt3.length_entry
            # Execute error correction when enough raw bits are accumulated.
            # Could be also based on number of epochs.
            if undigested_raw_bits > Process.config.minimal_block_size:
                if undigested_epochs % 2 == 1 : # Take odd number of epochs
                # notify the error correction process about the first epoch, number of epochs, and the servoed QBER
                    self.write(
                        PipesQKD.ECCMD, f'0x{first_epoch} {undigested_epochs} {float("{0:.4f}".format(self.servoed_QBER))}')
                    logger.info(
                        f'Started error correction for {undigested_epochs} epochs starting with epoch {first_epoch}.')
                    self._first_epoch_info = first_epoch
                    self._undigested_epochs_info = undigested_epochs
                    self._init_QBER_info = self.servoed_QBER
                    undigested_raw_bits = 0
                    undigested_epochs = 0
            else:
                logger.debug(
                    f'Undigested raw bits:{undigested_raw_bits}. Undigested epochs: {undigested_epochs}.')
            
            self.ec_queue.task_done()

        logger.info(f'Thread finished.')

    @property
    def ec_final_bits(self):
        return int(self._ec_final_bits)

    @property
    def ec_raw_bits(self):
        return int(self._ec_raw_bits)
    
    @property
    def ec_key_gen_rate(self):
        return round(self._ec_key_gen_rate, 2)

    @property
    def ec_nr_of_epochs(self):
        return int(self._ec_nr_of_epochs)

    @property
    def ec_err_fraction(self):
        return float(self._ec_err_fraction)

    @property
    def servoed_QBER(self):
        return self._servoed_QBER

    @property
    def init_QBER_info(self):
        return self._init_QBER_info
