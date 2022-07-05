# Abstract away common patterns across the different processes
import json
import os
import time
import io
import threading
from pathlib import Path
import subprocess
from types import SimpleNamespace

import psutil

from . import qkd_globals
from .qkd_globals import logger, PipesQKD, FoldersQKD

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
    
    @classmethod
    def load_config(cls, path=None):
        if not path:
            path = qkd_globals.config_file
        with open(path, 'r') as f:
            cls.config = json.load(f, object_hook=lambda d: SimpleNamespace(**d))

    def start(self, args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL):
        """Starts the process with specified args and standard streams.

        #TODO(justin): args...

        Standard input must be open to allow argument passing.

        Process pipes to '/dev/null'-equivalent file by default.

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

            [1]: https://docs.python.org/3/library/subprocess.html#:~:text=inheritable%20flag
        """
        # Parse stdout/stderr strings into file descriptors
        is_stdout_fd = is_stderr_fd = False

        if isinstance(stdout, str):
            path = Path(Process.config.data_root) / str(stdout)
            stdout = os.open(path, os.O_APPEND)
            is_stdout_fd = True

        if isinstance(stderr, str):
            path = Path(Process.config.data_root) / str(stdout)
            stdout = os.open(path, os.O_APPEND)
            is_stderr_fd = True

        # Run program in child process
        # psutil.Popen used for continuous tracking of PID
        self.process = psutil.Popen(
            [self.program, *list(map(str, args))],
            stdout=stdout, stderr=stderr,  # file descriptors are inherited
        )

        # Close file descriptors
        if is_stdout_fd: os.close(stdout)
        if is_stderr_fd: os.close(stderr)
    
    def stop(self, timeout=3):
        if self.process is None:
            return

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

        self.process = None

    def wait(self):
        return self.process.wait()

    def is_running(self):
        return self.process and self.process.poll() is None
    
    # Helper
    def read(self, pipe, callback, name='', wait=0.1):
        """TODO

        Args:
            pipe: Can be actual opened pipe, or path to pipe in filesystem.
        """
        def func(pipe):
            # Create pipe if is not already open for reading
            if not isinstance(pipe, io.IOBase):
                # Create file descriptor for read-only non-blocking pipe
                fd = os.open(pipe, os.O_RDONLY | os.O_NONBLOCK)
                # Open file descriptor with *no* buffer
                pipe = os.fdopen(fd, 'rb', 0)
            
            # Run callback on pipe until termination instruction
            with pipe:
                assert pipe.readable()
                while not self.is_running():
                    if wait:
                        time.sleep(wait)
                    try:
                        callback(pipe)
                    except OSError:
                        pass
            if name:
                logger.info(f"Pipe '{name}' closed.")

        thread = threading.Thread(target=func, args=(pipe,))
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
