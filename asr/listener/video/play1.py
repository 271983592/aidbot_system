import cv2
import subprocess as sp
cap = cv2.VideoCapture("udpsrc port=5600 ! application/x-rtp,payload=96,encoding-name=H264 ! rtpjitterbuffer mode=1 ! rtph264depay ! h264parse ! decodebin ! videoconvert ! appsink", cv2.CAP_GSTREAMER)
fps = int(cap.get(cv2.CAP_PROP_FPS))
width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
print(fps)
print(width)
print(height)
#out_rtsp_url = 'rtsp://admin:1qaz2wsx@172.30.160.154:8554/mystream'
#command = ['ffmpeg',
#               '-y',
#               '-f', 'rawvideo',
#               '-vcodec', 'rawvideo',
#               '-pix_fmt', 'bgr24',
#               '-s', "{}x{}".format(width, height),
#               '-r', '10',
#               '-i', '-',
#               '-c:v', 'libx264',
#               '-pix_fmt', 'yuv420p',
#               #'-preset', 'ultrafast',
#               '-f', 'rtsp',
#               out_rtsp_url]
out_rtsp_url = 'rtmp://172.30.160.154:1935/mystream'
command = ['ffmpeg',
              '-y',  # 覆盖已存在的文件
              '-f', 'rawvideo',
              '-pixel_format', 'bgr24',
              '-video_size', "{}x{}".format(width, height),
              '-i', '-',  # 从标准输入读取数据
              '-c:v', 'libx264', #使用x264编码器
              '-preset', 'ultrafast',
              '-tune', 'zerolatency',#零延迟
              '-pix_fmt', 'yuv420p',
              '-f', 'flv',
              out_rtsp_url]
p = sp.Popen(command, stdin=sp.PIPE)
isTrans = 0
while (cap.isOpened()):
    ret, frame = cap.read()
    if not ret:
        print("Opening camera is failed")
        break
    cv2.imshow("frame", frame)
    # 按键退出
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break
    #print(frame.shape)
    p.stdin.write(frame.tostring())
    #if isTrans == 50:
    #    import subprocess
    #    # 定义一个回调函数，用于处理子进程的输出
    #    def handle_output(output):
    #        print(output)
    #    # 异步调用shell命令
    #    def run_shell_command(command):
    #        process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    #        #while True:
    #        #    output = process.stdout.readline().decode().rstrip()  # 读取子进程的标准输出
    #        #    if output == '' and process.poll() is not None:  # 如果子进程已经结束且没有输出
    #        #        break
    #        #    if output:  # 如果有输出
    #        #        handle_output(output)  # 处理输出内容
    #    # 调用shell命令"ls"并异步执行
    #    run_shell_command('ffmpeg -i rtsp://admin:1qaz2wsx@172.30.160.154:8554/mystream -r 30 -q 0 -f mpegts -codec:v mpeg1video -s 1366x768  http://127.0.0.1:8081/supersecret')
    #    isTrans = isTrans + 1
    #elif isTrans < 50:
    #    isTrans = isTrans + 1
    #    print(isTrans)
# 关闭窗口
cv2.destroyAllWindows()
# 停止读取
cap.release()
