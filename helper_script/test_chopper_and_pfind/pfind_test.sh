#!/usr/bin/env bash

# change the prog_path to the folder containing the chopper/chopper2/pfind executables.
prog_path=/Users/mathias/Documents/GitHub/qcrypto/remotecrypto

rm -r type1
rm -r type2
rm -r type3
mkdir type1
mkdir type2
mkdir type3

echo 'Start chopper2'
$prog_path/chopper2 -i *alice*.ts -D type1
echo 'Chopper2 done'

echo 'Start chopper'
$prog_path/chopper -i *bob*.ts -D type2 -d type3& # this process does not terminate by itself.
chopperpid=$!
sleep 2 # adjust if this is too short
kill -9 $chopperpid;
echo 'Chopper done' 

echo 'Start pfind'
startepoch=`comm -12 <(ls type2) <(ls type1) | head -n 3 | tail -n 1` #get the 1st common epoch
# echo $startepoch
$prog_path/pfind -D type1 -d type2 -e "0x$startepoch" -V 3 -r 1 -q 17 -n 5