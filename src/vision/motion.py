import cv2
import numpy as np
import logging

from src.vision.schemas import MotionStatus

logger = logging.getLogger(__name__)


class MotionDetector:
    def __init__(self):
        self.prev_gray = None
        self.lk_params = dict(
            winSize=(15, 15),
            maxLevel=2,
            criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 10, 0.03),
        )
        self.feature_params = dict(
            maxCorners=100, qualityLevel=0.3, minDistance=7, blockSize=7
        )

    def detect(self, frame: np.ndarray) -> MotionStatus:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        if self.prev_gray is None or self.prev_gray.shape != gray.shape:
            self.prev_gray = gray
            return MotionStatus()

        try:
            p0 = cv2.goodFeaturesToTrack(
                self.prev_gray, mask=None, **self.feature_params
            )

            if p0 is None or len(p0) == 0:
                self.prev_gray = gray
                return MotionStatus(description="No trackable features found")

            p1, st, err = cv2.calcOpticalFlowPyrLK(
                self.prev_gray, gray, p0, None, **self.lk_params
            )

            if p1 is None:
                self.prev_gray = gray
                return MotionStatus()

            good_new = p1[st == 1]
            good_old = p0[st == 1]

            if len(good_new) == 0:
                self.prev_gray = gray
                return MotionStatus()

            distances = np.sqrt(
                np.sum((good_new - good_old) ** 2, axis=1)
            )
            magnitude = float(np.mean(distances))

            has_motion = magnitude > 2.0

            if magnitude > 10.0:
                desc = "Strong movement detected"
            elif magnitude > 5.0:
                desc = "Moderate movement detected"
            elif has_motion:
                desc = "Slight movement detected"
            else:
                desc = "No significant movement"

            self.prev_gray = gray
            return MotionStatus(
                has_motion=has_motion,
                motion_magnitude=round(magnitude, 2),
                description=desc,
            )

        except Exception as e:
            logger.error(f"Motion detection failed: {e}")
            self.prev_gray = gray
            return MotionStatus()
