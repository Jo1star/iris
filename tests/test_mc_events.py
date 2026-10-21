"""测试 MCP Bot 连接 + 看事件格式"""
import asyncio
import json
import os
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

MC_HOST = "127.0.0.1"
MC_PORT = 64008
MC_USERNAME = "Iris"
MC_VERSION = "1.20.1"

MCP_SERVER_PARAMS = StdioServerParameters(
    command="npx",
    args=["-y", "awesome-mineflayer-mcp"],
    env={**os.environ, "MCP_DISABLE_GROUPS": ""}
)


async def call_tool(session, name, args=None):
    try:
        result = await session.call_tool(name, args or {})
        if result and result.content:
            texts = [item.text for item in result.content if hasattr(item, "text")]
            return "\n".join(texts) if texts else "ok"
        return "ok"
    except Exception as e:
        return f"错误: {e}"


async def main():
    print("[Test] 启动 MCP 服务器...")
    async with stdio_client(MCP_SERVER_PARAMS) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("[Test] MCP 已连接")

            print(f"[Test] 让 Bot 进入 {MC_HOST}:{MC_PORT}...")
            result = await call_tool(session, "connect_bot", {
                "host": MC_HOST,
                "port": MC_PORT,
                "username": MC_USERNAME,
                "version": MC_VERSION,
                "auth": "offline",
                "respawn": True,
                "keepAlive": True,
            })
            print(f"[Test] 连接结果：{result[:300]}")

            print("[Test] 让 Iris 说句 hello 试试...")
            await call_tool(session, "chat", {"message": "测试：我是 Iris"})

            print("[Test] 现在去 MC 里打几句消息，我会打印 20 秒内收到的所有事件")
            print("[Test] （这 20 秒内请在 MC 里打 2-3 句话）")

            # 拉 20 秒事件
            since = 0
            import time
            start = time.time()
            while time.time() - start < 20:
                events = await call_tool(session, "get_events", {
                    "since": since,
                    "types": ["chat"],
                    "limit": 50
                })
                print(f"\n[Test] get_events 返回（前 800 字符）：\n{events[:800]}")

                # 尝试解析出 nextSince
                try:
                    data = json.loads(events)
                    if "nextSince" in data:
                        since = data["nextSince"]
                except Exception:
                    pass

                await asyncio.sleep(3)

            print("\n[Test] 结束")


if __name__ == "__main__":
    asyncio.run(main())