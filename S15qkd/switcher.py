#!/usr/bin/env python

import time
import requests
import threading
from S15lib.instruments import TripleOpticalSwitch

class OpticalSwitch(TripleOpticalSwitch):
    """
    Subclass with routing defined
    """
    def c(self, conn: int):
        """
        Connections depends on internal fiber connections to external outputs.
        May change on subsequent updates.
        """
        if conn == 0: # c-g
            self.route = (0,1,1)
        elif conn == 1: #d-g
            self.route = (0,0,0)
        elif conn == 2: #c-d
            self.route = (1,1,1)
        else:
            print(f"route undefined. Current route is: {self.route}")

class NetworkSwitchController(OpticalSwitch):
    """
    Class with network connections defined
    """
    def __init__(self, connections):
        self.conns = connections
        self.curr_conn = None
        self.threadlock = threading.Event()
        super().__init__()

    def send_url(self, add:str, req: str, port_num: int = 8000):
        p_num = f":{port_num}"
        try:
            ret = requests.get(f"http://{add}{p_num}/{req}")
        except:
            print("error")
            ret = requests.models.Response()
            ret.status_code = 504
        return ret

    def start(self, conn = None):
        if conn is None and self.curr_conn is None:
            print("Error, no connections defined")
            return
        elif conn is None:
            conn = self.curr_conn
        add0 = conn['add0']
        add1 = conn['add1']
        self.curr_conn = conn
        start_req = "start_keygen"
        ret = self.send_url(add0,start_req)
        if ret.status_code == 204:
            print(f"Starting key generation between {add0} and {add1}")

    def status(self, conn = None):
        if conn is None and self.curr_conn is None:
            print("Error, no connections defined")
            return
        elif conn is None:
            conn = self.curr_conn
        add0 = conn['add0']
        add1 = conn['add1']
        self.curr_conn = conn
        status_req = "status_keygen"
        ret = self.send_url(add0,status_req)
        ret1 = self.send_url(add1,status_req)
        if ret.status_code == 200 and ret1.status_code == 200 :
            print(f"Error correction running on {add0} and {add1}")
        if ret.text == ret1.text:
            return ret.text

    def stop(self, conn = None):
        if conn is None and self.curr_conn is None:
            print("No connections defined, stopping all")
            self.stop(self.conns['conn0'])
            self.stop(self.conns['conn1'])
            self.stop(self.conns['conn2'])
            return
        elif conn is None:
            conn = self.curr_conn
        add0 = conn['add0']
        add1 = conn['add1']
        self.curr_conn = conn
        stop_req = "stop_keygen"
        ret = self.send_url(add0,stop_req)
        ret1 = self.send_url(add1,stop_req)
        if ret.status_code == 204:
            print(f"Stopping key generation between {add0} and {add1}")

    def connect(self, conn):
        add0 = conn['add0']
        req0 = conn['req0']
        add1 = conn['add1']
        req1 = conn['req1']
        while True:
            ret1 = self.send_url(add0,req0)
            print(add0,ret1.status_code)
            ret2 = self.send_url(add1,req1)
            print(add1,ret2.status_code)
            if ret1.status_code == 204 and ret2.status_code == 204:
                break
        self.c(conn['route'])
        self.curr_conn = conn

    def begin(self, wait=20):
        def func():
            if self.curr_conn is None:
                i = 0
            else:
                i = int([j for j in self.conns if self.conns[j] == self.curr_conn][0][-1])
            wait_for = wait*60 #wait minutes switching
            print(f"Beginning switching cycle for {wait} minutes each")
            self.connect(self.conns[f'conn{i}'])
            self.start()
            end_time = time.time() + wait_for
            while not self.threadlock.is_set():
                if time.time() < end_time:
                    continue
                self.stop()
                if i == 2:
                    i = 0
                else:
                    i += 1
                self.connect(self.conns[f'conn{i}'])
                self.start()
                end_time = time.time() + wait_for

            print(f"Thread ended")
            self.stop()
            self.threadlock.clear()
        self.thread = threading.Thread(target = func)
        self.thread.start()

    def end(self):
        self.threadlock.set()

    def is_running(self):
        if hasattr(self,'thread'):
            return self.thread.is_alive()
        else:
            return False

import json
config_file = '/root/code/QKDSource/Settings_WebClient/config.json'
with open(config_file, 'r') as f:
    config = json.load(f)
conn = config['connections']

nsc = NetworkSwitchController(conn)

def status():
   return nsc.status()
def begin():
   return nsc.begin()
def end():
   return nsc.end()

if __name__ == "__main__":
    conn = {'conn0': {
                'add0': 'c.qkd.internal',
                'req0': 'set_conn/QKDE0006',
                'add1': 'g.qkd.internal',
                'req1': 'set_conn/QKDE0003',
                'route': 0
                },
            'conn1': {
                'add0': 'd.qkd.internal',
                'req0': 'set_conn/QKDE0006',
                'add1': 'g.qkd.internal',
                'req1': 'set_conn/QKDE0004',
                'route': 1
                },
            'conn2': {
                'add0': 'c.qkd.internal',
                'req0': 'set_conn/QKDE0004',
                'add1': 'd.qkd.internal',
                'req1': 'set_conn/QKDE0003',
                'route': 2
                }
            }

    nsc = NetworkSwitchController(conn)
    def begin():
        nsc.begin(wait = 4) #wait in minutes
        time.sleep(10)
        endtime= time.time() + 15*60
        while time.time() < endtime:
            nsc.status(nsc.curr_conn)
            time.sleep(30)
        nsc.end()
