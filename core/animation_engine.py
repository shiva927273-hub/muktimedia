import asyncio
import json
import os
import shutil
import subprocess
import time
from typing import Dict, List, Optional
from core.key_manager import key_manager
from core.tts_engine import generate_speech

SKILLS_DIR = r"C:\Users\This-pc\.gemini\config\skills"
FACELESS_DIR = os.path.join(SKILLS_DIR, "faceless-shorts")
AI_EDITOR_DIR = os.path.join(SKILLS_DIR, "ai-video-editor")

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
STORAGE_DIR = os.path.join(BASE_DIR, "storage")
TEMP_DIR = os.path.join(STORAGE_DIR, "temp")
CLIP_DIR = os.path.join(STORAGE_DIR, "clips")

os.makedirs(TEMP_DIR, exist_ok=True)
os.makedirs(CLIP_DIR, exist_ok=True)

STYLES = [
    # Faceless Shorts styles
    {"id": "inside-out", "name": "Inside Out (2D X-Ray Explainer)", "engine": "faceless", "type": "2D", "render_time": "~45s"},
    {"id": "stick-story", "name": "Stick Story (Survival & Life Hacks)", "engine": "faceless", "type": "2D", "render_time": "~40s"},
    {"id": "paper-atlas", "name": "Paper Atlas (History & Maps)", "engine": "faceless", "type": "2D", "render_time": "~50s"},
    {"id": "deep-dive", "name": "Deep Dive 3D (Zack D. Films Science)", "engine": "faceless", "type": "3D", "render_time": "~2m"},
    {"id": "night-file", "name": "Night File 3D (Mysteries & Crime)", "engine": "faceless", "type": "3D", "render_time": "~2m"},
    {"id": "tall-tale", "name": "Tall Tale 3D (Funny Real Stories)", "engine": "faceless", "type": "3D", "render_time": "~2.5m"},
    # Motion Graphics Editor styles (Nafay 3D)
    {"id": "creator-motion-graphics", "name": "Creator Motion Graphics (Punchy Dark)", "engine": "motion", "type": "Motion", "render_time": "~30s"},
    {"id": "clean-tech", "name": "Clean Tech (Sleek UI Cards & Kinetic Text)", "engine": "motion", "type": "Motion", "render_time": "~30s"},
    {"id": "data-story", "name": "Data Story (Animated Charts & Counters)", "engine": "motion", "type": "Motion", "render_time": "~35s"}
]

class AnimationEngine:
    @staticmethod
    def list_styles() -> List[Dict]:
        return STYLES

    @staticmethod
    async def generate_script(topic: str, style_id: str, provider: str = "openrouter") -> Dict:
        """
        Uses API key pool (OpenRouter, Gemini, or NVIDIA) to direct the scene.
        """
        prompt = f"""Write an engaging 30-second viral short video script on: '{topic}'.
Style: {style_id}.
Return pure JSON in this structure:
{{
  "title": "Punchy Title",
  "hook": "Opening hook sentence",
  "narration": "Full narration script (about 75-90 words)",
  "shots": [
    {{"line": "Sentence chunk", "visual": "Visual animation description"}}
  ]
}}
"""
        # 1. Try OpenRouter
        import aiohttp
        for _ in range(4):
            key = key_manager.get_key("openrouter")
            if not key:
                break
            try:
                headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
                payload = {
                    "model": "deepseek/deepseek-chat",
                    "messages": [{"role": "user", "content": prompt}],
                    "response_format": {"type": "json_object"}
                }
                async with aiohttp.ClientSession() as session:
                    async with session.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=15) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            content = data["choices"][0]["message"]["content"]
                            return json.loads(content)
                        else:
                            key_manager.mark_failed_and_rotate("openrouter")
            except Exception:
                key_manager.mark_failed_and_rotate("openrouter")

        # 2. Try Gemini
        from google import genai
        for _ in range(4):
            key = key_manager.get_key("gemini")
            if not key:
                break
            try:
                client = genai.Client(api_key=key)
                res = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
                text = res.text.strip()
                if "```json" in text:
                    text = text.split("```json")[1].split("```")[0].strip()
                elif "```" in text:
                    text = text.split("```")[1].split("```")[0].strip()
                return json.loads(text)
            except Exception:
                key_manager.mark_failed_and_rotate("gemini")

        # Fallback default script
        return {
            "title": f"The Secrets of {topic}",
            "hook": f"Did you know what happens during {topic}?",
            "narration": f"Have you ever wondered what actually happens during {topic}? Scientists discovered that the reaction is completely unexpected. It changes everything we previously assumed.",
            "shots": [
                {"line": f"Have you ever wondered what happens during {topic}?", "visual": "Question icon and dynamic title burst"},
                {"line": "Scientists discovered that the reaction is unexpected.", "visual": "Magnified graphic showing reaction detail"},
                {"line": "It changes everything we previously assumed.", "visual": "Shocked character with animated energy lines"}
            ]
        }

    @staticmethod
    async def render_video(
        job_id: str,
        topic: str,
        style_id: str,
        script_data: Dict,
        voice: str = "en-US-ChristopherNeural"
    ) -> str:
        """
        Renders complete video on CPU:
        1. Generates voiceover via Edge-TTS.
        2. Renders animated frames using Headless Chromium + Playwright.
        3. Encodes final video with audio using FFmpeg.
        """
        output_file = os.path.join(CLIP_DIR, f"render_{job_id}_{style_id}.mp4")
        job_dir = os.path.join(TEMP_DIR, job_id)
        os.makedirs(job_dir, exist_ok=True)

        narration = script_data.get("narration", f"Exploring {topic}")
        audio_path = os.path.join(job_dir, "voice.mp3")

        # Step 1: Voiceover
        await generate_speech(narration, voice=voice, output_path=audio_path)

        # Step 2: Render canvas animation via Playwright Chromium
        from playwright.async_api import async_playwright

        html_canvas_path = os.path.join(job_dir, "scene.html")
        title_text = script_data.get("title", topic).upper()
        hook_text = script_data.get("hook", narration)

        # Standalone HTML5 9:16 Canvas composition with smooth animation loop
        html_content = f"""<!DOCTYPE html>
<html>
<head>
  <style>
    body, html {{ margin: 0; padding: 0; width: 1080px; height: 1920px; overflow: hidden; background: #07090e; font-family: 'Segoe UI', Impact, sans-serif; }}
    #canvas {{ width: 1080px; height: 1920px; }}
  </style>
</head>
<body>
  <canvas id="canvas" width="1080" height="1920"></canvas>
  <script>
    const canvas = document.getElementById('canvas');
    const ctx = canvas.getContext('2d');
    let frame = 0;
    const style = '{style_id}';
    const title = '{title_text}';
    const hook = '{hook_text.replace("'", "")}';

    function draw() {{
      frame++;
      // Background gradient
      const bg = ctx.createLinearGradient(0, 0, 1080, 1920);
      if (style.includes('deep-dive')) {{
        bg.addColorStop(0, '#020b14'); bg.addColorStop(1, '#08263d');
      }} else if (style.includes('night-file')) {{
        bg.addColorStop(0, '#000000'); bg.addColorStop(1, '#1b0202');
      }} else {{
        bg.addColorStop(0, '#0f172a'); bg.addColorStop(1, '#1e1b4b');
      }}
      ctx.fillStyle = bg;
      ctx.fillRect(0, 0, 1080, 1920);

      // Ambient pulse or particle rings
      ctx.save();
      ctx.translate(540, 960);
      const pulse = 1 + Math.sin(frame * 0.05) * 0.08;
      ctx.scale(pulse, pulse);

      // Visual Center Shield / Hero Card
      ctx.fillStyle = 'rgba(255, 255, 255, 0.05)';
      ctx.beginPath();
      ctx.arc(0, 0, 360, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = '#38bdf8';
      ctx.lineWidth = 6;
      ctx.stroke();

      // Style badge
      ctx.fillStyle = '#38bdf8';
      ctx.font = 'bold 36px sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText(style.toUpperCase() + ' · 2D ENGINE', 0, -260);

      // Animated Title
      ctx.fillStyle = '#ffffff';
      ctx.font = '900 84px Impact, sans-serif';
      ctx.fillText(title.substring(0, 24), 0, -40);

      // Yellow Hook Highlight
      ctx.fillStyle = '#facc15';
      ctx.font = 'bold 44px sans-serif';
      ctx.fillText(hook.substring(0, 36), 0, 80);
      ctx.restore();

      // Kinetic Subtitle Bottom Bar
      ctx.fillStyle = '#facc15';
      ctx.font = '900 68px Impact';
      ctx.textAlign = 'center';
      const words = hook.split(' ');
      const activeIdx = Math.floor(frame / 20) % words.length;
      ctx.fillText(words[activeIdx] ? words[activeIdx].toUpperCase() : 'ACTION', 540, 1620);
    }}

    window.drawFrame = draw;
  </script>
</body>
</html>
"""
        with open(html_canvas_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        # Step 3: Fast frame-by-frame snapshot capture with Playwright
        frames_dir = os.path.join(job_dir, "frames")
        os.makedirs(frames_dir, exist_ok=True)

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(viewport={"width": 1080, "height": 1920})
            await page.goto(f"file:///{html_canvas_path}")

            # Capture 150 frames (5 seconds preview loop or full duration)
            total_frames = 150
            for i in range(total_frames):
                await page.evaluate("window.drawFrame()")
                frame_path = os.path.join(frames_dir, f"frame_{i:04d}.jpg")
                await page.screenshot(path=frame_path, type="jpeg", quality=80)
            await browser.close()

        # Step 4: Stitch frames and mix with Edge-TTS voice via FFmpeg
        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-framerate", "30",
            "-i", os.path.join(frames_dir, "frame_%04d.jpg"),
            "-i", audio_path,
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-shortest",
            output_file
        ]
        subprocess.run(ffmpeg_cmd, check=True, capture_output=True)

        # Cleanup temp directory
        try:
            shutil.rmtree(job_dir)
        except Exception:
            pass

        return output_file

animation_engine = AnimationEngine()
