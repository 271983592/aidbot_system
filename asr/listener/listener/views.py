import os.path
import time

from django.http import HttpResponse
from listener import settings
import sys
import json
import logging
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s %(filename)s[line:%(lineno)d] %(levelname)s %(message)s',
                    datefmt='%a, %d %b %Y %H:%M:%S',
                    filename='asr.log',
                    filemode='w')

sys.path.append("listener/asr_deploy")
import asr_client


def hello(request):
    return HttpResponse("Welcome to listener!")


def asr_start(request):
    if request.method == 'POST':
        sessionID = request.POST.get('SessionID')
        userName = request.POST.get('UserName')
    else:
        sessionID = request.GET.get('SessionID')
        userName = request.GET.get('UserName')
    print('UserName: {}; SessionID: {}'.format(userName, sessionID))
    asr_client.start(sessionID, userName)
    settings.ASR_STATUS = 'start'
    res = {"code": 20000, "status": "success", "message": "ASR start!"}
    logging.info(res)
    return HttpResponse(json.dumps(res), content_type='application/json')


def asr_stop(request):
    asr_client.stop()
    settings.ASR_STATUS = 'stop'
    settings.ASR_ISALIVE = False
    res = {"code": 20000, "status": "success", "message": "ASR stop!"}
    logging.info(res)
    return HttpResponse(json.dumps(res), content_type='application/json')


wavs_dir = "/home/songxm/devel/cetc/python/asr/wavs"
import requests


def find_person(wav_file):
    url = "http://localhost:12345/sv_find/"
    headers = {'Content-Type': 'application/json;charset=utf-8'}
    data = {"wav_file": wav_file}
    response = requests.post(url=url, headers=headers, data=json.dumps(data))
    res = "stranger"
    score = 0
    if 200 == response.status_code:
        # res.json()将字符串转换为字典类型
        res_json = json.loads(response.text)
        # {"code": 20000, "status": "success", "person": "stranger", "score": 0}
        res = res_json['person']
        score = res_json['score']
    return (res,score)


def asr_wav(request):
    wav_obj = request.FILES.get('wav_file')
    wav_file_path = os.path.join(wavs_dir, wav_obj.name)
    print("wav_file_path: " + wav_file_path)
    f = open(wav_file_path, mode='wb')
    for item in wav_obj.chunks():
        f.write(item)
    f.close()
    print('1'*10)
    res = asr_client.asr_wav(wav_file_path)
    print("asr_wav text: " + res)
    who,score = find_person(wav_file_path)
    print("asr_wav who: " + who)
    print("asr_wav score: {}".format(score))
    res = {"code": 20000, "status": "success", "text": res, "person": who, "score": score}
    logging.info(res)
    return HttpResponse(json.dumps(res, ensure_ascii=False), content_type='application/json')

import logging
def internal_asr_wav(request):
    wav_obj = request.FILES.get('wav_file')
    wav_file_path = os.path.join(wavs_dir, wav_obj.name)
    print("wav_file_path: " + wav_file_path)
    f = open(wav_file_path, mode='wb')
    for item in wav_obj.chunks():
        f.write(item)
    f.close()
    with open(wav_file_path, 'r') as rf:
        size = rf.seek(0, os.SEEK_END)
        if size == 44 or size < 100:
            res = 'file size is 44, ignored it.'
            print('file size is 44, ignored it.')
            response = {"code": -20000, "status": "failed", "text": res, "person": 'null', "score": -1}
            return HttpResponse(json.dumps(response, ensure_ascii=False), content_type='application/json')
    res = asr_client.asr_wav(wav_file_path)
    print("asr_wav text: " + res)
    who,score = find_person(wav_file_path)
    print("asr_wav who: " + who)
    print("asr_wav score: {}".format(score))
    url = 'http://localhost:9999/asr/chatbot/message' #请求地址
    data = {
        'UserName': who.capitalize(),
        'SessionID': 'xxxxxx',
        'Message': res
    } #请求内容数据
    data = json.dumps(data, ensure_ascii=False)
    data = data.encode('UTF-8')
    headers = {'Content-Type': 'application/json;charset=utf-8'}
    response = requests.post(url=url, headers=headers, data=data)
    if 200 == response.status_code:
        print('result has sent to sprintboot!')
    else:
        print(response.text)
    response = {"code": 20000, "status": "success", "text": res, "person": who, "score": score}
    logging.info(response)
    return HttpResponse(json.dumps(response, ensure_ascii=False), content_type='application/json')


#def video_play(request):
#    if request.method == 'POST':
#        name = request.POST.get('name')
#    else:
#        name = request.GET.get('name')
#    print('video play name: {}'.format(name))
#    if 'XY' not in name:
#        res = {"code": -20000, "status": "valid name: {}".format(name)}
#    else:
#        index = int(name[2:])
#        import subprocess
#        command = 'bash /home/songxm/devel/cetc/python/asr/listener/video/start.sh {}'.format(index)
#        print(command)
#        subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
#        # time.sleep(10000000)
#        # 定义一个回调函数，用于处理子进程的输出
#        # def handle_output(output):
#        #     print(output)
#        #
#        # # 异步调用shell命令
#        # def run_shell_command(command):
#        #     process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
#        #     while True:
#        #        output = process.stdout.readline().decode().rstrip()  # 读取子进程的标准输出
#        #        if output == '' and process.poll() is not None:  # 如果子进程已经结束且没有输出
#        #            break
#        #        if output:  # 如果有输出
#        #            handle_output(output)  # 处理输出内容
#        #
#        # # 调用shell命令"ls"并异步执行
#        # run_shell_command(command)
#
#        res = {"code": 20000, "status": "success"}
#    return HttpResponse(json.dumps(res), content_type='application/json')
def video_play(request):
    if request.method == 'POST':
        name = request.POST.get('name')
    else:
        name = request.GET.get('name')
    print('video play name: {}'.format(name))
    if 'XY' not in name:
        res = {"code": -20000, "status": "valid name: {}".format(name)}
    else:
        index = int(name[2:])
        url = 'rtmp://172.30.160.154:1935/mystream'
        if index == 1:
            url = 'rtmp://172.30.160.154:1935/mystream'
        elif index == 2:
            url = 'rtmp://172.30.160.154:1835/mystream'
        elif index == 3:
            url = 'rtmp://172.30.160.154:1735/mystream'
        elif index == 4:
            url = 'rtmp://172.30.160.154:1635/mystream'
        res = {"code": 20000, "status": "success", "url": url}
    return HttpResponse(json.dumps(res), content_type='application/json')
