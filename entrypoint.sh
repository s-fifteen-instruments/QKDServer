#!/bin/sh
#cd /root/code/qcrypto/remotecrypto \
#        && gcc -o transferd transferd.c \
#        && unlink errcd \
#        && ln -s ../errorcorrection/ecd2 errcd \

# Install dependencies
cd /root/code/QKDserver && pip install -e .

# Start authd in subprocess
# Note authd will automatically terminate when this script (gunicorn) exits
cd /root/code/QKDserver/S15qkd && python3 authd.py &

# Run and persist server
cd /root/code/QKDserver/Settings_WebClient \
        && gunicorn --threads=1 -b 0.0.0.0:8000 index:server

#&& apk add gcc build-base clang \
