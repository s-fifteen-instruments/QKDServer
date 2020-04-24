#!/bin/sh
cwd=`pwd`
dataroot=$cwd'/tmp/cryptostuff' 

makedirectories () {
	rm -r $dataroot
    mkdir $dataroot
    for i in t1 t3 rawkey receivefiles sendfiles histos finalkey
    do
    	mkdir $dataroot/$i 
    done

    for i in msgin msgout rawevents t1logpipe t2logpipe cmdpipe genlog transferlog splicepipe cntlogpipe eccmdpipe ecspipe ecrpipe ecnotepipe ecquery ecresp:
    do
    	mkfifo $dataroot/$i
    done

}


startcommunication () {
    ./transferd -d $dataroot/sendfiles -c $dataroot/cmdpipe -t 192.168.1.80 -D $dataroot/receivefiles -l $dataroot/transferlog -m $dataroot/msgin -M $dataroot/msgout -p 4852 -k -e $dataroot/ecspipe -E $dataroot/ecrpipe
}

makedirectories
startcommunication
