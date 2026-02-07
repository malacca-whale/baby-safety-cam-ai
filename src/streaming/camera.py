import cv2
import glob
import platform
import threading
import logging
import time
import numpy as np

from src.utils.config import Config

logger = logging.getLogger(__name__)


class CameraManager:
    def __init__(self):
        self.cap: cv2.VideoCapture | None = None
        self.current_camera_id = Config.CAMERA_ID
        self._lock = threading.Lock()
        self._frame: np.ndarray | None = None
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self, camera_id: int | None = None):
        if camera_id is not None:
            self.current_camera_id = camera_id

        self.cap = cv2.VideoCapture(self.current_camera_id)
        if not self.cap.isOpened():
            logger.error(f"Cannot open camera {self.current_camera_id}")
            return False

        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, Config.VIDEO_WIDTH)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, Config.VIDEO_HEIGHT)
        self.cap.set(cv2.CAP_PROP_FPS, Config.VIDEO_STREAM_FPS)

        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
        logger.info(f"Camera {self.current_camera_id} started")
        return True

    def _capture_loop(self):
        while self._running and self.cap and self.cap.isOpened():
            ret, frame = self.cap.read()
            if ret:
                with self._lock:
                    self._frame = frame
            else:
                time.sleep(0.01)

    def get_frame(self) -> np.ndarray | None:
        with self._lock:
            return self._frame.copy() if self._frame is not None else None

    def get_jpeg(self) -> bytes | None:
        frame = self.get_frame()
        if frame is None:
            return None
        _, buffer = cv2.imencode(
            ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, Config.JPEG_QUALITY]
        )
        return buffer.tobytes()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
        if self.cap:
            self.cap.release()
        logger.info("Camera stopped")

    def switch_camera(self, camera_id: int) -> bool:
        self.stop()
        return self.start(camera_id)

    def list_cameras(self, max_check: int = 5) -> list[dict]:
        cameras = []
        if platform.system() == "Linux":
            # On Linux, enumerate /dev/video* devices instead of opening them
            # (opening a device already in use by the capture thread will fail)
            devs = sorted(glob.glob("/dev/video*"))
            seen_ids: set[int] = set()
            for dev in devs:
                try:
                    idx = int(dev.replace("/dev/video", ""))
                except ValueError:
                    continue
                if idx in seen_ids:
                    continue
                seen_ids.add(idx)
                # For the currently active camera, read resolution from the live capture
                if idx == self.current_camera_id and self.cap and self.cap.isOpened():
                    w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                    h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                    cameras.append({"id": idx, "name": f"Camera {idx}", "resolution": f"{w}x{h}"})
                else:
                    cameras.append({"id": idx, "name": f"Camera {idx}", "resolution": "unknown"})
        else:
            # macOS / Windows: try opening each index
            for i in range(max_check):
                cap = cv2.VideoCapture(i)
                if cap.isOpened():
                    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                    cameras.append({"id": i, "name": f"Camera {i}", "resolution": f"{w}x{h}"})
                    cap.release()
        return cameras
