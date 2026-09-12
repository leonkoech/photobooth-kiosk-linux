"""Minimal Zowietek RTSP camera client for the Universe Booth.

Ported from gopro-automation-linux (agx_pipeline/preview.py::_rtsp_snapshot) —
that's the ~10-line core of grabbing a JPEG frame over RTSP via ffmpeg. This
module keeps just that, with none of the AGX baggage (no S3, no Firestore, no
6-camera fleet config, no boto3 dependency). One ZowieCamera = one unit.

Requires: ffmpeg on PATH. Nothing else.
"""

from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass
from typing import List


@dataclass
class ZowieCamera:
    ip: str
    port: int = 554
    path: str = "/main/av"          # Zowietek's default RTSP main-stream path

    @property
    def rtsp_url(self) -> str:
        return f"rtsp://{self.ip}:{self.port}{self.path}"

    def snapshot(self, out_path: str, *, full_res: bool = True, timeout: int = 12) -> bool:
        """Grab ONE JPEG frame. full_res=False scales to 640px wide (fast preview,
        matches the AGX dashboard's use of this same call). Returns True iff a
        non-empty file landed at out_path — never raises."""
        vf = [] if full_res else ["-vf", "scale=640:-2"]
        cmd = [
            "ffmpeg", "-nostdin", "-y", "-rtsp_transport", "tcp",
            "-i", self.rtsp_url,
            "-frames:v", "1", *vf, "-q:v", "2",
            out_path,
        ]
        try:
            subprocess.run(cmd, capture_output=True, timeout=timeout, stdin=subprocess.DEVNULL)
        except Exception as e:  # noqa: BLE001 — best-effort, caller decides what to do
            print(f"[zowie_camera] snapshot failed for {self.ip}: {e}")
            return False
        return os.path.exists(out_path) and os.path.getsize(out_path) > 0

    def burst(self, out_dir: str, count: int = 5, interval: float = 0.8,
              prefix: str = "shot") -> List[str]:
        """Take `count` full-res frames `interval` seconds apart (the photo-booth
        shape: a few seconds of shots after a countdown). Best-effort — skips a
        frame that fails rather than aborting the whole burst. Returns the saved
        file paths, in order.

        NOTE: no PTZ control exists yet for this unit (there's none in the
        source repo either) — this assumes a fixed frame. Pan/tilt/zoom is new
        work if the booth camera needs to be aimed remotely.
        """
        os.makedirs(out_dir, exist_ok=True)
        paths: List[str] = []
        for i in range(count):
            out = os.path.join(out_dir, f"{prefix}_{i + 1}.jpg")
            if self.snapshot(out):
                paths.append(out)
            if i < count - 1:
                time.sleep(interval)
        return paths


if __name__ == "__main__":
    # Quick manual test: python zowie_camera.py <camera-ip> [out_dir]
    import sys

    ip = sys.argv[1] if len(sys.argv) > 1 else "10.1.10.142"
    out_dir = sys.argv[2] if len(sys.argv) > 2 else "."
    cam = ZowieCamera(ip=ip)
    print(f"grabbing one frame from {cam.rtsp_url} ...")
    ok = cam.snapshot(os.path.join(out_dir, "test.jpg"))
    print("saved test.jpg" if ok else "FAILED — check the IP, port 554, and that ffmpeg is on PATH")
