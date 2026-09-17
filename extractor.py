import json
from llm import chat

EXTRACT_PROMPT = """
你是一个记忆抽取器。请从下面这轮对话中，抽取值得长期记住的信息。

规则：
- 只抽取关于用户（JoJo）的事实、偏好、重要事件、情绪状态。
- 不要抽取寒暄、重复确认、无关闲聊。
- 输出 JSON 数组，每个元素包含 type, content, importance。
- type 只能是：fact, preference, event, emotion
- importance 是 0 到 1 的小数，越重要越大。
- 如果没有值得记的，输出空数组 []。
- 只输出 JSON，不要加任何解释。

对话：
用户：{user_input}
Iris：{assistant_reply}
"""


def extract(user_input, assistant_reply):
    prompt = EXTRACT_PROMPT.format(
        user_input=user_input,
        assistant_reply=assistant_reply
    )
    raw = chat([{"role": "user", "content": prompt}])


    # 去掉可能的 markdown 代码块
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    try:
        memories = json.loads(raw)
        if not isinstance(memories, list):
            return []
        return memories
    except json.JSONDecodeError:
        return []