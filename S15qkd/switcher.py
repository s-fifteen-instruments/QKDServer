#!/usr/bin/env python

import time
import requests
from S15lib.instruments import TripleOpticalSwitch

class OpticalSwitch(object):
    def __init__(self, TOS_path: str = ""):
        if TOS_path is None:
            self.tos = TripleOpticalSwitch()
        else:
            self.tos = TripleOpticalSwitch(TOS_path)

        self._reset()

    def _reset(self):
        return

    def c(self, conn: int):
        if conn == 0: # c-g
            self.tos.route = (0,1,1)
        elif conn == 1: #d-g
            self.tos.route = (0,0,0)
        elif conn == 2: #c-d
            self.tos.route = (1,1,1)
        else:
            print(f"route undefined. Current route is: {self.tos.route}")

if __name__ == "__main__":
    tos = OpticalSwitch()

    def send_url(add:str, req: str, port_num: int = 8000):
        p_num = f":{port_num}"
        ret = requests.get(f"http://{add}{p_num}/{req}")
        return ret

    conn0 = [["c.qkd.internal", "set_conn/QKDE0006"],
             ["g.qkd.internal", "set_conn/QKDE0003"],
             0]

    conn1 = [["d.qkd.internal", "set_conn/QKDE0006"],
             ["g.qkd.internal", "set_conn/QKDE0004"],
             1]

    conn2 = [["c.qkd.internal", "set_conn/QKDE0004"],
             ["d.qkd.internal", "set_conn/QKDE0003"],
             2]
    def start(conn):
        add0 = conn[0][0]
        start_req = "start_keygen"
        ret = send_url(add0,start_req)
        if ret.status_code == 204:
           print(f"Starting key generation between {conn[0][0]} and {conn[1][0]}")
    def connect(conn):
        add0 = conn[0][0]
        req0 = conn[0][1]
        add1 = conn[1][0]
        req1 = conn[1][1]
        stop_req = "stop_keygen"
        #send_url(add0,stop_req)
        ret = send_url(add0,req0)
        print(ret.status_code)
        ret = send_url(add1,req1)
        print(ret.status_code)
        tos.c(conn[2])
        start(conn)
	
    conn = [conn0, conn1, conn2]
    i = 0
    wait_for = 30*60 #30 minutes switching
    while True:
        connect(conn[i])
        time.sleep(wait_for)
        if i == 2:
            i=0
        else:
            i+=1
