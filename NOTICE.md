# Third-party code

Parts of this project are adapted from
[Anil-matcha/AI-Youtube-Shorts-Generator](https://github.com/Anil-matcha/AI-Youtube-Shorts-Generator)
(commit `54e710ac9916675312c2afcb3760ff68e8756293`), MIT License,
Copyright (c) 2026 Anil Chandra Naidu Matcha. The full licence text is in
`LICENSES/AI-Youtube-Shorts-Generator-MIT.txt`.

Adapted files:
- `src/contentforge/highlights.py` — virality prompt, content-type detection, chunking of long
  transcripts, score-based dedupe. The paid MuAPI / OpenAI / Gemini backends were removed; the
  LLM call now goes to a local model.
- `src/contentforge/reframe.py` — OpenCV face-tracking vertical crop.
- `src/contentforge/transcribe.py` — Whisper device selection and the SRT transcript cache.
