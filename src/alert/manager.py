import logging
import threading
import time
from datetime import datetime

import numpy as np

from src.alert.discord import DiscordAlert
from src.vision.schemas import BabyStatus, MotionStatus, AudioStatus
from src.utils.config import Config

logger = logging.getLogger(__name__)


class AlertManager:
    def __init__(self):
        self.discord = DiscordAlert()
        self.status_history: list[dict] = []
        self.last_warning_time: float = 0
        self.warning_cooldown = 30  # seconds between duplicate warnings
        self.last_report_time: float = time.time()
        self._lock = threading.Lock()

    def check_and_alert(self, baby: BabyStatus, motion: MotionStatus, frame: np.ndarray | None = None):
        with self._lock:
            self.status_history.append({
                "baby": baby,
                "motion": motion,
                "timestamp": datetime.now(),
            })

        now = time.time()

        if baby.risk_level == "danger" and (now - self.last_warning_time > self.warning_cooldown):
            reasons = []
            if baby.face_covered:
                reasons.append("아기 얼굴이 가려짐 - 질식 위험!")
            if baby.blanket_near_face:
                reasons.append("이불이 아기 얼굴 근처에 위험하게 있음")
            if baby.position == "prone":
                reasons.append("아기가 엎드려 있음 (위험한 자세)")
            if not baby.in_crib:
                reasons.append("아기가 침대 밖에 있을 수 있음!")
            if baby.loose_objects:
                reasons.append("수면 공간에 위험한 물체 감지됨")

            title = "위험: 즉시 확인 필요"
            desc = "\n".join(reasons) if reasons else baby.description
            self.discord.send_warning(title, desc, "danger", frame)
            self.last_warning_time = now

        elif baby.risk_level == "warning" and (now - self.last_warning_time > self.warning_cooldown):
            self.discord.send_warning(
                "주의: 아기 확인 필요",
                baby.description,
                "warning",
                frame,
            )
            self.last_warning_time = now

        if now - self.last_report_time >= Config.STATUS_REPORT_INTERVAL:
            self._send_status_report(frame)
            self.last_report_time = now

    def _send_status_report(self, frame: np.ndarray | None = None):
        with self._lock:
            history = list(self.status_history)
            self.status_history.clear()

        if not history:
            summary = "이 기간 동안 수집된 데이터가 없습니다."
        else:
            positions = [h["baby"].position for h in history]
            risk_levels = [h["baby"].risk_level for h in history]
            motions = [h["motion"] for h in history]

            most_common_pos = max(set(positions), key=positions.count)
            pos_kr = {"supine": "등(안전)", "prone": "엎드림", "side": "옆으로", "sitting": "앉음", "unknown": "알 수 없음"}
            had_danger = "danger" in risk_levels
            had_warning = "warning" in risk_levels
            motion_count = sum(1 for m in motions if m.has_motion)
            avg_magnitude = (
                sum(m.motion_magnitude for m in motions) / len(motions)
                if motions
                else 0
            )

            lines = [
                f"**기간**: 최근 {Config.STATUS_REPORT_INTERVAL // 60}분",
                f"**샘플 수**: {len(history)}",
                f"**가장 많은 자세**: {pos_kr.get(most_common_pos, most_common_pos)}",
                f"**움직임 감지**: {motion_count}/{len(history)} 프레임",
                f"**평균 움직임 강도**: {avg_magnitude:.1f}",
            ]
            if had_danger:
                lines.append("🔴 **이 기간 동안 위험 이벤트 발생**")
            elif had_warning:
                lines.append("🟡 **이 기간 동안 주의 이벤트 발생**")
            else:
                lines.append("🟢 **이 기간 동안 안전 문제 없음**")

            last_desc = history[-1]["baby"].description
            if last_desc:
                lines.append(f"\n**최근 관찰**: {last_desc}")

            summary = "\n".join(lines)

        self.discord.send_status_report(summary, frame)

    def force_status_report(self, frame: np.ndarray | None = None):
        self._send_status_report(frame)
        self.last_report_time = time.time()
