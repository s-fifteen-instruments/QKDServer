#!/bin/sh

# Set timezone
TZ="Asia/Singapore"
echo ${TZ} > /etc/timezone
rm -rf /etc/localtime
ln -s /usr/share/zoneinfo/${TZ} /etc/localtime

# Optionally adds server certificate if cert/key pair exists in 'certs' subdirectory
CERT=/root/code/QKDServer/Settings_WebClient/certs/cert.crt
KEY=/root/code/QKDServer/Settings_WebClient/certs/cert.key
CERT_FLAGS=
if [ -f "$CERT" ] && [ -f "$KEY" ]; then
        CERT_FLAGS="--certfile=certs/cert.crt --keyfile=certs/cert.key"
fi

# Run and persist server
cd /root/code/QKDServer/Settings_WebClient \
        && gunicorn --timeout 30 --worker-connections=1 --threads=1 $CERT_FLAGS -b 0.0.0.0:8000 index:server

