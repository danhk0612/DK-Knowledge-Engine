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
    "제공된 근거 문서(매뉴얼·FAQ·안내서 등)의 내용만 사용하세요. 문서에 없는 정보는 추측하지 마세요. "
    "질문의 핵심 결론을 먼저 간결하게 답하고, 같은 결론이나 근거 설명을 반복하지 마세요. "
    "질문과 관계없는 추가 기능·배경·사용 사례는 설명하지 마세요. "
    "단, 실제 동작·안전 주의사항·필수 조건은 간결하게 답하더라도 빠뜨리지 마세요. "
    "원문의 주체·조건·부정·허용/금지·상태 변화·시간·수치·단위를 바꾸거나 임의로 인과관계를 만들지 마세요. "
    "질문이 절차나 문제 해결이면 문서에서 확인되는 필요한 순서를 최대 5단계로 구분하세요. "
    "사용자가 짧은 검색어로 물어도 해당 문서의 실제 값을 직접 답하세요. "
    "코드·포트·버전·파일명 등 정답 값이 문서에 있으면 정확히 복사해 답변에 포함하고, 문서 위치만 알려주지 마세요. "
    "비교 질문은 각 항목의 근거를 별도로 확인하고 실제 출력·전달·차단 여부를 혼동하지 마세요. "
    "권한표는 열 제목과 해당 행을 맞춰 읽으세요. O는 허용, X는 불가이며, 모르면 추측하지 마세요. "
    "실제로 답변에 사용한 근거 번호 [1], [2] 등만 답변 끝에 한 번 명시하세요. "
    "근거가 질문에 답하기에 부족하면 '제공된 근거 문서만으로는 답변을 확인할 수 없습니다.'라고 답하세요. "
    "답변은 한국어로 작성하세요."
)
_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)
_CITATION = re.compile(r"(?<!\w)\[(\d{1,2})\](?!\w)")


def _answer_sources(answer: str, candidates: list[dict]) -> tuple[str, list[dict]] | None:
    """Keep cited sources only; renumber them to match the returned source list.

    Citation numbers refer to the prompt's evidence order. A model that emits no
    citations still works with the highest-ranked passage as the sole source;
    it does not falsely display every retrieved passage as used evidence.
    """
    indexes = [int(match.group(1)) for match in _CITATION.finditer(answer)]
    if any(number < 1 or number > len(candidates) for number in indexes):
        return None
    if not indexes:
        return answer, candidates[:1]
    chosen = sorted(set(indexes))
    remap = {old: new for new, old in enumerate(chosen, 1)}
    revised = _CITATION.sub(lambda match: f"[{remap[int(match.group(1))]}]", answer)
    return revised, [candidates[old - 1] for old in chosen]



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


def _explicit_table_permission(question: str, hits: list[dict]) -> dict | None:
    """Answer an explicit O/X permissions row without a small model flipping X.

    Never infer missing cells or roles: require a labeled header, the exact
    user's role, a matching feature row and exactly one consistent O/X value.
    This is a narrow safety guard, not a general table understanding system.
    """
    if not re.search(r"할\s*수|가능|권한|허용|사용|실행", question):
        return None
    matches: list[tuple[str, str, bool, dict]] = []
    for hit in hits:
        lines = [line.strip() for line in hit["excerpt"].splitlines() if line.strip()]
        for header_at, line in enumerate(lines):
            header = re.search(r"(?:사용자별\s*등급|권한\s*구분|사용자\s*등급)\s+(.+)", line)
            if not header:
                continue
            roles = header.group(1).split()
            if not 2 <= len(roles) <= 8:
                continue
            requested_roles = [(i, role) for i, role in enumerate(roles) if role in question]
            if len(requested_roles) != 1:
                continue
            index, role = requested_roles[0]
            for row in lines[header_at + 1:header_at + 24]:
                parts = row.split()
                if len(parts) <= len(roles):
                    continue
                markers = parts[-len(roles):]
                if any(value not in ("O", "X", "○", "×") for value in markers):
                    continue
                features = " ".join(parts[:-len(roles)])
                for feature in re.split(r"[,，/·]", features):
                    feature = feature.strip()
                    if len(feature) >= 2 and feature in question:
                        allowed = markers[index] in ("O", "○")
                        matches.append((role, feature, allowed, hit))
    # Conflicting table rows or multiple feature/role interpretations abstain.
    if len(matches) != 1:
        return None
    role, feature, allowed, hit = matches[0]
    status = "사용할 수 있습니다" if allowed else "사용할 수 없습니다"
    return {
        "answer": f"{role}는 {feature} 기능을 {status}. [1]",
        "grounded": True,
        "sources": [{
            "document_id": hit["document_id"],
            "chunk_id": hit["chunk_id"],
            "source_path": hit["source_path"],
            "page_from": hit["page_from"],
        }],
        "elapsed_seconds": 0.0,
    }


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
    permission = _explicit_table_permission(question, hits)
    if permission is not None:
        return permission

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
        "근거 문서:\n" + "\n\n".join(excerpts) + "\n\n"
        + "질문: " + question + "\n"
        + "질문에 직접 필요한 내용을 먼저 답하고, 다른 기능이나 근거를 나열하지 마세요. "
        + "원문의 조건·부정·주체·동작을 바꾸지 말고, 코드·숫자·기호를 그대로 유지하세요. "
        + "문서 경로만 안내하지 말고 실제 값을 답하세요. "
        + "실제로 사용한 근거 번호만 답변 끝에 한 번 표시하세요.\n"
        + "답변:"
    )
    started = perf_counter()
    answer = generator.generate(_SYSTEM_PROMPT, prompt).strip()
    elapsed = round(perf_counter() - started, 3)
    if not answer:
        raise RuntimeError("Local LLM returned an empty answer")
    # Refusals must not be accompanied by irrelevant retrieval citations.
    if NO_DOCUMENT_ANSWER in answer or NO_EVIDENCE in answer:
        return {"answer": answer, "grounded": False, "sources": [],
                "elapsed_seconds": elapsed}
    selected = _answer_sources(answer, sources)
    if selected is None:
        return {"answer": NO_DOCUMENT_ANSWER, "grounded": False, "sources": [],
                "elapsed_seconds": elapsed}
    answer, sources = selected
    return {
        "answer": answer,
        "grounded": True,
        "sources": sources,
        "elapsed_seconds": elapsed,
    }
