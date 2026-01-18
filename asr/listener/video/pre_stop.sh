#!/bin/bash

ps -ef | grep rtsp-simple-server | grep -v grep | awk '{print $2}' | xargs kill -9
ps -ef | grep websocket-relay | grep -v grep | awk '{print $2}' | xargs kill -9
