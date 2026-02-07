import base64
import json
import logging
import os
import httpx
import cv2
import numpy as np
from datetime import datetime

from src.utils.config import Config
from src.vision.schemas import BabyStatus
from src.db.database import Database

logger = logging.getLogger(__name__)

DEFAULT_ANALYSIS_PROMPT = """당신은 SIDS 예방 가이드라인(AAP 안전 수면 권장사항)으로 훈련된 아기 수면 안전 모니터링 AI입니다.

이 아기 카메라 이미지를 주의 깊게 분석하세요. 다음 안전 조건들을 모두 확인하세요:

1. 아기 보임? 이 이미지에 아기/유아가 실제로 보입니까?
2. 수면 자세: 바로 누운 자세(등을 대고 누움, 안전), 엎드린 자세(얼굴이 아래로, 위험), 옆으로 누운 자세(경고), 앉은 자세(경고)
3. 얼굴 가려짐? 아기의 코/입 부분이 담요, 천, 베개 또는 다른 물체로 덮여 있습니까? (질식 위험 - 위험)
4. 얼굴 근처 담요? 아기 얼굴 5cm 이내에 담요나 천이 있습니까?
5. 침대 안? 아기가 유아용 침대, 바구니 또는 지정된 수면 공간 안에 있습니까?
6. 느슨한 물건? 수면 공간에 느슨한 물건(인형, 베개, 범퍼 패드, 느슨한 담요)이 있습니까?
7. 눈 뜸? 아기의 눈이 떠있습니까(깨어있음) 아니면 감겨있습니까(수면 중)?

위험 수준 규칙:
- 위험: 얼굴 가려짐 또는 (엎드린 자세이면서 수면 중으로 보임)
- 경고: 옆으로 누움 또는 엎드린 자세(깨어있음/tummy time) 또는 얼굴 근처 담요 또는 느슨한 물건 또는 침대 밖
- 안전: 바로 누운 자세, 얼굴 깨끗함, 침대 안, 느슨한 물건 없음

관찰한 내용을 자연스러운 한국어로 2-3문장으로 설명하세요. 아기의 상태와 안전성에 대해 명확하게 서술하세요."""


VQA_MAX_SIZE = 240  # max width for Ollama VQA requests


class VisionAnalyzer:
    def __init__(self):
        self.client = httpx.Client(timeout=600.0)
        self.last_status = BabyStatus()
        self._warmed_up = False
        self.db = Database()
        self._cached_prompt: str | None = None

    def get_prompt(self) -> str:
        """Get the current VLM prompt from DB (with caching)."""
        if self._cached_prompt is None:
            self._cached_prompt = self.db.get_config("vlm_prompt") or DEFAULT_ANALYSIS_PROMPT
        return self._cached_prompt

    def reload_prompt(self):
        """Force reload prompt from DB."""
        self._cached_prompt = self.db.get_config("vlm_prompt") or DEFAULT_ANALYSIS_PROMPT
        logger.info("VLM prompt reloaded from DB")

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

    def _judge_severity(self, vlm_text: str) -> tuple[str, str, bool]:
        """
        LLM reads VLM output and decides:
        - risk_level: safe/warning/danger
        - channel: alert or status
        - should_alert: whether to send Discord alert

        Returns: (risk_level, channel, should_alert)
        """
        try:
            judge_prompt = f"""아래는 아기 모니터링 AI가 카메라 이미지를 분석한 결과입니다:

"{vlm_text}"

이 분석 결과를 읽고 다음을 판단하세요:
1. 위험 수준: "safe", "warning", "danger" 중 하나
2. 이것이 즉각적인 알림이 필요한 심각한 상황입니까?

다음 기준을 따르세요:
- "danger": 얼굴 가려짐, 엎드려 자는 중, 질식 위험 등 → 즉시 알림 필요
- "warning": 침대 밖, 느슨한 물건, 경미한 위험 → 알림 필요할 수 있음
- "safe": 정상 수면, 안전한 환경 → 알림 불필요

JSON 형식으로만 답변하세요:
{{"risk_level": "safe/warning/danger", "should_alert": true/false, "reason": "판단 이유 한문장"}}"""

            response = self.client.post(
                f"{Config.OLLAMA_URL}/api/chat",
                json={
                    "model": Config.OLLAMA_MODEL,
                    "messages": [{"role": "user", "content": judge_prompt}],
                    "stream": False,
                    "format": "json",
                },
            )
            response.raise_for_status()
            data = response.json()
            judgment = json.loads(data["message"]["content"])

            risk_level = judgment.get("risk_level", "warning")
            should_alert = judgment.get("should_alert", False)
            channel = "alert" if should_alert else "status"

            logger.info(f"LLM judgment: {risk_level}, alert={should_alert}, reason={judgment.get('reason')}")
            return risk_level, channel, should_alert

        except Exception as e:
            logger.error(f"LLM judgment failed: {e}")
            # Fallback to safe defaults
            return "warning", "status", False

    def _save_resized(self, small: np.ndarray):
        out_dir = os.path.join(os.path.dirname(__file__), "..", "..", "output", "resized")
        os.makedirs(out_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(out_dir, f"{ts}.jpg")
        cv2.imwrite(path, small, [cv2.IMWRITE_JPEG_QUALITY, 70])
        logger.info(f"Saved resized frame: {path}")

    def analyze_frame(self, frame: np.ndarray) -> BabyStatus:
        try:
            small = self._resize_for_vqa(frame)
            self._save_resized(small)
            _, buffer = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 70])
            image_b64 = base64.b64encode(buffer).decode("utf-8")

            # Step 1: VLM analyzes image and returns plain text
            prompt = self.get_prompt()
            response = self.client.post(
                f"{Config.OLLAMA_URL}/api/chat",
                json={
                    "model": Config.OLLAMA_MODEL,
                    "messages": [
                        {
                            "role": "user",
                            "content": prompt,
                            "images": [image_b64],
                        }
                    ],
                    "stream": False,
                },
            )
            response.raise_for_status()
            data = response.json()
            vlm_text = data["message"]["content"].strip()

            logger.info(f"VLM analysis: {vlm_text}")

            # Step 2: LLM judges severity and decides channel
            risk_level, channel, should_alert = self._judge_severity(vlm_text)

            # Create BabyStatus with parsed info
            status = BabyStatus(
                baby_visible=True,  # Inferred from text
                face_covered=False,  # Parsed by LLM judge
                blanket_near_face=False,
                position="unknown",
                in_crib=True,
                loose_objects=False,
                eyes_open=None,
                risk_level=risk_level,
                description=vlm_text,
                timestamp=datetime.now(),
                alert_channel=channel,
                should_alert=should_alert,
            )

            self.last_status = status
            logger.info(f"Final status: {status.risk_level} (channel={channel}, alert={should_alert})")

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
