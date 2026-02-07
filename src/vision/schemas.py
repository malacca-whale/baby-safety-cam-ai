from pydantic import BaseModel
from typing import Literal
from datetime import datetime


class BabyStatus(BaseModel):
    face_covered: bool = False
    position: Literal["supine", "prone", "side", "sitting", "unknown"] = "unknown"
    in_crib: bool = True
    risk_level: Literal["safe", "warning", "danger"] = "safe"
    eyes_open: bool | None = None
    loose_objects: bool = False
    blanket_near_face: bool = False
    baby_visible: bool = True
    description: str = ""
    timestamp: datetime | None = None
    alert_channel: Literal["alert", "status"] = "status"
    should_alert: bool = False


class MotionStatus(BaseModel):
    has_motion: bool = False
    motion_magnitude: float = 0.0
    description: str = ""


class AudioStatus(BaseModel):
    is_crying: bool = False
    cry_type: str = ""
    cry_confidence: float = 0.0
    breathing_detected: bool = False
    breathing_rate: float = 0.0
    rms_level: float = 0.0
    spectral_centroid: float = 0.0
    description: str = ""


class CombinedStatus(BaseModel):
    baby: BabyStatus = BabyStatus()
    motion: MotionStatus = MotionStatus()
    audio: AudioStatus = AudioStatus()
    timestamp: datetime | None = None
    last_vision_update: datetime | None = None
    last_motion_update: datetime | None = None
    last_audio_update: datetime | None = None
    vlm_infer_started: datetime | None = None
    vlm_in_progress: bool = False
