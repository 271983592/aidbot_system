#!/bin/bash
# 激活环境
source /home/songxm/anaconda3/bin/activate py39
unset https_proxy http_proxy

# 启动 ASR 服务
cd asr_python_deploy
nohup python server.py \
  --model_config conf/decode_engine_V3.yaml \
  --host 0.0.0.0 --port 9876 \
  --vad_aggressiveness 3 \
  > /tmp/log.asr_python_deploy 2>&1 &

# 启动 Listener 服务
cd ../listener
nohup python manage.py runserver 0.0.0.0:5678 \
  > /tmp/log.listener 2>&1 &

# 等待两个端口都监听
for port in 9876 5678; do
  echo "Waiting for port $port ..."
  while ! lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; do
    sleep 1
  done
  echo "Port $port is ready."
done

# 两个服务都就绪后再调接口
curl localhost:5678/asr/start

# 可选：退出虚拟环境
conda deactivate
