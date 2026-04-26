"""
AlertX — Frame Grabber
Captures frames from live camera or uploaded video files.
Runs in its own thread and exposes frames via a thread-safe queue.
"""

import cv2
import time
import threading
import logging
from typing import Optional

from backend.config import CAMERA_SOURCE, FRAME_WIDTH, FRAME_HEIGHT, FPS_LIMIT

logger = logging.getLogger("alertx.frame_grabber")


class FrameGrabber:
    """
    Grabs frames from a video source (camera or file).
    Frames are stored in a single-slot buffer (latest-only) to avoid lag.
    """

    def __init__(self, source=None):
        raw = source if source is not None else CAMERA_SOURCE
        # Convert "0" string to integer for webcam
        self.source = int(raw) if str(raw).isdigit() else raw
        self._cap: Optional[cv2.VideoCapture] = None
        self._frame = None
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._frame_interval = 1.0 / FPS_LIMIT

    # ── Lifecycle ──────────────────────────────
    def start(self) -> bool:
        """Open source and begin grabbing in background thread."""
        actual_source = self.source
        
        # Stream Extraction for YouTube, Twitch, Kick, etc.
        if isinstance(self.source, str) and ("youtube.com" in self.source or "youtu.be" in self.source):
            try:
                import yt_dlp
                logger.info(f"Extracting YouTube stream: {self.source}")
                ydl_opts = {
                    'format': 'best[ext=mp4]/best', # Prioritize standard mp4/hls for OpenCV
                    'quiet': True,
                    'no_warnings': True,
                    'noplaylist': True,
                    'extract_flat': False,
                    'skip_download': True,
                    # Impersonate mobile browser to bypass bot detection
                    'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'extractor_args': {
                        'youtube': {
                            'player_client': ['android', 'web'],
                            'skip': ['hls', 'dash'] # Let yt-dlp pick the best available direct link
                        }
                    }
                }
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(self.source, download=False)
                    # Try to get the direct stream URL (m3u8 is usually best for live)
                    actual_source = info.get('url')
                    if not actual_source and 'formats' in info:
                        # Fallback: look for m3u8 formats manually
                        for f in info['formats']:
                            if f.get('protocol') == 'm3u8_native' or '.m3u8' in f.get('url', ''):
                                actual_source = f['url']
                                break
                    
                    if actual_source:
                        logger.info("Successfully extracted YouTube stream URL.")
                    else:
                        logger.warning("No direct stream URL found, falling back to raw source.")
                        actual_source = self.source
            except Exception as e:
                logger.error(f"YouTube extraction failed: {e}")
                actual_source = self.source

        self._cap = cv2.VideoCapture(actual_source)
        if not self._cap.isOpened():
            logger.error(f"Cannot open video source: {self.source}")
            return False

        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
        self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1) # ZERO LATENCY: No internal buffering
        self._running = True
        self._thread = threading.Thread(target=self._grab_loop, daemon=True)
        self._thread.start()
        logger.info(f"FrameGrabber started — source={self.source}")
        return True

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)
        if self._cap:
            self._cap.release()
        logger.info("FrameGrabber stopped")

    # ── Core loop ──────────────────────────────
    def _grab_loop(self):
        while self._running:
            t0 = time.time()
            ret, frame = self._cap.read()
            if not ret:
                # End of video file (for uploaded videos)
                if not isinstance(self.source, int):
                    logger.info("End of video file reached")
                    self._running = False
                    break
                continue

            # Store frame as is to avoid CPU overhead (detector will downscale)
            with self._lock:
                self._frame = frame

            # Rate-limit
            elapsed = time.time() - t0
            sleep_time = self._frame_interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    # ── Access ─────────────────────────────────
    def get_frame(self):
        """Return the latest frame (or None)."""
        with self._lock:
            return self._frame if self._frame is not None else None

    @property
    def is_running(self) -> bool:
        return self._running

    def get_fps(self) -> float:
        if self._cap and self._cap.isOpened():
            return self._cap.get(cv2.CAP_PROP_FPS) or FPS_LIMIT
        return FPS_LIMIT
