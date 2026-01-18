#!/bin/bash
cd /home/songxm/devel/cetc/python/asr/listener/video
#conda activate base
echo "/usr/bin/python3 play$1.py"
nohup /usr/bin/python3 play$1.py 2>&1 > /tmp/log &
