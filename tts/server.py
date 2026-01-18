import os
import asyncio
import io
import logging
from logging.handlers import RotatingFileHandler

import edge_tts
from fastapi import FastAPI
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
import uvicorn

from fastapi.middleware.cors import CORSMiddleware

# ===== 日志配置 =====
os.makedirs("logs", exist_ok=True)

logger = logging.getLogger("tts_app")
logger.setLevel(logging.INFO)

handler = RotatingFileHandler(
    "logs/app.log", maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
)
formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.propagate = False

# ===== FastAPI 应用 =====
app = FastAPI()

# ✅CORS：让前端可以 fetch 这个服务
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境建议写死前端域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class TtsRequest(BaseModel):
    text: str
    voice: str | None = "zh-CN-XiaoxiaoNeural"  # 可选：允许前端指定 voice


async def synthesize_mp3_bytes(text: str, voice: str) -> bytes:
    """
    调用 edge-tts 合成 mp3，并返回完整 mp3 bytes（适合中短文本）。
    """
    tts = edge_tts.Communicate(text, voice=voice)
    mp3_data = bytearray()
    async for chunk in tts.stream():
        if chunk["type"] == "audio":
            mp3_data.extend(chunk["data"])
    return bytes(mp3_data)


@app.post("/tts/synthesize")
async def tts_synthesize(req: TtsRequest):
    """
    ✅给浏览器用：返回 audio/mpeg，前端拿到后播放并可画波形
    """
    text = (req.text or "").strip()
    voice = (req.voice or "zh-CN-XiaoxiaoNeural").strip()

    if not text:
        return JSONResponse({"error": "text required"}, status_code=400)

    try:
        logger.info("Synthesize (mp3) start, len=%d, voice=%s", len(text), voice)
        mp3_bytes = await synthesize_mp3_bytes(text, voice)
        logger.info("Synthesize (mp3) done, bytes=%d", len(mp3_bytes))

        return StreamingResponse(
            io.BytesIO(mp3_bytes),
            media_type="audio/mpeg",
            headers={
                # 让浏览器可以缓存/或根据需要禁用缓存
                "Cache-Control": "no-store",
                "Content-Disposition": 'inline; filename="tts.mp3"',
            },
        )
    except Exception as e:
        logger.exception("TTS synthesize failed: %s", e)
        return JSONResponse({"error": "tts synthesize failed"}, status_code=500)


# ===== 可选：保留你原来的“服务器本机播放”接口（如果你还想要）=====
# 如不需要可删除这部分
try:
    import pyaudio
    from pydub import AudioSegment

    def play_pcm(raw_data: bytes, sample_rate: int, channels: int):
        pa = pyaudio.PyAudio()
        stream = pa.open(
            format=pyaudio.paInt16,
            channels=channels,
            rate=sample_rate,
            output=True
        )
        stream.write(raw_data)
        stream.stop_stream()
        stream.close()
        pa.terminate()

    async def synthesize_and_play(text: str, voice: str):
        try:
            logger.info("Start TTS synthesize/play: %s", text)
            mp3_bytes = await synthesize_mp3_bytes(text, voice)
            audio_segment = AudioSegment.from_file(io.BytesIO(mp3_bytes), format="mp3")
            play_pcm(audio_segment.raw_data, audio_segment.frame_rate, audio_segment.channels)
            logger.info("Playback finished: %s", text)
        except Exception as e:
            logger.exception("TTS synthesize/play failed: %s", e)

    @app.post("/tts/play")
    async def tts_play(req: TtsRequest):
        text = (req.text or "").strip()
        voice = (req.voice or "zh-CN-XiaoxiaoNeural").strip()
        if not text:
            return JSONResponse({"error": "text required"}, status_code=400)

        logger.info("Received TTS play request: %s", text)
        asyncio.create_task(synthesize_and_play(text, voice))
        return JSONResponse({"status": "playing", "text": text, "voice": voice})

except Exception:
    logger.warning("pyaudio/pydub not available; /tts/play disabled")


if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=7777)
