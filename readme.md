# Universe Booth — camera kiosk

Flask app that runs on a Jetson Nano and serves the entire booth UI: a live
view from a Zowietek RTSP camera, styled as a Polaroid, with a full
capture → sign → pay → print flow. This app *is* the kiosk frontend — the
Nano boots straight into it fullscreen via Brave in `--kiosk` mode (no
separate frontend project; `photobooth-kiosk-front` in this org is an
unrelated leftover from the original fork, not used here).

## What it does

1. Live camera preview (Zowie's lightweight `/sub/av` H.264 stream — the 4K
   `/main/av` stream is used only for the actual capture, not the live view;
   see `zowie_camera.py` for why).
2. Tap the shutter (or press spacebar, for a non-touch display) → 3-2-1
   countdown → flash → full-res capture.
3. Sign directly on the photo.
4. Pick quantity and pay (Stripe Reader M2 tap-to-pay — stubbed as
   "simulate payment" until the reader hardware is connected; see
   `/payment/charge` in `app.py`).
5. Prints via CUPS to a Canon Selphy CP1300 while the customer optionally
   enters a phone number, in parallel, during the print job's own wait time.
6. Hidden admin corner (top-right, sudo-password gated, blocked from the
   public Cloudflare Tunnel) for Wi-Fi settings / restarting the service /
   reboot / shutdown.

## Running it

```
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
ZOWIE_CAMERA_IP=<camera ip> ./venv/bin/python app.py
```

Opens on `http://localhost:5000/`.

## Setting up a new Jetson as a kiosk

`scripts/jetson-kiosk-setup.sh` provisions everything: GDM autologin, Brave
in kiosk mode, the `photobooth-kiosk` systemd service, and CUPS/Gutenprint
for the Selphy CP1300.

```
sudo ./scripts/jetson-kiosk-setup.sh
```

See the script's header comment for env vars (camera IP, display rotation,
printer name, etc.) and `terraform/` for the Cloudflare Tunnel/DNS side of
the deployment.

## Files

| File | Purpose |
|---|---|
| `app.py` | Flask routes: stream, capture, admin, payment stub, print |
| `zowie_camera.py` | RTSP client for the Zowietek camera (snapshot + live stream) |
| `templates/index.html` | The entire kiosk UI (single page, vanilla JS) |
| `scripts/jetson-kiosk-setup.sh` | Reproducible kiosk provisioning for a Jetson |
| `terraform/` | Cloudflare Tunnel + DNS for the public `booth-1.uai.tech` URL |
| `sensors.py` | Leftover from an earlier (unrelated) MQ-3/ultrasonic sensor project on Orange Pi hardware — not wired into the booth app, kept only in case it's revisited |
