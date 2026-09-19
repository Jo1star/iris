"""
Iris FastAPI 后端
启动：python server.py
访问：http://localhost:8000
"""
import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import memory
import emotion
import diary
from service import (
    stream_reply,
    save_user_message,
    save_assistant_message,
    spawn_extract,
)

BASE_DIR = Path(__file__).parent
WEB_DIR = BASE_DIR / "web"

# 初始化
memory.init_db()
memory.apply_time_decay()
emotion.init_emotion_table()

app = FastAPI()
app.mount("/web", StaticFiles(directory=str(WEB_DIR)), name="web")


# ============ 请求模型 ============

class ChatRequest(BaseModel):
    message: str


# ============ 页面 ============

@app.get("/", response_class=HTMLResponse)
def index():
    return (WEB_DIR / "index.html").read_text(encoding="utf-8")


@app.get("/iris.png")
def iris_png():
    return FileResponse(BASE_DIR / "iris.png")


@app.get("/jojo.png")
def jojo_png():
    return FileResponse(BASE_DIR / "jojo.png")


# ============ API ============

@app.get("/api/history")
def history(limit: int = 50):
    """拉最近对话历史"""
    return memory.load_recent_messages(limit=limit)


@app.get("/api/emotion")
def get_emotion():
    """当前情绪状态"""
    return emotion.get_state()


@app.get("/api/agent_messages")
def get_agent_messages(limit: int = 10):
    """Iris 主动说的话"""
    conn = memory.get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, content, intent, created_at FROM agent_messages ORDER BY id DESC LIMIT ?",
        (limit,)
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/api/memories")
def get_memories(limit: int = 30):
    """长期记忆列表"""
    return memory.load_memories(limit=limit)


@app.get("/api/inner_state")
def get_inner_state():
    """Agent 内部状态"""
    conn = memory.get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT last_thought, current_focus, pending_intent, pending_intent_due, updated_at FROM agent_inner_state WHERE id=1"
    )
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else {}


@app.post("/api/chat")
async def chat(req: ChatRequest):
    """流式聊天（SSE）"""
    history_data = memory.load_recent_messages(limit=30)
    save_user_message(req.message)
    history_data.append({"role": "user", "content": req.message})

    async def event_stream():
        full_reply = []
        try:
            for chunk in stream_reply(req.message, history_data[-20:], max_tokens=500):
                full_reply.append(chunk)
                payload = json.dumps({"delta": chunk}, ensure_ascii=False)
                yield f"data: {payload}\n\n"
        except Exception as e:
            err = json.dumps({"error": str(e)}, ensure_ascii=False)
            yield f"data: {err}\n\n"
            return

        reply = "".join(full_reply)
        save_assistant_message(reply)
        spawn_extract(req.message, reply)

        done = json.dumps({"done": True, "reply": reply}, ensure_ascii=False)
        yield f"data: {done}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )


@app.post("/api/diary")
def write_diary():
    """让 Iris 写今天的日记"""
    return {"result": diary.write_diary()}


def start_agent_core():
    """在后台线程跑 Agent 心跳循环"""
    import agent_core
    agent_core.main_loop()


if __name__ == "__main__":
    import uvicorn
    import threading

    # 后台启动 Agent Core
    threading.Thread(target=start_agent_core, daemon=True).start()

    # 启动 Web 服务
    uvicorn.run(app, host="0.0.0.0", port=8000)