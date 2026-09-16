import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com"
)

response = client.chat.completions.create(
    model="deepseek-chat",
    messages=[
        {"role": "system", "content": "你是Iris，一个陪伴型AI。"},
        {"role": "user", "content": "你好，我叫小明，我喜欢猫。"}
    ]
)

print(response.choices[0].message.content)