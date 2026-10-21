"""
Iris MC Bridge（全工具 + 极简 schema + 自主行动 + 农民作息 + 积极规划）
"""
import os
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

import asyncio
import json
import time
import random
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from llm import chat, chat_with_tools
from persona import PERSONA


# ========== 基础配置 ==========
MC_HOST = "127.0.0.1"
MC_PORT = 64008
MC_USERNAME = "Iris"
MC_VERSION = "1.20.1"
MC_SKIN = "Nihachu" # 如果之前设置成功了，这里其实不用改了

TOOL_BLACKLIST = {
    "whisper", "run_command", "wait_for_message",
    "get_events", "connect_bot", "disconnect_bot", "connect_default",
}

MAX_CONV = 10
MAX_ACTION = 10

MCP_SERVER_PARAMS = StdioServerParameters(
    command="npx",
    args=["-y", "awesome-mineflayer-mcp"],
    env={**os.environ, "MCP_DISABLE_GROUPS": ""}
)

# ========== 自主行动配置 ==========
AUTONOMOUS_ENABLED = True
AUTONOMOUS_IDLE_SECONDS = 120          # 玩家 2 分钟没说话，就开始自己找事做
AUTONOMOUS_MAX_STREAK = 5              # 连续自主最多 5 次（更活泼）
AUTONOMOUS_INTERVAL_MIN = 60           # 两次自主之间最少间隔（秒）
AUTONOMOUS_INTERVAL_MAX = 150          # 最多间隔

# 全局状态
session = None
tools_schema = []
conversation_log = []
action_log = []
current_task = None

last_player_activity = time.time()
last_player_name = "JoJo"
autonomous_streak = 0


def make_slim_schema(t):
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

    desc = (t.description or "").split(".")[0][:40]

    return {
        "type": "function",
        "function": {
            "name": t.name,
            "description": desc,
            "parameters": {"type": "object", "properties": slim_props}
        }
    }


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


# ========== 玩家对话 ==========
async def handle_player_message(player, message):
    try:
        await _handle_inner(player, message)
    except asyncio.CancelledError:
        print(f"[中断] 任务被取消：{message}")
        raise


def _is_autonomous_trigger(message):
    triggers = ["你自己玩", "你自己看着办", "随便你", "不用管我", "别管我", "自己玩吧", "随便逛逛"]
    return any(t in message for t in triggers)


async def _handle_inner(player, message):
    global last_player_activity
    print(f"\n[MC] {player}: {message}")

    system = PERSONA + f"""

【你在 Minecraft 里】
你和 {player} 一起玩 Minecraft。说的话简短（<50 字）。

【最近对话】
{format_conv()}

【你最近实际做过的动作 — 以这个为准】
{format_actions()}

【工具依赖规则 - 必须遵守】
- follow_entity / attack_entity 需要 entityId，必须先调 find_nearest_entity({{"username": "{player}"}})。
- toss_item 默认只扔 1 个，扔多个必须传 count。扔之前先 get_inventory。
- 工具 Error 不重试超过 2 次。

【回复规则】
- 玩家下达明确动作指令时，**必须调工具**，不能只嘴上答应。
- 回复内容要基于工具的实际返回值，不要凭空瞎编。"""

    push_conv("user", f"{player}: {message}")

    messages = [{"role": "system", "content": system}] + conversation_log[:-1]
    messages.append({"role": "user", "content": f"{player}: {message}"})

    try:
        for _ in range(6):
            msg = await asyncio.to_thread(chat_with_tools, messages, tools_schema, 500)

            if not msg.tool_calls:
                reply = msg.content or "……嗯。"
                print(f"[Iris] {reply}")
                push_conv("assistant", reply)
                await call_tool("chat", {"message": reply})
                return

            messages.append({
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [{"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}} for tc in msg.tool_calls]
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

                messages.append({"role": "tool", "tool_call_id": tc.id, "content": str(result)[:3000]})

        fallback = "我搞不定这个，换个事情吧。"
        print(f"[Iris] {fallback}")
        push_conv("assistant", fallback)
        await call_tool("chat", {"message": fallback})

    except asyncio.CancelledError:
        raise
    except Exception as e:
        print(f"[Error] {e}")


# ========== 自主行动（农民作息版） ==========
async def autonomous_action():
    global autonomous_streak
    idle_sec = int(time.time() - last_player_activity)
    idle_desc = f"{idle_sec // 60} 分钟" if idle_sec >= 60 else f"{idle_sec} 秒"

    system = PERSONA + f"""

【你在 Minecraft 里，现在是你的自主活动时间】
玩家 {last_player_name} 已经 {idle_desc}没说话了，你决定自己找点事做。

【你的作息与人设】
- 你遵循农民作息：日出而作，日落而息。
- 你可以用 get_time 查看现在是不是晚上。如果是晚上，你会想休息、待在安全的地方、陪玩家聊天。
- 白天，你会想干活（砍树、挖矿、种地、建小房子）。

【极其重要的规则：先问再做】
- **如果你想破坏方块、放置方块、挖矿、砍树，你必须在聊天里先问 JoJo！**
- 比如：“JoJo，我想把旁边这棵树砍了当建材，可以吗？” 或者 “我想去地下挖点铁，你要一起吗？”
- **只要你问了，这一轮自主行动就结束（不要自己偷偷去执行）。** 等 JoJo 回答“好”、“可以”，你才在对话模式下去做。
- 只有查询状态、跟随、走动、聊天，你可以直接做。

【你最近的动作】
{format_actions()}

【这一轮的行动决策】
1. 如果想做破坏/建造类动作 → 先调 chat 问 JoJo 的意见，然后结束。
2. 如果不想做危险动作 → 可以随便逛逛、看看周围、跟着 JoJo。
3. 把你想做的事，主动在 chat 里说出来，表现得活泼一点。

【输出要求】
- 要么用 chat 说话，要么做查询动作。
- 不要空说“我要去挖矿”然后不调工具，**必须先问**。
"""

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": "现在，自主活动一轮。"},
    ]

    said_content = None
    did_action = None

    try:
        for _ in range(4):
            msg = await asyncio.to_thread(chat_with_tools, messages, tools_schema, 300)

            if not msg.tool_calls:
                content = (msg.content or "").strip()
                if content:
                    print(f"[Iris 自主] {content}")
                    push_conv("assistant", content)
                    await call_tool("chat", {"message": content})
                    said_content = content
                break

            messages.append({
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [{"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}} for tc in msg.tool_calls]
            })

            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}

                print(f"[自主 Action] {tc.function.name}({args})")
                result = await call_tool(tc.function.name, args)
                print(f"[自主 Action] 结果: {str(result)[:200]}")
                log_action(tc.function.name, args, result)
                did_action = f"{tc.function.name}"

                if tc.function.name == "chat":
                    said_content = args.get("message", "")

                messages.append({"role": "tool", "tool_call_id": tc.id, "content": str(result)[:3000]})

        if did_action and not said_content:
            push_conv("assistant", f"（她自己做了：{did_action}）")

    except asyncio.CancelledError:
        raise
    except Exception as e:
        print(f"[自主] 错误：{e}")


async def autonomous_loop():
    global current_task, autonomous_streak

    await asyncio.sleep(60)  # 启动 1 分钟后开始检查

    while True:
        try:
            if not AUTONOMOUS_ENABLED:
                await asyncio.sleep(60)
                continue

            if os.path.exists("mc_auto_off"):
                await asyncio.sleep(60)
                continue

            if autonomous_streak >= AUTONOMOUS_MAX_STREAK:
                await asyncio.sleep(60)
                continue

            idle = time.time() - last_player_activity
            if idle >= AUTONOMOUS_IDLE_SECONDS:
                if current_task is None or current_task.done():
                    current_task = asyncio.create_task(autonomous_action())
                    try:
                        await current_task
                    except asyncio.CancelledError:
                        pass

                    autonomous_streak += 1
                    print(f"[自主循环] 第 {autonomous_streak}/{AUTONOMOUS_MAX_STREAK} 次自主")

                    wait_s = random.uniform(AUTONOMOUS_INTERVAL_MIN, AUTONOMOUS_INTERVAL_MAX)
                    print(f"[自主循环] 冷却 {int(wait_s)} 秒")
                    await asyncio.sleep(wait_s)
                    continue

        except Exception as e:
            print(f"[自主循环] 错误：{e}")

        await asyncio.sleep(30)


# ========== 事件与主流程 ==========
async def event_loop():
    global current_task, last_player_activity, last_player_name, autonomous_streak
    since = 0
    print("[MC Bridge] 进入事件循环...")

    while True:
        try:
            result = await call_tool("get_events", {"since": since, "types": ["chat"], "limit": 20})
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

                last_player_activity = time.time()
                last_player_name = username or last_player_name
                autonomous_streak = 0  # 玩家说话，自主计数清零

                if _is_autonomous_trigger(msg):
                    last_player_activity = time.time() - AUTONOMOUS_IDLE_SECONDS - 1

                if current_task and not current_task.done():
                    print(f"[中断] 取消当前任务")
                    current_task.cancel()
                    try:
                        await current_task
                    except asyncio.CancelledError:
                        pass
                    await call_tool("stop_pathfinding", {})
                    await call_tool("cancel_collect", {})

                current_task = asyncio.create_task(handle_player_message(username, msg))

        except Exception as e:
            print(f"[Event Loop] 错误: {e}")

        await asyncio.sleep(1)


async def main():
    global session, tools_schema, last_player_activity

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
                "skin": MC_SKIN
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

            last_player_activity = time.time()
            asyncio.create_task(autonomous_loop())
            await event_loop()


if __name__ == "__main__":
    asyncio.run(main())