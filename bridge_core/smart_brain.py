#!/usr/bin/env python3
"""
CHAOS TYPE ZERO Smart Brain — LLM Fallback System
14 providers, 12 task chains, semantic cache, auto key rotation
"""

import hashlib
import json
import os
import random
import time
from collections import OrderedDict
from datetime import datetime, timedelta
from pathlib import Path

# === Provider Registry ===
PROVIDERS = {
    "nvidia": {
        "prefix": "nvapi-",
        "base_url": "https://integrate.api.nvidia.com/v1",
        "free_tier": True,
        "rate_limit": 100,
        "models": ["meta/llama-3.1-8b-instruct", "mistralai/mistral-7b-instruct-v0.3"],
    },
    "groq": {
        "prefix": "gsk_",
        "base_url": "https://api.groq.com/openai/v1",
        "free_tier": True,
        "rate_limit": 1000,
        "models": ["llama-3.1-8b-instant", "mixtral-8x7b-32768"],
    },
    "mistral": {
        "prefix": "msk-",
        "base_url": "https://api.mistral.ai/v1",
        "free_tier": True,
        "rate_limit": 500,
        "models": ["mistral-small-latest", "mistral-7b-instruct"],
    },
    "gemini": {
        "prefix": "AIza",
        "base_url": "https://generativelanguage.googleapis.com/v1beta",
        "free_tier": True,
        "rate_limit": 1500,
        "models": ["gemini-2.0-flash", "gemini-1.5-flash"],
    },
    "together": {
        "prefix": "tok_",
        "base_url": "https://api.together.xyz/v1",
        "free_tier": True,
        "rate_limit": 200,
        "models": ["meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo"],
    },
    "openrouter": {
        "prefix": "sk-or-",
        "base_url": "https://openrouter.ai/api/v1",
        "free_tier": True,
        "rate_limit": 200,
        "models": ["meta-llama/llama-3.1-8b-instruct:free"],
    },
    "cloudflare": {
        "prefix": "cf_",
        "base_url": "https://api.cloudflare.com/client/v4",
        "free_tier": True,
        "rate_limit": 10000,
        "models": ["@cf/meta/llama-3.1-8b-instruct"],
    },
    "cohere": {
        "prefix": "coh-",
        "base_url": "https://api.cohere.ai/v1",
        "free_tier": True,
        "rate_limit": 1000,
        "models": ["command-r"],
    },
    "huggingface": {
        "prefix": "hf_",
        "base_url": "https://api-inference.huggingface.co/models",
        "free_tier": True,
        "rate_limit": 300,
        "models": ["meta-llama/Meta-Llama-3.1-8B-Instruct"],
    },
    "deepseek": {
        "prefix": "sk-ds-",  # Changed from "sk-" to avoid OpenAI collision
        "base_url": "https://api.deepseek.com/v1",
        "free_tier": False,
        "rate_limit": 500,
        "models": ["deepseek-chat"],
    },
    "sambanova": {
        "prefix": "sak_",
        "base_url": "https://api.sambanova.ai/v1",
        "free_tier": True,
        "rate_limit": 100,
        "models": ["Meta-Llama-3.1-8B-Instruct"],
    },
    "ollama": {
        "prefix": "",
        "base_url": "http://localhost:11434",
        "free_tier": True,
        "rate_limit": 999999,
        "models": ["llama3.1", "mistral", "codellama"],
    },
    "openai": {
        "prefix": "sk-",
        "base_url": "https://api.openai.com/v1",
        "free_tier": False,
        "rate_limit": 5000,
        "models": ["gpt-4o-mini", "gpt-4o"],
    },
    "anthropic": {
        "prefix": "sk-ant-",
        "base_url": "https://api.anthropic.com/v1",
        "free_tier": False,
        "rate_limit": 1000,
        "models": ["claude-3-haiku-20240307", "claude-3-sonnet-20240229"],
    },
}

# === Task Chains ===
TASK_CHAINS = {
    "code": {
        "preferred": ["nvidia", "groq", "deepseek"],
        "fallback": ["ollama", "openrouter"],
        "model_preference": ["code", "instruct"],
    },
    "research": {
        "preferred": ["gemini", "groq", "cohere"],
        "fallback": ["ollama", "huggingface"],
        "model_preference": ["8b", "7b"],
    },
    "vision": {
        "preferred": ["gemini", "openai"],
        "fallback": ["nvidia"],
        "model_preference": ["flash", "multimodal"],
    },
    "pentest": {
        "preferred": ["groq", "nvidia", "mistral"],
        "fallback": ["ollama"],
        "model_preference": ["instruct", "8b"],
    },
    "write": {
        "preferred": ["cohere", "gemini", "mistral"],
        "fallback": ["ollama", "groq"],
        "model_preference": ["command", "instruct"],
    },
    "speed": {
        "preferred": ["groq", "nvidia", "sambanova"],
        "fallback": ["ollama"],
        "model_preference": ["instant", "turbo", "8b"],
    },
    "quality": {
        "preferred": ["openai", "anthropic", "gemini"],
        "fallback": ["groq", "nvidia"],
        "model_preference": ["4o", "sonnet", "flash"],
    },
    "cost": {
        "preferred": ["ollama", "groq", "nvidia"],
        "fallback": ["sambanova", "huggingface"],
        "model_preference": ["8b", "7b"],
    },
    "local": {
        "preferred": ["ollama"],
        "fallback": [],
        "model_preference": ["llama3.1", "codellama"],
    },
    "hinglish": {
        "preferred": ["groq", "nvidia", "ollama"],
        "fallback": ["mistral", "gemini"],
        "model_preference": ["8b", "instruct"],
    },
    "data": {
        "preferred": ["groq", "nvidia", "deepseek"],
        "fallback": ["ollama", "openrouter"],
        "model_preference": ["instruct", "8b"],
    },
    "agent": {
        "preferred": ["groq", "nvidia", "ollama"],
        "fallback": ["mistral", "sambanova"],
        "model_preference": ["instruct", "8b"],
    },
    "ml": {
        "preferred": ["groq", "nvidia", "deepseek"],
        "fallback": ["ollama", "openrouter"],
        "model_preference": ["instruct", "8b"],
    },
}


class LRUCache:
    """Multi-level LRU cache for LLM responses"""

    def __init__(self, ram_size=100, disk_path=None):
        self.ram_cache = OrderedDict()
        self.ram_size = ram_size
        self.disk_path = disk_path or Path("data/cache/llm_responses.json")
        self.disk_cache = self._load_disk_cache()
        self.stats = {"hits": 0, "misses": 0}
        self._dirty = False  # Track if disk needs write

    def _load_disk_cache(self):
        try:
            if self.disk_path.exists():
                return json.loads(self.disk_path.read_text(encoding="utf-8", errors="replace"))
        except (json.JSONDecodeError, OSError) as e:
            print(f"[WARN] Failed to load disk cache: {e}")
        return {}

    def _save_disk_cache(self, force=False):
        """Save to disk with write coalescing — only write if dirty or forced."""
        if not force and not self._dirty:
            return
        try:
            self.disk_path.parent.mkdir(parents=True, exist_ok=True)
            # Keep only last 1000 entries
            if len(self.disk_cache) > 1000:
                sorted_keys = sorted(
                    self.disk_cache.keys(),
                    key=lambda k: self.disk_cache[k].get("time", 0),
                )
                for k in sorted_keys[:500]:
                    del self.disk_cache[k]
            self.disk_path.write_text(json.dumps(self.disk_cache, indent=2), encoding="utf-8")
            self._dirty = False
        except OSError as e:
            print(f"[WARN] Failed to save disk cache: {e}")

    def _hash_key(self, query, task_type, model, system_prompt=None):
        content = f"{query}|{task_type}|{model}|{system_prompt or ''}"
        return hashlib.sha256(content.encode()).hexdigest()[:32]

    def get(self, query, task_type="agent", model="default", system_prompt=None):
        key = self._hash_key(query, task_type, model, system_prompt)

        # L1: RAM
        if key in self.ram_cache:
            self.ram_cache.move_to_end(key)
            self.stats["hits"] += 1
            return self.ram_cache[key]["response"]

        # L2: Disk
        if key in self.disk_cache:
            entry = self.disk_cache[key]
            # Promote to RAM
            self.ram_cache[key] = entry
            if len(self.ram_cache) > self.ram_size:
                self.ram_cache.popitem(last=False)
            self.stats["hits"] += 1
            return entry["response"]

        self.stats["misses"] += 1
        return None

    def set(self, query, task_type, model, response, system_prompt=None):
        key = self._hash_key(query, task_type, model, system_prompt)
        entry = {
            "response": response,
            "time": time.time(),
            "task_type": task_type,
            "model": model,
        }

        # Save to RAM
        self.ram_cache[key] = entry
        if len(self.ram_cache) > self.ram_size:
            self.ram_cache.popitem(last=False)

        # Save to disk (lazy)
        self.disk_cache[key] = entry
        self._dirty = True
        self._save_disk_cache()

    def flush(self):
        """Force write to disk."""
        self._save_disk_cache(force=True)

    def clear(self):
        self.ram_cache.clear()
        self.disk_cache.clear()
        self._save_disk_cache(force=True)


class SmartBrain:
    """CHAOS TYPE ZERO Smart Brain — LLM routing with fallback and caching"""

    def __init__(self, keys_file=None):
        self.keys_file = keys_file or Path("config/.env")
        self.keys = self._load_keys()
        self.usage = {}  # Track usage per provider
        self.cache = LRUCache()
        self._init_usage()

    def _load_keys(self):
        """Load API keys from .env file"""
        keys = {}
        if self.keys_file.exists():
            for line in self.keys_file.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    name, value = line.split("=", 1)
                    keys[name.strip()] = value.strip()
        return keys

    def _init_usage(self):
        """Initialize usage tracking"""
        for provider in PROVIDERS:
            self.usage[provider] = {
                "count": 0,
                "last_reset": datetime.now().isoformat(),
                "errors": 0,
            }

    def _detect_provider(self, key_name, key_value):
        """Auto-detect provider from key prefix.
        
        Order matters: more specific prefixes must be checked first.
        - sk-ant- (Anthropic) before sk- (OpenAI)
        - sk-ds- (DeepSeek) before sk- (OpenAI)
        - sk-or- (OpenRouter) before sk- (OpenAI)
        """
        # Check specific prefixes first (longer/more specific)
        specific_order = [
            "anthropic",    # sk-ant-
            "deepseek",     # sk-ds-
            "openrouter",   # sk-or-
        ]
        for provider_name in specific_order:
            info = PROVIDERS[provider_name]
            if info["prefix"] and key_value.startswith(info["prefix"]):
                return provider_name

        # Then check all others
        for provider, info in PROVIDERS.items():
            if provider in specific_order:
                continue  # Already checked
            if info["prefix"] and key_value.startswith(info["prefix"]):
                return provider
        return None

    def _get_available_keys(self, provider):
        """Get all keys for a provider"""
        provider_keys = []
        for name, value in self.keys.items():
            detected = self._detect_provider(name, value)
            if detected == provider:
                provider_keys.append(value)
        return provider_keys

    def _check_rate_limit(self, provider):
        """Check if provider is rate-limited"""
        info = PROVIDERS.get(provider, {})
        usage = self.usage.get(provider, {})
        return usage.get("count", 0) < info.get("rate_limit", 999)

    def _rotate_key(self, provider):
        """Rotate to next available key for provider"""
        keys = self._get_available_keys(provider)
        if keys:
            return random.choice(keys)
        return None

    def select_provider(self, task_type="agent"):
        """Select best provider for task type"""
        chain = TASK_CHAINS.get(task_type, TASK_CHAINS["agent"])

        # Try preferred providers
        for provider in chain["preferred"]:
            if self._check_rate_limit(provider):
                key = self._rotate_key(provider)
                if key:
                    return provider, key

        # Try fallback providers
        for provider in chain["fallback"]:
            if self._check_rate_limit(provider):
                key = self._rotate_key(provider)
                if key:
                    return provider, key

        # Last resort: Ollama (always free)
        return "ollama", "local"

    def select_model(self, provider, task_type="agent"):
        """Select best model for provider + task"""
        chain = TASK_CHAINS.get(task_type, TASK_CHAINS["agent"])
        provider_info = PROVIDERS.get(provider, {})
        models = provider_info.get("models", [])

        # Match preference patterns
        for pattern in chain.get("model_preference", []):
            for model in models:
                if pattern.lower() in model.lower():
                    return model

        # Return first available
        return models[0] if models else "default"

    def query(self, prompt, task_type="agent", system_prompt=None, max_retries=3):
        """
        Query LLM with automatic provider selection, fallback, and caching.

        Returns: (response_text, provider, model, cached)
        """
        # Check cache first
        cached = self.cache.get(prompt, task_type, "auto", system_prompt)
        if cached:
            return cached, "cache", "cache", True

        last_error = None
        tried_providers = set()

        for attempt in range(max_retries):
            provider, key = self.select_provider(task_type)

            if provider in tried_providers:
                continue
            tried_providers.add(provider)

            try:
                model = self.select_model(provider, task_type)
                response = self._call_provider(provider, key, model, prompt, system_prompt)

                if response:
                    # Update usage
                    self.usage[provider]["count"] += 1

                    # Cache response
                    self.cache.set(prompt, task_type, model, response, system_prompt)

                    return response, provider, model, False

            except Exception as e:
                last_error = e
                self.usage[provider]["errors"] += 1
                continue

        return f"All providers failed. Last error: {last_error}", "none", "none", False

    def _call_provider(self, provider, key, model, prompt, system_prompt=None):
        """Call the appropriate provider adapter."""
        if provider == "ollama":
            return self._call_ollama(model, prompt, system_prompt)
        elif provider == "gemini":
            return self._call_gemini(key, model, prompt, system_prompt)
        elif provider == "cloudflare":
            return self._call_cloudflare(key, model, prompt, system_prompt)
        elif provider == "huggingface":
            return self._call_huggingface(key, model, prompt, system_prompt)
        elif provider == "cohere":
            return self._call_cohere(key, model, prompt, system_prompt)
        elif provider == "anthropic":
            return self._call_anthropic(key, model, prompt, system_prompt)
        else:
            # OpenAI-compatible format (nvidia, groq, mistral, together, openrouter, sambanova, deepseek, openai)
            return self._call_openai_compatible(provider, key, model, prompt, system_prompt)

    def _call_ollama(self, model, prompt, system_prompt=None):
        """Call Ollama locally"""
        import requests

        url = "http://localhost:11434/api/generate"
        payload = {
            "model": model,
            "prompt": prompt,
            "system": system_prompt or "",
            "stream": False,
        }

        resp = requests.post(url, json=payload, timeout=120)
        resp.raise_for_status()
        return resp.json().get("response", "")

    def _call_openai_compatible(self, provider, key, model, prompt, system_prompt=None):
        """Call any OpenAI-compatible API (nvidia, groq, mistral, together, openrouter, etc.)"""
        import requests

        info = PROVIDERS[provider]
        url = f"{info['base_url']}/chat/completions"

        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 32768,
        }

        resp = requests.post(url, json=payload, headers=headers, timeout=60)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    def _call_gemini(self, key, model, prompt, system_prompt=None):
        """Call Google Gemini API (non-OpenAI format)."""
        import requests

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"

        parts = []
        if system_prompt:
            parts.append({"text": f"[System]: {system_prompt}\n\n{prompt}"})
        else:
            parts.append({"text": prompt})

        payload = {
            "contents": [{"parts": parts}],
            "generationConfig": {
                "temperature": 0.7,
                "maxOutputTokens": 32768,
            },
        }

        resp = requests.post(url, json=payload, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]

    def _call_cloudflare(self, key, model, prompt, system_prompt=None):
        """Call Cloudflare Workers AI API."""
        import requests

        # Cloudflare uses account-based routing
        # URL format: /accounts/{account_id}/ai/v1/{model}/chat
        # But we use the simpler /chat endpoint
        url = f"https://api.cloudflare.com/client/v4/accounts/{key.split(':')[0]}/ai/v1/chat/completions" if ':' in key else f"{PROVIDERS['cloudflare']['base_url']}/chat/completions"

        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": model,
            "messages": messages,
        }

        resp = requests.post(url, json=payload, headers=headers, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        return data["result"]["response"]

    def _call_huggingface(self, key, model, prompt, system_prompt=None):
        """Call HuggingFace Inference API."""
        import requests

        url = f"https://api-inference.huggingface.co/models/{model}"

        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }

        full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
        payload = {
            "inputs": full_prompt,
            "parameters": {
                "max_new_tokens": 4096,
                "temperature": 0.7,
            },
        }

        resp = requests.post(url, json=payload, headers=headers, timeout=120)
        resp.raise_for_status()
        data = resp.json()

        # HuggingFace returns a list of generated texts
        if isinstance(data, list) and len(data) > 0:
            return data[0].get("generated_text", str(data))
        return str(data)

    def _call_cohere(self, key, model, prompt, system_prompt=None):
        """Call Cohere API (non-OpenAI format)."""
        import requests

        url = "https://api.cohere.ai/v1/chat"

        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": model,
            "message": prompt,
        }
        if system_prompt:
            preamble = system_prompt
        else:
            preamble = "You are a helpful AI assistant."

        payload["preamble"] = preamble

        resp = requests.post(url, json=payload, headers=headers, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        return data.get("text", str(data))

    def _call_anthropic(self, key, model, prompt, system_prompt=None):
        """Call Anthropic Claude API (Messages API)."""
        import requests

        url = "https://api.anthropic.com/v1/messages"

        headers = {
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

        payload = {
            "model": model,
            "max_tokens": 32768,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system_prompt:
            payload["system"] = system_prompt

        resp = requests.post(url, json=payload, headers=headers, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        return data["content"][0]["text"]

    def get_stats(self):
        """Get brain statistics"""
        return {
            "providers": len(PROVIDERS),
            "task_chains": len(TASK_CHAINS),
            "cache_hit_rate": (
                self.cache.stats["hits"]
                / max(1, self.cache.stats["hits"] + self.cache.stats["misses"])
                * 100
            ),
            "usage": self.usage,
            "keys_loaded": len(self.keys),
        }


# === Singleton ===
_brain = None

def get_brain():
    global _brain
    if _brain is None:
        _brain = SmartBrain()
    return _brain


if __name__ == "__main__":
    brain = get_brain()
    stats = brain.get_stats()
    print(json.dumps(stats, indent=2))
