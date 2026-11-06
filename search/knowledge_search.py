"""T03: read-only document search and deterministic event lookup for T02 DBs.

No web API, LLM inference, document import, or database mutation.
"""

from __future__ import annotations

import re
import sqlite3
from contextlib import contextmanager, closing
from itertools import zip_longest
from pathlib import Path
from typing import Iterator

SCHEMA_VERSION = "1"
_VERSION_PATTERN = re.compile(r"\d+(?:\.\d+)*\Z", re.ASCII)
_SEARCH_TOKENS = re.compile(r"[^\W_]+", re.UNICODE)
# Remove conversational filler before scoring; keep specific product terminology.
_QUESTION_FILLER = frozenset({
    "방법", "무엇인가요", "무엇입니까", "어떻게", "알려주세요",
    "해주세요", "하나요", "할까요", "인가요", "경우",
})
_KOREAN_PARTICLES = (
    "에서는", "에게는", "으로는", "에서", "에게", "으로",
    "부터", "까지", "에는", "에도", "보다",
    "은", "는", "을", "를", "이", "가", "의", "와", "과",
)
_HANGUL = re.compile(r"[가-힣]")


def _version(value: str) -> tuple[int, ...]:
    """Accept numeric dotted versions; never compare version strings lexically."""
    if not _VERSION_PATTERN.fullmatch(value):
        raise ValueError(f"Unsupported version: {value!r} (expected digits separated by dots)")
    return tuple(int(part) for part in value.split("."))


def _compare_versions(a: tuple[int, ...], b: tuple[int, ...]) -> int:
    for left, right in zip_longest(a, b, fillvalue=0):
        if left != right:
            return -1 if left < right else 1
    return 0


def _version_applies(
    requested: tuple[int, ...] | None, start: str | None, end: str | None
) -> bool:
    if start is None and end is None:
        return True
    if requested is None:
        return False  # Cannot safely choose version-specific information.
    try:
        low = _version(start) if start else None
        high = _version(end) if end else None
    except ValueError:
        return False  # Unknown authoring syntax never matches by accident.
    if low is not None and high is not None and _compare_versions(low, high) > 0:
        return False
    return ((low is None or _compare_versions(requested, low) >= 0)
            and (high is None or _compare_versions(requested, high) <= 0))


def _query_terms(question: str) -> list[tuple[str, bool]]:
    """Return distinct normalized terms and whether FTS prefix matching is safe.

    Only a small particle/filler list is removed. Prefixes cover Korean
    inflections, not semantic synonyms or arbitrary substring matching.
    """
    terms: dict[str, bool] = {}
    for raw in _SEARCH_TOKENS.findall(question.casefold()):
        token = raw
        for particle in _KOREAN_PARTICLES:
            if (token.endswith(particle) and len(token) - len(particle) >= 2
                    and _HANGUL.search(token)):
                token = token[:-len(particle)]
                break
        if token in _QUESTION_FILLER:
            continue
        prefix = len(token) >= 2 and (bool(_HANGUL.search(token)) or token != raw)
        terms[token] = terms.get(token, False) or prefix
    return list(terms.items())


def _fts_query(question: str) -> str | None:
    """Quote user terms to prevent FTS syntax injection; allow safe prefixes."""
    terms = _query_terms(question)
    if not terms:
        return None
    return " OR ".join(
        '"' + term.replace('"', '""') + '"' + ("*" if prefix else "")
        for term, prefix in terms
    )


def _matched_term_count(terms: list[tuple[str, bool]], content: str) -> int:
    """Count distinct *indexed word* matches, not arbitrary substrings."""
    words = set(_SEARCH_TOKENS.findall(content.casefold()))
    return sum(
        any(word == term or (prefix and word.startswith(term)) for word in words)
        for term, prefix in terms
    )


@contextmanager
def _database(path: str | Path) -> Iterator[sqlite3.Connection]:
    db_path = Path(path).resolve()
    if not db_path.is_file():
        raise FileNotFoundError(db_path)
    # URI mode=ro avoids silently creating/replacing the supplied knowledge file.
    with closing(sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        row = db.execute("SELECT value FROM schema_info WHERE key='schema_version'").fetchone()
        if row is None or row[0] != SCHEMA_VERSION:
            raise ValueError(f"Unsupported knowledge DB schema version: {row[0] if row else None}")
        yield db


def search_documents(
    database: str | Path, *, product_id: str, query: str,
    version: str | None = None, limit: int = 10,
) -> list[dict]:
    """Return only product/version-appropriate FTS5 hits, with source provenance.

    Basic unicode61 token search, *not* Korean morphological/semantic matching.
    """
    if not product_id or not product_id.strip():
        raise ValueError("product_id is required")
    if not query or not query.strip():
        return []
    if not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    requested = _version(version) if version is not None else None
    terms = _query_terms(query)
    expression = _fts_query(query)
    if not expression:
        return []
    # One vague shared term is not evidence for a multi-concept question.
    minimum_matches = 1 if len(terms) == 1 else 2
    with _database(database) as db:
        # Filter product in SQL first. Apply dotted version constraints before limit.
        rows = db.execute("""
            SELECT d.document_id, d.product_id, d.title, d.source_path,
                   d.version_from, d.version_to,
                   c.chunk_id, c.section_title, c.content,
                   c.page_from, c.page_to,
                   bm25(chunks_fts) AS rank
            FROM chunks_fts
            JOIN chunks c ON c.id = chunks_fts.rowid
            JOIN documents d ON d.document_id = c.document_id
            WHERE chunks_fts MATCH ? AND d.product_id = ?
            ORDER BY rank ASC, d.source_path ASC, c.sequence ASC
        """, (expression, product_id)).fetchall()
    ranked: list[tuple[int, float, dict]] = []
    for row in rows:
        if not _version_applies(requested, row["version_from"], row["version_to"]):
            continue
        matched = _matched_term_count(
            terms, (row["section_title"] or "") + " " + row["content"],
        )
        if matched < minimum_matches:
            continue
        ranked.append((matched, row["rank"], {
            "document_id": row["document_id"],
            "chunk_id": row["chunk_id"],
            "title": row["title"],
            "section_title": row["section_title"],
            "excerpt": row["content"],
            "source_path": row["source_path"],
            "page_from": row["page_from"],
            "page_to": row["page_to"],
        }))
    # Prefer coverage of distinct query terms before FTS5 BM25 score.
    # SQL's stable path/sequence ordering remains the tiebreaker.
    ranked.sort(key=lambda hit: (-hit[0], hit[1]))
    return [hit for _, _, hit in ranked[:limit]]


def match_event(
    database: str | Path, *, product_id: str, version: str | None = None,
    event_id: str | None = None, error_code: str | None = None,
    screen_id: str | None = None,
) -> dict:
    """Find approved guidance for an event, without generating an LLM answer.

    Specific rules override broad ones; ties at the winning specificity are
    ambiguous and never pick an arbitrary result.
    """
    if not product_id or not product_id.strip():
        raise ValueError("product_id is required")
    if not event_id and not error_code:
        raise ValueError("event_id or error_code is required")
    requested = _version(version) if version is not None else None
    with _database(database) as db:
        rows = db.execute("""
            SELECT r.*, d.version_from AS doc_version_from,
                   d.version_to AS doc_version_to, d.source_path AS document_path
            FROM help_rules r
            JOIN documents d ON d.document_id = r.document_id
            WHERE r.product_id = ? AND d.product_id = ?
        """, (product_id, product_id)).fetchall()
    matches: list[tuple[tuple[int, int, int], sqlite3.Row]] = []
    for rule in rows:
        if rule["event_id"] is not None and rule["event_id"] != event_id:
            continue
        if rule["error_code"] is not None and rule["error_code"] != error_code:
            continue
        if rule["screen_id"] is not None and rule["screen_id"] != screen_id:
            continue
        if not (rule["event_id"] or rule["error_code"]):
            continue
        if not _version_applies(requested, rule["version_from"], rule["version_to"]):
            continue
        if not _version_applies(requested, rule["doc_version_from"], rule["doc_version_to"]):
            continue
        specificity = (
            int(rule["event_id"] is not None) + int(rule["error_code"] is not None),
            int(rule["screen_id"] is not None),
            int(rule["version_from"] is not None) + int(rule["version_to"] is not None),
        )
        matches.append((specificity, rule))
    if not matches:
        return {"matched": False}
    top = max(score for score, _ in matches)
    winners = [rule for score, rule in matches if score == top]
    if len(winners) > 1:
        return {"matched": False, "reason": "ambiguous_rules"}
    rule = winners[0]
    return {
        "matched": True,
        "rule_id": rule["rule_id"],
        "title": rule["title"],
        "content": rule["content"],
        "source": {
            "document_id": rule["document_id"],
            "chunk_id": rule["chunk_id"],
            "source_path": rule["document_path"],
        },
    }
