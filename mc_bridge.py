"""
Iris MC Bridge — 连接 Mineflayer Bot 和 Iris 核心
运行：python mc_bridge.py
"""
import asyncio
import json
import websockets

import service
import memory


WS_URL = "ws://localhost:3001"


async def handle_chat(ws, player, message):
    print(f"[MC] {player}: {message}")

    # 让 Iris 知道是谁在说话
    user_input = f"{player} 对你说：{message}"

    history = memory.load_recent_messages(limit=20)

    reply_chunks = []
    for chunk in service.stream_reply(user_input, history[-20:], max_tokens=300):
        reply_chunks.append(chunk)
    reply = "".join(reply_chunks)

    print(f"[Iris] {reply}")

    await ws.send(json.dumps({"reply": reply}, ensure_ascii=False))


async def main():
    print("[MC Bridge] 启动，等待 Bot 连接...")
    while True:
        try:
            async with websockets.connect(WS_URL) as ws:
                print("[MC Bridge] 已连接到 Mineflayer Bot")
                async for raw in ws:
                    msg = json.loads(raw)
                    if msg.get("type") == "chat":
                        await handle_chat(ws, msg["player"], msg["message"])
        except Exception as e:
            print(f"[MC Bridge] 连接失败：{e}，5 秒后重试...")
            await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main())