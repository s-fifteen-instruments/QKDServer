import subprocess
import os
import signal
import time
import psutil
import asyncio  # for concurrent processes
import glob
import stat
import shutil
import locale

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
    # blocking = False
    # os.set_blocking(f, blocking)
    os.write(f, f'{localcountrate}\n'.encode())
    return localcountrate


def open_message_pipes():
    global debugval, commstat, dataroot, msgh, smsgh, messagepipestatus
    if commstat < 1:
        return
    if not messagepipestatus:
        pass  # needs to be implemented
    # open input pipe
    #     set msgh [open $dataroot/msgout r+]
    #     debugval = msgh
    #     fconfigure $msgh -blocking false
    #     fileevent $msgh readable hms
    #     # output pipe
    #     set smsgh [open $dataroot/msgin w]
    #     set messagepipestatus 1
    # }


async def startcommunication():
    # READ PIPE from process not working yet
    global debugval, commhandle, commstat, programroot, commprog, dataroot
    global portnum, targetmachine, receivenotehandle
    cmd = f'{commprog}'
    args = f'-d {cwd}/{dataroot}/sendfiles -c {cwd}/{dataroot}/cmdpipe -t {targetmachine} \
            -D {cwd}/{dataroot}/receivefiles -l {cwd}/{dataroot}/transferlog \
            -m {cwd}/{dataroot}/msgin -M {cwd}/{dataroot}/msgout -p {portnum} \
            -k -e {cwd}/{dataroot}/ecspipe -E {cwd}/{dataroot}/ecrpipe'

    if commstat == 0:
        _remove_stale_comm_files()
        proc_transferd = await asyncio.create_subprocess_exec(cmd, *args.split(),
                                                              stdout=asyncio.subprocess.PIPE,
                                                              stderr=asyncio.subprocess.PIPE)
        commstat = 1
        async for line in proc_transferd.stdout:
            print(line.decode())
            print('.')
            # await asyncio.sleep(0.1)
            # if commstat == 0: 
            #     proc_transferd.kill()
        return await proc_transferd.kill()

import select
if __name__ == '__main__':
    _prepare_folders()
    loop = asyncio.get_event_loop()
    # loop.run_until_complete(startcommunication())
    print(measure_local_count_rate())
    # asyncio.run(startcommunication())
    commstat = 0
    with open(f'{dataroot}/rawevents', 'r') as fifo:
        print(fifo.readline())
