#!/bin/bash
set -e
PORT=5000   # app.py 里默认端口，按需改

echo "Starting aidbot on port $PORT ..."
source /home/songxm/anaconda3/bin/activate py39

# 先清旧日志、写 PID
nohup python app.py > /tmp/log.aidbot 2>&1 &
echo $! > aidbot.pid

# 等待监听
until lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null 2>&1; do
  sleep 1
done

echo "aidbot is ready (PID $(cat aidbot.pid))"
conda deactivate
