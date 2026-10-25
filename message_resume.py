# -*- coding: utf-8 -*-
"""断联续读（message-resume）

给聊天机器人用的：掉线期间漏掉的消息，重连后补回来。

设计原则：
  · 只管"哪些漏了"，怎么处理交给调用方
  · 零依赖，纯标准库
  · 状态存 JSON，删掉就是重置
"""
import json
import os
import threading
import time

__all__ = ["MessageResume", "DEFAULT_STATE_FILE"]

DEFAULT_STATE_FILE = "message_resume_state.json"


class MessageResume:
    """断联续读

    >>> mr = MessageResume()
    >>> mr.mark("private:123", msg_id=1001, ts=1792936660)   # 处理完记一笔
    >>> gap = mr.find_gap("private:123", messages)           # 重连后找漏的
    """

    def __init__(self, state_file=DEFAULT_STATE_FILE,
                 max_catchup=8, max_age_hours=24, seen_max=500):
        self.state_file = state_file
        self.max_catchup = max_catchup
        self.max_age_hours = max_age_hours
        self.seen_max = seen_max
        self._lock = threading.RLock()
        self._state = self._load()

    # ---------- 状态 ----------
    def _load(self):
        try:
            d = json.load(open(self.state_file, encoding="utf-8"))
        except Exception:
            d = {}
        d.setdefault("convs", {})
        d.setdefault("seen", [])
        return d

    def _save(self):
        try:
            with self._lock:
                tmp = self.state_file + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(self._state, f, ensure_ascii=False)
                os.replace(tmp, self.state_file)
        except Exception:
            pass

    # ---------- 对外接口 ----------
    def mark(self, conv, msg_id, ts):
        """处理完一条消息后调用。conv 形如 'private:123' / 'group:456'"""
        with self._lock:
            c = self._state["convs"].setdefault(conv, {})
            c["last_time"] = max(int(ts or 0), int(c.get("last_time", 0)))
            c["last_id"] = msg_id
            seen = self._state["seen"]
            if msg_id not in seen:
                seen.append(msg_id)
                if len(seen) > self.seen_max:
                    del seen[:len(seen) - self.seen_max]
        self._save()

    def last_time(self, conv):
        with self._lock:
            return int(self._state["convs"].get(conv, {}).get("last_time", 0))

    def is_seen(self, msg_id):
        with self._lock:
            return msg_id in self._state["seen"]

    def needs_catchup(self, conv, min_gap_seconds=60):
        """值不值得为这个会话拉历史（上次处理足够久之前才值得）"""
        t = self.last_time(conv)
        return bool(t) and (time.time() - t) > min_gap_seconds

    def find_gap(self, conv, messages):
        """从历史消息里挑出漏掉的（比上次处理的新、没处理过、没太旧）"""
        since = self.last_time(conv)
        if not since:
            return []
        cutoff = time.time() - self.max_age_hours * 3600
        out = []
        with self._lock:
            seen = set(self._state["seen"])
        for m in messages or []:
            mid = m.get("message_id")
            ts = int(m.get("time") or 0)
            if not mid or ts <= since or ts < cutoff:
                continue
            if mid in seen:
                continue
            if not (m.get("raw_message") or "").strip():
                continue
            out.append(m)
        out.sort(key=lambda m: int(m.get("time") or 0))
        return out[:self.max_catchup]

    def stats(self):
        with self._lock:
            return {
                "conversations": len(self._state["convs"]),
                "tracked_messages": len(self._state["seen"]),
            }

    def reset(self):
        with self._lock:
            self._state = {"convs": {}, "seen": []}
        self._save()
