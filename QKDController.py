import subprocess
import os
import signal
import time
import psutil

dataroot = 'tmp/cryptostuff'
programroot = 'bin'
cwd = os.getcwd()
extclockopt = "-e"  # clock
localcountrate = -1
testing = 1  # CHANGE to 0 if you want to run it with hardware
if testing == 1:
    # this outputs one timestamp file in an endless loop. This is for testing only.
    prog_readevents = './out_timestamps.sh'
else:
    prog_readevents = programroot + '/readevents3'
prog_getrate = programroot + '/getrate'


def kill_process(proc_pid):
    process = psutil.Process(proc_pid)
    for proc in process.children(recursive=True):
        proc.kill()
    process.kill()


def measure_local_count_rate():
    '''
    Measure local photon count rate
    '''
    global programroot, dataroot, localcountrate, extclockopt, cwd
    localcountrate = -1
    p1 = subprocess.Popen((prog_readevents, '-a 1',
                           '-F',
                           '-u {extclockopt}',
                           '-S 20'),
                          stdout=subprocess.PIPE)
    p2 = subprocess.Popen(prog_getrate, stdin=p1.stdout,
                          stdout=subprocess.PIPE)
    p2.wait()
    try:
        kill_process(p1.pid)
        kill_process(p2.pid)
    except psutil.NoSuchProcess as a:
        pass

    localcountrate = (p2.stdout.read()).decode()
    with open(f"{dataroot}/rawevents", "w") as f:
        f.write(localcountrate)
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


def startcommunication():
    global debugval, commhandle, commstat, programroot, commprog, dataroot
    global portnum, targetmachine, receivenotehandle

    if commstat == 0:
        pass  # needs to be implemented
        # removestalecommfiles
        # capture file receipt notes
        # set receivenotehandle [open $dataroot / transferlog r + ]
        # set commhandle[open "|$programroot/$commprog -d $dataroot/sendfiles -c $dataroot/cmdpipe -t $targetmachine -D $dataroot/receivefiles -l $dataroot/transferlog -m $dataroot/msgin -M $dataroot/msgout -p $portnum -k -e $dataroot/ecspipe -E $dataroot/ecrpipe " r]
        # fconfigure $commhandle - blocking false
        # fileevent $commhandle readable digesttransferresponse
        # set commstat 1


if __name__ == '__main__':
    print(measure_local_count_rate())
