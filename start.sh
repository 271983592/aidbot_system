#!/bin/bash
source /home/songxm/anaconda3/bin/activate vllm
nohup vllm serve "deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B" 2>&1 > /tmp/log.vllm &
conda deactivate
cd asr
nohup bash start.sh 2>&1 >/dev/null &
cd -
#cd tts/project/tts_server
cd tts
nohup bash start.sh 2>&1 >/dev/null &
cd -
cd face_service
nohup bash start.sh 2>&1 >/dev/null &
cd -
#cd hands
#nohup bash start.sh 2>&1 >/dev/null &
#cd -
cd aidbot_system_ws
nohup bash start.sh 2>&1 > /dev/null &
cd -
