"""
Video-based baby sleep safety analysis test pipeline.

Reads test videos, extracts frames at intervals, sends each frame to
Ollama Qwen3-VL for safety analysis, and generates a comprehensive report.

Based on research from:
- MDPI "Intelligent Baby Monitor" (4-condition framework)
- IEEE "Edge DL for SIDS Prevention" (prone/supine classification)
- CribNet (crib hazard detection)
- ViTPose (infant pose estimation benchmarks)

Usage:
    uv run python test_video_analysis.py
"""

import base64
import csv
import json
import logging
import os
import sys
import time
from datetime import datetime

import cv2
import httpx
import numpy as np

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("video_test")

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3-vl:latest")
VQA_MAX_WIDTH = 512
FRAME_INTERVAL_SEC = 5  # analyze one frame every N seconds

ANALYSIS_PROMPT = """You are a baby sleep safety monitor AI trained on SIDS prevention guidelines (AAP Safe Sleep recommendations).

Analyze this baby camera image carefully. Check ALL of the following safety conditions:

1. **Baby visible?** Is a baby/infant actually visible in this image?
2. **Sleep position**: supine (on back, SAFE), prone (face-down/on stomach, DANGEROUS), side (on side, WARNING), sitting (upright, WARNING)
3. **Face covered?** Is the baby's nose/mouth area covered by a blanket, cloth, pillow, or any object? (SUFFOCATION RISK - DANGER)
4. **Blanket near face?** Is there a blanket or cloth within 5cm of the baby's face, even if not directly covering it? (WARNING)
5. **In crib/bed?** Is the baby inside a crib, bassinet, or designated sleep area?
6. **Loose objects?** Are there any loose objects in the sleep area (stuffed toys, pillows, bumper pads, loose blankets)?
7. **Eyes open?** Are the baby's eyes open (awake) or closed (sleeping)?

RISK LEVEL RULES:
- "danger": face_covered=true OR (position=prone AND baby appears to be sleeping)
- "warning": position=side OR position=prone (awake/tummy time) OR blanket_near_face=true OR loose_objects=true OR in_crib=false
- "safe": supine position, face clear, in crib, no loose objects

Respond with ONLY a JSON object. No other text."""

FORMAT_SCHEMA = {
    "type": "object",
    "properties": {
        "baby_visible": {"type": "boolean"},
        "face_covered": {"type": "boolean"},
        "blanket_near_face": {"type": "boolean"},
        "position": {
            "type": "string",
            "enum": ["supine", "prone", "side", "sitting", "unknown"],
        },
        "in_crib": {"type": "boolean"},
        "loose_objects": {"type": "boolean"},
        "eyes_open": {"type": "boolean"},
        "risk_level": {
            "type": "string",
            "enum": ["safe", "warning", "danger"],
        },
        "description": {"type": "string"},
    },
    "required": [
        "baby_visible", "face_covered", "blanket_near_face",
        "position", "in_crib", "loose_objects", "eyes_open",
        "risk_level", "description",
    ],
}

# Test video catalog with expected classifications
VIDEO_CATALOG = [
    {
        "file": "01_safe_sleep_positions.mp4",
        "label": "Safe Sleep Positions (educational)",
        "expected": "safe/warning",
        "scenario": "Educational video showing safe vs unsafe positions",
    },
    {
        "file": "02_prone_tummy.mp4",
        "label": "Prone/Tummy Time (2-month)",
        "expected": "warning/danger",
        "scenario": "Baby lying face-down on tummy (prone position)",
    },
    {
        "file": "02_safe_baby_bed.mp4",
        "label": "Baby Sleeping in Bed (Pixabay)",
        "expected": "safe",
        "scenario": "Newborn sleeping peacefully in bed",
    },
    {
        "file": "03_tummy_pushup.mp4",
        "label": "Tummy Time Pushup",
        "expected": "warning",
        "scenario": "Baby on stomach pushing up (tummy time exercise)",
    },
    {
        "file": "04_crib_crying.mp4",
        "label": "Cry-it-out Crib Timelapse",
        "expected": "warning",
        "scenario": "Baby crying in crib (cry-it-out sleep training)",
    },
    {
        "file": "05_rolling.mp4",
        "label": "Early Rolling (tummy time)",
        "expected": "warning",
        "scenario": "Baby beginning to roll during tummy time",
    },
    {
        "file": "07_crib_meltdown.mp4",
        "label": "Crib Meltdown",
        "expected": "warning",
        "scenario": "Baby having a meltdown in crib",
    },
    {
        "file": "08_safe_sleep_guide.mp4",
        "label": "Safe Sleep Guide (UC Davis)",
        "expected": "safe",
        "scenario": "Medical institution safe sleep practices guide",
    },
]


def resize_for_vqa(frame: np.ndarray) -> np.ndarray:
    h, w = frame.shape[:2]
    if w <= VQA_MAX_WIDTH:
        return frame
    scale = VQA_MAX_WIDTH / w
    return cv2.resize(frame, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)


def analyze_frame(client: httpx.Client, frame: np.ndarray) -> dict | None:
    small = resize_for_vqa(frame)
    _, buffer = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 70])
    image_b64 = base64.b64encode(buffer).decode("utf-8")

    try:
        t0 = time.time()
        response = client.post(
            f"{OLLAMA_URL}/api/chat",
            json={
                "model": OLLAMA_MODEL,
                "messages": [
                    {
                        "role": "user",
                        "content": ANALYSIS_PROMPT,
                        "images": [image_b64],
                    }
                ],
                "stream": False,
                "format": FORMAT_SCHEMA,
            },
        )
        response.raise_for_status()
        elapsed = time.time() - t0
        data = response.json()
        content = data["message"]["content"]
        result = json.loads(content)
        result["inference_time"] = round(elapsed, 2)
        return result
    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        return None


def process_video(client: httpx.Client, video_path: str, output_dir: str) -> list[dict]:
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        logger.error(f"Cannot open video: {video_path}")
        return []

    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / fps
    frame_skip = int(fps * FRAME_INTERVAL_SEC)

    basename = os.path.splitext(os.path.basename(video_path))[0]
    logger.info(f"Processing {basename}: {duration:.1f}s, {fps:.0f}fps, {total_frames} frames")

    results = []
    frame_idx = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_idx % frame_skip == 0:
            timestamp_sec = frame_idx / fps
            logger.info(f"  [{basename}] Analyzing frame at {timestamp_sec:.1f}s...")

            # Save the frame as image
            frame_filename = f"{basename}_frame_{frame_idx:05d}.jpg"
            frame_path = os.path.join(output_dir, frame_filename)
            cv2.imwrite(frame_path, frame)

            # Analyze
            result = analyze_frame(client, frame)
            if result:
                result["frame_idx"] = frame_idx
                result["timestamp_sec"] = round(timestamp_sec, 1)
                result["frame_file"] = frame_filename
                results.append(result)

                risk = result.get("risk_level", "?")
                pos = result.get("position", "?")
                desc = result.get("description", "")[:60]
                t = result.get("inference_time", 0)
                logger.info(f"  [{basename}] → {risk.upper()} | {pos} | {t}s | {desc}")

        frame_idx += 1

    cap.release()
    return results


def generate_report(all_results: dict, output_dir: str):
    report_path = os.path.join(output_dir, "VIDEO_TEST_REPORT.md")

    lines = [
        "# Baby Sleep Safety - Video Analysis Test Report",
        f"\n**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Model**: {OLLAMA_MODEL}",
        f"**VQA Image Width**: {VQA_MAX_WIDTH}px",
        f"**Frame Interval**: {FRAME_INTERVAL_SEC}s",
        "",
        "---",
        "",
        "## Research References",
        "",
        "This analysis uses an improved VLM prompt based on:",
        "- **AAP Safe Sleep Guidelines**: Back-to-sleep, clear crib, firm mattress",
        "- **MDPI 'Intelligent Baby Monitor'**: 4-condition detection (face covered, blanket off, movement, eyes open)",
        "- **IEEE 'Edge DL for SIDS Prevention'**: Prone/supine classification with 90% accuracy",
        "- **CribNet**: Crib hazard (toys/blankets) detection with YOLOv8",
        "- **ViTPose**: Infant pose estimation benchmark (best without fine-tuning)",
        "",
        "### Detection Conditions",
        "",
        "| Condition | Level | Source |",
        "|-----------|-------|--------|",
        "| Face covered by blanket/cloth | DANGER | AAP, MDPI, CribNet |",
        "| Prone (face-down) sleeping | DANGER | AAP, IEEE |",
        "| Side sleeping | WARNING | AAP |",
        "| Blanket near face | WARNING | CribNet |",
        "| Loose objects in crib | WARNING | AAP, CribNet |",
        "| Baby not in crib | WARNING | MDPI |",
        "| Eyes open (awake) | INFO | MDPI |",
        "",
        "---",
        "",
    ]

    # Summary table
    lines.append("## Summary")
    lines.append("")
    lines.append("| # | Video | Scenario | Expected | Frames | Results |")
    lines.append("|---|-------|----------|----------|--------|---------|")

    total_frames = 0
    total_danger = 0
    total_warning = 0
    total_safe = 0

    for i, catalog in enumerate(VIDEO_CATALOG):
        fname = catalog["file"]
        results = all_results.get(fname, [])
        n = len(results)
        total_frames += n

        risks = [r.get("risk_level", "?") for r in results]
        d = risks.count("danger")
        w = risks.count("warning")
        s = risks.count("safe")
        total_danger += d
        total_warning += w
        total_safe += s

        summary = f"D:{d} W:{w} S:{s}" if n else "No frames"
        lines.append(f"| {i+1} | {catalog['label']} | {catalog['scenario'][:40]} | {catalog['expected']} | {n} | {summary} |")

    lines.append("")
    lines.append(f"**Total**: {total_frames} frames analyzed. DANGER: {total_danger}, WARNING: {total_warning}, SAFE: {total_safe}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Detailed results per video
    for catalog in VIDEO_CATALOG:
        fname = catalog["file"]
        results = all_results.get(fname, [])
        if not results:
            continue

        lines.append(f"## {catalog['label']}")
        lines.append(f"\n**File**: `{fname}` | **Expected**: {catalog['expected']} | **Scenario**: {catalog['scenario']}")
        lines.append("")
        lines.append("| Time | Risk | Position | Face | Blanket | Objects | Eyes | Crib | Description |")
        lines.append("|------|------|----------|------|---------|---------|------|------|-------------|")

        for r in results:
            t = f"{r['timestamp_sec']:.1f}s"
            risk = r.get("risk_level", "?")
            risk_marker = {"danger": "**DANGER**", "warning": "WARNING", "safe": "safe"}.get(risk, risk)
            pos = r.get("position", "?")
            face = "YES" if r.get("face_covered") else "No"
            blanket = "YES" if r.get("blanket_near_face") else "No"
            objects = "YES" if r.get("loose_objects") else "No"
            eyes = "Open" if r.get("eyes_open") else "Closed"
            crib = "Yes" if r.get("in_crib") else "NO"
            desc = (r.get("description", ""))[:50]
            inf_t = r.get("inference_time", 0)

            lines.append(f"| {t} ({inf_t}s) | {risk_marker} | {pos} | {face} | {blanket} | {objects} | {eyes} | {crib} | {desc} |")

        lines.append("")
        # Frame screenshots reference
        frame_files = [r["frame_file"] for r in results[:3]]
        if frame_files:
            lines.append("**Sample frames**: " + ", ".join(f"`{f}`" for f in frame_files))
        lines.append("")
        lines.append("---")
        lines.append("")

    # Write report
    with open(report_path, "w") as f:
        f.write("\n".join(lines))

    logger.info(f"Report written to {report_path}")

    # Also write CSV for data analysis
    csv_path = os.path.join(output_dir, "video_test_results.csv")
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "video", "frame_idx", "timestamp_sec", "risk_level", "position",
            "face_covered", "blanket_near_face", "loose_objects", "eyes_open",
            "in_crib", "baby_visible", "inference_time", "description",
        ])
        for fname, results in all_results.items():
            for r in results:
                writer.writerow([
                    fname, r.get("frame_idx"), r.get("timestamp_sec"),
                    r.get("risk_level"), r.get("position"),
                    r.get("face_covered"), r.get("blanket_near_face"),
                    r.get("loose_objects"), r.get("eyes_open"),
                    r.get("in_crib"), r.get("baby_visible"),
                    r.get("inference_time"), r.get("description"),
                ])

    logger.info(f"CSV results written to {csv_path}")
    return report_path


def main():
    video_dir = os.path.join(os.path.dirname(__file__), "test_videos")
    output_dir = os.path.join(os.path.dirname(__file__), "output", "video_test")
    os.makedirs(output_dir, exist_ok=True)

    # Warmup Ollama
    logger.info("Warming up Ollama model...")
    client = httpx.Client(timeout=300.0)
    try:
        resp = client.post(
            f"{OLLAMA_URL}/api/chat",
            json={
                "model": OLLAMA_MODEL,
                "messages": [{"role": "user", "content": "hi"}],
                "stream": False,
            },
        )
        resp.raise_for_status()
        logger.info("Model warmed up")
    except Exception as e:
        logger.warning(f"Warmup failed: {e}")

    # Process each video
    all_results = {}
    for catalog in VIDEO_CATALOG:
        video_path = os.path.join(video_dir, catalog["file"])
        if not os.path.exists(video_path):
            logger.warning(f"Video not found: {video_path}")
            continue

        results = process_video(client, video_path, output_dir)
        all_results[catalog["file"]] = results
        logger.info(f"Completed {catalog['file']}: {len(results)} frames analyzed")

    client.close()

    # Generate report
    report_path = generate_report(all_results, output_dir)

    # Print summary
    total = sum(len(r) for r in all_results.values())
    logger.info(f"\n{'='*60}")
    logger.info(f"TEST COMPLETE: {total} frames analyzed across {len(all_results)} videos")
    logger.info(f"Report: {report_path}")
    logger.info(f"{'='*60}")


if __name__ == "__main__":
    main()
