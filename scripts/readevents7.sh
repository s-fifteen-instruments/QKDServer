#!/bin/sh
conf=S15qkd/qkd_engine_config.json

delays=$(jq '.local_detector_skew_correction[]' $conf | tr '\n' ',' | head -c -1)

ttl=$(jq '.qcrypto.readevents.use_ttl_trigger' $conf)
ttl=$([[ "$ttl" = "true" ]] && echo "-t2032" || echo "")

fast=$(jq '.qcrypto.readevents.use_fast_mode' $conf)
fast=$([[ "$fast" = "true" ]] && echo "-f" || echo "")

prog="readevents7 -A -a1 $ttl $fast -D$delays"
echo "Running: '$prog'" >&2
exec $prog
