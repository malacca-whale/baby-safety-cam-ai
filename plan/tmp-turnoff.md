# Temporarily Disabled Features (VLM-only testing)

## What's OFF

| Feature | File | What was disabled |
|---------|------|-------------------|
| Audio capture | `src/pipeline/processor.py:66-69` | `audio.start()` commented out |
| Motion detection thread | `src/pipeline/processor.py:80-81` | `_motion_loop` thread not started |
| Cry detection (audio-based) | `src/pipeline/processor.py:160-168` | Audio cry alert in vision loop commented out |

## What's still ON

| Feature | Notes |
|---------|-------|
| Web UI + camera streaming | Normal operation |
| VLM vision analysis (Ollama) | Running with 240px resize, saving to `output/resized/` |
| Discord alerts (danger/warning) | Triggered by VLM risk_level via `alert_manager.check_and_alert()` |
| Discord 5-min status reports | Triggered inside `check_and_alert()` timer |
| Vision throttling | 30s min interval, no duplicate requests |
| systemd auto-restart | `baby-ai-cam.service` enabled |

## How to restore

Search for `[TMP-OFF]` in `src/pipeline/processor.py` and uncomment the 3 blocks.
