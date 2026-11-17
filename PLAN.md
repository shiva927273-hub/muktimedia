# MEDIA DESK STUDIO: PLAN & SPEC (GSD + Ralph Loop + Ponytail)

## Objectives
- Build a personal, free, local OpusClip + 2D/3D video generator web application running at `http://localhost:8000`.
- 100% Free: Edge-TTS, Kokoro, Groq, Gemini, OpenRouter, NVIDIA NIM, Hugging Face.
- Multi-Account pool (up to 4 accounts per provider) with auto-failover/rotation.
- Strictly single-thread / concurrency=1 CPU-friendly pipeline for 2-core PC.
- No cloud dependencies: Modal, Stripe, S3, PostgreSQL removed.

## Architecture
- **Backend:** FastAPI + Uvicorn (lightweight async Python).
- **Frontend:** Single-page responsive HTML/Tailwind/JS dark dashboard (matching screenshots).
- **Core Modules:**
  1. `core/key_manager.py`: Pool rotator for Gemini, Groq, OpenRouter, NVIDIA, HF (4 accounts each).
  2. `core/clipper.py`: yt-dlp audio download, Groq/Whisper transcription, Gemini moment detection, FFmpeg 9:16 vertical crop + ASS stylish subtitles.
  3. `core/tts_engine.py`: Edge-TTS + Kokoro + VoiceStudio/Fish Audio with voice preview audio generator.
  4. `core/animation_engine.py`: Integration with `faceless-shorts` & `ai-video-editor` headless Chromium canvas renderers.
  5. `server.py`: FastAPI server serving static dashboard and REST API.

## Atomic Task List (Ralph Loop)
- [ ] Task 1: Create `config/keys.json` template & `core/key_manager.py` (Multi-account rotation).
- [ ] Task 2: Create `core/tts_engine.py` (Edge-TTS + preview sample generation).
- [ ] Task 3: Create `core/clipper.py` (yt-dlp + Groq/Whisper + Gemini moment detection + FFmpeg 9:16).
- [ ] Task 4: Create `core/animation_engine.py` (faceless shorts bridge).
- [ ] Task 5: Build Web UI dashboard (`web/index.html` matching 4 screenshots with tabs).
- [ ] Task 6: Build `server.py` and test end-to-end.

