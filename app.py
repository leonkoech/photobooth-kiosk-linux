"""Universe Booth camera page — Jetson Nano.

Serves a live MJPEG view from the Zowie camera as a locally-hosted page,
meant to be opened fullscreen (kiosk-mode browser) on the Nano's HDMI
output at boot.
"""

from __future__ import annotations

import base64
import functools
import hmac
import ipaddress
import json
import os
import re
import subprocess
import time

from flask import Flask, Response, abort, jsonify, request, send_from_directory

from zowie_camera import ZowieCamera

# The UI itself lives in the leonkoech/photobooth-kiosk-front repo (a Next.js
# app built with `output: "export"`) and is deployed here as a static export
# -- this Flask app is purely the API + camera/printer backend. Serving the
# export directly (static_url_path="") means its asset paths (/_next/...,
# /favicon.ico) resolve at the root alongside the API routes below, same
# origin, no CORS. Rebuild the frontend and copy its `out/` here to update.
FRONTEND_DIST = os.path.join(os.path.dirname(__file__), "frontend_dist")

app = Flask(__name__, static_folder=FRONTEND_DIST, static_url_path="")

CAMERA_IP = os.environ.get("ZOWIE_CAMERA_IP", "10.1.10.142")
CAPTURES_DIR = os.path.join(os.path.dirname(__file__), "captures")
PRINTS_DIR = os.path.join(os.path.dirname(__file__), "prints")
PHONES_LOG = os.path.join(os.path.dirname(__file__), "phones.jsonl")

# CUPS queue name for the Canon Selphy CP1300, once it's plugged in and added
# via `lpadmin -p Canon_SELPHY_CP1300 -E -v usb://... -m gutenprint.5.3://canon-cp1300/expert`
PRINTER_NAME = os.environ.get("PRINTER_NAME", "Canon_SELPHY_CP1300")

# The kiosk's own display — needed to launch GUI settings apps (e.g. Wi-Fi)
# from the Flask process, which runs headless under systemd.
KIOSK_DISPLAY = os.environ.get("KIOSK_DISPLAY", ":1")
KIOSK_XAUTHORITY = os.environ.get(
    "KIOSK_XAUTHORITY", "/run/user/1000/gdm/Xauthority"
)

# Shared secret the frontend sends on every camera/print/payment call. This
# is baked into the frontend's static JS bundle at build time (see
# photobooth-kiosk-front's lib/api.ts) -- since that bundle is served
# publicly over the Cloudflare Tunnel, anyone who views-source can read it.
# It's a deterrent against bots/scripts hitting these endpoints cold, NOT a
# real secret. The actual protection for anything that costs money or
# consumes paper (/capture, /burst, /print, /payment/charge) is the
# tunnel-level ingress exclusion below -- same technique already used for
# /admin/* -- which makes these routes unreachable from the public internet
# at all, regardless of the key. Set a real BOOTH_API_KEY via the systemd
# unit; this default is only for local dev.
BOOTH_API_KEY = os.environ.get("BOOTH_API_KEY", "dev-only-change-me")

camera = ZowieCamera(ip=CAMERA_IP)

os.makedirs(CAPTURES_DIR, exist_ok=True)
os.makedirs(PRINTS_DIR, exist_ok=True)


def _require_api_key():
    key = request.headers.get("X-Booth-Key", "")
    if not hmac.compare_digest(key, BOOTH_API_KEY):
        abort(401)


def api_key_required(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        _require_api_key()
        return fn(*args, **kwargs)
    return wrapper


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
    return send_from_directory(FRONTEND_DIST, "index.html")


@app.route("/stream")
def stream():
    return Response(
        mjpeg_generator(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


@app.route("/capture", methods=["POST"])
@api_key_required
def capture():
    filename = f"shot_{int(time.time() * 1000)}.jpg"
    out_path = os.path.join(CAPTURES_DIR, filename)
    ok = camera.snapshot(out_path, full_res=True)
    if not ok:
        return jsonify({"ok": False, "error": "camera snapshot failed"}), 502
    return jsonify({"ok": True, "url": f"/captures/{filename}"})


@app.route("/burst", methods=["POST"])
@api_key_required
def burst():
    # The classic photobooth shape: 4 shots a beat apart, customer picks
    # which to print and (optionally) which to save/send later.
    session = f"burst_{int(time.time() * 1000)}"
    out_dir = os.path.join(CAPTURES_DIR, session)
    paths = camera.burst(out_dir, count=4, interval=0.8, prefix="shot")
    if not paths:
        return jsonify({"ok": False, "error": "camera burst failed"}), 502
    urls = [f"/captures/{session}/{os.path.basename(p)}" for p in paths]
    return jsonify({"ok": True, "urls": urls})


@app.route("/captures/<path:filename>")
def captures(filename):
    return send_from_directory(CAPTURES_DIR, filename)


@app.route("/save_phone", methods=["POST"])
@api_key_required
def save_phone():
    body = request.get_json(silent=True) or {}
    phone = re.sub(r"[^0-9+]", "", body.get("phone", ""))
    if not phone:
        return jsonify({"ok": False, "error": "empty phone number"}), 400
    # No SMS/delivery service is wired up yet (AWS SNS, once that account is
    # configured) — this just records the number and which photo they
    # wanted saved, so nothing is lost once sending is wired up.
    photo_url = body.get("photo_url")
    with open(PHONES_LOG, "a") as f:
        f.write(json.dumps({"ts": time.time(), "phone": phone, "photo_url": photo_url}) + "\n")
    return jsonify({"ok": True})


@app.route("/payment/charge", methods=["POST"])
@api_key_required
def payment_charge():
    # PLACEHOLDER — the Stripe Reader M2 hasn't arrived yet. Once it has,
    # this needs: a backend endpoint that creates a Stripe Terminal
    # ConnectionToken, the Stripe Terminal JS SDK on the frontend to
    # discover/connect the M2 over Bluetooth, then create + collect +
    # confirm a PaymentIntent before calling this route. For now this
    # always "succeeds" so the rest of the flow (sign -> phone -> pay ->
    # print) can be built and tested without the hardware.
    return jsonify({"ok": True, "simulated": True})


@app.route("/print", methods=["POST"])
@api_key_required
def print_photo():
    body = request.get_json(silent=True) or {}
    data_url = body.get("image", "")
    copies = max(1, min(20, int(body.get("copies", 1) or 1)))
    match = re.match(r"^data:image/(png|jpeg);base64,(.+)$", data_url)
    if not match:
        return jsonify({"ok": False, "error": "invalid image data"}), 400

    ext = "png" if match.group(1) == "png" else "jpg"
    filename = f"print_{int(time.time() * 1000)}.{ext}"
    out_path = os.path.join(PRINTS_DIR, filename)
    with open(out_path, "wb") as f:
        f.write(base64.b64decode(match.group(2)))

    try:
        result = subprocess.run(
            ["lp", "-d", PRINTER_NAME, "-n", str(copies), out_path],
            capture_output=True, timeout=30,
        )
    except FileNotFoundError:
        return jsonify({"ok": False, "error": "CUPS 'lp' command not found"}), 500
    except subprocess.TimeoutExpired:
        return jsonify({"ok": False, "error": "print command timed out"}), 504

    if result.returncode != 0:
        return jsonify({
            "ok": False,
            "error": result.stderr.decode(errors="replace").strip() or "print job failed",
        }), 502
    return jsonify({"ok": True})


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
