import logging
import signal
import sys
import time

from flask import Flask, Response, jsonify, render_template, request
from flask_socketio import SocketIO

from src.pipeline.processor import Pipeline
from src.streaming.camera import CameraManager
from src.audio.analyzer import AudioAnalyzer
from src.utils.config import Config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(
    __name__,
    template_folder="../templates",
    static_folder="../static",
)
app.config["SECRET_KEY"] = "baby-monitor-secret"
socketio = SocketIO(app, cors_allowed_origins="*")

pipeline = Pipeline()


@app.route("/")
def index():
    cameras = CameraManager.list_cameras()
    microphones = AudioAnalyzer.list_devices()
    return render_template("index.html", cameras=cameras, microphones=microphones)


@app.route("/video_feed")
def video_feed():
    def generate():
        while True:
            jpeg = pipeline.camera.get_jpeg()
            if jpeg:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"
                )
            time.sleep(1.0 / Config.VIDEO_STREAM_FPS)

    return Response(
        generate(), mimetype="multipart/x-mixed-replace; boundary=frame"
    )


@app.route("/api/status")
def get_status():
    status = pipeline.get_status()
    return jsonify(status.model_dump(mode="json"))


@app.route("/api/cameras")
def get_cameras():
    return jsonify(CameraManager.list_cameras())


@app.route("/api/microphones")
def get_microphones():
    return jsonify(AudioAnalyzer.list_devices())


@app.route("/api/switch_camera", methods=["POST"])
def switch_camera():
    data = request.json
    camera_id = data.get("camera_id", 0)
    success = pipeline.camera.switch_camera(camera_id)
    return jsonify({"success": success})


@app.route("/api/switch_microphone", methods=["POST"])
def switch_microphone():
    data = request.json
    mic_id = data.get("microphone_id", 0)
    pipeline.audio.stop()
    pipeline.audio.start(mic_id)
    return jsonify({"success": True})


@app.route("/api/test_alert", methods=["POST"])
def test_alert():
    frame = pipeline.camera.get_frame()
    pipeline.alert_manager.discord.send_warning(
        "Test Alert",
        "This is a test alert from Baby Monitor.",
        "warning",
        frame,
    )
    return jsonify({"success": True})


@app.route("/api/force_report", methods=["POST"])
def force_report():
    frame = pipeline.camera.get_frame()
    pipeline.alert_manager.force_status_report(frame)
    return jsonify({"success": True})


def main():
    camera_id = Config.CAMERA_ID
    mic_id = Config.MICROPHONE_ID

    if not pipeline.start(camera_id=camera_id, mic_id=mic_id):
        logger.warning("Pipeline started without camera. Web UI will still be available.")
        logger.warning("Grant camera permission to Terminal/IDE and restart.")

    def shutdown(sig, frame):
        logger.info("Shutting down...")
        pipeline.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    logger.info(f"Starting server on {Config.FLASK_HOST}:{Config.FLASK_PORT}")
    socketio.run(
        app,
        host=Config.FLASK_HOST,
        port=Config.FLASK_PORT,
        debug=False,
        allow_unsafe_werkzeug=True,
    )


if __name__ == "__main__":
    main()
