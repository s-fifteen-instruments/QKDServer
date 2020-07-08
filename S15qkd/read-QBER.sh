#!/bin/bash
IFS=' '
#for i in {1..100..1}; do
sleep 0.7s
lastline=$(tail -n 1 /tmp/cryptostuff/diagnosis_log)
#echo $lastline
read -ra temp <<< "$lastline"
let qber1=${temp[0]} + ${temp[5]} + ${temp[10]} + ${temp[15]} 
let qber2=${temp[0]} + ${temp[5]} + ${temp[10]} + ${temp[15]} + ${temp[2]} + ${temp[7]} + ${temp[8]} + ${temp[13]}
qber=$(bc -l <<< $qber1/$qber2)
#echo $lastline
echo 0$qber
#done
