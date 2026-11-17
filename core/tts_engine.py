import asyncio
import os
import edge_tts
from typing import List, Dict

VOICE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "storage", "voices")
os.makedirs(VOICE_DIR, exist_ok=True)

POPULAR_VOICES = [
    {"id": "en-US-ChristopherNeural", "name": "Christopher (US Male - Narrative)", "lang": "en-US", "gender": "Male"},
    {"id": "en-US-JennyNeural", "name": "Jenny (US Female - Natural)", "lang": "en-US", "gender": "Female"},
    {"id": "en-US-GuyNeural", "name": "Guy (US Male - Energetic)", "lang": "en-US", "gender": "Male"},
    {"id": "en-US-AriaNeural", "name": "Aria (US Female - Expressive)", "lang": "en-US", "gender": "Female"},
    {"id": "en-GB-RyanNeural", "name": "Ryan (UK Male - Authoritative)", "lang": "en-GB", "gender": "Male"},
    {"id": "en-GB-SoniaNeural", "name": "Sonia (UK Female - Crisp)", "lang": "en-GB", "gender": "Female"},
    {"id": "hi-IN-MadhurNeural", "name": "Madhur (Hindi Male - Deep)", "lang": "hi-IN", "gender": "Male"},
    {"id": "hi-IN-SwaraNeural", "name": "Swara (Hindi Female - Smooth)", "lang": "hi-IN", "gender": "Female"}
]

async def list_available_voices() -> List[Dict]:
    return POPULAR_VOICES

async def generate_speech(
    text: str,
    voice: str = "en-US-ChristopherNeural",
    rate: str = "+0%",
    volume: str = "+0%",
    pitch: str = "+0Hz",
    output_path: str = None
) -> str:
    if not output_path:
        filename = f"tts_{abs(hash(text + voice)) % 1000000}.mp3"
        output_path = os.path.join(VOICE_DIR, filename)

    communicate = edge_tts.Communicate(text, voice, rate=rate, volume=volume, pitch=pitch)
    await communicate.save(output_path)
    return output_path

async def generate_preview(voice: str) -> str:
    text = "Hello! This is a preview of the voiceover engine for your video clips."
    sample_path = os.path.join(VOICE_DIR, f"sample_{voice}.mp3")
    if not os.path.exists(sample_path):
        await generate_speech(text, voice=voice, output_path=sample_path)
    return sample_path

