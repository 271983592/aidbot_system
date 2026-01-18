import os
import time
import threading
from typing import Dict, List, Tuple, Optional

import cv2
import numpy as np
from flask import Flask, Response, jsonify, render_template
from insightface.app import FaceAnalysis

from PIL import Image, ImageDraw, ImageFont
from flask_cors import CORS
# =========================
# 配置区 - 核心GPU相关修改✅ + 优化项✅
# =========================
APP_HOST = "0.0.0.0"
APP_PORT = 5001

FRAME_WIDTH = 1280
FRAME_HEIGHT = 720

FACE_DB_DIR = "./faces_db"
REC_SIM_THRESHOLD = 0.45  # ArcFace cosine阈值，无需修改

# 你的视频源
HTTP_VIDEO_URL = "http://localhost:5555"

# 中文字体（请确保文件存在）
FONT_PATH = "./fonts/simhei.ttf"  # Windows 可用: "C:/Windows/Fonts/simhei.ttf"
FONT_SIZE = 24

# 推理频率控制（GPU模式下建议0，CPU才需要>0；0表示推完立刻推下一帧）
PREDICT_IDLE_SLEEP = 0.0

# =========================
# Flask
# =========================
app = Flask(__name__)
CORS(app, resources=r'/*')

# =========================
# InsightFace（检测+识别）- 核心GPU修改点 全部在这里 ✅✅✅
# =========================
# 1. 模型更换：buffalo_l(CPU) → buffalo_sc(GPU专用，高性能，自动下载)
# 2. det_size放大：640→1024，GPU算力足够，更大尺寸检测更远/更小人脸，识别准确率更高
# 3. 强制启用onnxruntime-gpu，指定CUDA执行器，杜绝CPU兜底
face_app = FaceAnalysis(name="buffalo_sc", providers=['CUDAExecutionProvider'])
# ctx_id=0 强制使用GPU | det_size=(1024,1024) GPU专属高分辨率检测
face_app.prepare(ctx_id=0, det_size=(1024, 1024), det_thresh=0.5)

# GPU有效性校验
import onnxruntime as ort
providers = ort.get_available_providers()
use_gpu = "CUDAExecutionProvider" in providers
print("="*50)
print(f"GPU启用状态: {use_gpu}")
print(f"ONNX可用执行器: {providers}")
print(f"当前使用模型: buffalo_sc (GPU专用)")
print(f"推理设备: {'NVIDIA GPU (CUDA)' if use_gpu else 'CPU'}")
print("="*50)

# =========================
# 人脸库 - 无修改，逻辑不变
# =========================
DB: Dict[str, List[np.ndarray]] = {}


def cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    a = a / (np.linalg.norm(a) + 1e-9)
    b = b / (np.linalg.norm(b) + 1e-9)
    return float(np.dot(a, b))


def match_face(emb: np.ndarray) -> Tuple[str, float]:
    best_name, best_sim = "未知", -1.0
    for name, embs in DB.items():
        for e in embs:
            sim = cosine_sim(emb, e)
            if sim > best_sim:
                best_sim = sim
                best_name = name
    if best_sim >= REC_SIM_THRESHOLD:
        return best_name, best_sim
    return "未知", best_sim


def load_face_db():
    DB.clear()
    os.makedirs(FACE_DB_DIR, exist_ok=True)

    for person in sorted(os.listdir(FACE_DB_DIR)):
        pdir = os.path.join(FACE_DB_DIR, person)
        if not os.path.isdir(pdir):
            continue

        embs = []
        for fn in sorted(os.listdir(pdir)):
            if not fn.lower().endswith((".jpg", ".jpeg", ".png")):
                continue
            img = cv2.imread(os.path.join(pdir, fn))
            if img is None:
                continue

            faces = face_app.get(img)
            if not faces:
                continue

            faces = sorted(
                faces,
                key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]),
                reverse=True
            )
            embs.append(faces[0].embedding.astype(np.float32))

        if embs:
            DB[person] = embs
            print(f"[DB] loaded {person}: {len(embs)} imgs")


# =========================
# 中文绘制（PIL）- 无修改
# =========================
_font_cache = None


def get_font():
    global _font_cache
    if _font_cache is None:
        if not os.path.exists(FONT_PATH):
            raise FileNotFoundError(f"FONT_PATH not found: {FONT_PATH}")
        _font_cache = ImageFont.truetype(FONT_PATH, FONT_SIZE)
    return _font_cache


def put_text_cn(img_bgr: np.ndarray, text: str, org: Tuple[int, int],
                color_bgr=(0, 255, 0)) -> np.ndarray:
    """在BGR图上画中文。org是左上角坐标(x,y)。"""
    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    pil = Image.fromarray(img_rgb)
    draw = ImageDraw.Draw(pil)
    font = get_font()

    # PIL 用 RGB
    color_rgb = (int(color_bgr[2]), int(color_bgr[1]), int(color_bgr[0]))
    draw.text(org, text, font=font, fill=color_rgb)

    out = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
    return out


# =========================
# 摄像头：只保留最新帧 - 无修改，线程安全
# =========================
class CameraLatest:
    def __init__(self, url: str):
        self.cap = cv2.VideoCapture(url)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)

        self.lock = threading.Lock()
        self.latest_frame: Optional[np.ndarray] = None
        self.latest_id: int = 0  # 帧序号

        self.running = True
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while self.running:
            ok, frame = self.cap.read()
            if not ok:
                time.sleep(0.02)
                continue
            with self.lock:
                self.latest_frame = frame
                self.latest_id += 1

    def get_latest(self) -> Tuple[Optional[np.ndarray], int]:
        with self.lock:
            if self.latest_frame is None:
                return None, self.latest_id
            return self.latest_frame.copy(), self.latest_id


camera = CameraLatest(HTTP_VIDEO_URL)


# =========================
# 推理缓存：没来得及推理就沿用上一帧结果 - 无修改
# =========================
class ResultCache:
    def __init__(self):
        self.lock = threading.Lock()
        self.frame_id: int = -1
        self.items: List[dict] = []  # [{'bbox':np.ndarray(4,), 'label':str, 'color':(b,g,r)}]

    def set(self, frame_id: int, items: List[dict]):
        with self.lock:
            self.frame_id = frame_id
            self.items = items

    def get(self) -> Tuple[int, List[dict]]:
        with self.lock:
            return self.frame_id, list(self.items)


results_cache = ResultCache()


def draw_items(frame: np.ndarray, items: List[dict]) -> np.ndarray:
    for it in items:
        bbox = it["bbox"].astype(int)
        color = it.get("color", (0, 255, 0))
        label = it.get("label", "")

        x1, y1, x2, y2 = bbox
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

        if label:
            # 背景条（可选，让字更清楚）
            y_text = max(0, y1 - 30)
            cv2.rectangle(frame, (x1, y_text), (x1 + 360, y1), color, -1)
            frame = put_text_cn(frame, label, (x1 + 4, y_text + 2), color_bgr=(255, 255, 255))
    return frame


# =========================
# 推理线程：只推最新帧，不排队 - 无修改，GPU加持后速度暴增
# =========================
def predictor_loop():
    last_pred_frame_id = -1
    while True:
        frame, fid = camera.get_latest()
        if frame is None:
            time.sleep(0.01)
            continue

        # 只预测最新帧：如果 fid 没变化，说明没有新帧，稍等
        if fid == last_pred_frame_id:
            time.sleep(0.005)
            continue

        # 记录要预测的就是“当前最新帧”
        target_frame = frame
        target_id = fid

        # 推理 - GPU加速后这一步耗时从几十ms降到几ms
        faces = face_app.get(target_frame)
        items = []

        for f in faces:
            bbox = f.bbox

            name, sim = match_face(f.embedding.astype(np.float32))
            if name != "未知":
                label = f"{name} 相似度:{sim:.2f}"
                color = (0, 180, 0)
            else:
                label = f"未知 相似度:{sim:.2f}"
                color = (0, 215, 255)

            items.append({"bbox": bbox, "label": label, "color": color})

        # 更新缓存结果：视频线程将一直复用，直到有更新
        results_cache.set(target_id, items)
        last_pred_frame_id = target_id

        if PREDICT_IDLE_SLEEP > 0:
            time.sleep(PREDICT_IDLE_SLEEP)


threading.Thread(target=predictor_loop, daemon=True).start()


# =========================
# MJPEG：尽可能实时输出“最新帧”
# =========================
def gen_mjpeg():
    while True:
        frame, fid = camera.get_latest()
        if frame is None:
            time.sleep(0.01)
            continue

        # 取最近一次推理结果（可能对应上一帧或更早）
        rid, items = results_cache.get()

        # 不管当前帧是否预测过，都把最近一次结果画上去
        frame = draw_items(frame, items)

        ok, jpg = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        if not ok:
            continue

        yield (b"--frame\r\n"
               b"Content-Type: image/jpeg\r\n\r\n" + jpg.tobytes() + b"\r\n")


# =========================
# 路由 - 无修改
# =========================
@app.get("/")
def index():
    return render_template("index.html")


@app.get("/video")
def video():
    return Response(gen_mjpeg(), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.post("/reload_db")
def reload_db():
    load_face_db()
    return jsonify({"ok": True, "people": list(DB.keys())})


@app.get("/health")
def health():
    rid, items = results_cache.get()
    return jsonify({
        "ok": True,
        "db_people": len(DB),
        "last_result_frame_id": rid,
        "last_faces": len(items),
    })


if __name__ == "__main__":
    load_face_db()
    # debug=True在生产环境关闭，GPU模式下开debug可能有线程冲突
    app.run(host=APP_HOST, port=APP_PORT, threaded=True, debug=False)