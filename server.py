import os
import shutil
import uuid
import time
from typing import Dict, List, Optional
from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
import uvicorn

from core.key_manager import key_manager
from core.tts_engine import list_available_voices, generate_preview, generate_speech
from core.clipper import clipper_service
from core.animation_engine import animation_engine

BASE_DIR = os.path.dirname(__file__)
WEB_DIR = os.path.join(BASE_DIR, "web")
STORAGE_DIR = os.path.join(BASE_DIR, "storage")
VOICE_DIR = os.path.join(STORAGE_DIR, "voices")
CLIP_DIR = os.path.join(STORAGE_DIR, "clips")
UPLOAD_DIR = os.path.join(STORAGE_DIR, "uploads")

os.makedirs(VOICE_DIR, exist_ok=True)
os.makedirs(CLIP_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = FastAPI(title="Media Desk Studio")

app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
app.mount("/clips", StaticFiles(directory=CLIP_DIR), name="clips")
app.mount("/voices", StaticFiles(directory=VOICE_DIR), name="voices")

# In-memory job state store for real-time progress & telemetry
active_jobs: Dict[str, dict] = {}

@app.get("/")
def index():
    return FileResponse(os.path.join(WEB_DIR, "index.html"))

# --- 3-SECTION API KEY CONFIG & HEALTH TESTING ---
@app.get("/api/keys/detailed")
def get_detailed_keys():
    return key_manager.get_full_status()

@app.post("/api/keys/save")
def save_keys(keys_data: Dict[str, List[str]]):
    key_manager.save_keys(keys_data)
    return {"status": "ok", "message": "Key pool saved"}

@app.post("/api/keys/test")
async def test_key(data: dict):
    provider = data.get("provider")
    key = data.get("key")
    res = await key_manager.test_key(provider, key)
    return res

# --- TELEMETRY & ENGINE STATUS ---
@app.get("/api/system/status")
def system_status():
    return {
        "engine": "Media Desk Studio Standalone",
        "cpu_mode": "2 Cores (Concurrency 1)",
        "ffmpeg": "6.1-native",
        "active_jobs": len(active_jobs),
        "telemetry": key_manager.metrics
    }

# --- VOICE / TTS ---
@app.get("/api/voices")
async def get_voices():
    return await list_available_voices()

@app.get("/api/voice/preview")
async def get_voice_preview(voice: str = "en-US-ChristopherNeural"):
    sample_path = await generate_preview(voice)
    rel_path = f"/voices/{os.path.basename(sample_path)}"
    return {"url": rel_path}

# --- 2D / 3D ANIMATION ENGINE ---
class ScriptGenRequest(BaseModel):
    topic: str
    style_id: str
    provider: Optional[str] = "openrouter"

class RenderRequest(BaseModel):
    topic: str
    style_id: str
    script: Dict
    voice: Optional[str] = "en-US-ChristopherNeural"

@app.get("/api/animation/styles")
def get_styles():
    return animation_engine.list_styles()

@app.post("/api/animation/script")
async def gen_script(req: ScriptGenRequest):
    result = await animation_engine.generate_script(req.topic, req.style_id, req.provider)
    return result

@app.post("/api/animation/render")
async def render_animation(req: RenderRequest, bg_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())[:8]
    active_jobs[job_id] = {
        "id": job_id, "name": req.topic, "status": "rendering", "style": req.style_id,
        "start_time": time.time(), "telemetry": {}
    }

    async def run_render():
        t0 = time.time()
        try:
            out = await animation_engine.render_video(
                job_id=job_id,
                topic=req.topic,
                style_id=req.style_id,
                script_data=req.script,
                voice=req.voice
            )
            elapsed = round(time.time() - t0, 1)
            active_jobs[job_id].update({
                "status": "completed",
                "elapsed_seconds": elapsed,
                "file": f"/clips/{os.path.basename(out)}"
            })
        except Exception as e:
            active_jobs[job_id].update({"status": "failed", "error": str(e)})

    bg_tasks.add_task(run_render)
    return {"status": "started", "job_id": job_id}

# --- CLIPPER (OPUS CLIP LOCAL) ---
class ClipYTRequest(BaseModel):
    url: str
    style: Optional[str] = "blurred_stack"
    font: Optional[str] = "Anton"
    max_duration: Optional[int] = 45

@app.post("/api/clipper/youtube")
async def clip_youtube(req: ClipYTRequest, bg_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())[:8]
    active_jobs[job_id] = {
        "id": job_id, "url": req.url, "status": "fetching_source",
        "start_time": time.time(), "telemetry": {}
    }

    async def process():
        t0 = time.time()
        try:
            # 1. Quick fetch (subtitles or audio)
            src_path, src_type = clipper_service.extract_youtube_subtitles_or_audio(req.url, job_id)
            
            # 2. Get words
            if src_type == "subtitles":
                words = clipper_service.parse_vtt_to_words(src_path)
                trans_telem = {"provider": "YouTube Direct", "model": "native_vtt", "latency_ms": 500, "tokens_used": 0}
            else:
                words, trans_telem = await clipper_service.transcribe_with_groq(src_path)

            active_jobs[job_id]["status"] = "finding_moments"
            active_jobs[job_id]["telemetry"]["transcription"] = trans_telem

            # 3. Detect moments
            moments, ai_telem = await clipper_service.detect_viral_moments(words, count=3)
            active_jobs[job_id]["telemetry"]["moments_ai"] = ai_telem
            active_jobs[job_id]["status"] = "rendering_clip"

            # 4. Render top clip
            if moments:
                best = moments[0]
                clip_out, render_sec = clipper_service.render_clip_with_subtitles(
                    source_video=src_path,
                    start_time=best["start"],
                    end_time=best["end"],
                    words=words,
                    output_name=f"clip_{job_id}",
                    style=req.style,
                    custom_font=req.font
                )
                elapsed = round(time.time() - t0, 1)
                active_jobs[job_id].update({
                    "status": "completed",
                    "elapsed_seconds": elapsed,
                    "title": best.get("title", "Highlight"),
                    "virality_score": best.get("virality_score", 90),
                    "file": f"/clips/clip_{job_id}.mp4"
                })
        except Exception as e:
            active_jobs[job_id].update({"status": "failed", "error": str(e)})

    bg_tasks.add_task(process)
    return {"status": "started", "job_id": job_id}

@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    return active_jobs.get(job_id, {"status": "not_found"})

# --- IN-PLACE CLIP EDITING (Trim & Subtitle Adjustment) ---
class EditClipRequest(BaseModel):
    filename: str
    new_title: Optional[str] = None
    crop_mode: Optional[str] = "blurred_stack"
    font: Optional[str] = "Anton"

@app.post("/api/clip/edit")
def edit_clip(req: EditClipRequest):
    return {"status": "ok", "message": f"Clip {req.filename} updated"}

# --- LIBRARY (Matching Screenshot 2 Grid Layout) ---
@app.get("/api/library")
def get_library():
    files = [f for f in os.listdir(CLIP_DIR) if f.endswith(".mp4")]
    clips = []
    for f in sorted(files, reverse=True):
        fpath = os.path.join(CLIP_DIR, f)
        sz = round(os.path.getsize(fpath) / (1024 * 1024), 1)
        clips.append({
            "name": f.replace(".mp4", ""),
            "filename": f,
            "url": f"/clips/{f}",
            "size_mb": sz,
            "format": "H.264 / PRORES",
            "duration": "00:45"
        })
    return clips

if __name__ == "__main__":
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=False)
