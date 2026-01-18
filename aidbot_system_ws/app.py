from gevent import monkey
monkey.patch_all()  # 关键：让 requests 等阻塞 IO 变成可让出式

import json
import logging
import time
import uuid
from collections import deque
from datetime import datetime
from typing import Optional, Dict, Any, Callable
from concurrent.futures import ThreadPoolExecutor, Future

import requests
from flask import Flask, render_template, request, jsonify, Response
from flask_socketio import SocketIO, emit, join_room

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__, template_folder='templates', static_folder='static')
app.config['SECRET_KEY'] = 'your-secret-key-change-in-production'
socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode='gevent',
    ping_timeout=90,
    ping_interval=45,
    logger=False,
    engineio_logger=False,
    transports=['websocket', 'polling']
)

conversations: Dict[str, list] = {}
connected_clients: Dict[str, dict] = {}
message_history: Dict[str, list] = {}
message_queue = deque(maxlen=1000)

AI_INVOKE_URL = 'http://localhost:8000/v1/chat/completions'
_POOL = ThreadPoolExecutor(max_workers=4)


def stream_generate_text(prompt):
    headers = {
        'Authorization': 'Bearer sk-dummy',
        'Accept': 'application/json',
        'Content-Type': 'application/json'
    }
    try:
        data = {
            "messages": [{"role": "user", "content": prompt}],
            "stream": True,
            "model": "deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B",
            "max_tokens": 4096,
            "presence_penalty": 0,
            "frequency_penalty": 0,
            "top_p": 0.7,
            "temperature": 0.6
        }
        response = requests.post(AI_INVOKE_URL, headers=headers, data=json.dumps(data), stream=True)
        response.raise_for_status()
        total_content = ""
        skip_mode = True

        for chunk in response.iter_lines():
            if not chunk:
                continue
            line = chunk.decode("utf-8")
            if line == "data: [DONE]":
                break
            json_str = line[6:]
            data = json.loads(json_str)
            if "delta" not in data["choices"][0] or "content" not in data["choices"][0]["delta"]:
                continue
            seg = data["choices"][0]["delta"]["content"]
            if skip_mode:
                idx = seg.find("</think>")
                if idx == -1:
                    continue
                seg = seg[idx + len("</think>"):]
                skip_mode = False
            total_content += seg
            yield total_content
    except requests.exceptions.RequestException as e:
        logger.info(f"请求失败: {e}")
        yield "请求失败，请检查服务是否正常运行。"


def async_tts_play(text: str,
                   url: str = "http://localhost:7777/tts/play",
                   callback: Optional[Callable[[Dict[str, Any]], None]] = None) -> Future:
    def _target() -> Dict[str, Any]:
        try:
            start = time.perf_counter()
            resp = requests.post(
                url,
                data=json.dumps({"text": text}, ensure_ascii=False).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                timeout=100
            )
            resp.raise_for_status()
            cost = time.perf_counter() - start
            logger.info(f"[async_tts_play] 耗时 {cost:.3f}s: {text[:50]}...")
            return resp.json()
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    future = _POOL.submit(_target)
    if callback is not None:
        future.add_done_callback(lambda f: callback(f.result()))
    return future


def print_result(data: Dict[str, Any]) -> None:
    logger.info("TTS 回调 >>> %s", data)


def stream_and_emit(user_input: str, session_id: str, client_id: Optional[str], source: str = "web"):
    accumulated = ""
    timestamp = datetime.now().isoformat()

    conversations.setdefault(session_id, [])
    message_history.setdefault(client_id or "unknown", [])

    socketio.emit('ai_stream', {
        "session_id": session_id,
        "client_id": client_id,
        "content": "",
        "done": False,
        "timestamp": timestamp,
        "source": source,
        "is_start": True
    }, room=client_id or None)

    try:
        for chunk in stream_generate_text(user_input + "\n请用一句话回答"):
            accumulated = chunk
            socketio.emit('ai_stream', {
                "session_id": session_id,
                "client_id": client_id,
                "content": accumulated,
                "done": False,
                "timestamp": datetime.now().isoformat(),
                "source": source
            }, room=client_id or None)
    except Exception as e:
        logger.exception("[stream_and_emit] 流式生成异常: %s", e)
    finally:
        ai_response = accumulated if accumulated else "（生成失败）"
        done_ts = datetime.now().isoformat()

        socketio.emit('ai_stream', {
            "session_id": session_id,
            "client_id": client_id,
            "content": ai_response,
            "done": True,
            "timestamp": done_ts,
            "source": source
        }, room=client_id or None)

        ai_msg = {
            "id": str(uuid.uuid4()),
            "type": "ai",
            "content": ai_response,
            "timestamp": done_ts,
            "source": "ai"
        }
        conversations[session_id].append(ai_msg)
        if client_id:
            message_history[client_id].append({
                "type": "ai",
                "content": ai_response,
                "timestamp": done_ts
            })

        # async_tts_play(ai_response, callback=print_result)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/chat', methods=['POST'])
def api_chat():
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400

        user_input = data.get('message', '').strip()
        session_id = data.get('session_id', str(uuid.uuid4()))
        target_client = data.get('client_id')

        if not user_input:
            return jsonify({"error": "Message cannot be empty"}), 400

        conversations.setdefault(session_id, [])
        user_msg = {
            "id": str(uuid.uuid4()),
            "type": "user",
            "content": user_input,
            "timestamp": datetime.now().isoformat(),
            "source": "api",
            "client_id": target_client
        }
        conversations[session_id].append(user_msg)
        if target_client:
            message_history.setdefault(target_client, [])
            message_history[target_client].append({
                "type": "user",
                "content": user_input,
                "timestamp": user_msg["timestamp"]
            })

        socketio.emit('new_message', {
            "session_id": session_id,
            "user_message": user_input,
            "timestamp": user_msg["timestamp"],
            "source": "api",
            "client_id": target_client,
            "message_id": user_msg["id"]
        }, room=target_client or None)

        socketio.start_background_task(stream_and_emit, user_input, session_id, target_client, "api")

        return Response(
            json.dumps({
                "success": True,
                "session_id": session_id,
                "message": "Message accepted and streaming in background",
                "message_id": user_msg['id']
            }, ensure_ascii=False),
            mimetype='application/json; charset=utf-8'
        )


@socketio.on('connect')
def handle_connect():
    client_id = request.sid
    session_id = str(uuid.uuid4())
    connected_clients[client_id] = {
        'session_id': session_id,
        'connected_at': datetime.now().isoformat(),
        'last_active': datetime.now().isoformat(),
        'connected': True,
        'ip': request.remote_addr,
    }
    join_room('chat_room')
    join_room(client_id)
    emit('connection_success', {
        'session_id': session_id,
        'message': 'WebSocket连接成功！',
        'timestamp': datetime.now().isoformat(),
        'client_id': client_id
    }, room=client_id)


@socketio.on('disconnect')
def handle_disconnect():
    cid = request.sid
    if cid in connected_clients:
        connected_clients[cid]['connected'] = False
        connected_clients[cid]['disconnected_at'] = datetime.now().isoformat()
    logger.info(f"[WebSocket] 客户端断开: {cid}")


@socketio.on('user_message')
def handle_user_message(data):
    try:
        client_id = request.sid
        raw_msg = data.get('message', '')
        user_input = raw_msg.strip() if isinstance(raw_msg, str) else ''
        session_id = data.get('session_id', connected_clients.get(client_id, {}).get('session_id', str(uuid.uuid4())))
        if not user_input:
            emit('error', {'message': '消息不能为空'}, room=client_id)
            return

        conversations.setdefault(session_id, [])
        user_msg = {
            "id": str(uuid.uuid4()),
            "type": "user",
            "content": user_input,
            "timestamp": datetime.now().isoformat(),
            "source": "web",
            "client_id": client_id
        }
        conversations[session_id].append(user_msg)
        message_history.setdefault(client_id, [])
        message_history[client_id].append({
            "type": "user",
            "content": user_input,
            "timestamp": user_msg["timestamp"]
        })

        message_data = {
            "session_id": session_id,
            "user_message": user_input,
            "timestamp": user_msg["timestamp"],
            "source": "web",
            "client_id": client_id,
            "message_id": user_msg["id"]
        }
        emit('new_message', message_data, room=client_id)
        emit('new_message', message_data, room='chat_room', skip_sid=client_id)

        socketio.start_background_task(stream_and_emit, user_input, session_id, client_id, "web")

    except Exception as e:
        logger.error(f"[WebSocket] 处理消息时出错: {str(e)}")
        emit('error', {'message': f'处理消息时出错: {str(e)}'}, room=request.sid)


@socketio.on('connection_test')
def handle_connection_test(data):
    emit('connection_test_response', {
        'timestamp': datetime.now().isoformat(),
        'client_id': request.sid,
        'message': '连接测试成功',
        'echo': data.get('message', '')
    }, room=request.sid)


@app.route('/api/health', methods=['GET'])
def health_check():
    active_clients = len([c for c in connected_clients.values() if c.get('connected')])
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "active_clients": active_clients,
        "total_conversations": len(conversations)
    })


if __name__ == '__main__':
    print("=" * 60)
    print("Flask WebSocket 人机对话系统 - 流式版")
    print("=" * 60)
    socketio.run(app, host='0.0.0.0', port=5000, debug=False, use_reloader=False, log_output=True)
