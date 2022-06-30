#!/bin/sh

# Propagate local qcrypto changes (see Makefile regarding code injection), e.g.
# cd /root/code/qcrypto/remotecrypto \
#        && apk add gcc build-base clang \
#        && gcc -o transferd transferd.c \
#        && unlink errcd \
#        && ln -s ../errorcorrection/ecd2 errcd \

# Propagate local QKD server changes (see Makefile regarding code injection), e.g.
# Comment this line out in production environment.
cd /root/code/QKDserver && pip install -e .

# Start authd in subprocess
# Note authd will automatically terminate when this script (gunicorn) exits
cd /root/code/QKDserver/S15qkd && python3 authd.py &

# Run and persist server
cd /root/code/QKDserver/Settings_WebClient \
        && gunicorn --threads=1 -b 0.0.0.0:8000 index:server
