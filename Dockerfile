FROM python:3.12-slim

# FFmpeg for video work, DejaVu fonts for Hebrew subtitles, libglib for OpenCV.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core libglib2.0-0 ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# yt-dlp needs a JavaScript runtime for YouTube.
COPY --from=denoland/deno:bin-2.9.6 /deno /usr/local/bin/deno

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir ".[web,transcribe,facetrack,youtube]"

ENV CONTENTFORGE_DATA=/data \
    HF_HOME=/data/cache/huggingface \
    SUBTITLE_FONT="DejaVu Sans" \
    PYTHONUNBUFFERED=1
VOLUME /data
WORKDIR /data
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/healthz')"
CMD ["uvicorn", "contentforge.web:app", "--host", "0.0.0.0", "--port", "8000", "--timeout-keep-alive", "75"]
