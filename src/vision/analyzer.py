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

ANALYSIS_PROMPT = """You are a baby sleep safety monitor AI trained on SIDS prevention guidelines (AAP Safe Sleep recommendations).

Analyze this baby camera image carefully. Check ALL of the following safety conditions:

1. **Baby visible?** Is a baby/infant actually visible in this image?
2. **Sleep position**: supine (on back, SAFE), prone (face-down/on stomach, DANGEROUS), side (on side, WARNING), sitting (upright, WARNING)
3. **Face covered?** Is the baby's nose/mouth area covered by a blanket, cloth, pillow, or any object? (SUFFOCATION RISK - DANGER)
4. **Blanket near face?** Is there a blanket or cloth within 5cm of the baby's face, even if not directly covering it? (WARNING)
5. **In crib/bed?** Is the baby inside a crib, bassinet, or designated sleep area?
6. **Loose objects?** Are there any loose objects in the sleep area (stuffed toys, pillows, bumper pads, loose blankets)?
7. **Eyes open?** Are the baby's eyes open (awake) or closed (sleeping)?

RISK LEVEL RULES:
- "danger": face_covered=true OR (position=prone AND baby appears to be sleeping)
- "warning": position=side OR position=prone (awake/tummy time) OR blanket_near_face=true OR loose_objects=true OR in_crib=false
- "safe": supine position, face clear, in crib, no loose objects

IMPORTANT: Write the "description" field in Korean (한국어).

Respond with ONLY a JSON object. No other text."""


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
                            "baby_visible": {"type": "boolean"},
                            "face_covered": {"type": "boolean"},
                            "blanket_near_face": {"type": "boolean"},
                            "position": {
                                "type": "string",
                                "enum": ["supine", "prone", "side", "sitting", "unknown"],
                            },
                            "in_crib": {"type": "boolean"},
                            "loose_objects": {"type": "boolean"},
                            "eyes_open": {"type": "boolean"},
                            "risk_level": {
                                "type": "string",
                                "enum": ["safe", "warning", "danger"],
                            },
                            "description": {"type": "string"},
                        },
                        "required": [
                            "baby_visible",
                            "face_covered",
                            "blanket_near_face",
                            "position",
                            "in_crib",
                            "loose_objects",
                            "eyes_open",
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
