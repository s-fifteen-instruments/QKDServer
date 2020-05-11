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

__author__ = 'Mathias Alexander Seidler'
__copyright__ = 'Copyright 2020, S-Fifteen Instruments Pte. Ltd.'
__credits__ = ['']
__license__ = 'MIT'
__version__ = '0.0.1'
__maintainer__ = 'Mathias Seidler'
__email__ = 'mathias.seidler@s-fifteen.com'
__status__ = 'dev'

import json
import subprocess
import threading
import os
from queue import Queue, Empty
import time
import sys
import psutil


def load_transferd_config(config_file_name: str):
    global dataroot, programroot, target_ip, port_num, extclockopt
    with open(config_file_name, 'r') as f:
        config = json.load(f)
    dataroot = config['data_root']
    protocol = config['protocol']
    programroot = config['program_root']
    target_ip = config['target_ip']
    port_num = config['port_num']
    extclockopt = config['clock_source']


load_transferd_config('config/config.json')
cwd = os.getcwd()
proc_splicer = None
sleep_time = 1
prog_transferd = programroot + '/transferd'
prog_getrate = programroot + '/getrate'
communication_status = 0
low_count_side = None
remote_count_rate = -1
local_count_rate = -1
commhandle = None
first_received_epoch = None

testing = 1  # CHANGE to 0 if you want to run it with hardware
if testing == 1:
    prog_readevents = 'timestampsimulator/readevents_simulator.sh'
    # prog_readevents = 'helper_script/readevents_simulator.sh'
else:
    prog_readevents = programroot + '/readevents3'


def _local_callback(msg: str):
    '''
    The transferd process has a msgout pipe which contains received messages.
    Usually we let an external script manage the response to theses messages, 
    however when no response function is defined this function is used as a default response.

    [description]

    Arguments:
        msg {str} -- Contains the messages received in the msgout pipe.
    '''
    method_name = sys._getframe().f_code.co_name
    print(f'[{method_name}] The msgout pipe is printed locally by the transferd modul.\n\
          Define a callback function in start_communication to digest the msgout output in your custom function.')
    print(msg)


def start_communication(msg_out_callback=_local_callback):
    global debugval, commhandle, commstat, programroot, commprog, dataroot
    global portnum, targetmachine, receivenotehandle
    global commhandle

    args = f'-d {cwd}/{dataroot}/sendfiles -c {cwd}/{dataroot}/cmdpipe -t {target_ip} \
            -D {cwd}/{dataroot}/receivefiles -l {cwd}/{dataroot}/transferlog \
            -m {cwd}/{dataroot}/msgin -M {cwd}/{dataroot}/msgout -p {port_num} \
            -k -e {cwd}/{dataroot}/ecspipe -E {cwd}/{dataroot}/ecrpipe'
    q = Queue()  # I don't know why I need this but it works

    msg_out_thread = threading.Thread(target=_msg_out_digest,
                                      args=[msg_out_callback])
    transferlog_thread = threading.Thread(
        target=_transferlog_digest, args=())

    if communication_status == 0:
        # _remove_stale_comm_files()
        commhandle = subprocess.Popen((prog_transferd, *args.split()),
                                      stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE)
        print(args)
        # setup read thread for the process stdout
        t = threading.Thread(target=_transferd_stdout_digest,
                         args=(commhandle.stdout, commhandle.stderr, q))
        t.start()

        # setup read thread for the msgout pipe
        msg_out_thread.start()
        # setup read thread fro the transferlog
        transferlog_thread.start()
        time.sleep(0.1)  # give some time to connect to the partnering computer
        return commhandle  # returns the process handle


def _transferd_stdout_digest(out, err, queue):
    global commhandle, commstat
    method_name = sys._getframe().f_code.co_name
    print(f'[{method_name}] Thread started.')
    while commhandle.poll() is None:
        time.sleep(0.05)
        for line in iter(out.readline, b''):
            line = line.rstrip()
            print(f'[transferd:stdout] {line.decode()}')
            if line == b'connected.':
                commstat = 2
            elif line == b'disconnected.':
                commstat = 3
        for line in iter(err.readline, b''):
            print(f'[transferd:stderr] {line.decode()}')

    print(f'[{method_name}] Thread finished')
    # startcommunication() # this is to restart the startcomm process if it crashes


def _msg_out_digest(msg_out_callback):
    global commhandle
    method_name = sys._getframe().f_code.co_name
    pipe_name = f'{dataroot}/msgout'
    fd = os.open(pipe_name, os.O_RDONLY | os.O_NONBLOCK)
    f = os.fdopen(fd, 'rb', 0)  # non-blocking
    print(f'[{method_name}] Thread started.')
    while commhandle.poll() is None:
        time.sleep(0.1)
        try:
            message = f.readline().decode().lstrip('\x00').rstrip('\n')
            if len(message) == 0:
                continue
            print(f'[{method_name}:read] {message}')
            if message.split(':')[0] in {'ne1', 'ne2', 'ne3'}:
                _symmetry_negotiation_messaging(message)
            else:
                msg_out_callback(message)
        except OSError as a:
            pass
    print(f'[{method_name}] Thread finished')


def _transferlog_digest():
    '''
    Digests the transferlog which is written by the transferd process.

    This function usually runs as a thread and
    watches the transferlog file.
    '''
    global first_received_epoch, low_count_side
    method_name = sys._getframe().f_code.co_name
    log_file_name = f'{dataroot}/transferlog'
    splicer_pipe = f'{dataroot}/splicepipe'
    fd = os.open(log_file_name, os.O_RDONLY | os.O_NONBLOCK)
    f = os.fdopen(fd, 'rb', 0)  # non-blocking
    print(f'[{method_name}] Thread started.')
    while commhandle.poll() is None:
        time.sleep(0.1)
        try:
            message = f.readline().decode().rstrip()
            if len(message) == 0:
                continue
            print(f'[{method_name}:read] {message}')
            if first_received_epoch is None:
                first_received_epoch = message
                print(f'[{method_name}:first_rx_epoch] {first_received_epoch}')
            if low_count_side is True:
                _writer(splicer_pipe, message)
                print(f'[{method_name}] Sent epoch name {message} to splicer.')
        except OSError:
            pass
    print(f'[{method_name}] Thread finished.')


def _symmetry_negotiation_messaging(message):
    global remote_count_rate, local_count_rate, low_count_side
    method_name = sys._getframe().f_code.co_name
    msg_split = message.split(':')[:]
    msg_code = msg_split[0]

    if local_count_rate == -1:
        local_count_rate = measure_local_count_rate()

    if msg_code == 'ne1':
        remote_count_rate = int(msg_split[1])
        send_message(f'ne2:{local_count_rate}:{msg_split[1]}')

    if msg_code == 'ne2':
        remote_count_rate = int(msg_split[1])
        if int(msg_split[2]) == local_count_rate:
            send_message(f'ne3:{local_count_rate}:{remote_count_rate}')
            if local_count_rate <= remote_count_rate:
                low_count_side = True
                print(f'[{method_name}:ne2] This is the low count side.')
            else:
                low_count_side = False
                print(f'[{method_name}:ne2] This the high count side.')
        else:
            print(f'[{method_name}:ne2] Local countrates do not agree. \
                    Symmetry negotiation failed.')

    if msg_code == 'ne3':
        if int(msg_split[2]) == local_count_rate and int(msg_split[1]) == remote_count_rate:
            if local_count_rate < remote_count_rate:
                low_count_side = True
                print(f'[{method_name}:ne3] This is the low count side.')
            else:
                low_count_side = False
                print(f'[{method_name}:ne3] This is the high count side.')
            print(f'[{method_name}:ne3] Symmetry negotiation succeeded.')
        else:
            print(f'[{method_name}:ne3] Count rates in the messages do not agree. \
                Symmetry negotiation failed')


def _kill_process(proc_pid):
    if proc_pid is not None:
        method_name = sys._getframe().f_code.co_name
        # print(f'[{method_name}] Killing process: {proc_pid.pid}.')
        process = psutil.Process(proc_pid.pid)
        for proc in process.children(recursive=True):
            proc.kill()
        process.kill()


def stop_communication():
    if commhandle.poll() is None:
        _kill_process(commhandle)


def send_message(message):
    method_name = sys._getframe().f_code.co_name
    _writer(f'{dataroot}/msgin', message)
    print(f'[{method_name}:write] {message}')
    time.sleep(sleep_time)


def symmetry_negotiation():
    # global commhandle
    method_name = sys._getframe().f_code.co_name
    count_rate = measure_local_count_rate()
    if commhandle.poll() is None:
        send_message(f'ne1:{count_rate}')
    else:
        print(f'[{method_name}] Transferd process not running.')


def measure_local_count_rate():
    '''
    Measure local photon count rate.
    '''
    global programroot, dataroot, localcountrate, extclockopt
    localcountrate = -1

    p1 = subprocess.Popen((prog_readevents,
                           '-a 1',
                           '-F',
                           f'-u {extclockopt}',
                           '-S 20'),
                          stdout=subprocess.PIPE)
    p2 = subprocess.Popen(prog_getrate,
                          stdin=p1.stdout,
                          stdout=subprocess.PIPE)
    p2.wait()
    try:
        _kill_process(p1)
        _kill_process(p2)
    except psutil.NoSuchProcess as a:
        pass
    localcountrate = int((p2.stdout.read()).decode())
    return localcountrate


def _writer(file_name, message):
    f = os.open(file_name, os.O_WRONLY)
    os.write(f, f'{message}\n'.encode())
    os.close(f)


def main():
    start = time.time()
    print('start communication')
    start_communication()
    time.sleep(1)
    print('start symmetry negotiation')
    symmetry_negotiation()
    print(time.time() - start)
    stop_communication()


if __name__ == '__main__':
    main()
