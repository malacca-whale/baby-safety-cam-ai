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
                reasons.append("Baby's face is covered - suffocation risk!")
            if baby.position == "prone":
                reasons.append("Baby is face-down (prone position)")
            if not baby.in_crib:
                reasons.append("Baby may be outside the crib!")

            title = "DANGER: Immediate Attention Required"
            desc = "\n".join(reasons) if reasons else baby.description
            self.discord.send_warning(title, desc, "danger", frame)
            self.last_warning_time = now

        elif baby.risk_level == "warning" and (now - self.last_warning_time > self.warning_cooldown):
            self.discord.send_warning(
                "Warning: Check Baby",
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
            summary = "No data collected in this period."
        else:
            positions = [h["baby"].position for h in history]
            risk_levels = [h["baby"].risk_level for h in history]
            motions = [h["motion"] for h in history]

            most_common_pos = max(set(positions), key=positions.count)
            had_danger = "danger" in risk_levels
            had_warning = "warning" in risk_levels
            motion_count = sum(1 for m in motions if m.has_motion)
            avg_magnitude = (
                sum(m.motion_magnitude for m in motions) / len(motions)
                if motions
                else 0
            )

            lines = [
                f"**Period**: Last {Config.STATUS_REPORT_INTERVAL // 60} minutes",
                f"**Samples**: {len(history)}",
                f"**Most common position**: {most_common_pos}",
                f"**Movement detected**: {motion_count}/{len(history)} frames",
                f"**Avg motion magnitude**: {avg_magnitude:.1f}",
            ]
            if had_danger:
                lines.append("🔴 **Danger events occurred during this period**")
            elif had_warning:
                lines.append("🟡 **Warning events occurred during this period**")
            else:
                lines.append("🟢 **No safety concerns during this period**")

            last_desc = history[-1]["baby"].description
            if last_desc:
                lines.append(f"\n**Latest observation**: {last_desc}")

            summary = "\n".join(lines)

        self.discord.send_status_report(summary, frame)

    def force_status_report(self, frame: np.ndarray | None = None):
        self._send_status_report(frame)
        self.last_report_time = time.time()
