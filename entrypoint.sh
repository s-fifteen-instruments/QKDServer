#!/bin/sh
cd /root/code/qcrypto/remotecrypto \
	&& cd /root/code/QKDserver/S15qkd \
	&& python3 authd.py &
cd /root/code/QKDserver \
        && pip install -e . \
        && cd /root/code/QKDserver/Settings_WebClient \
        && gunicorn --threads=1 -b 0.0.0.0:8000 index:server

#&& apk add gcc build-base clang \
