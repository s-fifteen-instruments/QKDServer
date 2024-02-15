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
import threading
import time
from typing import Optional
from types import SimpleNamespace

# Internal processes
from .transferd import Transferd, SymmetryNegotiationState
from .chopper import Chopper
from .chopper2 import Chopper2
from .costream import Costream
from .splicer import Splicer
from .readevents import Readevents
from .pfind import Pfind
from .utils import Process, read_T2_header, HeadT2, get_current_epoch
from .error_correction import ErrorCorr
from .polarization_compensation import PolComp

# Own modules
from . import qkd_globals
from .qkd_globals import logger, QKDProtocol, QKDEngineState, FoldersQKD

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

        # TODO:
        #   Short-term: Add 'S15qkd' directory to configuration and call authd.py
        #     relative to imported directory, just like 'dir_qcrypto' above.
        #   Long-term: Subclass 'authd' as a Process, to use the same logging
        #     mechanisms.
        self.authd = Process("python3 /root/code/QKDServer/S15qkd/authd.py")

        # Raise readevents process priority if capability added
        readevents_prog = dir_qcrypto / 'readevents'
        if Process.config.ENVIRONMENT.raise_readevents_priority:
            readevents_prog = f"nice --adjustment=-20 {readevents_prog}"
        self.readevents = Readevents(readevents_prog)
        self.transferd = Transferd(dir_qcrypto / 'transferd')
        self.chopper = Chopper(dir_qcrypto / 'chopper')
        self.chopper2 = Chopper2(dir_qcrypto / 'chopper2')
        self.costream = Costream(dir_qcrypto / 'costream')
        self.splicer = Splicer(dir_qcrypto / 'splicer')
        if Process.config.qcrypto.pfind.frequency_search:
            self.pfind = Pfind("fpfind")
        else:
            self.pfind = Pfind(dir_qcrypto / 'pfind')
        self.errc = ErrorCorr(dir_qcrypto / 'errcd')

        self._clean_orphaned_qcrypto()
        self._initialize_pipes()  # cryptostuff directory needed to allow authd to write to file. Initialize only once to make needed structure and pips.
        self.restart_authd()

        if Process.config.LCR_polarization_compensator_path != "":
            self.polcom = PolComp(Process.config.LCR_polarization_compensator_path, self.service_to_BBM92)
            if Process.config.do_polarization_compensation:
                self.do_polcom = True
            else:
                self.do_polcom = False
        else:
            self.polcom = None
            self.do_polcom = False
        # Statuses
        self.qkd_engine_state = QKDEngineState.OFF
        self._qkd_protocol = QKDProtocol.SERVICE  # TODO(Justin): Deprecate this field.
        self._reset()

        # Auto-initialization when server starts up
        self._establish_connection()

        self._set_symmetry()

    def restart_authd(self):
        config = Process.config
        self.authd.stop()
        self.authd.start([
            "-H", config.target_hostname,
            "-p", config.port_authd,
            "-P", config.port_transd,
            "-r", config.remote_cert,
            "-c", config.local_cert,
            "-k", config.local_key,
        ],
        stderr="authd.err")

    def restart_connection(self):
        self.restart_authd()
        self.restart_transferd()  # restart to force out of inconsistent state

    def update_config(self):
        curr_conn = Process.config.remote_connection_id
        if self.polcom:
            Process.config.connections.__dict__[curr_conn].LCR_volt_info = SimpleNamespace()
            Process.config.connections.__dict__[curr_conn].LCR_volt_info.V1 = self.polcom.lcr.V1
            Process.config.connections.__dict__[curr_conn].LCR_volt_info.V2 = self.polcom.lcr.V2
            Process.config.connections.__dict__[curr_conn].LCR_volt_info.V3 = self.polcom.lcr.V3
            Process.config.connections.__dict__[curr_conn].LCR_volt_info.V4 = self.polcom.lcr.V4
            logger.debug(f"Current Polarization is: {self.polcom.lcr.V1}, {self.polcom.lcr.V2}, {self.polcom.lcr.V3}, {self.polcom.lcr.V4}. Config saved")

    def reload_configuration(self, conn_id: Optional[str] = None):
        self.update_config()
        Process.save_config()
        Process.load_config(conn_id=conn_id)
        logger.debug(f"New config {Process.config}")
        self.restart_authd()
        self.transferd.stop()  # stop transferd to force out of inconsistent state

        config = Process.config
        if self.polcom:
            self.polcom.set_voltage = [config.LCR_volt_info.V1, config.LCR_volt_info.V2, config.LCR_volt_info.V3, config.LCR_volt_info.V4]
            self.polcom._set_voltage()
            self.polcom.last_voltage_list = self.polcom.set_voltage.copy()

        if Process.config.do_polarization_compensation:
            self.do_polcom = True
        else:
            self.do_polcom = False
        # Statuses
        self.qkd_engine_state = QKDEngineState.OFF
        self._qkd_protocol = QKDProtocol.SERVICE  # TODO(Justin): Deprecate this field.
        self._reset()

        # Auto-initialization when server starts up
        self._establish_connection()

        self._set_symmetry()


    # INITIALIZATION

    def _reset(self):
        """Resets variables used in controller."""
        self._first_epoch: Optional[str] = None
        self._time_diff: Optional[int] = None
        self._sig_long: Optional[int] = None
        self._sig_short: Optional[int] = None
        self.transferd._first_received_epoch = None # Reset this value if not restarting/resetting transferd

    def _establish_connection(self):
        """Establish classical communication channel via transferd.

        No actual communication is performed, only connecting to socket.
        """
        # Responsibility for upkeeping connection should lie with 'transferd'
        # i.e. 'transferd' should not drop out if connection established.
        self._await_reply = 0
        if self.transferd.is_running():
            return

        # MSGIN / MSGOUT pipes need to be ready prior to communication
        # TODO(Justin): Check if method below fails if pipes already initialized.
        self.transferd.start(
            self.callback_msgout,
            self.readevents.measure_local_count_rate_system,
            self.restart_protocol,
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

    def _clean_orphaned_qcrypto(self):
        qkd_globals.kill_existing_qcrypto_processes()
        qkd_globals.kill_process_by_cmdline('authd.py')
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
    def restart_transferd(self):
        """ Stops and restarts tranferd"""
        self.stop_key_gen(inform_remote=False)
        self.transferd.stop()
        self.qkd_engine_state = QKDEngineState.OFF
        self.clear_comms()

        # Restart transferd
        self._establish_connection()
        self._set_symmetry()

    # TODO(Justin): Rename to 'stop' and update callback in QKD_status.py
    def stop_key_gen(self, inform_remote: bool = True):
        """Stops all processes locally and (best effort) remotely.

        Args:
            inform_remote: Whether stop command triggered locally.
        """
        if inform_remote:
            self._stop_key_gen_remote()

        # Stop own processes (except transferd)
        self.errc.stop()
        self.splicer.stop()
        self.pfind.stop()
        self.costream.stop()
        self.chopper2.stop()
        self.chopper.stop()
        self.readevents.stop()

        # Reset variables
        self._reset()

        # TODO(Justin): Refactor error correction and pipe creation
        self.clear_comms()

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
        # self._negotiate_symmetry()
        # time.sleep(0.4)

        # Set symmetry
        self._set_symmetry()

        # Initiate SERVICE mode
        self.send("serv_st1")
        self._expect_reply(timeout=10)

    def start_key_generation(self):
        """Restarts key generation mode.

        Typically this will be automatically called after SERVICE mode finishes
        polarization compensation - avoid calling this method directly, unless
        the polarization compensation already has known correction values.
        """
        # Ensure all services are stopped
        self.stop_key_gen()

        # Initiate symmetry negotiation
        #self._negotiate_symmetry()
        #time.sleep(0.8)

        # Initiate BBM92 mode
        self.send("st1")
        self._expect_reply(timeout=10)

    def restart_protocol(self):
        """Restarts respective SERVICE/KEYGEN mode.

        Useful as convenience function + process monitor restarting.
        """
        if self._qkd_protocol == QKDProtocol.SERVICE:
            self.start_service_mode()
        else:
            self.start_key_generation()

    def reset_timestamp(self):
        """Stops readevents, resets timestamp and restart"""
        self.readevents.powercycle()
        time.sleep(2) # at least 2 seconds needed for the chip to powerdown
        self.stop_key_gen()
        time.sleep(2) # at least 2 seconds needed for the monitors to end.
        self.restart_protocol()

    def send_epoch_notification(self, epoch, dt=None):
        """Disseminate coincidence results to readevents/polcom.

        Coincidence results include the raw keys after coincidence matching,
        and other coincidence statistics such as peak timing drift.
        Main candidates are 'readevents' reading timing difference for
        frequency compensation, and 'polcom' reading QBER for polarization
        compensation.

        This function is solely used as a callback to pass to costream
        and splicer.

        Args:
            epoch: Current epoch name.
            dt: Peak timing drift, in units of ns.

        Note:
            Previously termed 'callback_epoch', though not as intuitive.
        """

        # Send epochs to readevents
        use_frequency_correction = Process.config.qcrypto.frequency_correction.enable
        high_count_side = not self.transferd.low_count_side
        if use_frequency_correction and high_count_side:
            self.readevents.send_epoch(epoch, dt)

        # Only send epochs to polarization compensation in servicemode
        # and if LCVR exist
        if self._qkd_protocol == QKDProtocol.SERVICE and self.do_polcom:
            epoch_path = FoldersQKD.RAWKEYS + '/' + epoch
            self.polcom.send_epoch(epoch_path)

    def recompensate_service(self):
        """Convenience function"""
        if self.transferd.low_count_side:
            self.BBM92_to_service()
        else:
            None

    def drift_secure_comp(self,qber,epoch):
        """Convenience function"""
        if self.do_polcom:
            self.polcom.update_QBER_secure(qber,epoch)
        else:
            None

    def pol_com_walk(self):
        if self._qkd_protocol == QKDProtocol.SERVICE and self.do_polcom:
            thread = threading.Thread(target=self.polcom.do_walks) # defaults to lcvr_idx=0
            thread.start()
            logger.debug(f'do walk started')
        else:
            None
# CONTROL METHODS

    @requires_transferd
    def send(self, message: str):
        """Convenience method to forward messages to transferd."""
        return self.transferd.send(message)

    def _expect_reply(self, timeout: int):
        self._got_st1_reply = False
        if self._await_reply > 5:
            logger.debug(f'Awaited for {self._await_reply} times. Restarting transferd.')
            self.restart_transferd()
            time.sleep(2)
            self._await_reply = 0
            self.restart_protocol()
            return
        now = time.time()
        def reply_handler():
            time.sleep(0.1)
            while not self._got_st1_reply:
                if time.time() - now > timeout:
                    logger.debug(f'No reply within {timeout} s for st1')
                    self._await_reply += 1
                    self.restart_protocol()
                    return
            return
        thread = threading.Thread(target=reply_handler)
        thread.start()
        return

    @requires_transferd
    def _set_symmetry(self):
        """Sets Symmetry through pol_com status"""
        polcomp_is_lowcount = \
            Process.config.ENVIRONMENT.polarization_compensation_is_low_count
        if self.do_polcom:
            self.transferd._low_count_side = polcomp_is_lowcount
        else:
            self.transferd._low_count_side = not polcomp_is_lowcount
        self.transferd._negotiating = SymmetryNegotiationState.FINISHED

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

        # Bypass stopping and restarting readevents
        if code == "st_to_serv":
            self.BBM92_to_service()
            return

        if code == "serv_to_st":
            self.service_to_BBM92()
            return

        # Handle stopping of all processes
        if code == "stop":
            self.stop_key_gen(inform_remote=False)
            return

        # Do not set this as a global variable!
        # Single source of truth on transferd side (since we delegated transferd
        # to automate the symmetry negotiation process).
        low_count_side = self.transferd.low_count_side
        #if low_count_side is None:
        #    logger.info(
        #        f"Code = {code}; "
        #        "Symmetry negotiation not complete - key generation not started."
        #    )

        # Possible messages are 'serv_st*' and 'st*'
        seq = code.split("_")[-1]  # sequence; retrieve 'st*' codes
        qkd_protocol = QKDProtocol.SERVICE if code.startswith("serv_") else QKDProtocol.BBM92
        prepend_if_service = lambda s: ("serv_"+s) if qkd_protocol == QKDProtocol.SERVICE else s
        self._qkd_protocol = qkd_protocol

        # SERVICE mode codes
        # Whole process flow should kick off with low count side sending '*st1' message
        # 'serv_st1' is equivalent to a 'START' command
        if seq == "st1":
            self._got_st1_reply = True
            self._await_reply = 0
            if low_count_side:
                # Reflect message back to high_count_side
                self.transferd.send(prepend_if_service("st1"))
                return

            if qkd_protocol == QKDProtocol.BBM92:
                qkd_globals.FoldersQKD.remove_stale_comm_files()
            self.transferd.send(prepend_if_service("st2"))
            self.chopper2.start(self.restart_protocol, self.reset_timestamp)
            if Process.config.qcrypto.readevents.use_blinding_countermeasure:
                self.readevents.start_sb(self.restart_protocol, self.stop_key_gen)
            elif Process.config.qcrypto.frequency_correction.enable:
                self.readevents.start_fc(self.restart_protocol)
            else:
                self.readevents.start(self.restart_protocol)
            self.pol_com_walk()

        if seq == "st2":
            self._got_st1_reply = True
            self._await_reply = 0
            if not low_count_side:
                logger.error(f"High count side should not have received: {code}")
                return

            # Old comment: Provision to send signals to timestamps. Not used currently.
            if qkd_protocol == QKDProtocol.BBM92:
                qkd_globals.FoldersQKD.remove_stale_comm_files()
            self.transferd.send(prepend_if_service("st3"))
            self.chopper.start(qkd_protocol, self.restart_protocol, self.reset_timestamp)
            if Process.config.qcrypto.readevents.use_blinding_countermeasure:
                self.readevents.start_sb(self.restart_protocol, self.stop_key_gen)
            elif Process.config.qcrypto.frequency_correction.enable:
                self.readevents.start_fc(self.restart_protocol)
            else:
                self.readevents.start(self.restart_protocol)
            self.pol_com_walk()
            self.splicer.start(
                qkd_protocol,
                lambda msg: self.errc.ec_queue.put(msg),
                self.send_epoch_notification,
                self.restart_protocol,
            )


            # Important: 'st3' message is delayed so that both chopper and chopper2 can
            # generate sufficient initial epochs first.
            # TODO(Justin): Check if this assumption is really necessary.

        if seq == "st3":
            if low_count_side:
                logger.error(f"Low count side should not have received: {code}")
                return

            # try-except used here to short-circuit errors -> restart
            try:
                start_epoch, periods = self._retrieve_epoch_overlap()
                logger.debug(f"{start_epoch} {periods} {hex(int(start_epoch, 16) + periods)}")
                if Process.config.qcrypto.pfind.frequency_search:
                    (
                        self._freq_diff,
                        self._time_diff,
                    ) = self.pfind.measure_time_freq_diff(start_epoch, periods)
                    self._sig_long = 0
                    self._sig_short = 0
                else:
                    (
                        self._time_diff,
                        self._sig_long,
                        self._sig_short,
                    ) = self.pfind.measure_time_diff(start_epoch, periods)
                    self._freq_diff = 0
            except RuntimeError:
                self.restart_protocol()
                return

            # These variables should only be set here.
            self._first_epoch = start_epoch

           # If frequency difference exceeds threshold, restart with call to freqcd
            logger.info(
                f"Time difference: {self._time_diff}, freq difference: {self._freq_diff} "
                f"({round(self._freq_diff*1e9)} ppb)"
            )
            # Try to latch anyway
            if self._freq_diff != 0:
                self.readevents.update_freqcorr(self._freq_diff)

            self.costream.start(
                self._time_diff,
                start_epoch,
                qkd_protocol,
                self.send_epoch_notification,
                self.restart_protocol,
            )
        if qkd_protocol == QKDProtocol.BBM92 and Process.config.error_correction:
            if not self.errc.is_running():
                self.errc.start(
                    qkd_globals.PipesQKD.ECNOTE_GUARDIAN,
                    self.start_service_mode, # restart protocol
                    self.recompensate_service, # protocol for exceeding qber_limit
                    self.drift_secure_comp,
                    )
    @requires_transferd
    def BBM92_to_service(self):
        """Stops the programs which needs protocol, namely
        chopper, splicer and costream and restart them in service mode.
        Doing this, because readevents was not stopped, the time difference
        that pfind found should still be correct.
        Also reset error correction since it only works on continuous epochs
        for now.
        """
        low_count_side = self.transferd.low_count_side
        if low_count_side:
            self.send('st_to_serv')
            self.splicer.stop()
            self.chopper.stop()
            self.clear_comms()
            qkd_protocol = QKDProtocol.SERVICE
            self._qkd_protocol = qkd_protocol
            time.sleep(1.9) # to allow chopper and splicer to end gracefully
            self.errc.empty()
            self.chopper.start(qkd_protocol, self.restart_protocol, self.reset_timestamp)
            self.splicer.start(
                qkd_protocol,
                lambda msg: self.errc.ec_queue.put(msg),
                self.send_epoch_notification,
                self.restart_protocol,
            )
        else:
            # Assume called from (errc) low count side. Only need to restart costream with elapsed time difference and new epoch

            # Get current time difference before stopping costream
            try:
                td = int(self._time_diff) - int(self.costream.latest_deltat)
            except TypeError:
                self.restart_protocol()
            last_secure_epoch = self.transferd.last_received_epoch
            #
            self.costream.stop()
            self.clear_comms()
            qkd_protocol = QKDProtocol.SERVICE
            self._qkd_protocol = qkd_protocol
            logger.debug(f'SERVICE protocol set')
            last_secure_epoch = self.transferd.last_received_epoch
            try:
                start_epoch = self._retrieve_service_remote_epoch(hex(get_current_epoch())[2:])
            except RuntimeError:
                self.restart_protocol()
                return
            logger.debug(f'Retrieve_service is {start_epoch}')
            start_epoch = self._epochs_exist(start_epoch)
            self.costream.start(
                td,
                start_epoch,
                qkd_protocol,
                self.send_epoch_notification,
                self.restart_protocol,
            )
            self._first_epoch = start_epoch # Refresh first epoch and time_diff
            self._time_diff = int(td)
            logger.debug(f'costream restarted')

    def _remote_epoch_arrived(self, epoch: str, timeout: float = 15):
        end_time = time.time() + timeout
        while int(self.transferd.last_received_epoch,16) < int(epoch,16):
            logger.debug(f"remote epoch {epoch} not received yet")
            time.sleep(qkd_globals.EPOCH_DURATION)
            if time.time() > end_time:
                logger.debug(f"remote epoch {epoch} not received in {timeout} seconds.")
                raise RuntimeError
        return epoch

    def _epochs_exist(self, epoch: str):
        """Check that epoch exists in both receivedfiles and t1 folders
        If not wait till it appear
        """

        if (pathlib.Path(FoldersQKD.RECEIVEFILES + '/' + epoch).is_file() and
                 pathlib.Path(FoldersQKD.T1FILES + '/' + epoch).is_file()):
            logger.debug("Found {epoch} in first try")
            return epoch
        else:
            time.sleep(0.5)
            if (pathlib.Path(FoldersQKD.RECEIVEFILES + '/' + epoch).is_file() and
                    pathlib.Path(FoldersQKD.T1FILES + '/' + epoch).is_file()):
                logger.debug("Found {epoch} in second try")
                return epoch
            else:
                epoch = f"{int(epoch,16)+1:x}"
                if (pathlib.Path(FoldersQKD.RECEIVEFILES + '/' + epoch).is_file() and
                        pathlib.Path(FoldersQKD.T1FILES + '/' + epoch).is_file()):
                    logger.debug("Found {epoch} in last try")
                    return epoch

        return epoch


    @requires_transferd
    def _retrieve_service_remote_epoch(self, curr_epoch: str ):
        """Retrieve new epochs with correct protocol from remote(chopper) epoch
        and match with local (chopper2) epoch

        Performed by high count side.
        """
        epoch = self._remote_epoch_arrived(curr_epoch)
        file_path = f'{qkd_globals.FoldersQKD.RECEIVEFILES}/{epoch}'
        logger.debug(f'Filename {file_path}')
        headt2 = HeadT2(0,0,0,0,0xf,0)
        headt2 = read_T2_header(file_path)
        logger.debug(f'BITS per entry {headt2.base_bits}')
        i = 0
        while headt2.base_bits != 4:
            if i > 10:
                logger.error('No service epoch received after 10 tries')
                raise RuntimeError
            logger.debug(f'{hex(headt2.epoch)} {headt2.base_bits}')
            epoch = self._remote_epoch_arrived(hex(headt2.epoch+1)[2:])
            time.sleep(qkd_globals.EPOCH_DURATION)
            file_path = f'{qkd_globals.FoldersQKD.RECEIVEFILES}/{epoch}'
            headt2 = read_T2_header(file_path)
            i += 1

        return epoch

    @requires_transferd
    def service_to_BBM92(self):
        """Stops the programs which needs protocol, namely
        chopper, splicer and costream and restart them in non-service mode.
        Doing this, because readevents was not stopped, the time difference
        that pfind found should still be correct.
        """
        low_count_side = self.transferd.low_count_side
        if self.do_polcom:
            self.send('serv_to_st')
        if low_count_side:
            self.splicer.stop()
            self.chopper.stop()
            self.clear_comms()
            qkd_protocol = QKDProtocol.BBM92
            self._qkd_protocol = qkd_protocol
            time.sleep(1.9) # to allow chopper and splicer to end gracefully
            self.chopper.start(qkd_protocol, self.restart_protocol, self.reset_timestamp)
            self.splicer.start(
                qkd_protocol,
                lambda msg: self.errc.ec_queue.put(msg),
                self.send_epoch_notification,
                self.restart_protocol,
            )
        else:
            # Assume called from polcom (High) side. Only need to restart costream with elapsed time difference and new epoch

            # Get current time difference before stopping costream
            try:
                td = int(self._time_diff) - int(self.costream.latest_deltat)
            except TypeError:
                self.restart_protocol()
            last_service_epoch = self.transferd.last_received_epoch
            #
            self.costream.stop()
            self.clear_comms()
            qkd_protocol = QKDProtocol.BBM92
            self._qkd_protocol = qkd_protocol
            logger.debug(f'BBM92 protocol set')
            try:
                start_epoch = self._retrieve_secure_remote_epoch(hex(get_current_epoch())[2:])
            except RuntimeError:
                self.restart_protocol()
                return
            logger.debug(f'Retrieve_secure is {start_epoch}')
            start_epoch = self._epochs_exist(start_epoch)
            self.costream.start(
                td,
                start_epoch,
                qkd_protocol,
                self.send_epoch_notification,
                self.restart_protocol,
            )
            self._first_epoch = start_epoch # Refresh first epoch and time_diff
            self._time_diff = int(td)
            logger.debug(f'costream restarted')
        if Process.config.error_correction:
            if not self.errc.is_running():
                self.errc.start(
                    qkd_globals.PipesQKD.ECNOTE_GUARDIAN,
                    self.start_service_mode, # restart protocol
                    self.recompensate_service, # protocol for exceeding qber_limit
                    self.drift_secure_comp,
                   )

    @requires_transferd
    def _retrieve_secure_remote_epoch(self, curr_epoch: str ):
        """Retrieve new epochs with correct protocol from remote(chopper) epoch
        and match with local (chopper2) epoch

        Performed by high count side.
        """
        epoch = self._remote_epoch_arrived(curr_epoch)
        file_path = f'{qkd_globals.FoldersQKD.RECEIVEFILES}/{epoch}'
        logger.debug(f'Filename {file_path}')
        headt2 = HeadT2(0,0,0,0,0xf,0)
        headt2 = read_T2_header(file_path)
        logger.debug(f'BITS per entry {headt2.base_bits}')
        i = 0
        while headt2.base_bits != 1:
            if i > 10:
                logger.error('No secure epochs received after 10 tries')
                raise RuntimeError
            logger.debug(f'{hex(headt2.epoch)} {headt2.base_bits}')
            epoch = self._remote_epoch_arrived(hex(headt2.epoch+1)[2:])
            file_path = f'{qkd_globals.FoldersQKD.RECEIVEFILES}/{epoch}'
            headt2 = read_T2_header(file_path)
            i += 1

        return epoch

    @requires_transferd
    def _retrieve_epoch_overlap(self):
        """Calculate epoch overlap between local and remote servers.

        Performed by high count side.
        transferd (remote) and chopper2 (local) may have conflicting range of epochs,
        so resolving potential conflicts by calculating the epoch overlap.

        The usable periods is the number of overlapping epoch files.
        Different implementations are possible, with the following notes:

            - The first epoch files are potentially underfilled.
            - To account for latency and mismatch in epoch collection start times,
              an additional 2 epoch duration buffer is provided.
        """
        extra = 2 # one for first underfilled epoch and one for spare at the end
        target_num_epochs = Process.config.pfind_epochs + extra
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
            usable_periods = target_num_epochs
        else:
            start_epoch = self.chopper2.first_epoch
            usable_periods = target_num_epochs

        # Ignore the first potentially underfilled epoch, as per legacy code
        start_epoch = hex(int(start_epoch,16)+1)[2:]
        usable_periods -= extra
        return start_epoch, usable_periods

    def get_process_states(self):
        return {
            'transferd': self.transferd.is_running(),
            'readevents': self.readevents.is_running(),
            'chopper': self.chopper.is_running(),
            'chopper2': self.chopper2.is_running(),
            'costream': self.costream.is_running(),
            'splicer': self.splicer.is_running(),
            'error_correction': self.errc.is_running()
        }

    def get_status_info(self):
        return {
            'connection_status': Process.config.target_hostname if self.transferd.communication_status else '',
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
            'last_qber': self.polcom.last_qber if self.do_polcom and self._qkd_protocol is QKDProtocol.SERVICE  else '',
        }

    def get_error_corr_info(self):
        return {
            'first_epoch': self.errc._first_epoch_info,
            'undigested_epochs': self.errc._undigested_epochs_info,
            'ec_raw_bits': self.errc._ec_raw_bits,
            'ec_final_bits': self.errc._ec_final_bits,
            'ec_key_gen_rate': round(self.errc._ec_key_gen_rate,1) if self.errc._ec_key_gen_rate else '',
            'ec_err_fraction': self.errc._ec_err_fraction,
            'key_file_name': self.errc._ec_epoch,
            'total_ec_key_bits': self.errc.total_ec_key_bits,
            'init_QBER': self.errc.init_QBER_info,
        }

    def clear_comms(self):
        qkd_globals.PipesQKD.drain_all_pipes() # This reads all pipes
        qkd_globals.FoldersQKD.remove_stale_comm_files()

    def get_bl_info(self):
        return self.readevents.blinded

    @property
    def sig_long(self) -> Optional[int]:
        return self._sig_long

    @property
    def sig_short(self) -> Optional[int]:
        return self._sig_short

    def check_alive_threads(self):
        logger.debug(f"Checking for threads started by threading.")
        for thread in threading.enumerate():
            logger.debug(f"Threads alive are : {thread.name}")

Process.load_config()
controller = Controller()
controller.identity = Process.config.identity

def start_service_mode():
    """Initiated by QKD controller via the QKD server status page."""
    controller.start_service_mode()  # passthrough

def start_key_generation():
    controller.start_key_generation()

def stop_key_gen():
    """Initiated by QKD controller via the QKD server status page."""
    controller.stop_key_gen()
    controller._got_st1_reply = True
    time.sleep(2.5)
    controller.check_alive_threads()

def service_to_BBM92():
    return controller.service_to_BBM92()

def get_status_info():
    return controller.get_status_info()

def get_process_states():
    return controller.get_process_states()

def get_error_corr_info():
    return controller.get_error_corr_info()

def restart_transferd():
    return controller.restart_transferd()

def restart_connection():
    return controller.restart_connection()

def reload_configuration(conn_id):
    return controller.reload_configuration(conn_id)

