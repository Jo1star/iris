"""
Iris 事件总线（进程内）。
server.py 和 agent_core.py 在同一进程里，共享这个模块。
事件类型：message / emotion / reminder / manual
"""
import time
import queue
import threading

_queue = queue.Queue()
_wakeup = threading.Event()


def push(kind, payload=None):
    """推一个事件，唤醒 Agent Core"""
    _queue.put({
        "kind": kind,
        "payload": payload or {},
        "ts": time.time(),
    })
    _wakeup.set()


def wait(timeout):
    """等待事件或超时。返回事件列表（可能为空）"""
    if not _wakeup.wait(timeout):
        return []
    _wakeup.clear()
    events = []
    while True:
        try:
            events.append(_queue.get_nowait())
        except queue.Empty:
            break
    return events


def drain():
    """非阻塞取出所有当前事件"""
    events = []
    while True:
        try:
            events.append(_queue.get_nowait())
        except queue.Empty:
            break
    if events:
        _wakeup.clear()
    return events