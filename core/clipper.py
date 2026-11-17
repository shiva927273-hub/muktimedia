import asyncio
import json
import os
import subprocess
import time
from typing import List, Dict, Optional, Tuple
import pysubs2
from core.key_manager import key_manager

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
STORAGE_DIR = os.path.join(BASE_DIR, "storage")
UPLOAD_DIR = os.path.join(STORAGE_DIR, "uploads")
CLIP_DIR = os.path.join(STORAGE_DIR, "clips")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(CLIP_DIR, exist_ok=True)

class ClipperService:
    @staticmethod
    def extract_youtube_subtitles_or_audio(url: str, output_id: str) -> Tuple[Optional[str], str]:
        """
        Speed optimization:
        1. Checks if video has YouTube subtitles (auto or manual) -> grabs VTT directly in 1 second.
        2. If no subtitles exist, downloads audio stream as fallback.
        """
        # Try fetching subtitle first
        sub_tmpl = os.path.join(UPLOAD_DIR, f"{output_id}")
        cmd_sub = [
            "yt-dlp",
            "--skip-download",
            "--write-auto-subs",
            "--write-subs",
            "--sub-lang", "en.*,en,hi",
            "--sub-format", "vtt",
            "-o", sub_tmpl,
            url
        ]
        try:
            subprocess.run(cmd_sub, check=True, capture_output=True, timeout=12)
            # Find generated vtt file
            for f in os.listdir(UPLOAD_DIR):
                if f.startswith(output_id) and f.endswith(".vtt"):
                    return os.path.join(UPLOAD_DIR, f), "subtitles"
        except Exception:
            pass

        # Fallback to downloading audio stream
        out_tmpl = os.path.join(UPLOAD_DIR, f"{output_id}.%(ext)s")
        cmd_audio = [
            "yt-dlp",
            "-f", "ba/b",
            "-x",
            "--audio-format", "mp3",
            "-o", out_tmpl,
            url
        ]
        subprocess.run(cmd_audio, check=True, capture_output=True)
        return os.path.join(UPLOAD_DIR, f"{output_id}.mp3"), "audio"

    @staticmethod
    def parse_vtt_to_words(vtt_path: str) -> List[Dict]:
        """Parses YouTube .vtt into timestamped word/sentence segments instantly."""
        words = []
        try:
            subs = pysubs2.load(vtt_path)
            for event in subs:
                start_s = event.start / 1000.0
                end_s = event.end / 1000.0
                text = event.text.replace("\n", " ").strip()
                if text:
                    words.append({"word": text, "start": start_s, "end": end_s})
        except Exception as e:
            print(f"[Clipper] VTT parse error: {e}")
        return words

    @staticmethod
    async def transcribe_with_groq(audio_path: str) -> Tuple[List[Dict], dict]:
        """Transcribes with Groq Whisper and tracks model tokens and latency."""
        from groq import Groq
        t0 = time.time()
        for _ in range(4):
            key = key_manager.get_key("groq")
            if not key:
                break
            try:
                client = Groq(api_key=key)
                with open(audio_path, "rb") as file:
                    transcription = client.audio.transcriptions.create(
                        file=(os.path.basename(audio_path), file.read()),
                        model="whisper-large-v3-turbo",
                        response_format="verbose_json",
                        timestamp_granularities=["word"]
                    )
                latency_ms = int((time.time() - t0) * 1000)
                words = []
                raw_words = getattr(transcription, "words", []) or []
                for w in raw_words:
                    words.append({
                        "word": getattr(w, "word", "") or w.get("word", ""),
                        "start": getattr(w, "start", 0.0) or w.get("start", 0.0),
                        "end": getattr(w, "end", 0.0) or w.get("end", 0.0)
                    })
                tokens_est = len(words)
                key_manager.record_usage("groq", tokens_est, latency_ms)
                telemetry = {
                    "provider": "Groq LPU",
                    "model": "whisper-large-v3-turbo",
                    "latency_ms": latency_ms,
                    "tokens_used": tokens_est
                }
                return words, telemetry
            except Exception as e:
                print(f"[Clipper] Groq error: {e}. Rotating...")
                key_manager.mark_failed_and_rotate("groq")

        # Fallback to local
        telemetry = {"provider": "Local CPU", "model": "faster-whisper-base", "latency_ms": 5000, "tokens_used": 0}
        from faster_whisper import WhisperModel
        model = WhisperModel("base", device="cpu", compute_type="int8")
        segments, _ = model.transcribe(audio_path, word_timestamps=True)
        words = []
        for s in segments:
            for w in s.words:
                words.append({"word": w.word, "start": w.start, "end": w.end})
        return words, telemetry

    @staticmethod
    async def detect_viral_moments(words: List[Dict], count: int = 5) -> Tuple[List[Dict], dict]:
        """Detects top viral moments using Gemini 2.5 Flash and returns latency and token telemetry."""
        full_text = " ".join([w["word"] for w in words])
        prompt = f"""You are an elite video editor for TikTok, YouTube Shorts, and Reels.
Find the top {count} most engaging moments (20 to 60s long).
Return ONLY JSON:
[
  {{
    "title": "Viral Hook Title",
    "start": 12.0,
    "end": 45.0,
    "hook": "Opening hook sentence",
    "virality_score": 94,
    "category": "Story / Q&A / Shock"
  }}
]

Transcript:
{full_text[:12000]}
"""
        from google import genai
        t0 = time.time()
        for _ in range(4):
            key = key_manager.get_key("gemini")
            if not key:
                break
            try:
                client = genai.Client(api_key=key)
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt
                )
                latency_ms = int((time.time() - t0) * 1000)
                text = response.text.strip()
                if "```json" in text:
                    text = text.split("```json")[1].split("```")[0].strip()
                elif "```" in text:
                    text = text.split("```")[1].split("```")[0].strip()
                moments = json.loads(text)
                tokens_est = len(full_text.split()) + 200
                key_manager.record_usage("gemini", tokens_est, latency_ms)
                telemetry = {
                    "provider": "Google GenAI",
                    "model": "gemini-2.5-flash",
                    "latency_ms": latency_ms,
                    "tokens_used": tokens_est
                }
                return moments, telemetry
            except Exception as e:
                print(f"[Clipper] Gemini error: {e}. Rotating...")
                key_manager.mark_failed_and_rotate("gemini")

        # Default fallback
        telemetry = {"provider": "Built-in Rule", "model": "heuristic", "latency_ms": 10, "tokens_used": 0}
        max_duration = words[-1]["end"] if words else 60.0
        return [{
            "title": "Viral Highlight #1",
            "start": 0.0,
            "end": min(45.0, max_duration),
            "hook": "Key moment detected",
            "virality_score": 88,
            "category": "Highlight"
        }], telemetry

    @staticmethod
    def render_clip_with_subtitles(
        source_video: str,
        start_time: float,
        end_time: float,
        words: List[Dict],
        output_name: str,
        style: str = "blurred_stack",
        custom_font: str = "Anton",
        custom_color: str = "&H00FFFF", # Yellow in ASS BGR format
        outline_width: float = 3.0
    ) -> Tuple[str, float]:
        """Fast FFmpeg render with precise cuts and in-place ASS subtitle overlay."""
        t0 = time.time()
        clip_out = os.path.join(CLIP_DIR, f"{output_name}.mp4")
        ass_path = os.path.join(CLIP_DIR, f"{output_name}.ass")

        clip_words = [w for w in words if w["start"] >= start_time and w["end"] <= end_time]

        # Generate ASS subtitle
        subs = pysubs2.SSAFile()
        subs.info["PlayResX"] = 1080
        subs.info["PlayResY"] = 1920

        new_style = pysubs2.SSAStyle()
        new_style.fontname = custom_font
        new_style.fontsize = 110
        new_style.primarycolor = pysubs2.Color(255, 255, 0)
        new_style.outline = outline_width
        new_style.outlinecolor = pysubs2.Color(0, 0, 0)
        new_style.shadow = 2.0
        new_style.alignment = 2
        new_style.marginv = 340
        subs.styles["TikTok"] = new_style

        burst_size = 3
        for i in range(0, len(clip_words), burst_size):
            chunk = clip_words[i:i + burst_size]
            t_start = max(0.0, chunk[0]["start"] - start_time)
            t_end = max(t_start + 0.3, chunk[-1]["end"] - start_time)
            text = " ".join([w["word"].strip().upper() for w in chunk])
            line = pysubs2.SSAEvent(
                start=pysubs2.make_time(s=t_start),
                end=pysubs2.make_time(s=t_end),
                text=text,
                style="TikTok"
            )
            subs.events.append(line)

        subs.save(ass_path)
        safe_ass = ass_path.replace("\\", "/").replace(":", "\\:")

        duration = end_time - start_time
        # Optimized FFmpeg with fast boxblur (10:2 instead of 20:5)
        vf_filter = (
            f"[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=10:2[bg];"
            f"[0:v]scale=1080:-1[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2[base];"
            f"[base]ass='{safe_ass}'[v]"
        )

        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start_time),
            "-i", source_video,
            "-t", str(duration),
            "-filter_complex", vf_filter,
            "-map", "[v]",
            "-map", "0:a?",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-tune", "fastdecode",
            "-crf", "23",
            "-c:a", "aac",
            clip_out
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        render_duration = round(time.time() - t0, 1)
        return clip_out, render_duration

clipper_service = ClipperService()
