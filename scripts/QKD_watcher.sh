#!/bin/bash

# This is a script to check the status of the QKD detectors on both sides to
# ensure that they are in a normally functional and coherent state. If any
# incoherence occurs in their states, then an automatic restart connection
# and start key generation is executed.
#
# To periodically run script, add to crontab or install as a service.
#
# Changelog:
#       2024-10-18 Syed: Initial script for QKDEngine watcher

hostnameA=a
hostnameB=b
CERT=~/guardian/common/full-chain.cert.pem
CERT_FLAGS=
if [ -f "$CERT" ]; then
        CERT_FLAGS="--cacert ${CERT}"
        addA=https://$hostnameA:8000/status_data
        addB=https://$hostnameB:8000/status_data
        restart_tdA=https://$hostnameA:8000/restart_transferd
        restart_tdB=https://$hostnameB:8000/restart_transferd
        restart_connA=https://$hostnameA:8000/restart_connection
        restart_connB=https://$hostnameB:8000/restart_connection
        start_keygenA=https://$hostnameA:8000/start_keygen
        stop_keygenA=https://$hostnameA:8000/stop_keygen
        stop_keygenB=https://$hostnameB:8000/stop_keygen
else
        addA=http://$hostnameA:8000/status_data
        addB=http://$hostnameB:8000/status_data
        restart_tdA=http://$hostnameA:8000/restart_transferd
        restart_tdB=http://$hostnameB:8000/restart_transferd
        restart_connA=http://$hostnameA:8000/restart_connection
        restart_connB=http://$hostnameB:8000/restart_connection
        start_keygenA=http://$hostnameA:8000/start_keygen
        stop_keygenA=http://$hostnameA:8000/stop_keygen
        stop_keygenB=http://$hostnameB:8000/stop_keygen
fi

prog="curl -s ${CERT_FLAGS}"
qkd_statusA=$($prog $addA)
qkd_statusB=$($prog $addB)
stateA=$(echo $qkd_statusA | jq -r .status_info.state?)
stateB=$(echo $qkd_statusB | jq -r .status_info.state?)

# Compare states here. Good possible states are (B and A):
# PEAK_FINDING & SERVICE_MODE
# PEAK_FINDING & KEY_GENERATION
# SERVICE_MODE & SERVICE_MODE
# KEY_GENERATION & KEY_GENERATION
# ONLY_COMMUNICATION & ONLY_COMMUNICATION
# 
# Any other combination of "OFF", "ONLY_COMMUNICATION", "PEAK_FINDING",
# "SERVICE_MODE" and "KEY_GENERATION" are typically incorrect behaviour

off=OFF
key=KEY_GENERATION
ser=SERVICE_MODE
com=ONLY_COMMUNICATION
pkf=PEAK_FINDING
ini=INITIATING

restart=0
date=$(date -R)
if [[ "${stateA}" =~ ($off|$com|$ini)$ &&  "${stateB}" =~ ($off|$com)$ ]]; then
        if [[ "${stateA}" == "${stateB}" ]]; then
                echo "$date Both idle or not working"
                exit 0
        else
                echo "$date Mismatch in idle"
                restart=1
        fi
fi

if [[ "${stateA}" =~ ($key|$ser)$ && ! "${stateB}" =~ ($key|$ser|$pkf)$ ]]; then
        echo "$date A in running but B is not"
        restart=1
fi

if [[ "${stateB}" =~ ($key|$ser|$pkf)$ && ! "${stateA}" =~ ($key|$ser)$ ]]; then
        echo "$date B in running but A is not"
        restart=1
fi

if [ ${restart} == 1 ] ; then
        echo "$date Restarting transferd and key_generation"
        $prog $stop_keygenA &
        $prog $stop_keygenB &
        $prog $stop_keygenA 
        $prog $stop_keygenB
        $prog $restart_connB &
        sleep 1
        $prog $restart_connA
        sleep 5
        $prog $stop_keygenA &
        $prog $stop_keygenB &
        $prog $stop_keygenA 
        $prog $stop_keygenB
        $prog $start_keygenA
fi
