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
import threading
import time
from dataclasses import dataclass, field
from typing import Iterator, List, Optional


@dataclass
class ZowieCamera:
    ip: str
    port: int = 554
    path: str = "/main/av"          # full-res HEVC main stream — used for still captures
    stream_path: str = "/sub/av"    # lightweight H.264 640x360 stream — used for the live view
    stream_fps: int = 15

    _proc: Optional[subprocess.Popen] = field(default=None, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    _latest_frame: Optional[bytes] = field(default=None, init=False, repr=False)
    _frame_cond: threading.Condition = field(default_factory=threading.Condition, init=False, repr=False)
    _reader_started: bool = field(default=False, init=False, repr=False)

    @property
    def rtsp_url(self) -> str:
        return f"rtsp://{self.ip}:{self.port}{self.path}"

    @property
    def stream_rtsp_url(self) -> str:
        return f"rtsp://{self.ip}:{self.port}{self.stream_path}"

    def snapshot(self, out_path: str, *, full_res: bool = True, timeout: int = 12) -> bool:
        """Grab ONE JPEG frame from the full-res main stream. Returns True iff
        a non-empty file landed at out_path — never raises.

        NOTE: this opens a fresh RTSP connection every call (~1-2s of handshake
        overhead) — fine for an occasional still, too slow for a live view. Use
        mjpeg_frames() for continuous streaming (which uses the lighter
        sub-stream instead of this one).
        """
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

    # -- continuous streaming --------------------------------------------

    def _spawn_stream_proc(self) -> subprocess.Popen:
        # Deliberately uses the camera's lightweight H.264 sub-stream, not the
        # 4K HEVC main stream: the main stream's B-frame references didn't
        # survive continuous software decode on the Nano (visible as gray/
        # noisy corrupted frames — ffmpeg logged "Could not find ref with
        # POC ..." repeatedly). The sub-stream is plain H.264 baseline, which
        # tolerates the low-latency flags the HEVC stream choked on: skip
        # ffmpeg's default multi-MB probing/analyze pass (it was adding
        # noticeable startup/steady-state lag on its own) and disable input
        # jitter buffering so frames get decoded as they arrive instead of
        # being queued.
        cmd = [
            "ffmpeg", "-nostdin", "-loglevel", "error",
            "-fflags", "nobuffer", "-flags", "low_delay",
            "-probesize", "32", "-analyzeduration", "0",
            "-rtsp_transport", "tcp", "-i", self.stream_rtsp_url,
            "-an", "-r", str(self.stream_fps),
            "-q:v", "5", "-f", "mjpeg", "-",
        ]
        return subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL, bufsize=0,
        )

    def _reader_loop(self) -> None:
        """Runs in ONE background thread for the lifetime of the process.
        Drains ffmpeg's stdout, reassembles complete JPEG frames, and
        publishes each one to _latest_frame. Multiple client generators can
        safely consume the same published frame — only this thread ever
        touches the pipe, avoiding the split-frame corruption you get if two
        readers race on the same fd."""
        buf = b""
        while True:
            with self._lock:
                if self._proc is None or self._proc.poll() is not None:
                    self._proc = self._spawn_stream_proc()
            proc = self._proc
            chunk = proc.stdout.read(4096)
            if not chunk:
                with self._lock:
                    self._proc = None
                buf = b""
                time.sleep(0.5)
                continue
            buf += chunk
            while True:
                start = buf.find(b"\xff\xd8")
                if start == -1:
                    buf = b""
                    break
                end = buf.find(b"\xff\xd9", start + 2)
                if end == -1:
                    if start > 0:
                        buf = buf[start:]
                    break
                frame = buf[start:end + 2]
                buf = buf[end + 2:]
                with self._frame_cond:
                    self._latest_frame = frame
                    self._frame_cond.notify_all()

    def mjpeg_frames(self) -> Iterator[bytes]:
        """Yield the latest JPEG frame each time a new one arrives. Safe to
        call from multiple concurrent clients — each gets its own generator,
        but they all share the single background reader thread."""
        with self._lock:
            if not self._reader_started:
                self._reader_started = True
                threading.Thread(target=self._reader_loop, daemon=True).start()

        last = None
        while True:
            with self._frame_cond:
                self._frame_cond.wait_for(lambda: self._latest_frame is not last, timeout=2)
                frame = self._latest_frame
            if frame is not None and frame is not last:
                last = frame
                yield frame

    def stop_stream(self) -> None:
        with self._lock:
            if self._proc is not None:
                self._proc.kill()
                self._proc = None


if __name__ == "__main__":
    # Quick manual test: python zowie_camera.py <camera-ip> [out_dir]
    import sys

    ip = sys.argv[1] if len(sys.argv) > 1 else "10.1.10.142"
    out_dir = sys.argv[2] if len(sys.argv) > 2 else "."
    cam = ZowieCamera(ip=ip)
    print(f"grabbing one frame from {cam.rtsp_url} ...")
    ok = cam.snapshot(os.path.join(out_dir, "test.jpg"))
    print("saved test.jpg" if ok else "FAILED — check the IP, port 554, and that ffmpeg is on PATH")
