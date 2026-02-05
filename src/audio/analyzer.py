import logging
import threading
import numpy as np
import sounddevice as sd

from src.vision.schemas import AudioStatus

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000
CHUNK_DURATION = 4  # seconds


class AudioAnalyzer:
    def __init__(self):
        self._running = False
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._last_status = AudioStatus()
        self.device_id: int | None = None

    def start(self, device_id: int | None = None):
        self.device_id = device_id
        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
        logger.info(f"Audio analyzer started (device={device_id})")

    def _capture_loop(self):
        try:
            while self._running:
                audio = sd.rec(
                    int(SAMPLE_RATE * CHUNK_DURATION),
                    samplerate=SAMPLE_RATE,
                    channels=1,
                    dtype="float32",
                    device=self.device_id,
                )
                sd.wait()

                if not self._running:
                    break

                status = self._analyze_chunk(audio.flatten())
                with self._lock:
                    self._last_status = status

        except Exception as e:
            logger.error(f"Audio capture failed: {e}")

    def _analyze_chunk(self, audio: np.ndarray) -> AudioStatus:
        rms = float(np.sqrt(np.mean(audio**2)))
        peak = float(np.max(np.abs(audio)))

        # Simple energy-based cry detection
        is_crying = False
        cry_type = ""

        if rms > 0.05 and peak > 0.3:
            # Check for sustained loud sound (cry-like)
            frame_size = int(SAMPLE_RATE * 0.025)
            hop_size = int(SAMPLE_RATE * 0.01)
            energies = []
            for i in range(0, len(audio) - frame_size, hop_size):
                frame = audio[i : i + frame_size]
                energies.append(float(np.sum(frame**2)))

            if energies:
                high_energy_ratio = sum(1 for e in energies if e > 0.01) / len(energies)
                if high_energy_ratio > 0.3:
                    is_crying = True
                    cry_type = "crying detected"

        # Simple breathing detection via periodic low-amplitude patterns
        breathing_detected = False
        if 0.005 < rms < 0.05:
            breathing_detected = True

        desc_parts = []
        if is_crying:
            desc_parts.append(f"Crying detected (RMS={rms:.3f})")
        if breathing_detected:
            desc_parts.append("Breathing sounds detected")
        if not desc_parts:
            if rms < 0.005:
                desc_parts.append("Quiet / no audio")
            else:
                desc_parts.append(f"Ambient noise (RMS={rms:.3f})")

        return AudioStatus(
            is_crying=is_crying,
            cry_type=cry_type,
            breathing_detected=breathing_detected,
            description=", ".join(desc_parts),
        )

    def get_status(self) -> AudioStatus:
        with self._lock:
            return self._last_status

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
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
