import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3-vl:latest")

    DISCORD_WARNING_WEBHOOK = os.getenv("DISCORD_WARNING_WEBHOOK", "")
    DISCORD_STATUS_WEBHOOK = os.getenv("DISCORD_STATUS_WEBHOOK", "")

    CAMERA_ID = int(os.getenv("CAMERA_ID", "0"))
    MICROPHONE_ID = int(os.getenv("MICROPHONE_ID", "0"))

    VISION_FPS = int(os.getenv("VISION_FPS", "2"))
    MOTION_FPS = int(os.getenv("MOTION_FPS", "15"))
    VIDEO_STREAM_FPS = int(os.getenv("VIDEO_STREAM_FPS", "30"))

    STATUS_REPORT_INTERVAL = int(os.getenv("STATUS_REPORT_INTERVAL", "300"))

    VIDEO_WIDTH = 640
    VIDEO_HEIGHT = 480
    JPEG_QUALITY = 80

    FLASK_HOST = os.getenv("FLASK_HOST", "0.0.0.0")
    FLASK_PORT = int(os.getenv("FLASK_PORT", "8080"))
