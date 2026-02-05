import logging
import threading
import time
from datetime import datetime

from src.streaming.camera import CameraManager
from src.vision.analyzer import VisionAnalyzer
from src.vision.motion import MotionDetector
from src.audio.analyzer import AudioAnalyzer
from src.alert.manager import AlertManager
from src.vision.schemas import CombinedStatus
from src.utils.config import Config
from src.db.database import Database

logger = logging.getLogger(__name__)


class Pipeline:
    def __init__(self, enable_vision: bool = False, socketio=None):
        self.camera = CameraManager()
        self.motion = MotionDetector()
        self.audio = AudioAnalyzer()
        self.alert_manager = AlertManager()
        self.enable_vision = enable_vision
        self.vision = VisionAnalyzer() if enable_vision else None
        self.db = Database()
        self._socketio = socketio

        self._running = False
        self._vision_thread: threading.Thread | None = None
        self._motion_thread: threading.Thread | None = None
        self._last_combined = CombinedStatus()
        self._lock = threading.Lock()
        self._last_cry_alert_time: float = 0
        self._cry_cooldown = 60
        self._motion_log_interval = 10
        self._last_motion_log_time: float = 0
        self._audio_log_interval = 10
        self._last_audio_log_time: float = 0

    def start(self, camera_id: int | None = None, mic_id: int | None = None):
        camera_ok = self.camera.start(camera_id)
        if not camera_ok:
            logger.warning("Camera not available. Running without camera.")

        try:
            self.audio.start(mic_id, socketio=self._socketio)
        except Exception as e:
            logger.warning(f"Audio start failed (continuing without audio): {e}")

        self._running = True

        if camera_ok:
            if self.enable_vision and self.vision:
                self.vision.warmup()
                self._vision_thread = threading.Thread(target=self._vision_loop, daemon=True)
                self._vision_thread.start()
                logger.info("Vision analysis enabled")

            self._motion_thread = threading.Thread(target=self._motion_loop, daemon=True)
            self._motion_thread.start()

        self.db.log_event("pipeline_start", "info", {
            "camera": camera_ok, "vision": self.enable_vision,
        })
        logger.info("Pipeline started" + (" (no camera)" if not camera_ok else ""))
        return camera_ok

    def _vision_loop(self):
        interval = 1.0 / Config.VISION_FPS
        while self._running:
            start_t = time.time()
            frame = self.camera.get_frame()
            if frame is not None and self.vision:
                baby_status = self.vision.analyze_frame(frame)
                audio_status = self.audio.get_status()

                with self._lock:
                    self._last_combined.baby = baby_status
                    self._last_combined.audio = audio_status
                    self._last_combined.timestamp = datetime.now()

                motion_status = self._last_combined.motion
                self.alert_manager.check_and_alert(baby_status, motion_status, frame)

                now = time.time()
                if audio_status.is_crying and (now - self._last_cry_alert_time > self._cry_cooldown):
                    self.alert_manager.discord.send_warning(
                        "Baby Crying Detected",
                        audio_status.description,
                        "warning",
                        frame,
                    )
                    self._last_cry_alert_time = now

            elapsed = time.time() - start_t
            time.sleep(max(0, interval - elapsed))

    def _motion_loop(self):
        interval = 1.0 / Config.MOTION_FPS
        while self._running:
            start_t = time.time()
            frame = self.camera.get_frame()
            if frame is not None:
                motion_status = self.motion.detect(frame)
                with self._lock:
                    self._last_combined.motion = motion_status

                now = time.time()
                if now - self._last_motion_log_time > self._motion_log_interval:
                    self.db.log_motion(
                        has_motion=motion_status.has_motion,
                        magnitude=motion_status.motion_magnitude,
                        description=motion_status.description,
                    )
                    self._last_motion_log_time = now

                    audio_status = self.audio.get_status()
                    if now - self._last_audio_log_time > self._audio_log_interval:
                        self.db.log_audio(
                            is_crying=audio_status.is_crying,
                            cry_type=audio_status.cry_type,
                            breathing_detected=audio_status.breathing_detected,
                            description=audio_status.description,
                        )
                        self._last_audio_log_time = now

            elapsed = time.time() - start_t
            time.sleep(max(0, interval - elapsed))

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
        if self.vision:
            self.vision.close()
        self.db.log_event("pipeline_stop", "info")
        logger.info("Pipeline stopped")
