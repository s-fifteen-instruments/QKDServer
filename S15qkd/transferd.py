#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
This modules is a wrapper of the transferd process.
Transferd is reponsible for the communication between the two partnering nodes in a QKD protocol.
It allows us to do messaging and file transfer.


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

from enum import Enum, auto, unique
import subprocess
import time

from .utils import Process
from .qkd_globals import logger, PipesQKD, FoldersQKD

# Almost guaranteed to be connected due to authd
# Removing state 'OFF' 
@unique
class CommunicationStatus(int, Enum):
    """Represents connection state to remote transferd.
    
    In practice, transferd connection status is almost guaranteed to be
    connected due to dropout mitigation by authd.

    Note:
        OFF status is deprecated since this is equivalent to the combination
        'is_running() == False' and 'communication_status == DISCONNECTED'.
    """
    DISCONNECTED = 0
    CONNECTED = 1

# Note this is very much tied to 'low_count_side' status.
class SymmetryNegotiationState(int, Enum):
    NOTDONE = 0
    PENDING = 1
    FINISHED = 2

class Transferd(Process):

    def __init__(self, program):
        super().__init__(program)
        self._reset()
    
    def _reset(self):
        self._communication_status = CommunicationStatus.DISCONNECTED
        self._low_count_side = None  # SST
        self._remote_count_rate = None
        self._local_count_rate = None
        self._first_received_epoch = None
        self._last_received_epoch = None
        self._negotiating = SymmetryNegotiationState.NOTDONE

    def start(
            self,
            callback_msgout=None,
            callback_localrate=None,  # to readevents measurement
            callback_restart=None,    # to restart keygen
        ):
        assert not self.is_running()
        if self.communication_status != CommunicationStatus.DISCONNECTED:
            return

        self._reset()
        self._callback_msgout = callback_msgout
        self._callback_localrate = callback_localrate
        
        args = [
            '-d', FoldersQKD.SENDFILES,
            '-c', PipesQKD.CMD,
            '-t', Process.config.local_authd_ip,
            '-D', FoldersQKD.RECEIVEFILES,
            '-l', PipesQKD.TRANSFERLOG,
            '-m', PipesQKD.MSGIN,
            '-M', PipesQKD.MSGOUT,
            '-p', Process.config.port_transd,
            '-k',
            '-e', PipesQKD.ECS,
            '-E', PipesQKD.ECR,
            # Non-existent IP to avoid port binding conflict with authd
            '-s', '127.0.0.2', 
        ]
        super().start(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, callback_restart=callback_restart)

        self.read(self.process.stdout, self.digest_stdout, wait=0.5, name="transferd.stdout", persist=True)
        self.read(self.process.stderr, self.digest_stderr, wait=0.5, name="transferd.stderr", persist=True)
        self.read(PipesQKD.MSGOUT, self.digest_msgout, wait=0.05, persist=True)
        self.read(PipesQKD.TRANSFERLOG, self.digest_transferlog, wait=0.1, persist=True)

        time.sleep(0.2)  # give some time to connect to the partnering computer

    
    def digest_stdout(self, pipe):
        for line in iter(pipe.readline, b''):
            line = line.rstrip()
            logger.info(f'[stdout] {line.decode()}')
            if line == b'connected.':
                self._communication_status = CommunicationStatus.CONNECTED
                logger.debug("[stdout] connected.")
            elif line == b'disconnected.':
                self._communication_status = CommunicationStatus.DISCONNECTED
                logger.debug("[stdout] disconnected.")
    
    def digest_stderr(self, pipe):
        for line in iter(pipe.readline, b''):
            logger.info(f'[stderr] {line.decode()}')
        
    def digest_transferlog(self, pipe):
        '''
        Digests the transferlog which is written by the transferd process.

        This function usually runs as a thread and watches the transferlog file. 
        If this is the low count side this function notifies the splicer about file arrival.
        '''
        # message = pipe.readline().decode().rstrip()
        message = pipe.readline().rstrip()
        if len(message) == 0:
            return
        
        self._last_received_epoch = message
        logger.debug(f'[read msg] {message}')
        if self._first_received_epoch == None:
            self._first_received_epoch = message
            logger.info(f'[first_rx_epoch] {self._first_received_epoch}')
        if self._low_count_side is True:
            Process.write(PipesQKD.SPLICER, message)
            logger.debug(f'Sent epoch name {message} to splicer.')

    def digest_msgout(self, pipe):
        # message = pipe.readline().decode().lstrip('\x00').rstrip('\n')
        message = pipe.readline().lstrip('\x00').rstrip('\n')
        if len(message) == 0:
            return
        
        logger.info(f'[received message] {message}')
        if message.split(':')[0] in {'ne1', 'ne2', 'ne3'}:
            self.negotiate_symmetry(message)
        else:
            self._callback_msgout(message)
    
    def negotiate_symmetry(self, message: str = ''):
        """Negotiates low/high-count sides with remote server.

        If no message (response) is supplied, symmetry negotiation is initiated
        instead.

        Args:
            message: Response from remote transferd (optional)
            callback_localrate: ...
        """
        assert self.is_connected()

        # Negotiation was done, skip
        if self._low_count_side is not None and self._negotiating == SymmetryNegotiationState.FINISHED:
            return

        # Initialize with local count rate
        if self._local_count_rate == None:
            self._local_count_rate = self._callback_localrate()
        
        # Sending out negotiation request
        if not message: # and self._negotiating != SymmetryNegotiationState.FINISHED:
            self.send(f'ne1:{self._local_count_rate}')
            self._negotiating = SymmetryNegotiationState.PENDING
            return

        # Crafting response to received negotiation messages
        (
            msg_code,
            reported_remote_rate,
            reported_local_rate,
            *_,
        ) = message.split(':') + [0]  # avoid IndexError when no remote reported
        reported_remote_rate = int(reported_remote_rate)
        reported_local_rate = int(reported_local_rate)
        
        # Reply to initial negotiation request
        # remote -> (local)
        if msg_code == 'ne1':
            self._remote_count_rate = reported_remote_rate
            self.send(f'ne2:{self._local_count_rate}:{reported_remote_rate}')

        # Reply to response from negotiation request
        # local -> remote -> (local)
        elif msg_code == 'ne2':
            self._remote_count_rate = reported_remote_rate
            if self._local_count_rate != reported_local_rate:
                logger.info(
                    '[ne2] Local count rates do not agree. '
                    'Symmetry negotiation failed.'
                )
                self._negotiating = SymmetryNegotiationState.NOTDONE
                return

            self.send(f'ne3:{self._local_count_rate}:{self._remote_count_rate}')
            if reported_local_rate <= reported_remote_rate:
                self._low_count_side = True
                logger.info('[ne2] This is the low count side.')
            else:
                self._low_count_side = False
                logger.info('[ne2] This the high count side.')
            self._negotiating = SymmetryNegotiationState.FINISHED
        
        # Positive confirmation for symmetry state, no response needed
        # remote -> local -> remote -> (local)
        elif msg_code == 'ne3':
            if self._local_count_rate != reported_local_rate \
                    and self._remote_count_rate != reported_remote_rate:
                logger.info(
                    '[ne3] Count rates in the messages do not agree. '
                    'Symmetry negotiation failed.'
                )
                self._negotiating = SymmetryNegotiationState.NOTDONE
                return

            if reported_local_rate < reported_remote_rate:
                self._low_count_side = True
                logger.info('[ne3] This is the low count side.')
            else:
                self._low_count_side = False
                logger.info('[ne3] This the high count side.')
            logger.info(f'[ne3] Symmetry negotiation succeeded.')
            self._negotiating = SymmetryNegotiationState.FINISHED

    def send(self, message: str):
        """Writes to MSGIN pipe, which is forwarded to remote."""
        Process.write(PipesQKD.MSGIN, message)
        logger.info(message)
        #time.sleep(1)

    def is_running(self):
        result = super().is_running()
        # Ported from digest_stdout, marking comms via termination:
        # effectively the same since marked only when is_running checked
        # TODO(Justin): Check if this is actually necessary
        if not result:
            self._communication_status = CommunicationStatus.DISCONNECTED
        return result
    
    def is_connected(self):
        """Returns True if transferd is running and connected.
        
        Note:
            Avoids exposing CommunicationStatus.
        """
        return self.is_running() \
            and self._communication_status == CommunicationStatus.CONNECTED


    @property
    def communication_status(self):
        return self._communication_status
    
    @property
    def low_count_side(self):
        return self._low_count_side
    
    @property
    def remote_count_rate(self):
        return self._remote_count_rate
    
    @property
    def local_count_rate(self):
        return self._local_count_rate
    
    @property
    def first_received_epoch(self):
        return self._first_received_epoch
    
    @property
    def last_received_epoch(self):
        return self._last_received_epoch
    
    @property
    def negotiating(self):
        return self._negotiating
