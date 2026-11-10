# ContentForge AI

ContentForge AI takes a link to a long video and turns it into clips for each topic, merged from parts scattered across the video. It also writes posts, SEO titles, descriptions, keywords and hashtags, and blog articles, then publishes them to social networks and blogs.

**No paid API.** The AI runs on your own computer through [Ollama](https://ollama.com), and transcription runs locally with Whisper. Publishing goes through the platforms' own free APIs (WordPress, YouTube, Telegram, Facebook/Instagram).

The viral-moment detection and face-tracking crop are adapted from
[AI-Youtube-Shorts-Generator](https://github.com/Anil-matcha/AI-Youtube-Shorts-Generator) (MIT), with its paid services removed. Details are in [NOTICE.md](NOTICE.md).

## What it can do

| Capability | Command |
|---|---|
| Import a video from a link (YouTube, Vimeo, Facebook, TikTok and about 1,000 other sites) or a local file | `clips` |
| Find every part that covers a topic, from anywhere in the video, and **merge them into one clip** | `clips -t "topic"` |
| No topics given: find the strongest moments automatically | `clips` |
| Landscape version + vertical 9:16 version (face tracking / blurred background / centre crop) with burned-in subtitles and a thumbnail | `clips` |
| SEO title, alternative titles, meta description, slug, focus keyword, keywords, hashtags, tags | `clips` / `article` |
| A post tailored to each network within its length limit (TikTok, Instagram, Facebook, X, LinkedIn, Telegram, Shorts) | `clips --platforms` |
| SEO blog article with FAQ and JSON-LD (Article/FAQ) | `article` / `clips --article` |
| Short-video script and a text-on-screen video | `script` |
| Publishing: WordPress, Markdown for a static blog (Hugo/Jekyll/GitHub Pages), Telegram, YouTube, Facebook, Instagram Reels, webhook to n8n | `publish` |

## Installation

```bash
# 1. FFmpeg
sudo apt install ffmpeg          # macOS: brew install ffmpeg

# 2. Local AI model (free)
#    Install Ollama from https://ollama.com, then:
ollama pull gemma3:12b           # good multilingual quality, Hebrew included; lighter: qwen3:8b

# 3. The project
pip install -e '.[all,dev]'
cp .env.example .env             # edit as needed
contentforge doctor              # check that everything is installed
```

Hardware: `gemma3:12b` needs about 10GB of memory (a GPU helps but is not required). On a weaker machine, use `OLLAMA_MODEL=qwen3:8b` or `gemma3:4b` and `WHISPER_MODEL=base`.

## Usage

```bash
# Clips by topic: every part about each topic, merged into one clip of up to 90 seconds
contentforge clips "https://www.youtube.com/watch?v=..." -t "Search engine optimization" -t "Instagram marketing" --article

# Best moments automatically, 5 clips
contentforge clips video.mp4 --num-clips 5

# Article from a video or from a text file
contentforge article notes.md --topic "How to build a website" --words 1500

# Video script + text-on-screen video (Hebrew needs a font with Hebrew glyphs)
contentforge script "3 tips for a short video" --font /usr/share/fonts/truetype/dejavu/DejaVuSans.ttf

# Publish what was created (drafts / private)
contentforge publish output/manifest.json --to markdown,wordpress,telegram
```

All results land in `output/`. `manifest.json` holds every clip with its SEO package and posts, and you can edit it before publishing.

## Safe publishing

- WordPress posts are created as **drafts**, YouTube uploads as **private**, and Facebook video posts as **unpublished**. You approve them yourself.
- Instagram downloads the video from a public link, so the video is first uploaded to WordPress and its address is passed on.
- TikTok, X and LinkedIn have no simple free API for publishing video. Send them to a webhook (for example a self-hosted n8n instance, which is free) or upload them manually.
- Only download and reuse videos you own or have the rights to use.

## Structure

```
src/contentforge/
  ingest.py        download (yt-dlp)
  transcribe.py    subtitles / local Whisper, SRT
  topics.py        topic search across chunks + part merging
  highlights.py    automatic strong moments (adapted from upstream)
  video.py         FFmpeg: cut + join, vertical, subtitles, thumbnail, text video
  reframe.py       face tracking (OpenCV, adapted from upstream)
  content.py       SEO, posts, article, script (local model)
  seo.py           slug, hashtags, length limits, JSON-LD, keyword report
  llm.py           Ollama client with JSON schema
  pipeline.py      end-to-end pipeline + publishing
  publishers/      wordpress, telegram, meta, youtube, webhook, markdown
```

## Tests

```bash
pytest
```

The tests run without Ollama (a fake model stands in for it). They run FFmpeg for real on a generated video.
