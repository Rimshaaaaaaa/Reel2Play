"""Muse Glimmer on a Modal GPU, served by vLLM's OpenAI-compatible server (the play-tester).

Deploy:   modal deploy glimmer.py
Secrets:  a Modal secret named "huggingface" holding HF_TOKEN
Auth:     Modal servers require a proxy token by default. Set GLIMMER_API_KEY to
          "<token id>.<token secret>"; the API sends it as "Authorization: Bearer ...".
URL:      GLIMMER_BASE_URL is the URL `modal deploy` prints, followed by /v1.
"""

from __future__ import annotations

import json
import os
import subprocess

import modal

MODEL = os.environ.get("GLIMMER_MODEL", "meta-models/Muse-Glimmer-30B")
VLLM_VERSION = os.environ.get("VLLM_VERSION", "0.21.0")
PORT = 8000
MINUTES = 60

app = modal.App("reel2play-glimmer")
hf_cache = modal.Volume.from_name("huggingface-cache", create_if_missing=True)
vllm_cache = modal.Volume.from_name("vllm-cache", create_if_missing=True)
image = (
    modal.Image.from_registry("nvidia/cuda:12.9.0-devel-ubuntu22.04", add_python="3.12")
    .uv_pip_install(f"vllm=={VLLM_VERSION}")
    .env({"HF_XET_HIGH_PERFORMANCE": "1"})
)


@app.server(
    image=image,
    gpu="H100",
    volumes={"/root/.cache/huggingface": hf_cache, "/root/.cache/vllm": vllm_cache},
    secrets=[modal.Secret.from_name("huggingface")],
    port=PORT,
    startup_timeout=20 * MINUTES,
    scaledown_window=10 * MINUTES,
    target_concurrency=8,
)
class Glimmer:
    @modal.enter()
    def start(self) -> None:
        command = [
            "vllm",
            "serve",
            MODEL,
            "--served-model-name",
            MODEL,
            "--host",
            "0.0.0.0",
            "--port",
            str(PORT),
            "--max-model-len",
            "32768",
            "--gpu-memory-utilization",
            "0.92",
            "--limit-mm-per-prompt",
            json.dumps({"image": 4}),
        ]
        self.process = subprocess.Popen(command)

    @modal.exit()
    def stop(self) -> None:
        self.process.terminate()
