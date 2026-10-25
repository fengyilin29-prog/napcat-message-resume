# -*- coding: utf-8 -*-
"""NapCat / OneBot 11 完整示例

这是把 message_resume 接到一个最小 QQ 机器人上的样子。
跑之前改一下 NAPCAT 地址和你的 QQ 号。

流程：
  1. 收消息 → 处理 → mark()
  2. 断线 → 重连 → catch_up()
"""
import json
import threading
import time

import requests
import websocket

from message_resume import MessageResume

NAPCAT_HTTP = "http://127.0.0.1:3000"
NAPCAT_WS = "ws://127.0.0.1:3001"
MY_QQ = 10001                      # ← 改成你的机器人 QQ

mr = MessageResume("state.json")


def log(msg):
    print("[%s] %s" % (time.strftime("%H:%M:%S"), msg), flush=True)


def send(conv, text):
    kind, tid = conv.split(":")
    ep = "/send_private_msg" if kind == "private" else "/send_group_msg"
    key = "user_id" if kind == "private" else "group_id"
    requests.post(NAPCAT_HTTP + ep, json={key: int(tid), "message": text}, timeout=15)


def reply(ev, text):
    """真正的回复逻辑，换成你自己的"""
    conv = conv_of(ev)
    send(conv, text)
    log("回复 %s: %s" % (conv, text[:40]))


def conv_of(ev):
    if ev.get("message_type") == "group":
        return "group:%s" % ev.get("group_id")
    return "private:%s" % ev.get("user_id")


def handle(ev):
    """你的业务逻辑：收到一条消息怎么回"""
    text = (ev.get("raw_message") or "").strip()
    if not text:
        return
    reply(ev, "收到：%s" % text[:50])


# ---------- 关键部分 ----------

def on_message(ws, raw):
    try:
        ev = json.loads(raw)
    except Exception:
        return
    if ev.get("post_type") != "message":
        return

    handle(ev)

    # ① 处理完立刻记账
    mr.mark(conv_of(ev), ev.get("message_id"), ev.get("time"))


def fetch_history(conv, count=20):
    kind, tid = conv.split(":")
    if kind == "private":
        ep, key = "/get_friend_msg_history", "user_id"
    else:
        ep, key = "/get_group_msg_history", "group_id"
    r = requests.post(NAPCAT_HTTP + ep,
                      json={key: int(tid), "count": count}, timeout=15)
    return (r.json().get("data") or {}).get("messages") or []


def catch_up(conversations):
    """② 重连后补漏"""
    time.sleep(3)                              # 等 NapCat 站稳
    for conv in conversations:
        if not mr.needs_catchup(conv):
            continue
        try:
            gap = mr.find_gap(conv, fetch_history(conv))
            if not gap:
                log("CATCHUP %s: 没漏的" % conv)
                continue
            log("CATCHUP %s: 补 %d 条" % (conv, len(gap)))
            for m in gap:
                # 伪造一个事件喂给业务逻辑，或者直接 reply()
                ev = {
                    "message_type": conv.split(":")[0],
                    "user_id": m.get("sender", {}).get("user_id"),
                    "group_id": int(conv.split(":")[1]) if conv.startswith("group") else None,
                    "raw_message": m.get("raw_message"),
                    "message_id": m.get("message_id"),
                    "time": m.get("time"),
                }
                handle(ev)
                mr.mark(conv, m.get("message_id"), m.get("time"))
                time.sleep(1.2)                # 补的时候别太急，像人一点
        except Exception as e:
            log("catchup %s 失败: %s" % (conv, str(e)[:80]))


def on_open(ws):
    log("WS 已连接")
    threading.Thread(target=catch_up, args=([f"private:{MY_QQ}"],), daemon=True).start()


if __name__ == "__main__":
    log("启动，状态：%s" % mr.stats())
    while True:
        try:
            ws = websocket.WebSocketApp(NAPCAT_WS,
                                        on_message=on_message,
                                        on_open=on_open)
            ws.run_forever()
        except Exception as e:
            log("断了：%s" % str(e)[:80])
        time.sleep(5)
