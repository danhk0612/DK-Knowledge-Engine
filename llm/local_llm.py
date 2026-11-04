"""T04: connect T03 grounded retrieval to a local llama.cpp CLI process.

This module neither downloads models nor starts an HTTP server. It is intended
for single-turn CPU inference; rule-based /event handling stays in T03.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from time import perf_counter
from typing import Protocol

from search.knowledge_search import search_documents

NO_EVIDENCE = "등록된 문서에서 이 질문을 뒷받침하는 정보를 찾지 못했습니다."
NO_DOCUMENT_ANSWER = "제공된 근거 문서만으로는 답변을 확인할 수 없습니다."
_SYSTEM_PROMPT = (
    "답변은 간단한 한국어 한 문장으로 하세요. "
    "주어진 매뉴얼 내용만 사용하세요. "
    "매뉴얼에 없는 정보는 추측하지 마세요."
)
_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)


class TextGenerator(Protocol):
    def generate(self, system: str, user: str) -> str: ...


class LlamaCli:
    """Minimal llama-cli subprocess adapter; model is loaded on each request."""

    def __init__(
        self,
        executable: str | Path,
        model: str | Path,
        *,
        threads: int = 4,
        ctx_size: int = 4096,
        max_tokens: int = 192,
        timeout_seconds: int = 180,
    ) -> None:
        self.executable = Path(executable).resolve()
        self.model = Path(model).resolve()
        if not self.executable.is_file() or not self.model.is_file():
            raise FileNotFoundError("llama.cpp executable and local GGUF model must exist")
        if min(threads, ctx_size, max_tokens, timeout_seconds) < 1:
            raise ValueError("threads, context, generation length, and timeout must be positive")
        self.threads = threads
        self.ctx_size = ctx_size
        self.max_tokens = max_tokens
        self.timeout_seconds = timeout_seconds

    def generate(self, system: str, user: str) -> str:
        command = [
            str(self.executable),
            "-m", str(self.model),
            "-sys", system,
            "-p", user,
            "-t", str(self.threads),
            "-c", str(self.ctx_size),
            "-n", str(self.max_tokens),
            "-ngl", "0",   # CPU-only even if this PC has a GPU
            "--temp", "0",
            "--reasoning", "off",
            "--jinja",
            "--single-turn",
            "--simple-io",
            "--no-display-prompt",
            "--color", "off",
        ]
        result = subprocess.run(
            command,
            input="",
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=self.timeout_seconds,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(f"llama-cli returned exit code {result.returncode}: {result.stderr[-400:]}")
        text = _THINK.sub("", _ANSI.sub("", result.stdout))
        # An unfinished thinking segment must never be shown as a user answer.
        if "<think>" in text:
            text = text.split("<think>", 1)[0]
        text = text.replace("<|im_end|>", "").replace("<|eot_id|>", "").replace("[end of text]", "").strip()
        if any(marker in text for marker in ("Loading model...", "available commands:",
                                            "<references>", "Exiting...")):
            raise RuntimeError("llama.cpp returned a console transcript instead of an answer")
        if not text:
            raise RuntimeError("llama.cpp generated no visible answer")
        return text


def answer_from_knowledge(
    database: str | Path,
    *,
    product_id: str,
    question: str,
    generator: TextGenerator,
    version: str | None = None,
    max_sources: int = 3,
) -> dict:
    """Search T03 first; never invoke the model when sources are missing."""
    if not question or not question.strip():
        raise ValueError("question is required")
    if not 1 <= max_sources <= 5:
        raise ValueError("max_sources must be between 1 and 5")

    hits = search_documents(
        database, product_id=product_id, query=question,
        version=version, limit=max_sources,
    )
    if not hits:
        return {"answer": NO_EVIDENCE, "grounded": False, "sources": []}

    excerpts = []
    sources = []
    for position, hit in enumerate(hits, 1):
        sources.append({
            "document_id": hit["document_id"],
            "chunk_id": hit["chunk_id"],
            "source_path": hit["source_path"],
            "page_from": hit["page_from"],
        })
        excerpts.append(hit["excerpt"])
    prompt = (
        "매뉴얼: " + "\n".join(excerpts) + "\n"
        + "질문: " + question + " 답변:"
    )
    started = perf_counter()
    answer = generator.generate(_SYSTEM_PROMPT, prompt).strip()
    elapsed = round(perf_counter() - started, 3)
    if not answer:
        raise RuntimeError("Local LLM returned an empty answer")
    return {
        "answer": answer,
        "grounded": answer != NO_DOCUMENT_ANSWER,
        "sources": sources,
        "elapsed_seconds": elapsed,
    }
