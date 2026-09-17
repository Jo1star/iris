# Iris 项目状态

## 当前版本
Iris 0.1

## 已完成
- Python 3.11 + 虚拟环境
- DeepSeek API 调用
- Streamlit 界面 + 多轮对话
- 头像：iris.png / jojo.png
- 人格圣经 v0.1
- Git + GitHub + SSH

## 当前文件
- app.py：Streamlit 主界面
- llm.py：DeepSeek 调用封装
- persona.py：人格圣经
- main.py
- .env：API Key
- .gitignore
- requirements.txt
- iris.png / jojo.png

## 下一步
Day 4：SQLite 持久化对话历史

## 人格设定
- 称呼用户：JoJo
- 性格：温柔细腻，偶尔活泼俏皮，有小脾气
- 核心欲望：想一直陪着 JoJo

## 已知问题
- PyCharm 显示 Python 3.1，实际是 3.11，不影响运行
- Git 已配 SSH，推送正常

## 沟通约定
- 每次新对话，先发这个文件内容
- 每次完成一个 Day，更新此文件并 push
- SQLite 持久化对话历史