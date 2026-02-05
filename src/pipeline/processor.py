import logging
import threading
import time

from src.streaming.camera import CameraManager
from src.vision.analyzer import VisionAnalyzer
from src.vision.motion import MotionDetector
from src.audio.analyzer import AudioAnalyzer
from src.alert.manager import AlertManager
from src.vision.schemas import BabyStatus, CombinedStatus
from src.utils.config import Config

logger = logging.getLogger(__name__)


class Pipeline:
    def __init__(self):
        self.camera = CameraManager()
        self.vision = VisionAnalyzer()
        self.motion = MotionDetector()
        self.audio = AudioAnalyzer()
        self.alert_manager = AlertManager()

        self._running = False
        self._vision_thread: threading.Thread | None = None
        self._motion_thread: threading.Thread | None = None
        self._last_combined = CombinedStatus()
        self._lock = threading.Lock()

    def start(self, camera_id: int | None = None, mic_id: int | None = None):
        camera_ok = self.camera.start(camera_id)
        if not camera_ok:
            logger.warning("Camera not available. Running without camera.")

        try:
            self.audio.start(mic_id)
        except Exception as e:
            logger.warning(f"Audio start failed (continuing without audio): {e}")

        self._running = True

        if camera_ok:
            self._vision_thread = threading.Thread(target=self._vision_loop, daemon=True)
            self._vision_thread.start()

            self._motion_thread = threading.Thread(target=self._motion_loop, daemon=True)
            self._motion_thread.start()

        logger.info("Pipeline started" + (" (no camera)" if not camera_ok else ""))
        return camera_ok

    def _vision_loop(self):
        interval = 1.0 / Config.VISION_FPS
        while self._running:
            start = time.time()
            frame = self.camera.get_frame()
            if frame is not None:
                baby_status = self.vision.analyze_frame(frame)
                audio_status = self.audio.get_status()

                with self._lock:
                    self._last_combined.baby = baby_status
                    self._last_combined.audio = audio_status
                    from datetime import datetime
                    self._last_combined.timestamp = datetime.now()

                motion_status = self._last_combined.motion
                self.alert_manager.check_and_alert(baby_status, motion_status, frame)

                if audio_status.is_crying:
                    self.alert_manager.discord.send_warning(
                        "Baby Crying Detected",
                        audio_status.description,
                        "warning",
                        frame,
                    )

            elapsed = time.time() - start
            sleep_time = max(0, interval - elapsed)
            time.sleep(sleep_time)

    def _motion_loop(self):
        interval = 1.0 / Config.MOTION_FPS
        while self._running:
            start = time.time()
            frame = self.camera.get_frame()
            if frame is not None:
                motion_status = self.motion.detect(frame)
                with self._lock:
                    self._last_combined.motion = motion_status

            elapsed = time.time() - start
            sleep_time = max(0, interval - elapsed)
            time.sleep(sleep_time)

    def get_status(self) -> CombinedStatus:
        with self._lock:
            return self._last_combined.model_copy()

    def stop(self):
        self._running = False
        if self._vision_thread:
            self._vision_thread.join(timeout=5)
        if self._motion_thread:
            self._motion_thread.join(timeout=2)
        self.camera.stop()
        self.audio.stop()
        self.vision.close()
        logger.info("Pipeline stopped")
