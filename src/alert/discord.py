import logging
import cv2
import numpy as np
from datetime import datetime
from discord_webhook import DiscordWebhook, DiscordEmbed

from src.utils.config import Config
from src.db.database import Database

logger = logging.getLogger(__name__)

RISK_COLORS = {
    "safe": "2ecc71",
    "warning": "f39c12",
    "danger": "e74c3c",
}


class DiscordAlert:
    def __init__(self):
        self.warning_url = Config.DISCORD_WARNING_WEBHOOK
        self.status_url = Config.DISCORD_STATUS_WEBHOOK
        self.db = Database()

    def _frame_to_bytes(self, frame: np.ndarray) -> bytes | None:
        if frame is None:
            return None
        _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return buffer.tobytes()

    def send_warning(self, title: str, description: str, risk_level: str, frame: np.ndarray | None = None):
        try:
            webhook = DiscordWebhook(url=self.warning_url)
            color = RISK_COLORS.get(risk_level, "95a5a6")
            embed = DiscordEmbed(
                title=f"⚠️ {title}",
                description=description,
                color=int(color, 16),
            )
            embed.set_timestamp(datetime.now().isoformat())
            risk_kr = {"safe": "안전", "warning": "주의", "danger": "위험"}
            embed.add_embed_field(name="위험 수준", value=risk_kr.get(risk_level, risk_level.upper()), inline=True)

            has_image = False
            if frame is not None:
                img_bytes = self._frame_to_bytes(frame)
                if img_bytes:
                    webhook.add_file(file=img_bytes, filename="capture.jpg")
                    embed.set_image(url="attachment://capture.jpg")
                    has_image = True

            webhook.add_embed(embed)
            resp = webhook.execute()
            logger.info(f"Warning sent: {title}")

            self.db.log_discord_message(
                channel="warning", title=title, description=description,
                risk_level=risk_level, has_image=has_image, success=True,
            )
            self.db.log_event("discord_warning", risk_level, {
                "title": title, "description": description,
            })

            return resp
        except Exception as e:
            logger.error(f"Failed to send warning: {e}")
            self.db.log_discord_message(
                channel="warning", title=title, description=description,
                risk_level=risk_level, success=False, error=str(e),
            )
            return None

    def send_status_report(self, summary: str, frame: np.ndarray | None = None):
        try:
            webhook = DiscordWebhook(url=self.status_url)
            embed = DiscordEmbed(
                title="📊 아기 상태 보고서",
                description=summary,
                color=int("3498db", 16),
            )
            embed.set_timestamp(datetime.now().isoformat())

            has_image = False
            if frame is not None:
                img_bytes = self._frame_to_bytes(frame)
                if img_bytes:
                    webhook.add_file(file=img_bytes, filename="status.jpg")
                    embed.set_image(url="attachment://status.jpg")
                    has_image = True

            webhook.add_embed(embed)
            resp = webhook.execute()
            logger.info("Status report sent")

            self.db.log_discord_message(
                channel="status", title="아기 상태 보고서",
                description=summary, has_image=has_image, success=True,
            )
            self.db.log_event("discord_status", "info", {"summary": summary[:200]})

            return resp
        except Exception as e:
            logger.error(f"Failed to send status report: {e}")
            self.db.log_discord_message(
                channel="status", title="아기 상태 보고서",
                description=summary, success=False, error=str(e),
            )
            return None
