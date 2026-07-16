"""
播客录音工具 — Podcast Record
桌面端单文件可视化录音软件
依赖: pyaudio, numpy, tkinter, wave, threading, os, time, datetime
"""

import tkinter as tk
from tkinter import ttk, messagebox
import pyaudio
import numpy as np
import wave
import threading
import os
import time
from datetime import datetime

# ============ 常量 ============
CHUNK = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 44100
SAVE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "recordings")
WAVE_CANVAS_W = 580
WAVE_CANVAS_H = 140
MAX_RECORDINGS_DISPLAY = 20


class PodcastRecorder:
    def __init__(self, root):
        self.root = root
        self.root.title("播客录音工具 — Podcast Record")
        self.root.geometry("640x620")
        self.root.resizable(False, False)
        self.root.configure(bg="#1e1e2e")

        # 状态变量
        self.recording = False
        self.paused = False
        self.audio = pyaudio.PyAudio()
        self.stream = None
        self.frames = []
        self.record_thread = None
        self.start_time = None
        self.pause_start = None
        self.total_pause = 0.0
        self.wave_data = []
        self.current_file = ""
        self.recordings = []

        # 确保保存目录存在
        if not os.path.exists(SAVE_DIR):
            os.makedirs(SAVE_DIR)

        self.build_ui()
        self.refresh_recordings()
        self.update_timer()

    def build_ui(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background="#1e1e2e")
        style.configure("TLabel", background="#1e1e2e", foreground="#cdd6f4", font=("微软雅黑", 10))
        style.configure("Title.TLabel", font=("微软雅黑", 16, "bold"), foreground="#cdd6f4")

        # 标题栏
        title_frame = ttk.Frame(self.root)
        title_frame.pack(fill=tk.X, padx=20, pady=(16, 0))
        ttk.Label(title_frame, text="播客录音工具", style="Title.TLabel").pack(side=tk.LEFT)

        # 计时显示
        timer_frame = ttk.Frame(self.root)
        timer_frame.pack(fill=tk.X, padx=20, pady=(10, 0))
        self.timer_label = ttk.Label(
            timer_frame, text="00:00:00",
            font=("Consolas", 36, "bold"),
            foreground="#f5c2e7", background="#1e1e2e"
        )
        self.timer_label.pack()

        self.status_label = ttk.Label(
            timer_frame, text="就绪 — 点击开始录音",
            font=("微软雅黑", 10), foreground="#a6adc8"
        )
        self.status_label.pack(pady=(4, 0))

        # 波形画布
        self.wave_canvas = tk.Canvas(
            self.root, width=WAVE_CANVAS_W, height=WAVE_CANVAS_H,
            bg="#181825", highlightthickness=1, highlightbackground="#313244"
        )
        self.wave_canvas.pack(pady=(14, 0))
        self._draw_wave_grid()

        # 控制按钮
        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(pady=(14, 0))

        self.btn_record = tk.Button(
            btn_frame, text="开始录音", command=self.toggle_record,
            font=("微软雅黑", 12, "bold"), bg="#a6e3a1", fg="#1e1e2e",
            activebackground="#94e2d5", activeforeground="#1e1e2e",
            width=12, height=1, relief=tk.FLAT, cursor="hand2", bd=0
        )
        self.btn_record.pack(side=tk.LEFT, padx=6)

        self.btn_pause = tk.Button(
            btn_frame, text="暂停", command=self.toggle_pause,
            font=("微软雅黑", 12, "bold"), bg="#89b4fa", fg="#1e1e2e",
            activebackground="#74c7ec", activeforeground="#1e1e2e",
            width=10, height=1, relief=tk.FLAT, cursor="hand2", bd=0, state=tk.DISABLED
        )
        self.btn_pause.pack(side=tk.LEFT, padx=6)

        self.btn_stop = tk.Button(
            btn_frame, text="停止", command=self.stop_record,
            font=("微软雅黑", 12, "bold"), bg="#f38ba8", fg="#1e1e2e",
            activebackground="#eba0ac", activeforeground="#1e1e2e",
            width=10, height=1, relief=tk.FLAT, cursor="hand2", bd=0, state=tk.DISABLED
        )
        self.btn_stop.pack(side=tk.LEFT, padx=6)

        # 历史录音列表
        list_label_frame = ttk.Frame(self.root)
        list_label_frame.pack(fill=tk.X, padx=20, pady=(16, 0))
        ttk.Label(
            list_label_frame, text="历史录音",
            font=("微软雅黑", 11, "bold"), foreground="#cdd6f4"
        ).pack(side=tk.LEFT)

        self.recording_listbox = tk.Listbox(
            self.root, bg="#181825", fg="#cdd6f4",
            selectbackground="#45475a", selectforeground="#f5c2e7",
            font=("微软雅黑", 9), activestyle="none",
            highlightthickness=0, bd=1, relief=tk.FLAT
        )
        self.recording_listbox.pack(fill=tk.BOTH, expand=True, padx=20, pady=(6, 6))
        self.recording_listbox.bind("<Double-Button-1>", self.on_double_click)

        # 底部操作栏
        bottom_frame = ttk.Frame(self.root)
        bottom_frame.pack(fill=tk.X, padx=20, pady=(0, 14))

        ttk.Button(
            bottom_frame, text="打开目录", command=self.open_save_dir
        ).pack(side=tk.RIGHT, padx=4)

        ttk.Button(
            bottom_frame, text="刷新列表", command=self.refresh_recordings
        ).pack(side=tk.RIGHT, padx=4)

    # ============ 波形绘制 ============
    def _draw_wave_grid(self):
        self.wave_canvas.delete("grid")
        for i in range(1, 5):
            y = i * WAVE_CANVAS_H / 4
            self.wave_canvas.create_line(
                0, y, WAVE_CANVAS_W, y, fill="#313244", tags="grid"
            )

    def draw_wave(self):
        self.wave_canvas.delete("wave")
        data = self.wave_data
        if not data:
            return
        points = []
        step = max(1, len(data) // WAVE_CANVAS_W)
        mid = WAVE_CANVAS_H / 2
        for i in range(WAVE_CANVAS_W):
            idx = i * step
            if idx >= len(data):
                break
            segment = data[idx : idx + step]
            if not segment:
                continue
            amp = max(abs(min(segment)), abs(max(segment))) if isinstance(segment[0], (int, float)) else 0
            amp = min(amp / 32768, 1.0)
            y_top = mid - amp * (WAVE_CANVAS_H / 2 - 4)
            y_bot = mid + amp * (WAVE_CANVAS_H / 2 - 4)
            points.extend((i, y_top, i, y_bot))
        if points:
            for j in range(0, len(points), 4):
                self.wave_canvas.create_line(
                    points[j], points[j + 1], points[j + 2], points[j + 3],
                    fill="#cba6f7", width=1, tags="wave"
                )

    # ============ 音频采集 ============
    def audio_callback(self, in_data, frame_count, time_info, status):
        if self.recording and not self.paused:
            audio_data = np.frombuffer(in_data, dtype=np.int16)
            self.frames.append(in_data)
            self.wave_data.extend(audio_data.tolist())
            # 限制波形数据量
            if len(self.wave_data) > RATE * 60:
                self.wave_data = self.wave_data[-(RATE * 30):]
        return (in_data, pyaudio.paContinue)

    def start_recording(self):
        self.frames = []
        self.wave_data = []
        self.recording = True
        self.paused = False
        self.start_time = time.time()
        self.total_pause = 0.0

        try:
            self.stream = self.audio.open(
                format=FORMAT,
                channels=CHANNELS,
                rate=RATE,
                input=True,
                frames_per_buffer=CHUNK,
                stream_callback=self.audio_callback
            )
            self.stream.start_stream()
        except Exception as e:
            messagebox.showerror("录音错误", f"无法打开麦克风：{e}\n请检查麦克风是否已连接并授权。")
            self.recording = False
            return

        self.status_label.config(text="录音中…")
        self.btn_record.config(text="录音中…", bg="#f9e2af")
        self.btn_pause.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.NORMAL)

    def toggle_record(self):
        if not self.recording:
            self.start_recording()
        else:
            self.stop_record()

    def toggle_pause(self):
        if not self.recording:
            return
        if self.paused:
            self.paused = False
            if self.pause_start:
                self.total_pause += time.time() - self.pause_start
            self.pause_start = None
            self.btn_pause.config(text="暂停", bg="#89b4fa")
            self.status_label.config(text="录音中…")
        else:
            self.paused = True
            self.pause_start = time.time()
            self.btn_pause.config(text="继续", bg="#fab387")
            self.status_label.config(text="已暂停")

    def stop_record(self):
        if not self.recording:
            return

        self.recording = False
        self.paused = False

        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
            self.stream = None

        # 保存音频
        if self.frames:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"podcast_{timestamp}.wav"
            filepath = os.path.join(SAVE_DIR, filename)

            # 防重复覆盖
            counter = 1
            base = filename[:-4]
            while os.path.exists(filepath):
                filename = f"{base}_{counter}.wav"
                filepath = os.path.join(SAVE_DIR, filename)
                counter += 1

            wf = wave.open(filepath, "wb")
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(self.audio.get_sample_size(FORMAT))
            wf.setframerate(RATE)
            wf.writeframes(b"".join(self.frames))
            wf.close()

            self.current_file = filepath
            self.status_label.config(text=f"已保存: {filename}")
        else:
            self.status_label.config(text="没有录制到音频数据")

        self.btn_record.config(text="开始录音", bg="#a6e3a1")
        self.btn_pause.config(text="暂停", bg="#89b4fa", state=tk.DISABLED)
        self.btn_stop.config(state=tk.DISABLED)

        self.frames = []
        self.wave_data = []
        self._draw_wave_grid()
        self.refresh_recordings()

    # ============ 计时器 ============
    def update_timer(self):
        if self.recording and not self.paused:
            elapsed = time.time() - self.start_time - self.total_pause
            h = int(elapsed // 3600)
            m = int((elapsed % 3600) // 60)
            s = int(elapsed % 60)
            self.timer_label.config(text=f"{h:02d}:{m:02d}:{s:02d}")
        elif self.recording and self.paused:
            pass  # 保持当前时间
        else:
            self.timer_label.config(text="00:00:00")

        # 波形刷新
        if self.recording and not self.paused:
            self.draw_wave()

        self.root.after(50, self.update_timer)

    # ============ 历史录音管理 ============
    def refresh_recordings(self):
        self.recording_listbox.delete(0, tk.END)
        if not os.path.exists(SAVE_DIR):
            return

        files = []
        for f in os.listdir(SAVE_DIR):
            if f.endswith(".wav"):
                fp = os.path.join(SAVE_DIR, f)
                size = os.path.getsize(fp)
                mtime = os.path.getmtime(fp)
                files.append((f, size, mtime, fp))

        files.sort(key=lambda x: x[2], reverse=True)
        self.recordings = files[:MAX_RECORDINGS_DISPLAY]

        for fname, size, mtime, fpath in self.recordings:
            size_mb = size / (1024 * 1024)
            dt = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
            display = f"{dt}  |  {size_mb:.1f} MB  |  {fname}"
            self.recording_listbox.insert(tk.END, display)

    def on_double_click(self, event):
        selection = self.recording_listbox.curselection()
        if selection:
            idx = selection[0]
            if idx < len(self.recordings):
                fpath = self.recordings[idx][3]
                os.startfile(fpath)

    def open_save_dir(self):
        os.startfile(SAVE_DIR)

    def close(self):
        if self.recording:
            self.stop_record()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = PodcastRecorder(root)
    root.protocol("WM_DELETE_WINDOW", app.close)
    root.mainloop()
