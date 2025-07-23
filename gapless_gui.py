import tkinter as tk
import tkinter.ttk as ttk
from tkinter import filedialog
import sounddevice as sd
import wave
import threading
import queue
import numpy as np

# 버퍼 설정
BUFFER_SIZE = 1024
#current_channels = 2  # 기본값

audio_queue = queue.Queue()
stop_flag = threading.Event()

class GaplessGUIPlayer:
    def __init__(self):
        self.files = []
        self.root = tk.Tk()
        self.root.title("🎵 Gapless WAV Player")
        self.root.geometry("300x300") 
        self.progress = ttk.Progressbar(self.root, orient="horizontal", length=250, mode="determinate")
        self.progress.pack(pady=10) 
        self.total_duration = 0  # 전체 오디오 길이 (초)
        self.played_seconds = 0
        self.currently_playing_file = None # 현재 표시 중인 곡 이름

        # 버튼들
        tk.Button(self.root, text="📂 파일 선택", command=self.select_files).pack(pady=10)
        tk.Button(self.root, text="▶ 재생 시작", command=self.start_stream).pack(pady=10)
        tk.Button(self.root, text="⏹️ 정지", command=self.stop_stream).pack(pady=10)

        self.playlist_box = tk.Listbox(self.root, height=5, width=40)
        self.playlist_box.pack(pady=10)

        self.root.mainloop()

    def select_files(self):
        paths = filedialog.askopenfilenames(filetypes=[("WAV files", "*.wav")])
        self.files = list(paths)
        self.playlist_box.delete(0, tk.END)
        for f in self.files:
            self.playlist_box.insert(tk.END, f.split("/")[-1])

    def highlight_by_filename(self, fname):
        for idx, f in enumerate(self.files):
            if f == fname:
                self.playlist_box.selection_clear(0, tk.END)
                self.playlist_box.selection_set(idx)
                self.playlist_box.activate(idx)
                self.playlist_box.see(idx)
                break

    def preload_audio(self):
        #global current_channels
        self.total_duration = 0
        for i, fname in enumerate(self.files):
            wf = wave.open(fname, 'rb')
            self.current_channels = wf.getnchannels()
            frames = wf.getnframes()
            rate = wf.getframerate() 
            sampwidth = wf.getsampwidth()
            duration = frames / float(rate)
            self.total_duration += duration
            dtype = 'int16'
            total_frames = wf.getnframes()

            frames_read = 0
            while frames_read < total_frames and not stop_flag.is_set():
                frames_to_read = min(BUFFER_SIZE, total_frames - frames_read)
                data = wf.readframes(frames_to_read)
                if not data:
                    break
                channels = wf.getnchannels()  # 채널 수 변수 저장
                audio_queue.put((data, rate, channels, dtype, fname))
                frames_read += frames_to_read
            wf.close()

    def callback(self, outdata, frames, time, status):
        try:
            data_total = np.empty((0, self.current_channels), dtype=np.int16)
            frames_remaining = frames
    
            while frames_remaining > 0:
                try:
                    # 버퍼에서 데이터 꺼내기
                    data, rate, ch, dtype, fname = audio_queue.get(timeout=1)
                    data_np = np.frombuffer(data, dtype=np.int16).reshape(-1, ch)
    
                    # 만약 현재 재생 중인 곡이 바뀌었으면 하이라이트 갱신
                    if fname != self.currently_playing_file:
                        self.currently_playing_file = fname
                        self.highlight_by_filename(fname)
    
                    # 프레임 수 맞춰서 자르거나 이어 붙이기
                    if data_np.shape[0] > frames_remaining:
                        chunk = data_np[:frames_remaining]
                        leftover = data_np[frames_remaining:]
                        # 남은 데이터 다시 큐에 넣음
                        audio_queue.put((
                            leftover.tobytes(), rate, ch, dtype, fname
                        ))
                        data_total = np.vstack([data_total, chunk])
                        frames_remaining = 0
                    else:
                        data_total = np.vstack([data_total, data_np])
                        frames_remaining -= data_np.shape[0]
    
                except queue.Empty:
                    # 버퍼가 비어 있으면 무음으로 남은 프레임 채움 (선택사항)
                    padding = np.zeros((frames_remaining, self.current_channels), dtype=np.int16)
                    data_total = np.vstack([data_total, padding])
                    break
    
            # 최종 데이터 전송
            outdata[:] = data_total
    
        except Exception as e:
            print("⚠️ Callback error:", e)
            raise sd.CallbackStop()
        

    def start_stream(self):
        if not self.files:
            print("📁 WAV 파일이 선택되지 않았어요!")
            return
        stop_flag.clear()

        wf_test = wave.open(self.files[0], 'rb')
        self.stream = sd.OutputStream(
            samplerate=wf_test.getframerate(),
            channels=wf_test.getnchannels(),
            dtype='int16',
            blocksize=BUFFER_SIZE,
            callback=self.callback
        )
        wf_test.close()

        # 오디오 로딩 스레드 시작
        preloader = threading.Thread(target=self.preload_audio)
        preloader.start()

        # 🔥 프로그레스 바 업데이트 시작!
        self.played_seconds = 0
        self.update_progress()

        # 스트리밍 시작
        self.stream.start()

    def stop_stream(self):
        stop_flag.set()
        try:
            self.stream.stop()
        except Exception:
            pass
        print("🛑 스트리밍 중지!")

    def update_progress(self, _=None):
        if stop_flag.is_set():
            return
        self.played_seconds += 0.2  # 200ms마다 갱신
        if self.total_duration:
            progress_percent = min(100, self.played_seconds / self.total_duration * 100)
            self.progress['value'] = progress_percent
        self.root.after(200, self.update_progress)

GaplessGUIPlayer()

