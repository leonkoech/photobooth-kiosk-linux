"""Universe Booth camera page — Jetson Nano.

Serves a live MJPEG view from the Zowie camera as a locally-hosted page,
meant to be opened fullscreen (kiosk-mode browser) on the Nano's HDMI
output at boot.
"""

from __future__ import annotations

import os
import time

from flask import Flask, Response, jsonify, render_template, send_from_directory

from zowie_camera import ZowieCamera

app = Flask(__name__)

CAMERA_IP = os.environ.get("ZOWIE_CAMERA_IP", "10.1.10.142")
CAPTURES_DIR = os.path.join(os.path.dirname(__file__), "captures")

camera = ZowieCamera(ip=CAMERA_IP)

os.makedirs(CAPTURES_DIR, exist_ok=True)


def mjpeg_generator():
    boundary = b"--frame"
    for frame in camera.mjpeg_frames():
        yield (
            boundary + b"\r\n"
            b"Content-Type: image/jpeg\r\n"
            b"Content-Length: " + str(len(frame)).encode() + b"\r\n\r\n"
            + frame + b"\r\n"
        )


@app.route("/")
def index():
    return render_template("index.html", camera_ip=CAMERA_IP)


@app.route("/stream")
def stream():
    return Response(
        mjpeg_generator(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


@app.route("/capture", methods=["POST"])
def capture():
    filename = f"shot_{int(time.time() * 1000)}.jpg"
    out_path = os.path.join(CAPTURES_DIR, filename)
    ok = camera.snapshot(out_path, full_res=True)
    if not ok:
        return jsonify({"ok": False, "error": "camera snapshot failed"}), 502
    return jsonify({"ok": True, "url": f"/captures/{filename}"})


@app.route("/captures/<path:filename>")
def captures(filename):
    return send_from_directory(CAPTURES_DIR, filename)


if __name__ == "__main__":
    port = int(os.environ.get("BOOTH_PORT", "5000"))
    app.run(host="0.0.0.0", port=port, threaded=True)
