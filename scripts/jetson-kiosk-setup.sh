#!/usr/bin/env bash
#
# jetson-kiosk-setup.sh — turn a Jetson Nano (Ubuntu 22.04 + GNOME/GDM) into
# the Universe Booth kiosk: boots straight past login into a fullscreen,
# chrome-free view of the local photobooth-kiosk-linux Flask app.
#
# This is the Jetson equivalent of gopro-automation-linux's
# scripts/pi-kiosk-setup.sh, but for this box specifically -- Chromium isn't
# usable here (only ships as a snap on this Ubuntu image, and snap-confine
# fails outright in this environment: "required permitted capability
# cap_dac_override not found"), so this uses Epiphany (GNOME Web) instead,
# worked around for its rough edges (see comments below).
#
#   sudo ./scripts/jetson-kiosk-setup.sh
#
# Idempotent -- re-run any time (e.g. after `git pull`) to refresh the
# deployed helper scripts and systemd units.
#
# Target: Ubuntu 22.04 (Jammy) on Jetson Nano/Orin with L4T NVIDIA drivers,
# GNOME on Xorg via GDM. Assumes this repo is already cloned somewhere on
# the box (APP_DIR below) with a Python venv at $APP_DIR/venv.

set -euo pipefail

# ---------------------------------------------------------------------------
KIOSK_USER="${KIOSK_USER:-developer}"
APP_DIR="${APP_DIR:-/home/$KIOSK_USER/app/photobooth-kiosk-linux}"
BOOTH_PORT="${BOOTH_PORT:-5000}"
ZOWIE_CAMERA_IP="${ZOWIE_CAMERA_IP:-10.1.10.142}"
DISPLAY_OUTPUT="${DISPLAY_OUTPUT:-DP-0}"
ROTATE="${ROTATE:-left}"   # left|right|inverted|normal
PRINTER_NAME="${PRINTER_NAME:-Canon_SELPHY_CP1300}"
# ---------------------------------------------------------------------------

die() { echo "ERROR: $*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "run with sudo"
id "$KIOSK_USER" &>/dev/null || die "user '$KIOSK_USER' does not exist (set KIOSK_USER=...)"
[[ -d "$APP_DIR" ]] || die "APP_DIR '$APP_DIR' does not exist -- clone the repo there first (or set APP_DIR=...)"

HOME_DIR="/home/$KIOSK_USER"
echo "==> kiosk user: $KIOSK_USER  home: $HOME_DIR"
echo "==> app dir:    $APP_DIR"

# --- 1. packages -----------------------------------------------------------
echo "==> installing packages…"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y --no-install-recommends \
  epiphany-browser xdotool unclutter python3-tk \
  cups cups-client printer-driver-gutenprint

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

# --- 3. toolbar-cover helper -------------------------------------------------
# Epiphany's F11 fullscreen only strips window-manager chrome, not its own
# internal nav toolbar (back/forward/URL bar) -- there's no clean flag to
# remove that in this WebKitGTK version. Cover it with a fixed black bar.
echo "==> installing toolbar-cover helper…"
cat > "$HOME_DIR/toolbar_cover.py" <<'PYEOF'
#!/usr/bin/env python3
"""Covers the Epiphany navigation toolbar with a fixed black bar.

Epiphany 42's F11 fullscreen only strips window-manager decorations, not its
own internal nav toolbar (back/forward/URL bar) -- there's no clean way to
hide that short of the (broken, in this environment) --application-mode. This
just paints over it.
"""
import tkinter as tk

root = tk.Tk()
root.overrideredirect(True)
root.attributes("-topmost", True)
root.configure(bg="black")

width = root.winfo_screenwidth()
height = 60

root.geometry(f"{width}x{height}+0+0")
root.mainloop()
PYEOF
chown "$KIOSK_USER:$KIOSK_USER" "$HOME_DIR/toolbar_cover.py"
chmod +x "$HOME_DIR/toolbar_cover.py"

# --- 4. kiosk launcher --------------------------------------------------
echo "==> installing kiosk launcher…"
cat > "$HOME_DIR/booth-kiosk-launch.sh" <<EOF
#!/bin/bash
# Universe Booth kiosk launcher — run from GNOME autostart.
set -u

URL="http://localhost:$BOOTH_PORT/"
DISPLAY_OUTPUT="$DISPLAY_OUTPUT"
ROTATE="$ROTATE"   # left|right|inverted|normal — flip to "right" if upside down

sleep 8   # let the desktop + photobooth-kiosk service settle

export DISPLAY="\${DISPLAY:-:1}"

# This Nano's NVIDIA/Tegra driver doesn't ship a Mesa-compatible DRI blob, so
# WebKitGTK's DMA-BUF/GBM accelerated-compositing path fails every frame
# (libEGL: "failed to open nvidia-drm_dri.so" / "failed to create dri2
# screen"), which was crashing the WebProcess intermittently and causing
# Epiphany to pop open a blank "New Tab" as its crash-recovery fallback.
# This env var makes WebKitGTK skip that path entirely.
export WEBKIT_DISABLE_DMABUF_RENDERER=1

# never let the screen lock/blank over the kiosk
gsettings set org.gnome.desktop.session idle-delay 0
gsettings set org.gnome.desktop.screensaver lock-enabled false
gsettings set org.gnome.desktop.screensaver idle-activation-enabled false
gdbus call --session --dest org.gnome.ScreenSaver --object-path /org/gnome/ScreenSaver --method org.gnome.ScreenSaver.SetActive false >/dev/null 2>&1

xrandr --output "\$DISPLAY_OUTPUT" --rotate "\$ROTATE"
xset s off -dpms s noblank
pkill -f unclutter 2>/dev/null
unclutter -idle 0.5 -root &

pkill -f epiphany 2>/dev/null
pkill -f toolbar_cover.py 2>/dev/null
sleep 1

read -r SCREEN_W SCREEN_H < <(xdotool getdisplaygeometry)
PROFILE="\$HOME/.local/share/epiphany-kiosk"
mkdir -p "\$PROFILE"

setsid python3 "\$HOME/toolbar_cover.py" >/tmp/toolbar_cover.log 2>&1 < /dev/null &

# Safety net for the physical shutter (spacebar): if anything ever steals
# OS-level window focus from the kiosk (a transient dialog, etc.), a
# keypress won't reach the page's JS at all no matter how the listener is
# attached in-page. Periodically re-assert focus on the Epiphany window.
(
  while true; do
    sleep 5
    W=\$(xdotool search --onlyvisible --class "Epiphany" 2>/dev/null | tail -1)
    [ -n "\$W" ] && xdotool windowactivate "\$W" 2>/dev/null
  done
) &

while true; do
  # The kiosk always wants the same single URL -- never let Epiphany's
  # crash-recovery restore old (possibly crashed) tabs from a previous run.
  rm -f "\$PROFILE/session_state.xml" "\$PROFILE/session_state.xml~"

  epiphany --new-window --profile="\$PROFILE" "\$URL" &
  EPI_PID=\$!

  WIN=""
  for i in 1 2 3 4 5 6 7 8; do
    sleep 1
    WIN=\$(xdotool search --onlyvisible --class "Epiphany" 2>/dev/null | tail -1)
    [ -n "\$WIN" ] && break
  done

  if [ -n "\$WIN" ]; then
    xdotool windowactivate --sync "\$WIN" 2>/dev/null
    xdotool windowfocus --sync "\$WIN" 2>/dev/null
    sleep 0.5
    xdotool key F11
  fi

  wait "\$EPI_PID"
  sleep 2
done
EOF
chown "$KIOSK_USER:$KIOSK_USER" "$HOME_DIR/booth-kiosk-launch.sh"
chmod +x "$HOME_DIR/booth-kiosk-launch.sh"

# --- 5. GNOME autostart entry ------------------------------------------------
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

# --- 6. photobooth-kiosk systemd service -------------------------------------
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
      -- change it: sudo systemctl edit photobooth-kiosk (set ZOWIE_CAMERA_IP)

    Printer: once the Selphy $PRINTER_NAME is plugged in over USB, register it:
      lpadmin -p $PRINTER_NAME -E -v usb://Canon/SELPHY%20CP1300 \\
        -m gutenprint.5.3://canon-cp1300/expert
      (run 'lpinfo -v' first to confirm the exact usb:// device URI)

    Display rotation is set to "$ROTATE" -- change with ROTATE=right/normal/inverted
    and re-run this script, or edit ~$KIOSK_USER/booth-kiosk-launch.sh directly.
EOF
