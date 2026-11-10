"""Face-tracking vertical crop with OpenCV (optional: pip install 'contentforge-ai[facetrack]').

Adapted from Anil-matcha/AI-Youtube-Shorts-Generator (MIT, see NOTICE.md). A crop window at the
target aspect ratio follows the largest face with smoothing, then the audio is muxed back.
Without OpenCV, use ``video.make_vertical`` (centre crop or blurred background) instead.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def available() -> bool:
    try:
        import cv2  # noqa: F401
        return True
    except ImportError:
        return False


def crop_size(src_w: int, src_h: int, ratio: float) -> tuple[int, int]:
    """Largest even-sized crop with the target ratio that fits inside the frame."""
    if ratio < src_w / src_h:
        h, w = src_h, int(src_h * ratio)
    else:
        w, h = src_w, int(src_w / ratio)
    return max(2, w - w % 2), max(2, h - h % 2)


def face_track_vertical(src: Path, out: Path, aspect_ratio: str = "9:16", smoothing: float = 0.15) -> Path:
    import cv2

    w_r, h_r = (float(x) for x in aspect_ratio.split(":"))
    cap = cv2.VideoCapture(str(src))
    if not cap.isOpened():
        raise RuntimeError(f"could not open {src}")
    src_w, src_h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    crop_w, crop_h = crop_size(src_w, src_h, w_r / h_r)

    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    silent = out.with_suffix(".silent.mp4")
    writer = cv2.VideoWriter(str(silent), cv2.VideoWriter_fourcc(*"mp4v"), fps, (crop_w, crop_h))

    center: tuple[int, int] | None = None
    frame_no = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if frame_no % 3 == 0:  # detecting every 3rd frame is plenty and much faster
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(40, 40))
            if len(faces):
                x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
                cx, cy = x + w // 2, y + h // 2
                center = (cx, cy) if center is None else (
                    int(center[0] + (cx - center[0]) * smoothing),
                    int(center[1] + (cy - center[1]) * smoothing),
                )
        frame_no += 1
        cx, cy = center or (src_w // 2, src_h // 2)
        x0 = max(0, min(src_w - crop_w, cx - crop_w // 2))
        y0 = max(0, min(src_h - crop_h, cy - crop_h // 2))
        writer.write(frame[y0:y0 + crop_h, x0:x0 + crop_w])
    cap.release()
    writer.release()

    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(silent), "-i", str(src),
         "-map", "0:v:0", "-map", "1:a:0?", "-c:v", "libx264", "-crf", "20", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "160k", "-shortest", str(out)],
        check=True,
    )
    os.remove(silent)
    return out
