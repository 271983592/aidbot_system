#!/bin/bash
# kill_ports.sh  用法：./kill_ports.sh
ports=(
    5000         #人机交互界面
    )   # 需要清理的端口列表

for port in "${ports[@]}"; do
  pids=$(lsof -t -i :"$port" 2>/dev/null)
  if [[ -z $pids ]]; then
    echo "Port $port is free."
    continue
  fi

  for pid in $pids; do
    cmd=$(pwdx "$pid" 2>/dev/null | cut -d' ' -f2-)
    echo "Killing PID $pid on port $port  ($cmd)"
    kill -TERM "$pid"
  done

  sleep 1
  for pid in $pids; do
    if kill -0 "$pid" 2>/dev/null; then
      echo "Force killing PID $pid on port $port"
      kill -9 "$pid"
    fi
  done
done
echo "All specified ports are free."
rm -f /tmp/log.aidbot
