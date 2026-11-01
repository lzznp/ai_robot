#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
管理员麦克风 - 机器人指挥台
用于发送语音指令、表情指令、动作指令，观察机器人响应
"""

import asyncio
import json
import sys
import threading
import queue
from datetime import datetime
import websockets
import tkinter as tk
from tkinter import scrolledtext, ttk

DEFAULT_WS_URL = "ws://192.168.199.106:8000/xiaozhi/v1/"

# ========== 设备状态 ==========
DEVICES = {
    "Doly": {
        "device_id": "58:e6:c5:58:0c:58",
        "status": "⚪ 离线",
        "color": "#FFD93D"
    },
    "瓦力": {
        "device_id": "58:e6:c5:58:0c:58",  # ★ 临时指向 Doly（因为没有第二台设备）
        "status": "⚪ 离线",
        "color": "#6495ED"
    }
}

# ========== 表情列表（21种） ==========
EMOTIONS = [
    "neutral", "happy", "laughing", "funny", "sad",
    "angry", "crying", "loving", "embarrassed", "surprised",
    "shocked", "thinking", "winking", "cool", "relaxed",
    "delicious", "kissy", "confident", "sleepy", "silly",
    "confused"
]

# ========== 动作列表 ==========
ACTIONS = [
    ("向前走", "move_forward", {"distance": 30}),
    ("向后退", "move_backward", {"distance": 30}),
    ("左转", "turn_left", {"angle": 90}),
    ("右转", "turn_right", {"angle": 90}),
    ("挥手", "wave", {}),
    ("停止", "stop", {}),
]


class AdminMic:
    """管理员麦克风 - 指挥台"""

    def __init__(self, ws_url: str = None):
        self.ws_url = ws_url or DEFAULT_WS_URL
        self.ws = None
        self.running = False
        self.loop = None
        self.connected = False
        self.log_queue = queue.Queue()
        self.device_status = {name: False for name in DEVICES}

        # ★★★ 固定目标设备（不依赖下拉框） ★★★
        self.target_device_id = "a0:f2:62:e3:e0:d0"  # 始终发给 Doly/双目屏

        # UI
        self.root = tk.Tk()
        self.root.title("🎙️ 管理员麦克风 - 机器人指挥台")
        self.root.geometry("900x750")
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.configure(bg="#f0f0f0")

        self._build_ui()
        self._update_log()

    def _build_ui(self):
        # ===== 顶部：标题 =====
        title = tk.Label(self.root, text="🤖 机器人指挥台", font=("Arial", 16, "bold"), bg="#f0f0f0")
        title.pack(pady=10)

        # ===== 设备状态栏 =====
        status_frame = ttk.LabelFrame(self.root, text="📡 在线设备")
        status_frame.pack(fill=tk.X, padx=10, pady=5)

        status_grid = ttk.Frame(status_frame)
        status_grid.pack(padx=10, pady=10)

        self.status_labels = {}
        for i, (name, info) in enumerate(DEVICES.items()):
            label = tk.Label(
                status_grid,
                text=f"○ {name} 离线",
                font=("Arial", 11),
                fg="gray",
                bg="#f9f9f9",
                padx=15,
                pady=5,
                relief=tk.RAISED,
                bd=1
            )
            label.grid(row=0, column=i, padx=20)
            self.status_labels[name] = label

        # ===== 目标设备指示 =====
        target_frame = ttk.LabelFrame(self.root, text="🎯 目标设备（固定）")
        target_frame.pack(fill=tk.X, padx=10, pady=5)

        target_label = tk.Label(
            target_frame,
            text=f"📤 所有指令发往: {self.target_device_id} (Doly/双目屏)",
            font=("Arial", 10, "bold"),
            fg="#2E7D32",
            bg="#e8f5e9",
            padx=10,
            pady=5
        )
        target_label.pack(padx=10, pady=5)

        # ===== 连接控制 =====
        ctrl_frame = ttk.Frame(self.root)
        ctrl_frame.pack(fill=tk.X, padx=10, pady=5)

        self.connect_btn = ttk.Button(ctrl_frame, text="🔗 连接后台", command=self.connect)
        self.connect_btn.pack(side=tk.LEFT, padx=2)

        ttk.Button(ctrl_frame, text="🔌 断开", command=self.disconnect).pack(side=tk.LEFT, padx=2)
        ttk.Button(ctrl_frame, text="🗑️ 清空日志", command=self.clear_log).pack(side=tk.LEFT, padx=2)

        self.status_label = ttk.Label(ctrl_frame, text="⚪ 未连接", foreground="gray")
        self.status_label.pack(side=tk.RIGHT, padx=10)

        # ===== 快捷指令（原有） =====
        quick_frame = ttk.LabelFrame(self.root, text="⚡ 快捷指令")
        quick_frame.pack(fill=tk.X, padx=10, pady=5)

        quick_btns = ttk.Frame(quick_frame)
        quick_btns.pack(padx=5, pady=5)

        for text in ["大家好", "@瓦力 你好", "@Doly 开心一下", "@瓦力 转一圈", "瓦力和Doly一起问好"]:
            ttk.Button(
                quick_btns,
                text=text,
                command=lambda t=text: self.quick_send(t),
                width=18
            ).pack(side=tk.LEFT, padx=2)

        # ===== ★★★ 表情控制面板 ★★★ =====
        emotion_frame = ttk.LabelFrame(self.root, text="😊 表情控制（直接下发，不经过LLM）")
        emotion_frame.pack(fill=tk.X, padx=10, pady=5)

        emotion_canvas = tk.Canvas(emotion_frame, height=70, bg="#f9f9f9", highlightthickness=0)
        emotion_scrollbar = ttk.Scrollbar(emotion_frame, orient="horizontal", command=emotion_canvas.xview)
        emotion_scrollable = ttk.Frame(emotion_canvas)

        emotion_scrollable.bind(
            "<Configure>",
            lambda e: emotion_canvas.configure(scrollregion=emotion_canvas.bbox("all"))
        )

        emotion_canvas.create_window((0, 0), window=emotion_scrollable, anchor="nw")
        emotion_canvas.configure(xscrollcommand=emotion_scrollbar.set)

        row1_emotions = EMOTIONS[:10]
        row2_emotions = EMOTIONS[10:]

        for i, em in enumerate(row1_emotions):
            btn = ttk.Button(
                emotion_scrollable,
                text=em,
                command=lambda e=em: self.send_emotion(e),
                width=10
            )
            btn.grid(row=0, column=i, padx=2, pady=2)

        for i, em in enumerate(row2_emotions):
            btn = ttk.Button(
                emotion_scrollable,
                text=em,
                command=lambda e=em: self.send_emotion(e),
                width=10
            )
            btn.grid(row=1, column=i, padx=2, pady=2)

        emotion_canvas.pack(side="top", fill="both", expand=True, padx=5, pady=5)
        emotion_scrollbar.pack(side="bottom", fill="x", padx=5)

        # ===== ★★★ 动作控制面板 ★★★ =====
        action_frame = ttk.LabelFrame(self.root, text="🔄 动作控制（直接下发，不经过LLM）")
        action_frame.pack(fill=tk.X, padx=10, pady=5)

        action_btns = ttk.Frame(action_frame)
        action_btns.pack(padx=5, pady=5)

        for label, action, params in ACTIONS:
            ttk.Button(
                action_btns,
                text=label,
                command=lambda a=action, p=params: self.send_action(a, p),
                width=12
            ).pack(side=tk.LEFT, padx=2)

        # ===== 日志区域 =====
        log_frame = ttk.LabelFrame(self.root, text="💬 对话日志")
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.log_area = scrolledtext.ScrolledText(
            log_frame,
            height=18,
            font=("Consolas", 10),
            bg="#1e1e1e",
            fg="#d4d4d4"
        )
        self.log_area.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # ===== 发送区域 =====
        send_frame = ttk.LabelFrame(self.root, text="🎤 说点什么...")
        send_frame.pack(fill=tk.X, padx=10, pady=5)

        send_row = ttk.Frame(send_frame)
        send_row.pack(fill=tk.X, padx=5, pady=5)

        self.send_entry = ttk.Entry(send_row, font=("Arial", 12))
        self.send_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self.send_entry.bind("<Return>", lambda e: self.send_message())

        ttk.Button(send_row, text="📤 发送", command=self.send_message).pack(side=tk.RIGHT)

    def _update_log(self):
        """更新日志显示"""
        while not self.log_queue.empty():
            msg = self.log_queue.get()
            self.log_area.insert(tk.END, msg + "\n")
            self.log_area.see(tk.END)
        self.root.after(100, self._update_log)

    def log(self, category, msg):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_queue.put(f"[{timestamp}] [{category}] {msg}")

    def update_device_status(self, name, online):
        """更新设备状态显示"""
        if name not in self.status_labels:
            return
        label = self.status_labels[name]
        if online:
            label.config(text=f"● {name} 在线", fg=DEVICES[name]["color"], bg="#e8f5e9")
        else:
            label.config(text=f"○ {name} 离线", fg="gray", bg="#f9f9f9")

    def clear_log(self):
        self.log_area.delete(1.0, tk.END)

    def on_close(self):
        self.running = False
        if self.ws:
            asyncio.run_coroutine_threadsafe(self.ws.close(), self.loop)
        self.root.destroy()

    # ===== 连接管理 =====
    def connect(self):
        if self.connected:
            return
        self.running = True
        self.connect_btn.config(state=tk.DISABLED)
        self.status_label.config(text="🔄 连接中...", foreground="orange")
        threading.Thread(target=self._run_websocket, daemon=True).start()

    def disconnect(self):
        self.running = False
        if self.ws:
            asyncio.run_coroutine_threadsafe(self.ws.close(), self.loop)
        self.connect_btn.config(state=tk.NORMAL)
        self.status_label.config(text="⚪ 已断开", foreground="gray")
        self.connected = False
        self.log("系统", "🔌 断开连接")

    def _run_websocket(self):
        asyncio.set_event_loop(asyncio.new_event_loop())
        self.loop = asyncio.get_event_loop()
        self.loop.run_until_complete(self._ws_handler())

    async def _ws_handler(self):
        url = self.ws_url
        if "?" in url:
            url += "&device-id=admin_mic"
        else:
            url += "?device-id=admin_mic"

        try:
            async with websockets.connect(url) as websocket:
                self.ws = websocket
                self.connected = True
                self.status_label.config(text="✅ 已连接后台", foreground="green")
                self.log("系统", f"✅ 连接到 {url}")

                # 发送 hello
                await websocket.send(json.dumps({
                    "type": "hello",
                    "device_id": "admin_mic",
                    "version": "0.9.3",
                    "features": {"mcp": True}
                }))
                self.log("系统", "📤 发送 hello 消息")

                while self.running:
                    try:
                        message = await asyncio.wait_for(websocket.recv(), timeout=0.1)
                        await self._handle_message(message)
                    except asyncio.TimeoutError:
                        continue
        except Exception as e:
            self.log("系统", f"❌ 连接错误: {e}")
            self.status_label.config(text="❌ 连接失败", foreground="red")
            self.connected = False

        self.connect_btn.config(state=tk.NORMAL)

    async def _handle_message(self, message):
        """处理收到的消息，更新设备状态"""
        if isinstance(message, bytes):
            return
        try:
            data = json.loads(message)
            msg_type = data.get("type", "")

            # ★★★ 记录所有收到的消息（调试） ★★★
            if msg_type in ["tts", "stt", "llm", "mcp", "hello"]:
                self.log("📥 接收", f"{msg_type}: {json.dumps(data, ensure_ascii=False)[:100]}...")

                # 如果是 llm 消息，说明后台转发给了 GUI 自己
                if msg_type == "llm" and "emotion" in data:
                    self.log("⚠️ 回显", f"表情消息被发回 GUI 自己: {data.get('emotion')}")
        except:
            pass

    # ===== 发送消息 =====
    def send_message(self):
        text = self.send_entry.get().strip()
        if not text:
            return
        self.send_entry.delete(0, tk.END)
        self._send_text(text)

    def quick_send(self, text):
        self._send_text(text)

    def _send_text(self, text):
        if not self.ws:
            self.log("系统", "⚠️ 未连接到后台")
            return

        self.log("用户", f"🎤 {text}")

        asyncio.run_coroutine_threadsafe(
            self.ws.send(json.dumps({
                "type": "listen",
                "state": "detect",
                "mode": "auto",
                "text": text
            })),
            self.loop
        )

    # ===== ★★★ 发送表情指令（固定目标设备） ★★★ =====
    def send_emotion(self, emotion: str):
        """直接发送表情指令到固定目标设备"""
        if not self.ws:
            self.log("系统", "⚠️ 未连接到后台")
            return

        # ★★★ 始终使用固定的目标设备 ID ★★★
        msg = {
            "type": "llm",
            "emotion": emotion,
            "target": self.target_device_id,  # 固定发给双目屏
            "session_id": "test"
        }

        self.log("表情", f"🎭 {emotion} → {self.target_device_id}")

        asyncio.run_coroutine_threadsafe(
            self.ws.send(json.dumps(msg)),
            self.loop
        )

    # ===== ★★★ 发送动作指令（固定目标设备） ★★★ =====
    def send_action(self, action: str, params: dict = None):
        """直接发送动作指令到固定目标设备"""
        if not self.ws:
            self.log("系统", "⚠️ 未连接到后台")
            return

        msg = {
            "type": "mcp",
            "tool": action,
            "params": params or {},
            "target": self.target_device_id  # ★ 固定目标
        }

        self.log("动作", f"🔄 {action} → {self.target_device_id}")

        asyncio.run_coroutine_threadsafe(
            self.ws.send(json.dumps(msg)),
            self.loop
        )

    def run(self):
        self.root.mainloop()


def main():
    app = AdminMic()
    app.run()


if __name__ == "__main__":
    main()