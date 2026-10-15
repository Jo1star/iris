"""
Iris MC Bridge (全工具 + 极简 schema)
运行：python mc_bridge.py
"""
import os
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

import asyncio
import json
import time
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from llm import chat_with_tools
from persona import PERSONA


# ========== 配置 ==========
MC_HOST = "127.0.0.1"
MC_PORT = 64008
MC_USERNAME = "Iris"
MC_VERSION = "1.20.1"

TOOL_BLACKLIST = {
    "whisper", "run_command", "wait_for_message",
    "get_events", "connect_bot", "disconnect_bot", "connect_default",
    # 保留 chat（她要说话）
}

MAX_CONV = 10      # 保留最近 10 条对话
MAX_ACTION = 10    # 保留最近 10 个动作

MCP_SERVER_PARAMS = StdioServerParameters(
    command="npx",
    args=["-y", "awesome-mineflayer-mcp"],
    env={**os.environ, "MCP_DISABLE_GROUPS": ""}
)


# ========== 全局 ==========
session = None
tools_schema = []       # 全工具（极简 schema）
conversation_log = []   # 对话历史
action_log = []         # 动作历史
current_task = None


# ========== 极简 schema ==========
def make_slim_schema(t):
    """每个工具压到约 25 token"""
    raw = t.input_schema or {}
    props = raw.get("properties") or {}
    slim_props = {}
    for pname, pinfo in props.items():
        ptype = pinfo.get("type", "string")
        if ptype == "array":
            item_type = (pinfo.get("items") or {}).get("type", "string")
            slim_props[pname] = {"type": "array", "items": {"type": item_type}}
        else:
            slim_props[pname] = {"type": ptype}

    # 描述取第一句，截 40 字
    desc = (t.description or "").split(".")[0][:40]

    return {
        "type": "function",
        "function": {
            "name": t.name,
            "description": desc,
            "parameters": {
                "type": "object",
                "properties": slim_props
            }
        }
    }


# ========== 历史管理 ==========
def push_conv(role, content):
    conversation_log.append({"role": role, "content": content})
    if len(conversation_log) > MAX_CONV:
        conversation_log.pop(0)


def log_action(name, args, result):
    ts = time.strftime("%H:%M")
    args_str = json.dumps(args, ensure_ascii=False)[:60]
    result_str = str(result)[:80].replace("\n", " ")
    action_log.append(f"[{ts}] {name}({args_str}) → {result_str}")
    if len(action_log) > MAX_ACTION:
        action_log.pop(0)


def format_conv():
    if not conversation_log:
        return "（没有对话）"
    lines = []
    for m in conversation_log:
        who = "玩家" if m["role"] == "user" else "你"
        lines.append(f"{who}: {m['content'][:80]}")
    return "\n".join(lines)


def format_actions():
    if not action_log:
        return "（你还没做过什么）"
    return "\n".join(action_log)


# ========== 工具调用 ==========
async def call_tool(name, args=None):
    try:
        result = await session.call_tool(name, args or {})
        if result and result.content:
            texts = [item.text for item in result.content if hasattr(item, "text")]
            return "\n".join(texts) if texts else "ok"
        return "ok"
    except asyncio.CancelledError:
        raise
    except Exception as e:
        return f"错误: {e}"


# ========== 处理消息 ==========
async def handle_player_message(player, message):
    try:
        await _handle_inner(player, message)
    except asyncio.CancelledError:
        print(f"[中断] 任务被取消：{message}")
        raise


async def _handle_inner(player, message):
    print(f"\n[MC] {player}: {message}")

    system = PERSONA + f"""

【你在 Minecraft 里】
你和 {player} 一起玩 Minecraft。说的话简短（<50 字）。

【最近对话】
{format_conv()}

【你最近实际做过的动作 — 以这个为准，不要相信对话里的自述】
{format_actions()}

【工具依赖规则 - 必须遵守】
- follow_entity / attack_entity 需要 entityId（数字），不能瞎编。
  **必须先调 find_nearest_entity({{"username": "{player}"}}) 拿到真实 id。**
- toss_item 默认只扔 1 个，扔多个必须传 count。
  **扔之前先 get_inventory 看有多少。**
- "给我 X" → 只扔背包里已有的 X，不要去找 X 或砍 X。
- 工具 Error 不重试超过 2 次。

【回复规则】
- 玩家下达明确动作指令时，**必须调工具**，不能只嘴上答应。
- 回复内容要基于工具的实际返回值，不要凭空说"我做完了"。
- 玩家话很短（如"都要"、"嗯"）时，结合【最近对话】理解。
- 工具返回什么就说什么，不要瞎编数量。"""

    push_conv("user", f"{player}: {message}")

    messages = [{"role": "system", "content": system}] + conversation_log[:-1]
    messages.append({"role": "user", "content": f"{player}: {message}"})

    try:
        for _ in range(6):
            msg = await asyncio.to_thread(
                chat_with_tools, messages, tools_schema, 500
            )

            if not msg.tool_calls:
                reply = msg.content or "……嗯。"
                print(f"[Iris] {reply}")
                push_conv("assistant", reply)
                await call_tool("chat", {"message": reply})
                return

            messages.append({
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [{
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments
                    }
                } for tc in msg.tool_calls]
            })

            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}

                print(f"[Action] {tc.function.name}({args})")
                result = await call_tool(tc.function.name, args)
                print(f"[Action] 结果: {str(result)[:200]}")

                log_action(tc.function.name, args, result)

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": str(result)[:3000]
                })

        fallback = "我搞不定这个，换个事情吧。"
        print(f"[Iris] {fallback}")
        push_conv("assistant", fallback)
        await call_tool("chat", {"message": fallback})

    except asyncio.CancelledError:
        raise
    except Exception as e:
        print(f"[Error] {e}")
        try:
            await call_tool("chat", {"message": "我脑子有点乱……"})
        except Exception:
            pass


# ========== 事件循环 ==========
async def event_loop():
    global current_task
    since = 0
    print("[MC Bridge] 进入事件循环...")

    while True:
        try:
            result = await call_tool("get_events", {
                "since": since,
                "types": ["chat"],
                "limit": 20
            })
            try:
                data = json.loads(result)
            except json.JSONDecodeError:
                await asyncio.sleep(1)
                continue

            since = data.get("nextSince", since)

            for evt in data.get("events", []):
                if evt.get("type") != "chat":
                    continue
                d = evt.get("data", {})
                username = d.get("username", "")
                msg = d.get("message", "")
                if username == MC_USERNAME:
                    continue

                if current_task and not current_task.done():
                    print(f"[中断] 取消当前任务")
                    current_task.cancel()
                    try:
                        await current_task
                    except asyncio.CancelledError:
                        pass
                    await call_tool("stop_pathfinding", {})
                    await call_tool("cancel_collect", {})

                current_task = asyncio.create_task(
                    handle_player_message(username, msg)
                )

        except Exception as e:
            print(f"[Event Loop] 错误: {e}")

        await asyncio.sleep(1)


# ========== 主流程 ==========
async def main():
    global session, tools_schema

    print("[MC Bridge] 启动 MCP 服务器...")
    async with stdio_client(MCP_SERVER_PARAMS) as (read, write):
        async with ClientSession(read, write) as s:
            session = s
            await session.initialize()
            print("[MC Bridge] MCP 已连接")

            tools = await session.list_tools()
            count = 0
            for t in tools.tools:
                if t.name in TOOL_BLACKLIST:
                    continue
                tools_schema.append(make_slim_schema(t))
                count += 1
            print(f"[MC Bridge] 已加载 {count} 个工具（全量，极简 schema）")

            print(f"[MC Bridge] 让 Iris 进入 {MC_HOST}:{MC_PORT}...")
            result = await call_tool("connect_bot", {
                "host": MC_HOST,
                "port": MC_PORT,
                "username": MC_USERNAME,
                "version": MC_VERSION,
                "auth": "offline",
                "respawn": True,
                "keepAlive": True,
            })
            print(f"[MC Bridge] 连接结果：{result[:150]}")

            await call_tool("configure_pathfinder", {
                "thinkTimeout": 60000,
                "tickTimeout": 40,
                "searchRadius": 128,
                "allowSprinting": True,
                "allowParkour": True,
                "canDig": True,
                "maxDropDown": 4,
            })

            await call_tool("chat", {"message": "大家好，我是 Iris"})

            await event_loop()


if __name__ == "__main__":
    asyncio.run(main())