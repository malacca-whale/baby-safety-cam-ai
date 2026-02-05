import base64
import json
import logging
import httpx
import cv2
import numpy as np
from datetime import datetime

from src.utils.config import Config
from src.vision.schemas import BabyStatus
from src.db.database import Database

logger = logging.getLogger(__name__)

ANALYSIS_PROMPT = """You are a baby safety monitor AI. Analyze this baby camera image and respond ONLY with a JSON object (no markdown, no explanation, no extra text).

Check for:
1. Is the baby's face covered by cloth/blanket? (suffocation risk)
2. What position is the baby in? (supine=on back, prone=on stomach, side=on side)
3. Is the baby inside the crib/bed?
4. Overall risk level: "safe", "warning", or "danger"

Respond with EXACTLY this JSON format:
{"face_covered": false, "position": "supine", "in_crib": true, "risk_level": "safe", "description": "Baby is sleeping safely on their back"}

IMPORTANT: Output ONLY the JSON object. No other text."""


VQA_MAX_SIZE = 512  # max width for Ollama VQA requests


class VisionAnalyzer:
    def __init__(self):
        self.client = httpx.Client(timeout=300.0)
        self.last_status = BabyStatus()
        self._warmed_up = False
        self.db = Database()

    def warmup(self):
        """Send a short text-only request to pre-load the model into memory."""
        try:
            logger.info("Warming up Ollama model...")
            resp = self.client.post(
                f"{Config.OLLAMA_URL}/api/chat",
                json={
                    "model": Config.OLLAMA_MODEL,
                    "messages": [{"role": "user", "content": "hi"}],
                    "stream": False,
                },
            )
            resp.raise_for_status()
            self._warmed_up = True
            logger.info("Ollama model warmed up successfully")
            self.db.log_event("vision_warmup", "info", {"status": "success"})
        except Exception as e:
            logger.warning(f"Ollama warmup failed (will retry on first analysis): {e}")
            self.db.log_event("vision_warmup", "warning", {"error": str(e)})

    def _resize_for_vqa(self, frame: np.ndarray) -> np.ndarray:
        h, w = frame.shape[:2]
        if w <= VQA_MAX_SIZE:
            return frame
        scale = VQA_MAX_SIZE / w
        new_w, new_h = int(w * scale), int(h * scale)
        return cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)

    def analyze_frame(self, frame: np.ndarray) -> BabyStatus:
        try:
            small = self._resize_for_vqa(frame)
            _, buffer = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 70])
            image_b64 = base64.b64encode(buffer).decode("utf-8")

            response = self.client.post(
                f"{Config.OLLAMA_URL}/api/chat",
                json={
                    "model": Config.OLLAMA_MODEL,
                    "messages": [
                        {
                            "role": "user",
                            "content": ANALYSIS_PROMPT,
                            "images": [image_b64],
                        }
                    ],
                    "stream": False,
                    "format": {
                        "type": "object",
                        "properties": {
                            "face_covered": {"type": "boolean"},
                            "position": {
                                "type": "string",
                                "enum": ["supine", "prone", "side", "unknown"],
                            },
                            "in_crib": {"type": "boolean"},
                            "risk_level": {
                                "type": "string",
                                "enum": ["safe", "warning", "danger"],
                            },
                            "description": {"type": "string"},
                        },
                        "required": [
                            "face_covered",
                            "position",
                            "in_crib",
                            "risk_level",
                            "description",
                        ],
                    },
                },
            )
            response.raise_for_status()
            data = response.json()
            content = data["message"]["content"]

            parsed = json.loads(content)
            parsed["timestamp"] = datetime.now()
            status = BabyStatus(**parsed)
            self.last_status = status
            logger.info(f"Vision analysis: {status.risk_level} - {status.description}")

            self.db.log_vision(
                face_covered=status.face_covered,
                position=status.position,
                in_crib=status.in_crib,
                risk_level=status.risk_level,
                description=status.description,
            )

            return status

        except Exception as e:
            logger.error(f"Vision analysis failed: {e}")
            self.db.log_event("vision_error", "error", {"error": str(e)})
            return self.last_status

    def close(self):
        self.client.close()
