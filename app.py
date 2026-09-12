"""Universe Booth camera page — Jetson Nano.

Serves a live MJPEG view from the Zowie camera as a locally-hosted page,
meant to be opened fullscreen (kiosk-mode browser) on the Nano's HDMI
output at boot.
"""

from __future__ import annotations

import ipaddress
import os
import subprocess
import time

from flask import Flask, Response, abort, jsonify, render_template, request, send_from_directory

from zowie_camera import ZowieCamera

app = Flask(__name__)

CAMERA_IP = os.environ.get("ZOWIE_CAMERA_IP", "10.1.10.142")
CAPTURES_DIR = os.path.join(os.path.dirname(__file__), "captures")

# The kiosk's own display — needed to launch GUI settings apps (e.g. Wi-Fi)
# from the Flask process, which runs headless under systemd.
KIOSK_DISPLAY = os.environ.get("KIOSK_DISPLAY", ":1")
KIOSK_XAUTHORITY = os.environ.get(
    "KIOSK_XAUTHORITY", "/run/user/1000/gdm/Xauthority"
)

camera = ZowieCamera(ip=CAMERA_IP)

os.makedirs(CAPTURES_DIR, exist_ok=True)


def _require_local_request():
    """The admin routes control the physical machine (Wi-Fi, reboot, shutdown)
    and accept a sudo password over HTTP. This box is also reachable publicly
    via a Cloudflare Tunnel, so these routes are additionally blocked at the
    tunnel config (path-excluded from the ingress rule) — this check is a
    second layer in case that ever gets misconfigured. Only requests that
    genuinely originate from this machine or its LAN are allowed."""
    try:
        addr = ipaddress.ip_address(request.remote_addr)
    except ValueError:
        abort(403)
    if addr.is_loopback or addr.is_private:
        return
    abort(403)


def _run_sudo(password: str, args: list[str], timeout: int = 20) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["sudo", "-S", "-k", *args],
        input=(password + "\n").encode(),
        capture_output=True,
        timeout=timeout,
    )


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


@app.route("/admin/verify", methods=["POST"])
def admin_verify():
    _require_local_request()
    password = (request.get_json(silent=True) or {}).get("password", "")
    result = _run_sudo(password, ["-v"])
    return jsonify({"ok": result.returncode == 0})


@app.route("/admin/action", methods=["POST"])
def admin_action():
    _require_local_request()
    body = request.get_json(silent=True) or {}
    password = body.get("password", "")
    action = body.get("action", "")

    gui_env = {**os.environ, "DISPLAY": KIOSK_DISPLAY, "XAUTHORITY": KIOSK_XAUTHORITY}

    if action == "wifi":
        # No sudo needed for the settings UI itself — just gated behind the
        # same admin password for a consistent "admin only" experience.
        check = _run_sudo(password, ["-v"])
        if check.returncode != 0:
            return jsonify({"ok": False, "error": "incorrect password"}), 401
        subprocess.Popen(
            ["gnome-control-center", "wifi"], env=gui_env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        return jsonify({"ok": True})

    if action == "restart_camera":
        result = _run_sudo(password, ["systemctl", "restart", "photobooth-kiosk"])
        return jsonify({"ok": result.returncode == 0})

    if action == "reboot":
        result = _run_sudo(password, ["reboot"])
        return jsonify({"ok": result.returncode == 0})

    if action == "shutdown":
        result = _run_sudo(password, ["shutdown", "now"])
        return jsonify({"ok": result.returncode == 0})

    return jsonify({"ok": False, "error": "unknown action"}), 400


if __name__ == "__main__":
    port = int(os.environ.get("BOOTH_PORT", "5000"))
    app.run(host="0.0.0.0", port=port, threaded=True)
