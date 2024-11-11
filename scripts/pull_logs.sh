#!/bin/sh
# Pulls only relevant QKDServer logs, ignoring

datestamp=$1
host=$2
target=logs/${datestamp}/cryptostuff_${host}

mkdir -p ${target}

function backup() {
    docker cp qkd:/tmp/cryptostuff/$1 ${target}
}

# Connection
backup authd.err
backup debuglog

# Event handling
backup readeventserror
backup choppererror
backup chopper2error
backup pfinderror
backup fpfinderror
backup cmdins
backup rawpacketindex
backup costreamerror
backup histos
backup splicer_stderr
backup splicer_stdout
backup errcd_stdout
backup errcd_stderr

# Keying material, for additional debugging
#backup t1
#backup t3
#backup sendfiles
#backup receivefiles
#backup rawkey
