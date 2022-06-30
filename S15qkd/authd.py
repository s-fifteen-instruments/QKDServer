#!/usr/bin/env python3
# Justin 2022-01-21
# TODO: Figure out workaround for NULL-SHA256 (authentication RSA, encryption NULL)
# Some issues faced:
# - Python 3.6 does not support _disabling_ using 'ssl.Options.OP_NO_TLSv1_3',
#   introduced only in 3.7+, see: https://docs.python.org/3/library/ssl.html#ssl.OP_NO_TLSv1_3.
#   Note minor version can be checked with 'sys.version_info.minor'.
# - Python 3.8.8 seems to face difficulties in setting maximum TLS version, at least
#   as shown in SSL_CONTEXT_*.get_ciphers()
# - Forcing 'NULL-SHA256' with SSL_CONTEXT_*.maximum_version = ssl.TLSVersion.TLSv1_2 yields
#   'ssl.SSLError: [SSL: UNEXPECTED_MESSAGE] unexpected message (_ssl.c:1125)' error.
#   This is with OpenSSL 1.1.1d (Sep 2019)

import select
import socket
import ssl
import sys

# For bookkeeping only
import json
import logging
import time
import traceback
from types import SimpleNamespace
import qkd_globals

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y%m%d_%H%M%S"
)
logger = logging.getLogger(__name__)

#with open("authd.conf.json") as f:
#    config = json.load(f)
#HOSTNAME = config["target_hostname"]
#PORT = config["port_authd"]
#PORT_TD = config["port_transd"]
#REMOTE_CERT = config["remote_cert"]
#LOCAL_CERT = config["local_cert"]
#LOCAL_KEY = config["local_key"]
with open(qkd_globals.config_file, 'r') as f:
    config = json.load(f, object_hook=lambda d: SimpleNamespace(**d))
HOSTNAME = config.target_hostname
PORT = config.port_authd
PORT_TD = config.port_transd
REMOTE_CERT = config.remote_cert
LOCAL_CERT = config.local_cert
LOCAL_KEY = config.local_key

SSL_CONTEXT_CLIENT = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
SSL_CONTEXT_CLIENT.load_verify_locations(cafile=REMOTE_CERT)
SSL_CONTEXT_CLIENT.load_cert_chain(LOCAL_CERT, LOCAL_KEY)
SSL_CONTEXT_CLIENT.verify_mode = ssl.CERT_REQUIRED
SSL_CONTEXT_CLIENT.check_hostname = False

SSL_CONTEXT_SERVER = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
SSL_CONTEXT_SERVER.load_verify_locations(cafile=REMOTE_CERT)
SSL_CONTEXT_SERVER.load_cert_chain(LOCAL_CERT, LOCAL_KEY)
SSL_CONTEXT_SERVER.verify_mode = ssl.CERT_REQUIRED

def connect_as_authd_client(hostname, port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
    conn = SSL_CONTEXT_CLIENT.wrap_socket(sock, server_hostname=hostname)
    logger.debug(f"Attempting connection as client to {hostname}:{port}.")
    conn.connect((hostname, port))
    conn.setblocking(False)
    logger.info(f"Connected as client to authd at {hostname}:{port} with {conn.cipher()}.")
    return conn, sock

def connect_as_authd_server(server_socket):
    logger.info(f"Waiting for connection with authd...")
    sock, addr = server_socket.accept()  # blocking
    conn = SSL_CONTEXT_SERVER.wrap_socket(sock, server_side=True)
    conn.setblocking(False)
    logger.info(f"Connected as server to authd at {addr[0]}:{addr[1]} with {conn.cipher()}.")
    return conn, sock

def connect_as_transferd_server(server_socket):
    logger.info(f"Waiting for connection with transferd...")
    conn, addr = server_socket.accept()
    conn.setblocking(False)
    logger.info(f"Connected as server to transferd at {addr[0]}:{addr[1]}.")
    return conn

def listen_as_server(addr: str = "0.0.0.0", port: int = 55555) -> socket.socket:
    ssock = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
    ssock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # reuse port address
    ssock.bind((addr, port))
    ssock.listen()
    logger.info(f"Listening as server on {port}/tcp for connections...")
    return ssock

# Handle terminating program
try:
    ssock_td = ssock = sock = conn_td = conn = None
    
    # Listen for incoming ipv4 TCP connections from local transferd
    ssock_td = listen_as_server("127.0.0.1",port = PORT_TD)

    # Setup connection with remote authd, first as a client,
    # failing which, listen for connections as server
    try:
        is_server = False
        conn, sock = connect_as_authd_client(HOSTNAME, PORT)

    except (ConnectionRefusedError, OSError):
        is_server = True
        ssock = listen_as_server(port = PORT)
        conn, sock = connect_as_authd_server(ssock)

    # Setup connection with local 'transferd'
    conn_td = connect_as_transferd_server(ssock_td)

    # Internal authd buffer, in case of asymmetric transfer rates
    # See https://stackoverflow.com/a/57748513 for amortized O(1) bytearray pop_front
    to_remote = bytearray()
    to_local = bytearray()

    # Main loop, make sure connections stay up
    while True:

        # Make sure authd connection is available
        if conn is None:
            logger.info("Attempting reconnection to authd.")
            if is_server:
                conn, sock = connect_as_authd_server(ssock)
            else:
                while True:
                    try:
                        conn, sock = connect_as_authd_client(HOSTNAME, PORT)
                        break
                    except (ConnectionRefusedError, OSError):
                        logger.info(f"Failed to connect as client to {HOSTNAME}:{PORT}. "
                            "Trying again after 10 seconds...")
                        time.sleep(10)

        # Make sure transferd connection is available
        if conn_td is None:
            logger.info("Attempting reconnection to transferd.")
            conn_td = connect_as_transferd_server(ssock_td)

        # Handle connection error / dropouts
        try:
        
            # All connections available, loop me
            # TODO: Use separate processes for each pipe, if authd is throttling
            while True:
                conn_list = [conn, conn_td]
                # TODO: Do something with the exceptions from select call
                readables, writeables, exceptionals = select.select(
                    conn_list, conn_list, [], 0)

                for c in readables:
                    if c is conn_td:
                        msg = c.recv(1023)  # transferd max message length = 1023 bytes
                        logger.debug(f"[transferd  ->] {repr(msg)}")
                        if msg == b"":
                            conn_td = None
                            raise IOError("transferd disconnected.")
                        to_remote += msg
                    elif c is conn:
                        try:
                            msg = c.recv(2048)  # hardcoded
                        except ssl.SSLWantReadError:
                            logger.warning("Problematic SSL handshake. Ignoring.")
                            continue
                        logger.debug(f"[  authd    ->] {repr(msg)}")
                        if msg == b"":
                            conn = None
                            raise IOError("authd disconnected.")
                        to_local += msg

                for c in writeables:
                    if c is conn_td and to_local:
                        msg = to_local[:1023]
                        del to_local[:1023]
                        logger.debug(f"[transferd <- ] {repr(bytes(msg))}")
                        c.send(msg)
                    elif c is conn and to_remote:
                        msg = to_remote[:2048]  # hardcoded
                        del to_remote[:2048]  # hardcoded
                        logger.debug(f"[  authd   <- ] {repr(bytes(msg))}")
                        c.send(msg)

        except KeyboardInterrupt:
            break  # Ignore user-termination
        except:
            # Handle connection error / dropouts
            error = traceback.format_exc().split("\n")[-2]  # get _latest_ error
            logger.error(error)
            continue

except KeyboardInterrupt:
    pass  # Ignore user-termination
finally:
    # Handle terminating program
    # TODO: Check if need to shutdown socket on other end with 'socket.SHUT_RDWR'
    if conn_td: conn_td.close()
    if ssock_td: ssock_td.close()
    if conn: conn.close()
    if sock: sock.close()
    if ssock: ssock.close()
