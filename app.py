"""Universe Booth camera page — Jetson Nano.

Serves a live MJPEG view from the Zowie camera as a locally-hosted page,
meant to be opened fullscreen (kiosk-mode Chromium) on the Nano's HDMI
output at boot.
"""

from __future__ import annotations

import os
import time

from flask import Flask, Response, render_template

from zowie_camera import ZowieCamera

app = Flask(__name__)

CAMERA_IP = os.environ.get("ZOWIE_CAMERA_IP", "10.1.10.142")
FRAME_PATH = "/tmp/universe_booth_frame.jpg"

camera = ZowieCamera(ip=CAMERA_IP)


def mjpeg_generator():
    boundary = b"--frame"
    while True:
        ok = camera.snapshot(FRAME_PATH, full_res=False)
        if ok:
            with open(FRAME_PATH, "rb") as f:
                frame = f.read()
            yield (
                boundary + b"\r\n"
                b"Content-Type: image/jpeg\r\n"
                b"Content-Length: " + str(len(frame)).encode() + b"\r\n\r\n"
                + frame + b"\r\n"
            )
        else:
            time.sleep(0.5)


@app.route("/")
def index():
    return render_template("index.html", camera_ip=CAMERA_IP)


@app.route("/stream")
def stream():
    return Response(
        mjpeg_generator(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


if __name__ == "__main__":
    port = int(os.environ.get("BOOTH_PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
