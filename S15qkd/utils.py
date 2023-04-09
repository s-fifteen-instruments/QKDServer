# Abstract away common patterns across the different processes
import json
import os
import time
import io
import threading
import math
from struct import unpack
from pathlib import Path
import subprocess
from types import SimpleNamespace, FunctionType
from typing import Union, Optional, NamedTuple

import psutil

from . import qkd_globals
from .qkd_globals import QKDProtocol, logger, PipesQKD, FoldersQKD

class Process:
    """Represents a single process.

    Functionality repeated across all processes are abstracted away
    into the class to reduce code duplication.
    
    Note:
        The singleton pattern is avoided to prevent difficulties with:
        (1) global states (a singleton is effectively a global),
        (2) testing/mocking.
    """

    # Shared by all processes
    config = None

    def __init__(self, program):
        self.program = program
        self.process = None
        self._persist_read = None  # See read() below.
        self._expect_running = False  # See monitor() below.
        self.stop_event = threading.Event()

    @classmethod
    def load_config(cls, path=None):
        if not path:
            path = qkd_globals.config_file
        with open(path, 'r') as f:
            cls.config = json.load(f, object_hook=lambda d: SimpleNamespace(**d))

    def start(
            self,
            args: list,
            stdout: Union[int, str, PipesQKD] = subprocess.DEVNULL,
            stderr: Union[int, str, PipesQKD] = subprocess.DEVNULL,
            callback_restart=None,
            stdin : Union[int, str, PipesQKD] = subprocess.DEVNULL,
        ):
        """Starts the process with specified args and standard streams.

        Standard input must be open to allow argument passing.

        Process pipes to '/dev/null'-equivalent file by default.

        Args:
            args: Command line arguments for program.
            stdout: Standard output stream.
            stderr: Standard error stream.
            callback_restart: Callback to controller to perform restart.
            stdin: Standard in stream

        Note:
            An alternative implementation to write to file is previously performed as:

            ```
            with open(FILEPATH, 'a+') as f:
                subprocess.Popen(..., stderr=f)
            ```

            This is valid code - see [1]. This encapsulates a series of processes:

                1. File object to FILEPATH is opened within 'with' context.
                2. File descriptor to file object (and not the file object itself) is
                   automatically inherited by child process created by Popen. Note
                   that 'close_fds' argument of Popen do not apply to standard streams.
                3. File object to FILEPATH (in parent process) closed upon leaving
                   context, but file object opened by child process using inherited
                   descriptor remains open.

            For semantic reasons, this is translated to a file descriptor picture.

            Process monitoring can also consider introducing a 'monitor' kwargs defaulting
            to True, to allow override of '_expect_running' so that processes designed to
            terminate (wait) do not inadvertently force a restart. This is currently mitigated
            by adding a one-second interval between process start and monitor start.

            [1]: https://docs.python.org/3/library/subprocess.html#:~:text=inheritable%20flag
        """
        # Parse stdout/stderr strings into file descriptors
        is_stdout_fd = is_stderr_fd = is_stdin_fd =  False

        if isinstance(stdout, PipesQKD):
            stdout = os.open(stdout, os.O_WRONLY)
            # stdout = os.open(stdout, os.O_WRONLY | os.O_NONBLOCK) TODO
            is_stdout_fd = True

        elif isinstance(stdout, str):
            path = Path(Process.config.data_root) / stdout
            stdout = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT)
            is_stdout_fd = True
        
        if isinstance(stderr, PipesQKD):
            stderr = os.open(stderr, os.O_WRONLY)
            # stderr = os.open(stderr, os.O_WRONLY | os.O_NONBLOCK) TODO
            is_stderr_fd = True

        elif isinstance(stderr, str):
            path = Path(Process.config.data_root) / stderr
            stderr = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT)
            is_stderr_fd = True

        if isinstance(stdin, PipesQKD):
            stdin = os.open(stdin, os.O_RDONLY)
            # stdinr = os.open(stdin, os.O_RDONLY | os.O_NONBLOCK) TODO
            is_stdin_fd = True

        elif isinstance(stdin, str):
            path = Path(Process.config.data_root) / stdin
            stdin = os.open(path, os.O_RDONLY | os.O_CREAT)
            is_stdin_fd = True

        # Run program in child process
        # psutil.Popen used for continuous tracking of PID
        command = [self.program, *list(map(str, args))]
        self.process = psutil.Popen(
            command,
            stdin=stdin,
            stdout=stdout, stderr=stderr,  # file descriptors are inherited
        )
        logger.debug(f"Started: {' '.join(map(str, command))}")

        # Close file descriptors
        if is_stdout_fd: os.close(stdout)
        if is_stderr_fd: os.close(stderr)
        if is_stdin_fd: os.close(stdin)

        # Issue monitoring thread
        # TODO(Justin): Consider scenario where services stops and starts immediately,
        # but callback_restart is not updated to new condition. Can be mitigated by
        # shorter polling duration compared to process start time.
        #
        # Activate callback restart only if defined
        if callback_restart:
            self._expect_running = True
            self.mon_thread = self.monitor(callback_restart,self.stop_event)
    
    def stop(self, timeout=3):
        if self.process is None:
            return

        self.stop_event.set()
        if self._expect_running:
            self._expect_running = False
            try:
                self.mon_thread.join()
            except RuntimeError:
                logger.debug(f"Thread closed")

        # Stop persistence read pipes attached to process
        if self._persist_read:
            self._persist_read = False

        try:
            # 'qcrypto' likely does not have child processes, but
            # gathering them all up to avoid any orphaned zombie processes.
            procs = self.process.children(recursive=True)  # stop process tree
            procs.append(self.process)  # stop process itself as well
            
            # Attempt graceful terminate
            for p in procs:
                p.terminate()
                
            # Wait on terminated processes and kill processes that are still alive
            gone, alive = psutil.wait_procs(
                procs,
                timeout=timeout,
                callback=lambda p: logger.debug(f'Process {p} terminated.')
            )
            for p in alive:
                p.kill()
                logger.debug(f'Process {p} killed.')

        except psutil.NoSuchProcess:
            logger.debug(f"Process '{self.process}' already prematurely terminated ('{self.program}')")

        except AttributeError:
            logger.debug(f"Process went missing. ({self.program})")

        self.process = None
        self.stop_event.clear()

    def wait(self):
        self._expect_running = False
        return self.process.wait()

    def is_running(self):
        return self.process and self.process.poll() is None
    
    # Helper
    def read(self, pipe, callback, name='', wait=0.1, persist=False):
        """TODO

        If opening any pipes from the same parent thread, ensure that
        the process itself has been started first. The opened pipe
        is designed to terminate automatically together with the process.
        
        Notably, some processes cannot start if the pipe is not already there, e.g.
        chopper, splicer. If persist set to True, a single-valued boolean
        container (list) will be provided to signal termination.

        Args:
            pipe: Can be actual opened pipe, or path to pipe in filesystem.
        """
        if persist:
            self._persist_read = True
        
        def func(pipe, name):
            # Create pipe if is not already open for reading
            if not isinstance(pipe, io.IOBase):
                if not name:
                    name = pipe
                # Create file descriptor for read-only non-blocking pipe
                # TODO(Justin): Why must a single threaded pipe read be non-blocking?
                fd = os.open(pipe, os.O_RDONLY)
                # Open file descriptor with *no* buffer
                pipe = os.fdopen(fd, 'r')

                # TODO
                # pipe = os.fdopen(fd, 'rb', 0)
            
            # Run callback on pipe until termination instruction
            with pipe:
                if name:
                    logger.info(f"Named pipe '{name}' opened.")
                assert pipe.readable()

                # Swap between parent process or persistence flag
                predicate = lambda: self.is_running()
                if self._persist_read is not None:
                    predicate = lambda: self._persist_read

                while predicate() and not self.stop_event.is_set():
                    if wait:
                        time.sleep(wait)

                    # Note that the try-except around pipe to catch OSError is *necessary*,
                    # observed in Python 3.6, specifically for unbuffered non-blocking pipes.
                    # A read performed when the pipe (_io.FileIO) has no data, even though
                    # readable() returns true, raises:
                    #    OSError: read() should have returned a bytes object, not 'NoneType'
                    # Possibly related unresolved bug: https://bugs.python.org/issue13322
                    #
                    # Implementation ported from old code.
                    # TODO(Justin): Consider switching to a line buffered pipe.
                    try:
                        callback(pipe)
                    except OSError:
                        pass
            if name:
                logger.info(f"Named pipe '{name}' closed.")

        thread = threading.Thread(target=func, args=(pipe,name))
        thread.start()
        return thread
    
    @staticmethod
    def write(target, message: str, name=''):
        """Write line to pipe."""
        # Create pipe if is not already open for reading
        if not isinstance(target, io.IOBase):
            return Process.write_file(target, message, name)
        
        # Target itself should be open and writable
        assert target.writable()
        result = target.write(f'{message}\n'.encode())
        logger.debug(f"'{message}' written to '{name}'.")
        return result

    @staticmethod
    def write_file(path, message, name=''):
        """Write directly to file/pipe located at path."""
        fd = os.open(path, os.O_WRONLY)
        with os.fdopen(fd, 'wb', 0) as f:
            f.write(f'{message}\n'.encode())
        if not name:
            name = path
        logger.debug(f"'{message}' written to '{name}'.")

    def monitor(self, callback_restart, stop_event):
        """Restarts keygen if process terminates without a wait/stop trigger.
        
        Polls performed every 1 second.
        """
        
        def monitor_daemon():
            time.sleep(2)
            while self._expect_running and not stop_event.is_set():
                if not self.is_running():
                    logger.debug(f"Activated process monitor for '{self.program}' ('{self.process}')")
                    callback_restart()
                time.sleep(2)
            logger.debug(f"Terminated process monitor for '{self.program}' ('{self.process}')")
    
        logger.debug(f"Starting process monitor for '{self.program}' ('{self.process}')")
        thread = threading.Thread(target=monitor_daemon)
        thread.daemon = True
        thread.start()
        return thread

    def start_thread_method(self, method_name: FunctionType):
        logger.debug(f"Started method {method_name} for '{self.program}' ('{self.process}')")
        thread = threading.Thread(target = method_name)
        thread.daemon = True
        thread.start()
        return thread

class HeadT1(NamedTuple):
    tag: int
    epoch: int
    length_bits: int
    bits_per_entry: int
    base_bits: int

class HeadT2(NamedTuple):
    tag: int
    epoch: int
    length_bits: int
    timeorder: int
    base_bits: int
    protocol: int

class HeadT3(NamedTuple):
    tag: int
    epoch: int
    length_entry: int
    bits_per_entry: int

class HeadT4(NamedTuple):
    tag: int
    epoch: int
    length_bits: int
    timeorder: int
    base_bits: int

from dataclasses import dataclass

@dataclass
class ServiceT3:
    head: HeadT3
    coinc_matrix: list
    garbage: list
    okcount: int
    qber: float

def read_T2_header(file_name: str):
    if Path(file_name).is_file():
        with open(file_name, 'rb') as f:
            head_info = f.read(4*6)
    else:
        headt2 = HeadT2(2,int(file_name.split('/')[-1],16),0,0,4,0)
        return headt2
    headt2 = HeadT2._make(unpack('iIIiii', head_info))
    if (headt2.tag != 0x102 and headt2.tag != 2) :
        logger.error(f'{file_name} is not a Type2 header file')
    if hex(headt2.epoch) != ('0x' + file_name.split('/')[-1]):
        logger.error(f'Epoch in header {headt2.epoch} does not match epoc filename {file_name}')
    #logger.debug(f"{tag} {epoc} {length_bits} {time_order} {base_bits} {protocol}")
    return headt2

def read_T3_header(file_name: str) -> Optional[HeadT3]:
    if Path(file_name).is_file():
        with open(file_name, 'rb') as f:
            head_info = f.read(16) # 16 bytes of T3 header https://qcrypto.readthedocs.io/en/documentation/file%20specification.html
    else:
        headt3 = HeadT3(3,int(file_name.split('/')[-1],16),0,0)
        return headt3
    headt3 = HeadT3._make(unpack('iIIi', head_info)) #int, unsigned int, unsigned int, int
    if (headt3.tag != 0x103 and headt3.tag != 3) :
        logger.error(f'{file_name} is not a Type3 header file')
    if hex(headt3.epoch) != ('0x' + file_name.split('/')[-1]):
        logger.error(f'Epoch in header {headt3.epoch} does not match epoc filename {file_name}')
    return headt3

def read_T4_header(file_name: str):
    if Path(file_name).is_file():
        with open(file_name, 'rb') as f:
            head_info = f.read(4*5)
    else:
        headt4 = HeadT4(4,0,0,0,-1)
        return headt4
    headt4 = HeadT4._make(unpack('iIIii', head_info))
    if (headt4.tag != 0x104 and headt4.tag != 4) :
        logger.error(f'{file_name} is not a Type4 header file')
    if hex(headt4.epoch) != ('0x' + file_name.split('/')[-1]):
        logger.error(f'Epoch in header {headt4.epoch} does not match epoc filename {file_name}')
    return headt4

def service_T3(file_name: str) -> Optional[ServiceT3]:
    decode = [-1, 0, 1, -1, 2, -1, -1, -1, 3, -1, -1, -1, -1, -1, -1, -1] # translate valid bit values to 4 array index
    er_coinc_id = [0, 5, 10, 15] #VV, ADAD, HH, DD
    gd_coinc_id = [2, 7, 8, 13] #VH, ADD, HV, DAD 
    body = []
    headt3 = read_T3_header(file_name)
    header_info_size = 16
    with open(file_name,'rb') as f:
        f.seek(header_info_size)
        word = f.read(4)
        while word != b"":
            dat, = unpack('<I', word) # comma is important to get correct type
            # unpacking was done wrongly in original diagnosis.c code.
            dat_bytes = dat.to_bytes(4,'little')
            body.append(dat_bytes[3])
            body.append(dat_bytes[2])
            body.append(dat_bytes[1])
            body.append(dat_bytes[0])
            word = f.read(4)

    service = ServiceT3(headt3,[0]*16,[0,0],0,1)
    if (headt3.bits_per_entry !=8):
        logger.warning(f'Not a service file with 8 bits per entry')
    total_bytes = math.ceil((headt3.length_entry*headt3.bits_per_entry)/8) + header_info_size
    total_words = math.ceil(total_bytes/4)
    if total_words*4 != (len(body) + header_info_size):
        logger.error(f'stream 3 size inconsistency')
    for i in range(headt3.length_entry):
        b = decode[body[i] & 0xf] # Bob 
        a = decode[(body[i]>>4) & 0xf] # Alice
        if a < 0:
            service.garbage[0] += 1
        if b < 0:
            service.garbage[1] += 1
        if ((a >= 0) and (b >= 0)) :
            service.coinc_matrix[a * 4 + b] += 1
            service.okcount += 1


    er_coin = sum(service.coinc_matrix[i] for i in er_coinc_id)
    gd_coin = sum(service.coinc_matrix[i] for i in gd_coinc_id)
    if (er_coin + gd_coin) == 0:
        service.qber = 1.0
        return service
    service.qber = float(round(er_coin /(er_coin + gd_coin),3)) #ignore garbage
    return service

def epoch_after(epoch: str, added: int) -> str:
    return hex(int(epoch,16)+10)[2:]

