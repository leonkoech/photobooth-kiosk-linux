#!/usr/bin/env bash
#
# jetson-kiosk-setup.sh — turn a Jetson Nano (Ubuntu 22.04 + GNOME/GDM) into
# the Universe Booth kiosk: boots straight past login into a fullscreen,
# chrome-free view of the local photobooth-kiosk-linux Flask app.
#
# This is the Jetson equivalent of gopro-automation-linux's
# scripts/pi-kiosk-setup.sh -- same idea (autologin + a browser locked into
# one URL, no chrome, auto-restart on crash), different browser. Chromium
# itself only ships as a snap on this Ubuntu image and snap-confine fails
# outright here ("required permitted capability cap_dac_override not
# found"), so this installs Brave instead: a real .deb (not snap), genuine
# Chromium engine, and a true --kiosk mode with no tab strip to begin with.
#
#   sudo ./scripts/jetson-kiosk-setup.sh
#
# Idempotent -- re-run any time (e.g. after `git pull`) to refresh the
# deployed launcher script and systemd units. Re-running preserves an
# already-configured ZOWIE_CAMERA_IP unless you explicitly override it.
#
# Target: Ubuntu 22.04 (Jammy) on Jetson Nano/Orin with L4T NVIDIA drivers,
# GNOME on Xorg via GDM. Assumes this repo is already cloned somewhere on
# the box (APP_DIR below) with a Python venv at $APP_DIR/venv.

set -euo pipefail

# ---------------------------------------------------------------------------
KIOSK_USER="${KIOSK_USER:-developer}"
APP_DIR="${APP_DIR:-/home/$KIOSK_USER/app/photobooth-kiosk-linux}"
BOOTH_PORT="${BOOTH_PORT:-5000}"
DISPLAY_OUTPUT="${DISPLAY_OUTPUT:-DP-0}"
ROTATE="${ROTATE:-left}"   # left|right|inverted|normal
PRINTER_NAME="${PRINTER_NAME:-Canon_SELPHY_CP1300}"

EXISTING_SERVICE=/etc/systemd/system/photobooth-kiosk.service
if [[ -z "${ZOWIE_CAMERA_IP:-}" && -f "$EXISTING_SERVICE" ]]; then
  ZOWIE_CAMERA_IP="$(grep -oP 'ZOWIE_CAMERA_IP=\K[0-9.]+' "$EXISTING_SERVICE" || true)"
fi
ZOWIE_CAMERA_IP="${ZOWIE_CAMERA_IP:-10.1.10.142}"
# ---------------------------------------------------------------------------

die() { echo "ERROR: $*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "run with sudo"
id "$KIOSK_USER" &>/dev/null || die "user '$KIOSK_USER' does not exist (set KIOSK_USER=...)"
[[ -d "$APP_DIR" ]] || die "APP_DIR '$APP_DIR' does not exist -- clone the repo there first (or set APP_DIR=...)"

HOME_DIR="/home/$KIOSK_USER"
echo "==> kiosk user:  $KIOSK_USER  home: $HOME_DIR"
echo "==> app dir:     $APP_DIR"
echo "==> camera IP:   $ZOWIE_CAMERA_IP"

# --- 1. packages -----------------------------------------------------------
echo "==> installing packages…"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y --no-install-recommends \
  xdotool unclutter cups cups-client printer-driver-gutenprint

if ! command -v brave-browser >/dev/null; then
  echo "==> adding Brave's apt repo and installing brave-browser…"
  curl -fsS https://brave-browser-apt-release.s3.brave.com/brave-core.asc \
    | gpg --dearmor -o /usr/share/keyrings/brave-browser-archive-keyring.gpg
  echo "deb [signed-by=/usr/share/keyrings/brave-browser-archive-keyring.gpg arch=$(dpkg --print-architecture)] https://brave-browser-apt-release.s3.brave.com/ stable main" \
    > /etc/apt/sources.list.d/brave-browser-release.list
  apt-get update -qq
  apt-get install -y brave-browser
else
  echo "==> brave-browser already installed"
fi

# --- 2. GDM autologin (no password prompt on boot) --------------------------
echo "==> enabling GDM autologin for $KIOSK_USER…"
GDM_CONF=/etc/gdm3/custom.conf
if [[ -f "$GDM_CONF" ]]; then
  sed -i \
    -e 's/^#\?\s*AutomaticLoginEnable\s*=.*/AutomaticLoginEnable = true/' \
    -e "s/^#\?\s*AutomaticLogin\s*=.*/AutomaticLogin = $KIOSK_USER/" \
    "$GDM_CONF"
  grep -q '^AutomaticLoginEnable' "$GDM_CONF" || \
    sed -i "/^\[daemon\]/a AutomaticLoginEnable = true\nAutomaticLogin = $KIOSK_USER" "$GDM_CONF"
else
  echo "WARNING: $GDM_CONF not found -- skipping autologin setup, configure manually."
fi

# --- 3. kiosk launcher --------------------------------------------------
echo "==> installing kiosk launcher…"
cat > "$HOME_DIR/booth-kiosk-launch.sh" <<EOF
#!/bin/bash
# Universe Booth kiosk launcher — run from GNOME autostart.
set -u

URL="http://localhost:$BOOTH_PORT/"
DISPLAY_OUTPUT="$DISPLAY_OUTPUT"
ROTATE="$ROTATE"   # left|right|inverted|normal — flip to "right" if upside down
PROFILE="\$HOME/.config/brave-kiosk"

sleep 8   # let the desktop + photobooth-kiosk service settle

export DISPLAY="\${DISPLAY:-:1}"

# never let the screen lock/blank over the kiosk
gsettings set org.gnome.desktop.session idle-delay 0
gsettings set org.gnome.desktop.screensaver lock-enabled false
gsettings set org.gnome.desktop.screensaver idle-activation-enabled false
gdbus call --session --dest org.gnome.ScreenSaver --object-path /org/gnome/ScreenSaver --method org.gnome.ScreenSaver.SetActive false >/dev/null 2>&1

xrandr --output "\$DISPLAY_OUTPUT" --rotate "\$ROTATE"
xset s off -dpms s noblank
pkill -f unclutter 2>/dev/null
unclutter -idle 0.5 -root &

pkill -9 -f brave-browser 2>/dev/null
sleep 1

# Safety net for the physical shutter (spacebar): if anything ever steals
# OS-level window focus from the kiosk, a keypress won't reach the page's
# JS at all. Periodically re-assert focus on the Brave window.
(
  while true; do
    sleep 5
    W=\$(xdotool search --onlyvisible --class "Brave-browser" 2>/dev/null | tail -1)
    [ -n "\$W" ] && xdotool windowactivate "\$W" 2>/dev/null
  done
) &

while true; do
  brave-browser \\
    --kiosk \\
    --noerrdialogs \\
    --disable-infobars \\
    --no-first-run \\
    --disable-session-crashed-bubble \\
    --disable-features=Translate \\
    --overscroll-history-navigation=0 \\
    --password-store=basic \\
    --check-for-update-interval=31536000 \\
    --user-data-dir="\$PROFILE" \\
    "\$URL" &
  BRAVE_PID=\$!
  wait "\$BRAVE_PID"
  sleep 2
done
EOF
chown "$KIOSK_USER:$KIOSK_USER" "$HOME_DIR/booth-kiosk-launch.sh"
chmod +x "$HOME_DIR/booth-kiosk-launch.sh"

# clean up the now-unused Epiphany-based helper from earlier iterations
rm -f "$HOME_DIR/toolbar_cover.py"

# --- 4. GNOME autostart entry ------------------------------------------------
echo "==> installing autostart entry…"
install -d -o "$KIOSK_USER" -g "$KIOSK_USER" "$HOME_DIR/.config/autostart"
cat > "$HOME_DIR/.config/autostart/booth-kiosk.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Universe Booth Kiosk
Exec=$HOME_DIR/booth-kiosk-launch.sh
X-GNOME-Autostart-enabled=true
EOF
chown "$KIOSK_USER:$KIOSK_USER" "$HOME_DIR/.config/autostart/booth-kiosk.desktop"

# --- 5. photobooth-kiosk systemd service -------------------------------------
echo "==> installing photobooth-kiosk systemd service…"
cat > /etc/systemd/system/photobooth-kiosk.service <<EOF
[Unit]
Description=Universe Booth Camera Page
After=network.target

[Service]
Type=simple
User=$KIOSK_USER
WorkingDirectory=$APP_DIR
Environment="ZOWIE_CAMERA_IP=$ZOWIE_CAMERA_IP"
Environment="BOOTH_PORT=$BOOTH_PORT"
Environment="PRINTER_NAME=$PRINTER_NAME"
ExecStart=$APP_DIR/venv/bin/python app.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable photobooth-kiosk.service
systemctl restart photobooth-kiosk.service

cat <<EOF

==> Done.

    Reboot for autologin + kiosk autostart to take effect:  sudo reboot

    Service:
      sudo systemctl status photobooth-kiosk
      sudo journalctl -u photobooth-kiosk -f

    Camera IP (Zowie sub/main stream): $ZOWIE_CAMERA_IP
      -- change it: ZOWIE_CAMERA_IP=x.x.x.x sudo -E ./scripts/jetson-kiosk-setup.sh

    Printer: once the Selphy $PRINTER_NAME is plugged in over USB, register it:
      lpadmin -p $PRINTER_NAME -E -v usb://Canon/SELPHY%20CP1300 \\
        -m gutenprint.5.3://canon-cp1300/expert
      (run 'lpinfo -v' first to confirm the exact usb:// device URI)

    Display rotation is set to "$ROTATE" -- change with ROTATE=right/normal/inverted
    and re-run this script, or edit ~$KIOSK_USER/booth-kiosk-launch.sh directly.
EOF
