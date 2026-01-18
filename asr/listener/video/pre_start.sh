#!/bin/bash

#~/devel/github/px4/camara/rtsp$ ./rtsp-simple-server
cd ~/devel/github/px4/camara/rtsp
nohup /home/songxm/devel/github/px4/camara/rtsp/rtsp-simple-server 2>&1 > /tmp/log.rtsp-simple-server &
#~/devel/github/px4/camara/rtsp/chong/jsmpeg-master$ node websocket-relay.js supersecret 8081 8082
cd ~/devel/github/px4/camara/rtsp/chong/jsmpeg-master
nohup node websocket-relay.js supersecret 8081 8082 2>&1 > /tmp/log.node &
