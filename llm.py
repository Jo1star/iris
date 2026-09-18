import os
import time
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# 主回复用的 client
client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com",
    timeout=60.0,
    max_retries=2
)

# 抽取专用的 client，和主回复隔离，避免抢连接
extract_client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com",
    timeout=30.0,
    max_retries=1
)


def chat(messages, max_tokens=800):
    """普通调用，用于开场白"""
    last_error = None
    for attempt in range(2):
        try:
            response = client.chat.completions.create(
                model="deepseek-chat",
                messages=messages,
                max_tokens=max_tokens
            )
            return response.choices[0].message.content
        except Exception as e:
            last_error = e
            if attempt == 0:
                time.sleep(2)
                continue
            raise last_error


def chat_stream(messages, max_tokens=500):
    """流式调用，用于对话回复"""
    stream = client.chat.completions.create(
        model="deepseek-chat",
        messages=messages,
        stream=True,
        max_tokens=max_tokens
    )
    for chunk in stream:
        if chunk.choices and chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content


def extract_chat(messages, max_tokens=500):
    """抽取专用，用独立 client"""
    response = extract_client.chat.completions.create(
        model="deepseek-chat",
        messages=messages,
        max_tokens=max_tokens
    )
    return response.choices[0].message.content

def chat_with_tools(messages, tools, max_tokens=500):
    """支持 function calling 的对话。返回完整 message 对象（可能带 tool_calls）"""
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=messages,
        tools=tools,
        max_tokens=max_tokens
    )
    return response.choices[0].message