#!/bin/sh
#cd /root/code/qcrypto/remotecrypto \
#        && gcc -o transferd transferd.c \
#        && unlink errcd \
#        && ln -s ../errorcorrection/ecd2 errcd \

# Install dependencies
#cd /root/code/QKDserver && pip install -e .

# Start authd in subprocess
# Note authd will automatically terminate when this script (gunicorn) exits
cd /root/code/QKDserver/S15qkd && python3 authd.py &

# Optionally adds server certificate if cert/key pair exists in 'certs' subdirectory
CERT=/root/code/QKDserver/Settings_WebClient/certs/cert.crt
KEY=/root/code/QKDserver/Settings_WebClient/certs/cert.key
CERT_FLAGS=
if [ -f "$CERT" ] && [ -f "$KEY" ]; then
        CERT_FLAGS="--certfile=certs/cert.crt --keyfile=certs/cert.key"
fi

# Run and persist server
cd /root/code/QKDserver/Settings_WebClient \
        && gunicorn --threads=1 $CERT_FLAGS -b 0.0.0.0:8000 index:server

#&& apk add gcc build-base clang \
