import subprocess
import os
import signal
import time
import psutil
import asyncio  # for concurrent processes
import glob  # for file system access
import stat
import shutil  # delete complete folders with everything underneath
import signal  # used for pipe read timeouts
import sys
import threading
import select
from queue import Queue, Empty

dataroot = 'tmp/cryptostuff'
programroot = 'bin/remotecrypto'
cwd = os.getcwd()
extclockopt = "-e"  # clock
localcountrate = -1
testing = 1  # CHANGE to 0 if you want to run it with hardware
if testing == 1:
    # this outputs one timestamp file in an endless loop. This is for testing only.
    prog_readevents = 'helper_script/out_timestamps.sh'
else:
    prog_readevents = programroot + '/readevents3'
prog_getrate = programroot + '/getrate'
commprog = programroot + '/transferd'
targetmachine = '127.0.0.1'
portnum = 4852
commstat = 0
commhandle = None


def kill_process(proc_pid: int):
    process = psutil.Process(proc_pid)
    for proc in process.children(recursive=True):
        proc.kill()
    process.kill()


def _prepare_folders():
    global dataroot
    if os.path.exists(dataroot):
        shutil.rmtree(dataroot)
    folder_list = ('/sendfiles', '/receivefiles', '/t1',
                   '/t3', '/rawkey', '/histos', '/finalkey')
    for i in folder_list:
        if os.path.exists(i):
            print('error')
        os.makedirs(dataroot + i)

    fifo_list = ('/msgin', '/msgout', '/rawevents',
                 '/t1logpipe', '/t2logpipe', '/cmdpipe', '/genlog',
                 '/transferlog', '/splicepipe', '/cntlogpipe',
                 '/eccmdpipe', '/ecspipe', '/ecrpipe', '/ecnotepipe',
                 '/ecquery', '/ecresp')
    for i in fifo_list:
        fifo_path = dataroot + i
        if os.path.exists(fifo_path):
            if stat.S_ISFIFO(os.stat(fifo_path).st_mode):
                os.unlink(fifo_path)
            else:
                os.remove(fifo_path)
        os.mkfifo(dataroot + i)


def _remove_stale_comm_files():
    files = glob.glob(dataroot + '/receivefiles/*')
    for f in files:
        os.remove(f)
    files = glob.glob(dataroot + '/sendfiles/*')
    for f in files:
        os.remove(f)


def measure_local_count_rate():
    '''
    Measure local photon count rate
    '''
    global programroot, dataroot, localcountrate, extclockopt, cwd
    localcountrate = -1

    p1 = subprocess.Popen((prog_readevents,
                           '-a 1',
                           '-F',
                           '-u {extclockopt}',
                           '-S 20'),
                          stdout=subprocess.PIPE)
    p2 = subprocess.Popen([prog_getrate, '>', f'{dataroot}/rawevents'],
                          stdin=p1.stdout,
                          stdout=subprocess.PIPE)
    p2.wait()
    try:
        kill_process(p1.pid)
        kill_process(p2.pid)
    except psutil.NoSuchProcess as a:
        pass
    localcountrate = (p2.stdout.read()).decode()
    f = os.open(f'{dataroot}/rawevents', os.O_RDWR)
    os.write(f, f'{localcountrate}\n'.encode())
    return localcountrate



def transferd_stdout_digest(out, queue):
    global commhandle, commstat
    while commhandle.poll() == None:
        for line in iter(out.readline, b''):
            print(f'[transferd stdout] {line.decode()}')
            if line == b'connected.\n':
                commstat = 2
            elif line == b'disconnected.\n':
                commstat = 3
            time.sleep(0.1)
    print('transferd thread finished')
    # startcommunication() # this is to restart the startcomm process if it crashes


def msg_out_digest():
    global commhandle
    global read_timeout
    read_timeout = 0.05
    out = open(f'{dataroot}/msgout', 'r')
    while commhandle.poll() == None:
        readers = select.select([out], [], [], read_timeout)[0] # this is non-blocking reader with a timeout. Only works on Unix
        if not readers:
            time.sleep(0.1)
        else:
            for r in readers:
                print(f'[msgout] {r.readline()}')
    print('msg_out_digest thread finished')


def startcommunication():
    global debugval, commhandle, commstat, programroot, commprog, dataroot
    global portnum, targetmachine, receivenotehandle
    global commhandle

    cmd = f'{commprog}'
    args = f'-d {cwd}/{dataroot}/sendfiles -c {cwd}/{dataroot}/cmdpipe -t {targetmachine} \
            -D {cwd}/{dataroot}/receivefiles -l {cwd}/{dataroot}/transferlog \
            -m {cwd}/{dataroot}/msgin -M {cwd}/{dataroot}/msgout -p {portnum} \
            -k -e {cwd}/{dataroot}/ecspipe -E {cwd}/{dataroot}/ecrpipe'

    if commstat == 0:
        _remove_stale_comm_files()
        commhandle = subprocess.Popen((cmd, *args.split()), 
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        q = Queue()  # I don't know why I need this but it works
        # t.daemon = True
        commstat = 1
        # setup read thread for the process stdout
        t = threading.Thread(target=transferd_stdout_digest,
                             args=(commhandle.stdout, q))
        t.start()
        # setup read thread for the msgout pipe
        msg_out_thread = threading.Thread(target=msg_out_digest, args=())
        msg_out_thread.start()


def signal_handler(signum, frame):
    # print(frame)
    print('pipe read timeout')
    raise IOError("Couldn't read pipe!")


if __name__ == '__main__':
    if os.path.exists(dataroot):
        shutil.rmtree(dataroot)
    _prepare_folders()
    startcommunication()
    print(measure_local_count_rate())
    fd = os.open(f'{dataroot}/rawevents', os.O_RDWR) # non-blocking
    f = os.fdopen(fd, 'r') # non-blocking
    readers = select.select([f], [], [], 0.1)[0] # non-blocking
    if readers:
        for i in readers:
            print(i.readline())


    signal.alarm(0)
    time.sleep(1)
    print('try to write')
    f = os.open(f'{dataroot}/msgout', os.O_RDWR)
    os.write(f, f'test\n'.encode())
    time.sleep(2)
    kill_process(commhandle.pid)
