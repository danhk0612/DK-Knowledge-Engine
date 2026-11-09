"""Local llama.cpp embedding executable adapter.

The same embedding GGUF model *and* prefixes must be used during authoring
and user queries. No cloud services or numpy/torch are required.
"""
from __future__ import annotations

import hashlib
import json
import math
import subprocess
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1048576), b""):
            digest.update(block)
    return digest.hexdigest()


def normalize_vector(vector: list[float]) -> list[float]:
    if not 16 <= len(vector) <= 4096:
        raise ValueError("Embedding dimension must be between 16 and 4096")
    if any(not isinstance(n, (float, int)) or not math.isfinite(n) for n in vector):
        raise ValueError("Embedding has non-finite coordinates")
    norm = math.sqrt(sum(float(n) * float(n) for n in vector))
    if norm < 1e-7:
        raise ValueError("Embedding is a zero-length vector")
    return [float(n) / norm for n in vector]


class LlamaEmbedder:
    """Small local model inference; the executable exits after each request.

    This trades cold-load latency for a low idle-memory footprint on client PCs.
    """
    def __init__(self, executable: str | Path, model: str | Path, *,
                 timeout_seconds: int = 180, gpu_layers: int = 0):
        self.executable = Path(executable).resolve()
        self.model = Path(model).resolve()
        if not self.executable.is_file() or not self.model.is_file():
            raise FileNotFoundError("Embedding runtime and GGUF model are required")
        if self.model.suffix.lower() != ".gguf":
            raise ValueError("Embedding model must be GGUF")
        if not 1 <= timeout_seconds <= 600 or not 0 <= gpu_layers <= 999:
            raise ValueError("Invalid embedding runtime limits")
        self.timeout_seconds = timeout_seconds
        self.gpu_layers = gpu_layers

    def encode(self, text: str) -> list[float]:
        if not isinstance(text, str) or not text.strip() or len(text) > 4000:
            raise ValueError("Embedding input must be 1..4000 characters")
        cmd = [
            str(self.executable), "-m", str(self.model),
            "--pooling", "mean", "--embd-normalize", "2",
            "--embd-output-format", "array",
            "-p", text.strip(),
        ]
        # Avoid pointless GPU warnings on a CPU-only runtime. Model load
        # errors remain visible in stderr, even on failed local inference.
        if self.gpu_layers > 0:
            cmd.extend(("-ngl", str(self.gpu_layers)))
        process = subprocess.run(
            cmd, input="", capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=self.timeout_seconds, check=False,
        )
        if process.returncode != 0:
            raise RuntimeError(
                f"Local embedding inference failed (exit={process.returncode}): "
                + process.stderr[-1200:]
                + (("; stdout: " + process.stdout[-350:]) if process.stdout.strip() else "")
            )
        data = process.stdout.strip()
        try:
            decoded = json.loads(data)
            if (not isinstance(decoded, list) or len(decoded) != 1 or
                    not isinstance(decoded[0], list)):
                raise ValueError("Embedding output requires exactly one pooled vector")
            return normalize_vector(decoded[0])
        except (ValueError, TypeError) as error:
            raise RuntimeError("Invalid pooled embedding output") from error
