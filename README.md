# napcat-message-resume

> 断联续读 —— 给 QQ 机器人补回掉线期间漏掉的消息。

机器人掉线那几分钟里，用户发的消息就没了。重连之后它兴冲冲地说"我在呀"，可刚才那三句话它一句都没看见。

这个模块解决的就是这一件事：**记住处理到哪儿了，重连后把漏掉的找出来**。

---

## 它不做什么

- ❌ 不接管你的消息处理逻辑
- ❌ 不改你的桥接代码结构
- ❌ 不引入任何第三方依赖（纯标准库）

- ✅ 只回答一个问题：**"从上次到现在，漏了哪几条？"**

怎么回复那几条，由你决定。

---

## 安装

把 `message_resume.py` 复制到你的项目里。没有 pip 依赖。

Python 3.8+。

---

## 用法（三步）

### 1. 处理消息时，记一笔

```python
from message_resume import MessageResume

mr = MessageResume("state.json")

def on_message(ev):
    conv = f"{ev['message_type']}:{ev['user_id'] if ev['message_type']=='private' else ev['group_id']}"

    # ... 你的处理逻辑 ...

    mr.mark(conv, ev["message_id"], ev["time"])   # 处理完记一笔
```

### 2. 重连成功后，找漏的

```python
def on_reconnect():
    for conv in my_conversations:
        if not mr.needs_catchup(conv):
            continue

        history = fetch_history(conv)          # 用你的方式拉历史
        gap = mr.find_gap(conv, history)       # ← 就这一句

        for m in gap:
            reply_to(m)                        # 补回复
            mr.mark(conv, m["message_id"], m["time"])
```

### 3. 完事

不需要清理，不需要定时任务。它自己会保持状态。

---

## NapCat / OneBot 11 示例

NapCat 提供了历史消息接口，直接就能用：

```python
import requests

NAPCAT = "http://127.0.0.1:3000"

def fetch_history(conv, count=20):
    kind, tid = conv.split(":")
    if kind == "private":
        ep, key = "/get_friend_msg_history", "user_id"
    else:
        ep, key = "/get_group_msg_history", "group_id"

    r = requests.post(f"{NAPCAT}{ep}", json={key: int(tid), "count": count}, timeout=15)
    return (r.json().get("data") or {}).get("messages") or []
```

完整可运行例子见 [`example_napcat.py`](example_napcat.py)。

---

## 原理

一句话：**时间戳水位线 + 已处理 ID 集合**。

```
状态文件：
{
  "convs": { "private:123": {"last_time": 1792936660, "last_id": 1298150969} },
  "seen": [1298150969, 1298150970, ...]
}
```

- `last_time` 是水位线：比它新的才可能是漏的
- `seen` 是保险：防止同一条被补两次

为什么不用纯 ID 比较？因为 NapCat 的 `message_id` 在不同会话、不同重启后不保证单调。用**时间**判断更稳，**ID** 只用来去重。

---

## 安全阀

默认值，都能改：

| 参数 | 默认 | 作用 |
|---|---|---|
| `max_catchup` | 8 | 一次最多补几条（避免重连暴击刷屏） |
| `max_age_hours` | 24 | 只补 24 小时内的（太老的补来没意义） |
| `seen_max` | 500 | 记住最近多少条 ID（控制状态文件大小） |

```python
mr = MessageResume("state.json", max_catchup=5, max_age_hours=12)
```

---

## 什么时候会不灵

老实说几个坑：

1. **NapCat 的历史接口有保留期**。掉线太久（几小时以上），历史里可能已经查不到了，补不回来。
2. **群消息量大**。群活跃的话，20 条历史可能不够覆盖掉线期间，把 `count` 调大。
3. **补读可能重复回复**。如果掉线前的消息其实处理了、只是没来得及 `mark()`，就会补重复。所以 `mark()` 要尽量靠近处理成功那一刻。
4. **`needs_catchup()` 有 60 秒门槛**。刚重连马上就又断的情况不会触发补读——这是故意的，避免抖来抖去时反复补。

---

## License

MIT
