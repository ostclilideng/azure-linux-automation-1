#!/bin/bash
duration=$1
filename=$2
echo $filename-top.log $duration $filename $filename-sar.log 
[ -f $filename-top.log  ] && rm -rf $filename-top.log 
[ -f $filename-sar.log  ] && rm -rf $filename-sar.log 
sar -n DEV 1 $duration 2>&1 > $filename-sar.log&
for i in $(seq 1 $duration)
do
	top -bn1 | grep "Cpu(s)" | sed "s/.*, *\([0-9.]*\)%* id.*/\1/" | awk '{print 100 - $1"%"}' >> $filename-top.log
	sleep 1
done

exit 0
