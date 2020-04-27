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
import json

# configuration file contains the most important paths and the target ip and port number
with open('config/config.json', 'r') as f:
    config = json.load(f)

for key, value in config['local_detector_skew_correction'].items():
    vars()[key + 'corr'] = value
dataroot = config['data_root']
programroot = config['program_root']
protocol = config['protocol']
max_event_diff = config['max_event_diff']
cwd = os.getcwd()
extclockopt = "-e"  # clock
localcountrate = -1
remote_count_rate = -1
testing = 1  # CHANGE to 0 if you want to run it with hardware
if testing == 1:
    # this outputs one timestamp file in an endless loop. This is for testing only.
    prog_readevents = 'helper_script/out_timestamps.sh'
else:
    prog_readevents = programroot + '/readevents3'
prog_getrate = programroot + '/getrate'
prog_splicer = programroot + '/splicer'
commprog = programroot + '/transferd'
prog_chopper = programroot + '/chopper'
targetmachine = config['target_ip']
portnum = config['port_num']
commstat = 0
commhandle = None
proc_chopper = proc_readevents = None
sleep_time = 0.05
low_count_side = None
t2logpipe_digest_thread_flag = True
kill_option = config['kill_option']


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
        # os.close(dataroot + i)


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
    localcountrate = int((p2.stdout.read()).decode())
    f = os.open(f'{dataroot}/rawevents', os.O_RDWR)
    os.write(f, f'{localcountrate}\n'.encode())
    return localcountrate


def transferd_stdout_digest(out, err, queue):
    global commhandle, commstat
    while commhandle.poll() == None:
        for line in iter(out.readline, b''):
            line = line.rstrip()
            print(f'[transferd:stdout] {line.decode()}')
            if line == b'connected.':
                commstat = 2
            elif line == b'disconnected.':
                commstat = 3
        for line in iter(err.readline, b''):
            print(f'[transferd:stderr] {line.decode()}')
        time.sleep(sleep_time)
    print('transferd_stdout_digest thread finished')
    # startcommunication() # this is to restart the startcomm process if it crashes


def msg_response(message):
    global remote_count_rate, localcountrate, low_count_side

    msg_split = message.split(':')[:]
    msg_code = msg_split[0]

    # Symmetry negtiations
    if msg_code == 'ne1':
        remote_count_rate = int(msg_split[1])
        send_message(f'ne2:{measure_local_count_rate()}:{msg_split[1]}')

    if msg_code == 'ne2':
        remote_count_rate = int(msg_split[1])
        if int(msg_split[2]) == localcountrate:
            send_message(f'ne3:{localcountrate}:{remote_count_rate}')
            if localcountrate <= remote_count_rate:
                low_count_side = True
                print('This is the low count side')
        else:
            print(
                '[msg_response] Local countrates do not agree. Symmetry negotiation failed.')

    if msg_code == 'ne3':
        if int(msg_split[2]) == localcountrate and int(msg_split[1]) == remote_count_rate:
            print('[msg_response] Symmetry negotiation succeeded.')
            if localcountrate < remote_count_rate:
                low_count_side = True
                print('[msg_response] This is the low count side.')
        else:
            print(
                '[msg_response] Remote count rates do not agree. Symmetry negotiation failed')


def msg_out_digest():
    global commhandle
    global read_timeout
    method_name = sys._getframe().f_code.co_name
    read_timeout = 0.01
    fd = os.open(f'{dataroot}/msgout', os.O_RDWR)  # non-blocking
    f = os.fdopen(fd, 'r')  # non-blocking
    while commhandle.poll() == None:
        # this is a non-blocking reader with a timeout. Only works on Unix
        readers = select.select([f], [], [], read_timeout)[0]
        if not readers:
            time.sleep(sleep_time)
        else:
            for r in readers:
                message = ((f.readline()).rstrip('\n')).lstrip('\x00')
                print(f'[{method_name}:read] {message}')
                msg_response(message)
    print(f'[{method_name}] Thread finished.')


def _t2logpipe_digest():
    global proc_chopper, t2logpipe_digest_thread_flag
    method_name = sys._getframe().f_code.co_name
    t2logpipe_digest_thread_flag = True
    fd = os.open(f'{dataroot}/t2logpipe', os.O_RDWR)  # non-blocking
    f = os.fdopen(fd, 'r')  # non-blocking

    while t2logpipe_digest_thread_flag == True:
        readers = select.select([f], [], [], sleep_time + 0.05)[0]
        if not readers:
            time.sleep(sleep_time)
        else:
            for r in readers:
                message = ((f.readline()).rstrip('\n')).lstrip('\x00')
                print(f'[{method_name}] {message}')
                # msg_response(message)
    print('t2logpipe_out_digest thread finished')

def _t1logpipe_digest():
    global proc_chopper, t1logpipe_digest_thread_flag
    method_name = sys._getframe().f_code.co_name
    t1logpipe_digest_thread_flag = True
    fd = os.open(f'{dataroot}/t1logpipe', os.O_RDWR)  # non-blocking
    f = os.fdopen(fd, 'r')  # non-blocking

    while t1logpipe_digest_thread_flag == True:
        readers = select.select([f], [], [], sleep_time)[0]
        if not readers:
            time.sleep(sleep_time)
        else:
            for r in readers:
                message = ((f.readline()).rstrip('\n')).lstrip('\x00')
                print(f'[{method_name}:read] {message}')
                # msg_response(message)
    print(f'[{method_name}] Thread finished.')


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
                             args=(commhandle.stdout, commhandle.stderr, q))
        t.start()
        # setup read thread for the msgout pipe
        msg_out_thread = threading.Thread(target=msg_out_digest, args=())
        msg_out_thread.start()
        time.sleep(sleep_time)


def send_message(message):
    f = os.open(f'{dataroot}/msgin', os.O_RDWR)
    os.write(f, f'{message}\n'.encode())
    print('[msgin write] Sent message: {}'.format(message))
    time.sleep(sleep_time)


def symmetry_negotiation():
    count_rate = measure_local_count_rate()
    send_message(f'ne1:{count_rate}')


def initiate_proto_negotiation():
    global wantprotocol, protocol
    protocol = 0  # disable protocol on asking
    sendmsg(f'pr1:{protocol}')


def start_raw_key_generation():
    global protocol
    method_name = sys._getframe().f_code.co_name
    if low_count_side is None:
        print(f'[{method_name}] Symmetry negotiation not finished.')
        return
    send_message('st1')
    if low_count_side:
        _start_input_part_1()
        _start_splicer()  # equal to start_digest_part_1
        # startinputpart1
        # startdigestpart1


def _splice_pipe_digest():
    global read_timeout
    method_name = sys._getframe().f_code.co_name
    print(f'[{method_name}] Starting splice_pipe_digest thread.')
    # t2logpipe_digest_thread_flag = True
    fd = os.open(f'{dataroot}/splicepipe', os.O_RDWR)  # non-blocking
    f = os.fdopen(fd, 'r')  # non-blocking
    fd_genlog = os.open(f'{dataroot}/genlog', os.O_RDWR)  # non-blocking
    f_genlog = os.fdopen(fd_genlog, 'r')  # non-blocking
    while proc_splicer.poll() is None:
        readers = select.select([f], [], [], sleep_time + 0.05)[0]
        if not readers:
            time.sleep(sleep_time)
        else:
            for r in readers:
                message = ((f.readline()).rstrip('\n')).lstrip('\x00')
                print(f'[{method_name}:splicepipe] {message}')
        readers = select.select([f_genlog], [], [], sleep_time + 0.05)[0]
        if not readers:
            time.sleep(sleep_time)
        else:
            for r in readers:
                message = ((f_genlog.readline()).rstrip('\n')).lstrip('\x00')
                print(f'[{method_name}:genlog] {message}')
                # msg_response(message)
    print(f'[{method_name}] Thread finished.')


def _start_splicer():
    '''
    Starts splicer
    '''
    global proc_splicer
    method_name = sys._getframe().f_code.co_name

    # thread_splicepipe_digest = threading.Thread(target=splicepipe_digest, args=())
    args = f'-d {cwd}/{dataroot}/t3 -D {dataroot}/receivefiles \
            -f {cwd}/{dataroot}/rawkey \
            -E {cwd}/{dataroot}/splicepipe \
            {kill_option} \
            -p {protocol} \
            -m {cwd}/{dataroot}/genlog'
    proc_splicer = subprocess.Popen([prog_splicer, *args.split()])
    print(f'[{method_name}] Started splicer process.')
    thread_splicepipe_digest = threading.Thread(target=_splice_pipe_digest,
                                                args=())
    thread_splicepipe_digest.start()


def _start_chopper():
    method_name = sys._getframe().f_code.co_name  # used for logging
    global proc_chopper, protocol, max_event_diff, low_count_side
    t2logpipe_thread = threading.Thread(target=_t2logpipe_digest, args=())
    cmd = f'{prog_chopper}'
    args = f'-i {cwd}/{dataroot}/rawevents \
            -D {cwd}/{dataroot}/sendfiles \
            -d {cwd}/{dataroot}/t3 \
            -l {cwd}/{dataroot}/t2logpipe \
            -V 3 -U -p {protocol} -Q 5 -F \
            -y 20 -m {max_event_diff}'

    if low_count_side is False:
        print(f'[{method_name}] Error: Not the low count rate or symmetry negotiation not completed.')
        return

    t2logpipe_thread.start()
    with open(f'{cwd}/{dataroot}/choppererror', 'a+') as f:
        proc_chopper = subprocess.Popen((cmd, *args.split()),
                                        stdout=subprocess.PIPE, stderr=f)
    print(f'[{method_name}] Started chopper.')

def _start_chopper2():
    global proc_chopper2, protocol, max_event_diff, low_count_side
    method_name = sys._getframe().f_code.co_name  # used for logging
    cmd = f'{prog_chopper2}'
    args = f'-i {cwd}/{dataroot}/rawevents \
            -l {cwd}/{dataroot}/t1logpipe -V 3 \
            -D {cwd}/{dataroot}/t1 -U -F \
            -m {maxeventdiff}'
    t1logpipe_thread = threading.Thread(target=_t1logpipe_digest, args=())

    t1logpipe_thread.start()
    if low_count_side is True:
        print(f'[{method_name}] Error: Not the low count rate or symmetry negotiation not completed.')
        return

    with open(f'{cwd}/{dataroot}/chopper2error', 'a+') as f:
        proc_chopper2 = subprocess.Popen((cmd, *args.split()),
                                        stdout=subprocess.PIPE, stderr=f)
    print(f'[{method_name}] Started chopper.')

def _start_readevents():
    '''
    Start reader and chopper on sender side (low-count side)
    '''
    method_name = sys._getframe().f_code.co_name  # used for logging
    global proc_readevents, prog_readevents
    args = f'-a 1 -R -A {extclockopt} -S 20 \
            -d {det1corr},{det2corr},{det3corr},{det4corr}'
    fd = os.open(f'{dataroot}/rawevents', os.O_RDWR)  # non-blocking
    f_stdout = os.fdopen(fd, 'w')  # non-blocking

    with open(f'{cwd}/{dataroot}/readeventserror', 'a+') as f_stderr:
        proc_readevents = subprocess.Popen((prog_readevents, *args.split()),
                                           stdout=f_stdout,
                                           stderr=f_stderr)
    print(f'[{method_name}] Started readevents.')


if __name__ == '__main__':
    if os.path.exists('tmp'):
        shutil.rmtree('tmp')
    _prepare_folders()
    _start_chopper()
    time.sleep(1)
    _start_readevents()
    # print(proc_chopper.pid, proc_readevents.pid)
    # print(proc_splicer.pid)
    time.sleep(5)
    kill_process(proc_chopper.pid)
    kill_process(proc_readevents.pid)
    t1logpipe_digest_thread_flag = False
    t2logpipe_digest_thread_flag = False
    # kill_process(proc_splicer.pid)
    # t2logpipe_digest_thread_flag = False
    # if os.path.exists('tmp'):
    #     shutil.rmtree('tmp')
