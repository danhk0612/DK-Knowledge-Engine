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

from search.knowledge_search import QueryEmbedder, search_documents

NO_EVIDENCE = "등록된 문서에서 이 질문을 뒷받침하는 정보를 찾지 못했습니다."
NO_DOCUMENT_ANSWER = "제공된 근거 문서만으로는 답변을 확인할 수 없습니다."
_SYSTEM_PROMPT = (
    "제공된 매뉴얼 내용만 사용하세요. 매뉴얼에 없는 정보는 추측하지 마세요. "
    "질문이 절차나 문제 해결이면 필요한 순서를 최대 5단계로 구분하세요. "
    "결론을 뒷받침하는 매뉴얼 근거 번호 [1], [2] 등을 명시하세요. "
    "제공된 근거가 질문에 답하기에 부족하면 '제공된 근거 문서만으로는 답변을 확인할 수 없습니다.'라고 답하세요. "
    "사용자가 짧은 검색어로 물어도 질문에 해당하는 매뉴얼의 실제 값을 직접 답하세요. "
    "코드·포트·버전·파일명 등 정답 값이 매뉴얼에 있으면 정확히 복사해 답변에 포함하고, 문서 위치만 알려주지 마세요. "
    "답변은 한국어로 작성하세요. "
    "불필요한 추론 과정이나 문서에 없는 원인을 만들어 내지 마세요."
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
        gpu_layers: int = 0,
        prompt_mode: str = "qwen3",
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
        if type(gpu_layers) is not int or gpu_layers < 0:
            raise ValueError("gpu_layers must be a non-negative integer")
        if prompt_mode not in ("qwen3", "raw_chatml", "jinja"):
            raise ValueError("prompt_mode must be qwen3, raw_chatml or jinja")
        self.timeout_seconds = timeout_seconds
        self.gpu_layers = gpu_layers
        self.prompt_mode = prompt_mode

    def generate(self, system: str, user: str) -> str:
        command = [
            str(self.executable),
            "-m", str(self.model),
            "-t", str(self.threads),
            "-c", str(self.ctx_size),
            "-n", str(self.max_tokens),
            "-ngl", str(self.gpu_layers),
            "--temp", "0",
        ]
        if self.prompt_mode in ("qwen3", "jinja"):
            command += [
                "-sys", system,
                "-p", user,
                "--jinja",
                "--single-turn",
            ]
            if self.prompt_mode == "qwen3":
                command += ["--reasoning", "off"]
        else:
            # Compatibility mode for llama.cpp versions/models whose Jinja
            # conversation mode rejects the synthetic -sys/-p single turn.
            # Only intended for models that use ChatML tokens.
            prompt = (
                "<|im_start|>system\n" + system + "<|im_end|>\n"
                + "<|im_start|>user\n" + user + "<|im_end|>\n"
                + "<|im_start|>assistant\n<think>\n\n</think>\n"
            )
            command += ["-no-cnv", "-p", prompt]
        command += [
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
        # Raw ChatML may emit only the closing thinking delimiter after the prefill.
        text = re.sub(r"^(?:</think>\s*)+", "", text).strip()
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
    max_sources: int = 5,
    embedder: QueryEmbedder | None = None, min_similarity: float = 0.72,
) -> dict:
    """Search T03 first; never invoke the model when sources are missing."""
    if not question or not question.strip():
        raise ValueError("question is required")
    if not 1 <= max_sources <= 5:
        raise ValueError("max_sources must be between 1 and 5")

    hits = search_documents(
        database, product_id=product_id, query=question,
        version=version, limit=max_sources, embedder=embedder,
        min_similarity=min_similarity,
    )
    if not hits:
        return {"answer": NO_EVIDENCE, "grounded": False, "sources": []}

    excerpts = []
    sources = []
    remaining_chars = 4400  # Keep source context bounded on the default 4096-token CPU package.
    for position, hit in enumerate(hits, 1):
        content = hit["excerpt"].strip()
        if not content or remaining_chars < 160:
            break
        selected_text = content[:min(1100, remaining_chars)]
        remaining_chars -= len(selected_text)
        label = f"[{position}] {hit['source_path']}"
        if hit["page_from"] is not None:
            label += f" (p.{hit['page_from']})"
        sources.append({
            "document_id": hit["document_id"],
            "chunk_id": hit["chunk_id"],
            "source_path": hit["source_path"],
            "page_from": hit["page_from"],
        })
        excerpts.append(label + "\n" + selected_text)
    if not excerpts:
        return {"answer": NO_EVIDENCE, "grounded": False, "sources": []}
    prompt = (
        "매뉴얼:\n" + "\n\n".join(excerpts) + "\n\n"
        + "질문: " + question + "\n"
        + "질문과 일치하는 실제 값이나 코드를 매뉴얼에서 그대로 찾아 먼저 답하세요. "
        + "코드·숫자·기호를 바꾸거나 생략하지 말고, 문서 경로만 안내하지 마세요. "
        + "한국어로 답하고 맨 끝에 근거 번호 [1] 등을 표시하세요.\n"
        + "답변:"
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
