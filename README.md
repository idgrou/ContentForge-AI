# ContentForge AI

Work in progress: a Python pipeline that imports long videos from a link, finds the parts that
cover chosen topics, cuts and merges them into clips (16:9 and 9:16 with subtitles), and
generates SEO titles, descriptions, keywords and hashtags for social posts and blog articles.

## Done so far
- `ingest.py` – download video and subtitles with yt-dlp
- `transcribe.py` – parse VTT/SRT, optional local Whisper, SRT writing and remapping for clips
- `topics.py` – Claude picks parts of the video per topic; parts are cleaned and merged
- `video.py` – FFmpeg cut-and-join, vertical version, burned subtitles, thumbnails, text videos
- `models.py`, `llm.py`, `config.py` – data models, Claude structured-output wrapper, settings

## Still to do
- Post / article / SEO generation module
- Publishers (WordPress, YouTube, Telegram, Facebook/Instagram, webhook)
- CLI and tests

## Setup
```bash
pip install -e '.[dev]'
cp .env.example .env
```
Requires FFmpeg on PATH.
