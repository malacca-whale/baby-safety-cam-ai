from pydantic import BaseModel
from typing import Literal
from datetime import datetime


class BabyStatus(BaseModel):
    face_covered: bool = False
    position: Literal["supine", "prone", "side", "unknown"] = "unknown"
    in_crib: bool = True
    risk_level: Literal["safe", "warning", "danger"] = "safe"
    description: str = ""
    timestamp: datetime | None = None


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
