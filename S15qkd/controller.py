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

# Warning: Note that Flask will initialize the entire app twice if
# using Werkzeug hot reloader.

# Built-in/Generic Imports
import pathlib
import time
from typing import Optional

# Internal processes
from .transferd import Transferd, SymmetryNegotiationState
from .chopper import Chopper
from .chopper2 import Chopper2
from .costream import Costream
from .splicer import Splicer
from .readevents import Readevents
from .pfind import Pfind
from .utils import Process

# Own modules
from . import error_correction
from . import qkd_globals
from .qkd_globals import logger, QKDProtocol, QKDEngineState

# class ProcessWatchDog(threading.Thread):
#     '''Monitors all processes neccessary to generate QKD keys.

#     Basic logging of events and restart processes in case they crash.
#     '''

#     def __init__(self, log_file_name: str = 'process_watchdog.log'):
#         super(ProcessWatchDog, self).__init__()
#         self._running = True
#         self._logger = logging.getLogger('processes_watchdog')
#         self._logger.setLevel(logging.DEBUG)
#         self._fh = logging.FileHandler(log_file_name, mode="a+")
#         self._fh.setLevel(logging.DEBUG)
#         self._fh.setFormatter(logging.Formatter(
#             '%(asctime)s | %(process)d | %(levelname)s | %(module)s | %(message)s'))
#         self._logger.addHandler(self._fh)
#         self._logger.info('Initialized watchdog.')
#         # store process states to obsrver changes
#         self.prev_proc_states = get_process_states()
#         self.prev_status = get_status_info()
#         self._logger.info(self.prev_proc_states)

#     def terminate(self):
#         self._running = False

#     def run(self):
#         global proc_readevents
#         while self._running:
#             time.sleep(0.5)
#             proc_states = get_process_states()
#             status = get_status_info()
#             for key in proc_states:
#                 if self.prev_proc_states[key] != proc_states[key]:
#                     if proc_states[key]:
#                         self._logger.info(f'{key} started.')
#                     else:
#                         self._logger.info(f'{key} stopped.')
#             if status['connection_status'] == CommunicationStatus.DISCONNECTED and self.prev_status['connection_status'] == CommunicationStatus.CONNECTED:
#                 self._logger.info('Disconnected.')
#                 self._logger.info('Stopping all key generation processes')
#                 chopper.stop_chopper()
#                 chopper2.stop_chopper2()
#                 splicer.stop_splicer()
#                 costream.stop_costream()
#                 error_correction.stop_error_correction()
#                 qkd_globals.kill_process(proc_readevents)
#             self.prev_proc_states = proc_states
#             self.prev_status = status
#             self.crash_detection_and_restart(proc_states)

#     def crash_detection_and_restart(self, process_states):
#         '''
#         Checks if processes are running and restarts if any abnormalities are detected.
#         '''

#         if qkd_engine_state in [QKDEngineState.SERVICE_MODE, QKDEngineState.KEY_GENERATION]:
#             if process_states['transferd'] is False:
#                 self._logger.error(f'Transferd crashed. Trying to restart communication and key generation.')
#                 stop_key_gen()
#                 transferd.stop_communication()
#                 start_communication()
#                 time.sleep(1)
#                 logger.debug('I killed something')
#                 start_service_mode()
#                 return
#             if transferd.low_count_side is True:
#                 if False in [process_states['readevents'],
#                              process_states['chopper'],
#                              process_states['splicer']]:
#                     self._logger.error(f'Crash detected. Processes running: Readevents: {process_states["readevents"]} \
#                                    Chopper: {process_states["chopper"]} \
#                                    Splicer: {process_states["splicer"]}')
#                     stop_key_gen()
#                     start_service_mode()
#             elif transferd.low_count_side is False:
#                 if False in [process_states['readevents'],
#                              process_states['chopper2'],
#                              process_states['costream']]:
#                     self._logger.error(f"Crash detected. Processes running: readevents: {process_states['readevents']} \
#                                    chopper2: {process_states['chopper2']} \
#                                    costream: {process_states['costream']}")
#                     stop_key_gen()
#                     start_service_mode()

#         if qkd_engine_state == QKDEngineState.KEY_GENERATION:
#             if process_states['error_correction'] is False:
#                 self._logger.error(f'Error correction not started. stopping key gen')
#                 stop_key_gen()
#                 start_service_mode()


# TODO(Justin): Rename 'program_root' in config.

class Controller:
    """
    
    Note:
        Avoid using QKDEngineState for status checking - there is always a risk
        of it being out-of-sync with actual running processes. This should only
        be used to perform any callbacks by View/GUI for status updates.
    """

    def __init__(self):
        """
        
        Configuration currently held by Process, but may transit into a
        more appropriately named class. Avoid loading configuration here,
        to ensure single source of truth.
        """
        Process.load_config()
        dir_qcrypto = pathlib.Path(Process.config.program_root)

        self.readevents = Readevents(dir_qcrypto / 'readevents')
        self.transferd = Transferd(dir_qcrypto / 'transferd')
        self.chopper = Chopper(dir_qcrypto / 'chopper')
        self.chopper2 = Chopper2(dir_qcrypto / 'chopper2')
        self.costream = Costream(dir_qcrypto / 'costream')
        self.splicer = Splicer(dir_qcrypto / 'splicer')
        self.pfind = Pfind(dir_qcrypto / 'pfind')

        # Statuses
        self.qkd_engine_state = QKDEngineState.OFF
        self._reset()

        # Auto-initialization when server starts up
        self._establish_connection()



    # INITIALIZATION

    def _reset(self):
        """Resets variables used in controller."""
        self._first_epoch: Optional[str] = None
        self._time_diff: Optional[int] = None
        self._sig_long: Optional[int] = None
        self._sig_short: Optional[int] = None
        self._qkd_protocol = QKDProtocol.SERVICE  # TODO(Justin): Deprecate this field.
    
    def _establish_connection(self):
        """Establish classical communication channel via transferd.
        
        No actual communication is performed, only connecting to socket.
        """
        # Responsibility for upkeeping connection should lie with 'transferd'
        # i.e. 'transferd' should not drop out if connection established.
        if self.transferd.is_connected():
            return
        
        # MSGIN / MSGOUT pipes need to be ready prior to communication
        # TODO(Justin): Check if method below fails if pipes already initialized.
        self._initialize_pipes()
        self.transferd.start(
            self.callback_msgout,
            self.readevents.measure_local_count_rate,
        )
        
        # Verify connection status, timeout 10s
        num_checks = 10
        while not self.transferd.is_connected():
            time.sleep(1)
            num_checks -= 1
            if num_checks == 0:
                break
        else:
            self.qkd_engine_state = QKDEngineState.ONLY_COMMUNICATION
    
    def _initialize_pipes(self):
        """Prepares folders and pipes for connection.

        Note:
            Folders used are effectively pipes, but with property of being
            many-to-many and supports random access.
        """
        # TODO(Justin): Check if method below can fail if
        # the folders and pipes already exist.
        qkd_globals.FoldersQKD.prepare_folders()
        qkd_globals.PipesQKD.prepare_pipes()

    def requires_transferd(f):
        """Decorator to start transferd if not already running.
        
        Applicable to all instance methods.
        """
        def helper(self, *args, **kwargs):
            if not self.transferd.is_connected():
                self._establish_connection()
                if not self.transferd.is_connected():
                    logger.warning("transferd failed to establish connection.")
            return f(self, *args, **kwargs)
        return helper
        


    # MAIN CONTROL METHODS

    # TODO(Justin): Rename to 'stop' and update callback in QKD_status.py
    def stop_key_gen(self, inform_remote: bool = True):
        """Stops all processes locally and (best effort) remotely.
        
        Args:
            inform_remote: Whether stop command triggered locally.
        """
        if inform_remote:
            self._stop_key_gen_remote()

        # Stop own transferd to terminate all incoming instructions from remote,
        # since some commands may initiate certain processes to restart themselves
        self.transferd.stop()
        self.qkd_engine_state = QKDEngineState.OFF
        
        # Stop own processes (except transferd)
        self.readevents.stop()
        self.chopper.stop()
        self.chopper2.stop()
        self.costream.stop()
        self.splicer.stop()

        # Reset variables
        self._reset()
        
        # TODO(Justin): Refactor error correction and pipe creation
        error_correction.stop_error_correction()
        qkd_globals.PipesQKD.drain_all_pipes()
        qkd_globals.FoldersQKD.remove_stale_comm_files()

        # Restart transferd
        self._establish_connection()

    @requires_transferd
    def _stop_key_gen_remote(self):
        # Request remote server to stop operation / key generation
        if self.transferd.is_connected():
            self.send("stop")
            self.qkd_engine_state = QKDEngineState.ONLY_COMMUNICATION
        else:
            logger.warning("Could not communicate to remote server to request stop.")
            self.qkd_engine_state = QKDEngineState.OFF
        
    def start_service_mode(self):
        """Restarts service mode.
        
        Typically the starting point.
        """
        # Ensure all services are stopped
        self.stop_key_gen()
        
        # Initiate symmetry negotiation
        self._negotiate_symmetry()
        
        # Initiate SERVICE mode
        self.send("serv_st1")

    def _start_key_generation(self):
        """Restarts key generation mode.
        
        Typically this will be automatically called after SERVICE mode finishes
        polarization compensation - avoid calling this method directly, unless
        the polarization compensation already has known correction values.
        """
        # Ensure all services are stopped
        self.stop_key_gen()
        
        # Initiate symmetry negotiation
        self._negotiate_symmetry()
        
        # Initiate BBM92 mode
        self.send("st1")



    # CONTROL METHODS

    @requires_transferd
    def send(self, message: str):
        """Convenience method to forward messages to transferd."""
        return self.transferd.send(message)

    @requires_transferd
    def _negotiate_symmetry(self):
        """Forwards symmetry negotiation request to transferd and set low_count_side."""
        # TODO(Justin): Check if negotiation proceeds when symmetry previously negotiated.
        self.transferd.negotiate_symmetry()

        # Await response from transferd
        # Timeout borrowed from old code, repeated checking -> may block threads.
        timeout_seconds = 3
        end_time = time.time() + timeout_seconds
        while self.transferd.low_count_side is None:
            if time.time() > end_time:
                break

        # Log errors, optional
        negotiation_state = self.transferd.negotiating
        if negotiation_state == SymmetryNegotiationState.NOTDONE:
            logger.error("transferd failed to complete symmetry negotiation")
        elif negotiation_state == SymmetryNegotiationState.PENDING:
            logger.error("transferd timed out")

    @requires_transferd
    def callback_msgout(self, message: str) -> None:
        """Core of the server."""

        # Messages are of the format: '[CODE](:[PART])*'
        message_components = message.split(':')
        code = message_components[0]

        # Handle stopping of all processes
        if code == "stop":
            self.stop_key_gen(inform_remote=False)
            return

        # Do not set this as a global variable!
        # Single source of truth on transferd side (since we delegated transferd
        # to automate the symmetry negotiation process).
        low_count_side = self.transferd.low_count_side
        if low_count_side is None:
            logger.info(
                f"Code = {code}; "
                "Symmetry negotiation not complete - key generation not started."
            )

        # Possible messages are 'serv_st*' and 'st*'
        seq = code.split("_")[-1]  # sequence; retrieve 'st*' codes
        qkd_protocol = QKDProtocol.SERVICE if code.startswith("serv_") else QKDProtocol.BBM92
        prepend_if_service = lambda s: ("serv_"+s) if qkd_protocol == QKDProtocol.SERVICE else s
        self._qkd_protocol = qkd_protocol

        # SERVICE mode codes
        # Whole process flow should kick off with low count side sending '*st1' message
        # 'serv_st1' is equivalent to a 'START' command
        if seq == "st1":
            if low_count_side:
                # Reflect message back to remote
                self.transferd.send(prepend_if_service("st1"))
                return
            
            if qkd_protocol == QKDProtocol.BBM92:
                qkd_globals.FoldersQKD.remove_stale_comm_files()
            self.transferd.send(prepend_if_service("st2"))
            self.chopper2.start()
            self.readevents.start()
            
        if seq == "st2":
            if not low_count_side:
                logger.error(f"High count side should not have received: {code}")
                return
            
            # Old comment: Provision to send signals to timestamps. Not used currently.
            if qkd_protocol == QKDProtocol.BBM92:
                qkd_globals.FoldersQKD.remove_stale_comm_files()
            self.chopper.start(qkd_protocol)
            self.readevents.start()
            self.splicer.start(
                qkd_protocol,
                lambda msg: error_correction.ec_queue.put(msg),
            )

            # Important: 'st3' message is delayed so that both chopper and chopper2 can
            # generate sufficient initial epochs first.
            # TODO(Justin): Check if this assumption is really necessary.
            self.transferd.send(prepend_if_service("st3"))
                
        if seq == "st3":
            if low_count_side:
                logger.error(f"Low count side should not have received: {code}")
                return
            
            # try-except used here to short-circuit errors -> restart
            try:
                start_epoch, periods = self._retrieve_epoch_overlap()
                logger.debug(f"{start_epoch} {periods} {hex(int(start_epoch, 16) + periods)}")
                td, sl, ss = self.pfind.measure_time_diff(start_epoch, periods)
            except RuntimeError:
                if qkd_protocol == QKDProtocol.SERVICE:
                    self.start_service_mode()
                else:
                    self._start_key_generation()
                return

            # These variables should only be set here.
            self._first_epoch = start_epoch
            self._time_diff = td
            self._sig_long = sl
            self._sig_short = ss

            self.costream.start(
                td,
                start_epoch,
                qkd_protocol,
                self.start_service_mode if QKDProtocol.SERVICE else self._start_key_generation,
                self._start_key_generation,
            )
            if qkd_protocol == QKDProtocol.BBM92 and Process.config.error_correction:
                error_correction.start_error_correction()  # TODO

    @requires_transferd
    def _retrieve_epoch_overlap(self):
        """Calculate epoch overlap between local and remote servers.

        Performed by high count side.
        transferd (remote) and chopper2 (local) may have conflicting range of epochs,
        so resolving potential conflicts by calculating the epoch overlap.
        """
        target_num_epochs = Process.config.pfind_epochs
        timeout_seconds = (target_num_epochs + 2) * qkd_globals.EPOCH_DURATION
        end_time = time.time() + timeout_seconds

        # Wait for epochs
        while self.transferd.first_received_epoch is None \
                or self.chopper2.first_epoch is None \
                or self.chopper2.t1_epoch_count < target_num_epochs:
            if time.time() > end_time:
                if self.chopper2.t1_epoch_count < target_num_epochs:
                    logger.error(f"Insufficient epochs within {timeout_seconds}s")
                else:
                    logger.error("No data generated/received within {timeout_seconds}s")
                raise RuntimeError  # TODO(Justin): Subclass this...?
        
        # Find usable epoch periods
        remote_epoch = int(self.transferd.first_received_epoch, 16)
        local_epoch = int(self.chopper2.first_epoch, 16)

        if remote_epoch > local_epoch:
            start_epoch = self.transferd.first_received_epoch
            usable_periods = target_num_epochs - abs(remote_epoch-local_epoch)
        else:
            start_epoch = self.chopper2.first_epoch
            usable_periods = target_num_epochs
        
        # TODO(Justin): This was in the old code. Not sure why usable_periods are reduced.
        usable_periods -= 1
        return start_epoch, usable_periods

    def get_process_states(self):
        return {
            'transferd': self.transferd.is_running(),
            'readevents': self.readevents.is_running(),
            'chopper': self.chopper.is_running(),
            'chopper2': self.chopper2.is_running(),
            'costream': self.costream.is_running(),
            'splicer': self.splicer.is_running(),
            'error_correction': error_correction.is_running()
        }

    def get_status_info(self):
        return {
            'connection_status': self.transferd.communication_status,
            'state': self.qkd_engine_state,  # TODO(Justin): Possible to replace protocol?
            'last_received_epoch': self.transferd.last_received_epoch,
            'init_time_diff': self._time_diff,
            'sig_long': self._sig_long,
            'sig_short': self._sig_short,
            'tracked_time_diff': self.costream.latest_deltat,
            'symmetry': self.transferd.low_count_side,
            'coincidences': self.costream.latest_coincidences,
            'accidentals': self.costream.latest_accidentals,
            'protocol': self._qkd_protocol,
        }

    def get_error_corr_info(self):
        return {
            'first_epoch': error_correction.first_epoch_info,
            'undigested_epochs': error_correction.undigested_epochs_info,
            'ec_raw_bits': error_correction.ec_raw_bits,
            'ec_final_bits': error_correction.ec_final_bits,
            'ec_err_fraction': error_correction.ec_err_fraction,
            'key_file_name': error_correction.ec_epoch,
            'total_ec_key_bits': error_correction.total_ec_key_bits,
            'init_QBER': error_correction.init_QBER_info,
        }

    @property
    def sig_long(self) -> Optional[int]:
        return self._sig_long
    
    @property
    def sig_short(self) -> Optional[int]:
        return self._sig_short
    


Process.load_config()
identity = Process.config.identity
controller = Controller()

def start_service_mode():
    """Initiated by QKD controller via the QKD server status page."""
    controller.start_service_mode()  # passthrough

def stop_key_gen():
    """Initiated by QKD controller via the QKD server status page."""
    controller.stop_key_gen()

def get_status_info():
    return controller.get_status_info()

def get_process_states():
    return controller.get_process_states()

def get_error_corr_info():
    return controller.get_error_corr_info()

# initialize()
# watchdog = ProcessWatchDog()
# watchdog.daemon = True
# watchdog.start()
