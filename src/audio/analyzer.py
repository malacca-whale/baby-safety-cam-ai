import logging
import threading
import time
import numpy as np
import sounddevice as sd
import librosa
from scipy.signal import find_peaks

from src.vision.schemas import AudioStatus

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000
CHUNK_DURATION = 4  # seconds for analysis
BLOCK_SIZE = 1600  # 100ms blocks for streaming


class AudioAnalyzer:
    def __init__(self):
        self._running = False
        self._stream: sd.InputStream | None = None
        self._analysis_thread: threading.Thread | None = None
        self._stream_thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._last_status = AudioStatus()
        self._analysis_buffer: list[float] = []
        self._stream_buffer: list[float] = []
        self._socketio = None
        self.device_id: int | None = None

    def start(self, device_id: int | None = None, socketio=None):
        self.device_id = device_id
        self._socketio = socketio
        self._running = True
        self._analysis_buffer = []
        self._stream_buffer = []

        try:
            self._stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="float32",
                device=device_id,
                callback=self._audio_callback,
                blocksize=BLOCK_SIZE,
            )
            self._stream.start()
        except Exception as e:
            logger.error(f"Failed to open audio stream: {e}")
            self._running = False
            return

        self._analysis_thread = threading.Thread(target=self._analysis_loop, daemon=True)
        self._analysis_thread.start()

        if socketio:
            self._stream_thread = threading.Thread(target=self._stream_loop, daemon=True)
            self._stream_thread.start()

        logger.info(f"Audio analyzer started (device={device_id}, streaming={'yes' if socketio else 'no'})")

    def _audio_callback(self, indata, frames, time_info, status):
        data = indata[:, 0].copy()
        with self._lock:
            self._analysis_buffer.extend(data)
            if self._socketio:
                self._stream_buffer.extend(data)

    def _analysis_loop(self):
        chunk_size = int(SAMPLE_RATE * CHUNK_DURATION)
        while self._running:
            time.sleep(0.5)
            with self._lock:
                if len(self._analysis_buffer) >= chunk_size:
                    chunk = np.array(self._analysis_buffer[:chunk_size], dtype=np.float32)
                    self._analysis_buffer = self._analysis_buffer[chunk_size:]
                else:
                    continue
            try:
                status = self._analyze_chunk(chunk)
                with self._lock:
                    self._last_status = status
            except Exception as e:
                logger.error(f"Audio analysis failed: {e}")

    def _stream_loop(self):
        while self._running:
            time.sleep(0.1)
            with self._lock:
                if len(self._stream_buffer) == 0:
                    continue
                data = np.array(self._stream_buffer, dtype=np.float32)
                self._stream_buffer.clear()
            try:
                pcm16 = (data * 32767).astype(np.int16)
                self._socketio.emit("audio_data", pcm16.tobytes())
            except Exception:
                pass

    def _analyze_chunk(self, audio: np.ndarray) -> AudioStatus:
        rms = float(np.sqrt(np.mean(audio ** 2)))
        peak = float(np.max(np.abs(audio)))

        # --- Spectral features via librosa ---
        sc = librosa.feature.spectral_centroid(y=audio, sr=SAMPLE_RATE)
        spectral_centroid = float(np.mean(sc))

        zcr = librosa.feature.zero_crossing_rate(y=audio)
        zcr_mean = float(np.mean(zcr))

        # --- Cry detection ---
        # Baby cry: high energy + high spectral centroid (>1500Hz) + high ZCR
        is_crying = False
        cry_type = ""
        cry_confidence = 0.0

        if rms > 0.08 and peak > 0.2:
            score = 0.0
            if spectral_centroid > 2000:
                score += 0.35
            elif spectral_centroid > 1200:
                score += 0.2
            if zcr_mean > 0.08:
                score += 0.25
            elif zcr_mean > 0.04:
                score += 0.1
            if rms > 0.3:
                score += 0.25
            elif rms > 0.15:
                score += 0.15

            # Check sustained loudness
            frame_size = int(SAMPLE_RATE * 0.025)
            hop_size = int(SAMPLE_RATE * 0.01)
            energies = []
            for i in range(0, len(audio) - frame_size, hop_size):
                energies.append(float(np.sum(audio[i:i + frame_size] ** 2)))
            if energies:
                high_ratio = sum(1 for e in energies if e > 0.01) / len(energies)
                if high_ratio > 0.4:
                    score += 0.15

            cry_confidence = min(score, 1.0)
            if cry_confidence >= 0.55:
                is_crying = True
                if spectral_centroid > 2500 and rms > 0.3:
                    cry_type = "고통"
                elif rms > 0.25:
                    cry_type = "배고픔"
                else:
                    cry_type = "칭얼거림"

        # --- Breathing detection ---
        breathing_detected = False
        breathing_rate = 0.0

        if 0.003 < rms < 0.08 and not is_crying:
            try:
                # Compute energy envelope
                frame_len = int(SAMPLE_RATE * 0.1)  # 100ms frames
                hop_len = int(SAMPLE_RATE * 0.05)   # 50ms hop
                envelope = []
                for i in range(0, len(audio) - frame_len, hop_len):
                    envelope.append(float(np.sqrt(np.mean(audio[i:i + frame_len] ** 2))))

                if len(envelope) > 20:
                    env = np.array(envelope)
                    env = env - np.mean(env)
                    if np.std(env) > 0.0005:
                        # Autocorrelation to find periodicity
                        corr = np.correlate(env, env, mode="full")
                        corr = corr[len(corr) // 2:]
                        corr = corr / (corr[0] + 1e-10)

                        # Breathing: 20-60 breaths/min → 1-3 sec period → 20-60 samples at 20Hz
                        min_idx = 20  # ~1s
                        max_idx = min(60, len(corr))  # ~3s
                        if max_idx > min_idx:
                            segment = corr[min_idx:max_idx]
                            peaks, props = find_peaks(segment, height=0.2, distance=5)
                            if len(peaks) > 0:
                                breathing_detected = True
                                best = peaks[np.argmax(props["peak_heights"])]
                                period_samples = best + min_idx
                                period_sec = period_samples * 0.05  # hop = 50ms
                                breathing_rate = round(60.0 / period_sec, 1)
            except Exception:
                pass

        # --- Build description ---
        desc_parts = []
        if is_crying:
            desc_parts.append(f"울음 [{cry_type}] (확신도={cry_confidence:.0%}, RMS={rms:.3f})")
        if breathing_detected:
            desc_parts.append(f"호흡 감지됨 (~{breathing_rate:.0f} bpm)")
        if not desc_parts:
            if rms < 0.003:
                desc_parts.append("조용함 / 오디오 없음")
            else:
                desc_parts.append(f"주변 소음 (RMS={rms:.3f})")

        return AudioStatus(
            is_crying=is_crying,
            cry_type=cry_type,
            cry_confidence=round(cry_confidence, 2),
            breathing_detected=breathing_detected,
            breathing_rate=breathing_rate,
            rms_level=round(rms, 4),
            spectral_centroid=round(spectral_centroid, 1),
            description=", ".join(desc_parts),
        )

    def get_status(self) -> AudioStatus:
        with self._lock:
            return self._last_status

    def stop(self):
        self._running = False
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        if self._analysis_thread:
            self._analysis_thread.join(timeout=5)
        if self._stream_thread:
            self._stream_thread.join(timeout=2)
        logger.info("Audio analyzer stopped")

    @staticmethod
    def list_devices() -> list[dict]:
        devices = []
        for i, dev in enumerate(sd.query_devices()):
            if dev["max_input_channels"] > 0:
                devices.append({
                    "id": i,
                    "name": dev["name"],
                    "channels": dev["max_input_channels"],
                    "sample_rate": dev["default_samplerate"],
                })
        return devices
