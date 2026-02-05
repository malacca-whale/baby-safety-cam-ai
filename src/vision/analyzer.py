import base64
import json
import logging
import httpx
import cv2
import numpy as np

from src.utils.config import Config
from src.vision.schemas import BabyStatus

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


class VisionAnalyzer:
    def __init__(self):
        self.client = httpx.Client(timeout=60.0)
        self.last_status = BabyStatus()

    def analyze_frame(self, frame: np.ndarray) -> BabyStatus:
        try:
            _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
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
            from datetime import datetime

            parsed["timestamp"] = datetime.now()
            status = BabyStatus(**parsed)
            self.last_status = status
            logger.info(f"Vision analysis: {status.risk_level} - {status.description}")
            return status

        except Exception as e:
            logger.error(f"Vision analysis failed: {e}")
            return self.last_status

    def close(self):
        self.client.close()
