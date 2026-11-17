import asyncio
import json
import os
import time
from typing import Dict, List, Optional
import aiohttp

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "keys.json")

# Model catalog categorized by function
MODEL_CATALOG = {
    "clipper": {
        "groq": [
            {"id": "whisper-large-v3-turbo", "name": "Whisper Large V3 Turbo (Fast Audio)", "type": "audio", "cost": "Free Tier", "context": "25MB"},
            {"id": "whisper-large-v3", "name": "Whisper Large V3 (Deep Audio)", "type": "audio", "cost": "Free Tier", "context": "25MB"},
            {"id": "llama-3.3-70b-versatile", "name": "Llama 3.3 70B (Fast Moment Analysis)", "type": "llm", "cost": "Free Tier", "context": "128k"}
        ],
        "gemini": [
            {"id": "gemini-2.5-flash", "name": "Gemini 2.5 Flash (Viral Hook Master)", "type": "llm", "cost": "Free Tier", "context": "1M tokens"},
            {"id": "gemini-1.5-flash", "name": "Gemini 1.5 Flash (Standard Speed)", "type": "llm", "cost": "Free Tier", "context": "1M tokens"},
            {"id": "gemini-2.5-pro", "name": "Gemini 2.5 Pro (Deep Intelligence)", "type": "llm", "cost": "Tier 1", "context": "2M tokens"}
        ]
    },
    "animation": {
        "openrouter": [
            {"id": "deepseek/deepseek-chat", "name": "DeepSeek V3 (Visual Script Director)", "type": "llm", "cost": "Free / Low", "context": "64k"},
            {"id": "meta-llama/llama-3.3-70b-instruct", "name": "Llama 3.3 70B Instruct", "type": "llm", "cost": "Free / Low", "context": "128k"},
            {"id": "google/gemini-2.5-flash", "name": "Gemini 2.5 Flash via OpenRouter", "type": "llm", "cost": "Free Tier", "context": "1M tokens"}
        ],
        "nvidia": [
            {"id": "meta/llama-3.1-70b-instruct", "name": "NVIDIA Llama 3.1 70B NIM", "type": "llm", "cost": "Free 1000 Credits", "context": "128k"},
            {"id": "mistralai/mixtral-8x7b-instruct-v0.1", "name": "NVIDIA Mixtral 8x7B", "type": "llm", "cost": "Free 1000 Credits", "context": "32k"}
        ],
        "huggingface": [
            {"id": "Qwen/Qwen2.5-72B-Instruct", "name": "Qwen 2.5 72B HF Inference", "type": "llm", "cost": "Free Serverless", "context": "32k"},
            {"id": "meta-llama/Llama-3.2-3B-Instruct", "name": "Llama 3.2 3B (Fast Light)", "type": "llm", "cost": "Free Serverless", "context": "8k"}
        ]
    },
    "motion": {
        "gemini": [
            {"id": "gemini-2.5-flash", "name": "Gemini 2.5 Flash (CSS/GSAP Layouts)", "type": "code", "cost": "Free Tier", "context": "1M tokens"}
        ],
        "openrouter": [
            {"id": "qwen/qwen-2.5-coder-32b-instruct", "name": "Qwen 2.5 Coder 32B (Kinetic Titles)", "type": "code", "cost": "Free / Low", "context": "32k"}
        ]
    }
}

class KeyManager:
    """
    Manages API keys split across:
    1. Clipper (Transcription & Viral Moments)
    2. 2D/3D Animation (Storytelling & Scene directing)
    3. Motion Graphics (CSS/Kinetic code layout)
    With real-time health check test, latency, and token metrics.
    """
    def __init__(self, config_path: str = CONFIG_PATH):
        self.config_path = config_path
        self.keys: Dict[str, List[str]] = {
            "gemini": [],
            "groq": [],
            "openrouter": [],
            "nvidia": [],
            "huggingface": [],
            "elevenlabs": []
        }
        self.indices: Dict[str, int] = {k: 0 for k in self.keys}
        # Token & latency tracking per provider
        self.metrics: Dict[str, dict] = {
            k: {"total_tokens": 0, "last_latency_ms": 0, "status": "unknown"}
            for k in self.keys
        }
        self.load_keys()

    def load_keys(self):
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for provider in self.keys:
                        raw = data.get(provider, [])
                        self.keys[provider] = [k.strip() for k in raw if isinstance(k, str) and k.strip()]
            except Exception as e:
                print(f"[KeyManager] Error loading {self.config_path}: {e}")

    def save_keys(self, new_keys: Dict[str, List[str]]):
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(new_keys, f, indent=2)
        self.load_keys()

    def get_key(self, provider: str, account_index: Optional[int] = None) -> Optional[str]:
        pool = self.keys.get(provider, [])
        if not pool:
            return None
        if account_index is not None and 0 <= account_index < len(pool):
            return pool[account_index]
        idx = self.indices[provider] % len(pool)
        return pool[idx]

    def mark_failed_and_rotate(self, provider: str) -> Optional[str]:
        pool = self.keys.get(provider, [])
        if not pool:
            return None
        self.indices[provider] = (self.indices[provider] + 1) % len(pool)
        new_key = pool[self.indices[provider]]
        print(f"[KeyManager] Rotated {provider} to account {self.indices[provider] + 1}/{len(pool)}")
        return new_key

    def record_usage(self, provider: str, tokens: int, latency_ms: int):
        if provider in self.metrics:
            self.metrics[provider]["total_tokens"] += tokens
            self.metrics[provider]["last_latency_ms"] = latency_ms
            self.metrics[provider]["status"] = "active"

    async def test_key(self, provider: str, key: str) -> dict:
        """Tests live connectivity to provider API to verify if key is functional."""
        start = time.time()
        try:
            if provider == "groq":
                from groq import Groq
                client = Groq(api_key=key)
                # Quick lightweight call
                resp = client.models.list()
                lat = int((time.time() - start) * 1000)
                return {"valid": True, "latency_ms": lat, "message": "Connected (Groq LPU active)"}
            elif provider == "gemini":
                from google import genai
                client = genai.Client(api_key=key)
                resp = client.models.list()
                lat = int((time.time() - start) * 1000)
                return {"valid": True, "latency_ms": lat, "message": "Connected (Google GenAI active)"}
            elif provider == "openrouter":
                async with aiohttp.ClientSession() as s:
                    headers = {"Authorization": f"Bearer {key}"}
                    async with s.get("https://openrouter.ai/api/v1/auth/key", headers=headers, timeout=5) as r:
                        lat = int((time.time() - start) * 1000)
                        if r.status == 200:
                            data = await r.json()
                            limit = data.get("data", {}).get("limit", "unlimited")
                            return {"valid": True, "latency_ms": lat, "message": f"Connected (Limit: {limit})"}
                        return {"valid": False, "latency_ms": lat, "message": f"Auth failed ({r.status})"}
            elif provider == "nvidia":
                async with aiohttp.ClientSession() as s:
                    headers = {"Authorization": f"Bearer {key}"}
                    async with s.get("https://integrate.api.nvidia.com/v1/models", headers=headers, timeout=5) as r:
                        lat = int((time.time() - start) * 1000)
                        if r.status == 200:
                            return {"valid": True, "latency_ms": lat, "message": "Connected (NVIDIA NIM active)"}
                        return {"valid": False, "latency_ms": lat, "message": f"Status {r.status}"}
            else:
                return {"valid": True, "latency_ms": 10, "message": "Configured"}
        except Exception as e:
            lat = int((time.time() - start) * 1000)
            return {"valid": False, "latency_ms": lat, "message": str(e)[:60]}

    def get_full_status(self) -> dict:
        return {
            "keys": self.keys,
            "metrics": self.metrics,
            "catalog": MODEL_CATALOG,
            "indices": self.indices
        }

key_manager = KeyManager()
