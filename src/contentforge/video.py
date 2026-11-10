"""FFmpeg helpers: cut and join parts, vertical 9:16 versions, burned-in subtitles, thumbnails,
and simple text-on-screen videos made from a script.

Each ``*_cmd`` function only builds the argument list, so it can be tested without FFmpeg.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

VIDEO_CODEC = ["-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p"]
AUDIO_CODEC = ["-c:a", "aac", "-b:a", "160k"]


class FFmpegError(RuntimeError):
    pass


def _run(cmd: list[str]) -> None:
    if shutil.which(cmd[0]) is None:
        raise FFmpegError(f"{cmd[0]} is not installed or not on PATH")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise FFmpegError(f"{' '.join(cmd[:3])}... failed:\n{proc.stderr[-2000:]}")


def probe_duration(path: Path) -> float:
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(json.loads(proc.stdout)["format"]["duration"])


def _escape_filter_path(path: Path) -> str:
    # Inside a filter graph, ':' '\' and "'" need escaping.
    return str(path).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")


# --- cut and join --------------------------------------------------------------

def cut_and_join_cmd(src: Path, parts: list[tuple[float, float]], out: Path, has_audio: bool = True) -> list[str]:
    """One FFmpeg pass: trim each part (frame-accurate) and concatenate them in order."""
    if not parts:
        raise ValueError("no parts to cut")
    chains, labels = [], []
    for i, (start, end) in enumerate(parts):
        chains.append(f"[0:v]trim=start={start:.3f}:end={end:.3f},setpts=PTS-STARTPTS[v{i}]")
        labels.append(f"[v{i}]")
        if has_audio:
            chains.append(f"[0:a]atrim=start={start:.3f}:end={end:.3f},asetpts=PTS-STARTPTS[a{i}]")
            labels.append(f"[a{i}]")
    concat = f"{''.join(labels)}concat=n={len(parts)}:v=1:a={1 if has_audio else 0}[v]" + ("[a]" if has_audio else "")
    cmd = ["ffmpeg", "-y", "-i", str(src), "-filter_complex", ";".join(chains + [concat]), "-map", "[v]"]
    if has_audio:
        cmd += ["-map", "[a]", *AUDIO_CODEC]
    return cmd + [*VIDEO_CODEC, "-movflags", "+faststart", str(out)]


def has_audio_stream(path: Path) -> bool:
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    )
    return bool(proc.stdout.strip())


def cut_and_join(src: Path, parts: list[tuple[float, float]], out: Path) -> Path:
    _run(cut_and_join_cmd(src, parts, out, has_audio=has_audio_stream(src)))
    return out


# --- vertical version with subtitles -------------------------------------------

SUBTITLE_STYLE = "FontName=Arial,FontSize=13,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=0,Alignment=2,MarginV=70"


def vertical_cmd(src: Path, out: Path, subtitles: Path | None = None, mode: str = "blur",
                 width: int = 1080, height: int = 1920) -> list[str]:
    """9:16 for Reels / Shorts / TikTok.

    mode="crop": fill the frame by cropping the centre.
    mode="blur": keep the whole frame, on a blurred, zoomed copy of itself.
    """
    if mode == "crop":
        graph = f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},setsar=1[base]"
    elif mode == "blur":
        graph = (
            f"[0:v]split[bg][fg];"
            f"[bg]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},boxblur=20:2[bgb];"
            f"[fg]scale={width}:{height}:force_original_aspect_ratio=decrease[fgs];"
            f"[bgb][fgs]overlay=(W-w)/2:(H-h)/2,setsar=1[base]"
        )
    else:
        raise ValueError(f"unknown mode {mode!r}")
    last = "base"
    if subtitles:
        graph += f";[base]subtitles='{_escape_filter_path(subtitles)}':force_style='{SUBTITLE_STYLE}'[out]"
        last = "out"
    return ["ffmpeg", "-y", "-i", str(src), "-filter_complex", graph, "-map", f"[{last}]", "-map", "0:a?",
            *VIDEO_CODEC, *AUDIO_CODEC, "-movflags", "+faststart", str(out)]


def make_vertical(src: Path, out: Path, subtitles: Path | None = None, mode: str = "blur") -> Path:
    _run(vertical_cmd(src, out, subtitles, mode))
    return out


def burn_subtitles_cmd(src: Path, subtitles: Path, out: Path) -> list[str]:
    graph = f"subtitles='{_escape_filter_path(subtitles)}':force_style='{SUBTITLE_STYLE}'"
    return ["ffmpeg", "-y", "-i", str(src), "-vf", graph, "-map", "0:v", "-map", "0:a?",
            *VIDEO_CODEC, *AUDIO_CODEC, "-movflags", "+faststart", str(out)]


def burn_subtitles(src: Path, subtitles: Path, out: Path) -> Path:
    _run(burn_subtitles_cmd(src, subtitles, out))
    return out


def thumbnail(src: Path, out: Path, at: float = 1.0) -> Path:
    _run(["ffmpeg", "-y", "-ss", f"{at:.2f}", "-i", str(src), "-frames:v", "1", "-q:v", "2", str(out)])
    return out


# --- text-on-screen video from a script ----------------------------------------

def text_scene_cmd(text_file: Path, out: Path, duration: float, font: Path | None = None,
                   background: str = "0x101828", width: int = 1080, height: int = 1920) -> list[str]:
    font_opt = f"fontfile='{_escape_filter_path(font)}':" if font else ""
    draw = (
        f"drawtext={font_opt}textfile='{_escape_filter_path(text_file)}':fontcolor=white:fontsize=72:"
        f"line_spacing=20:x=(w-text_w)/2:y=(h-text_h)/2:"
        f"alpha='if(lt(t,0.4),t/0.4,1)'"
    )
    return ["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c={background}:s={width}x{height}:d={duration:.2f}:r=30",
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", f"{duration:.2f}",
            "-vf", draw, *VIDEO_CODEC, *AUDIO_CODEC, "-shortest", str(out)]


def render_text_video(scenes: list[tuple[str, float]], out: Path, workdir: Path, font: Path | None = None) -> Path:
    """Render one card per scene and join them. Add a voice-over track afterwards if needed.

    Hebrew/Arabic need an FFmpeg build with libharfbuzz + libfribidi and a font that has the glyphs.
    """
    workdir.mkdir(parents=True, exist_ok=True)
    files = []
    for i, (text, duration) in enumerate(scenes):
        txt = workdir / f"scene_{i}.txt"
        txt.write_text(text, encoding="utf-8")
        clip = workdir / f"scene_{i}.mp4"
        _run(text_scene_cmd(txt, clip, duration, font))
        files.append(clip)
    listing = workdir / "scenes.txt"
    listing.write_text("".join(f"file '{f.resolve()}'\n" for f in files), encoding="utf-8")
    _run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", str(out)])
    return out
