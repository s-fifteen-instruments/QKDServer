# Abstract away common patterns across the different processes
import json
import os
import time
import io
import threading
from pathlib import Path
import subprocess
from types import SimpleNamespace
from typing import Union

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
        ):
        """Starts the process with specified args and standard streams.

        Standard input must be open to allow argument passing.

        Process pipes to '/dev/null'-equivalent file by default.

        Args:
            args: Command line arguments for program.
            stdout: Standard output stream.
            stderr: Standard error stream.
            callback_restart: Callback to controller to perform restart.

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
        is_stdout_fd = is_stderr_fd = False

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

        # Run program in child process
        # psutil.Popen used for continuous tracking of PID
        command = [self.program, *list(map(str, args))]
        self.process = psutil.Popen(
            command,
            stdout=stdout, stderr=stderr,  # file descriptors are inherited
        )
        logger.debug(f"Started: {' '.join(map(str, command))}")

        # Close file descriptors
        if is_stdout_fd: os.close(stdout)
        if is_stderr_fd: os.close(stderr)

        # Issue monitoring thread
        # TODO(Justin): Consider scenario where services stops and starts immediately,
        # but callback_restart is not updated to new condition. Can be mitigated by
        # shorter polling duration compared to process start time.
        #
        # Activate callback restart only if defined
        if callback_restart:
            self._expect_running = True
            self.monitor(callback_restart)
    
    def stop(self, timeout=3):
        if self.process is None:
            return

        self._expect_running = False

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

        self.process = None

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

                while predicate():
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

    def monitor(self, callback_restart):
        """Restarts keygen if process terminates without a wait/stop trigger.
        
        Polls performed every 1 second.
        """
        
        def monitor_daemon():
            time.sleep(1)
            while self._expect_running:
                if not self.is_running():
                    logger.debug("Activated process monitor for '{self.program}' ('{self.process}')")
                    callback_restart()
                    return
                time.sleep(1)
            logger.debug("Terminated process monitor for '{self.program}' ('{self.process}')")
    
        logger.debug(f"Starting process monitor for '{self.program}' ('{self.process}')")
        thread = threading.Thread(target=monitor_daemon)
        thread.daemon = True
        thread.start()
