# -*- coding: utf-8 -*-
import cv2
from flask import Flask, Response

# 初始化Flask HTTP服务
app = Flask(__name__)
# 初始化摄像头：参数0 = 电脑默认摄像头，多摄像头依次改为1、2、3...
cap = cv2.VideoCapture(0)

# 关键：视频帧生成器，实时读取摄像头画面，生成流式帧数据
def generate_frames():
    while True:
        # 读取摄像头的一帧画面
        success, frame = cap.read()
        if not success:  # 读取失败（摄像头断开/占用）则退出循环
            break
        else:
            # 将视频帧编码为JPEG格式（流媒体最优格式，体积小、传输快）
            ret, buffer = cv2.imencode('.jpg', frame)
            # 转为字节流，HTTP传输必须为字节格式
            frame_bytes = buffer.tobytes()
            # 按照HTTP流媒体的规范格式返回：帧头 + 帧数据
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

# 定义HTTP路由，访问根路径就返回视频流
@app.route('/')
def video_feed():
    # 返回流式响应，指定媒体类型为 多部分数据流
    return Response(generate_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

# 主程序入口
if __name__ == '__main__':
    # 启动HTTP服务：0.0.0.0表示监听本机所有IP，端口5000，debug=False关闭调试（稳定优先）
    app.run(host='0.0.0.0', port=5555, debug=False)