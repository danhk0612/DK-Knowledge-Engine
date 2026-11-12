"""T03: read-only document search and deterministic event lookup for T02 DBs.

No web API, LLM inference, document import, or database mutation.
"""

from __future__ import annotations

import re
import sqlite3
import struct
from contextlib import contextmanager, closing
from itertools import zip_longest
from pathlib import Path
from typing import Iterator, Protocol

SCHEMA_VERSION = "1"
_VERSION_PATTERN = re.compile(r"\d+(?:\.\d+)*\Z", re.ASCII)
_SEARCH_TOKENS = re.compile(r"[^\W_]+", re.UNICODE)
# Remove conversational filler before scoring; keep specific product terminology.
_QUESTION_FILLER = frozenset({
    "방법", "무엇인가요", "무엇입니까", "어떻게", "알려주세요",
    "해주세요", "하나요", "할까요", "인가요", "경우",
})
# "프로그램" is a useful subject qualifier in two-term questions
# ("프로그램 설치" must not match unrelated driver installation).
# Omit it only when at least two other meaningful terms remain.
_GENERIC_CONTEXT_TERMS = frozenset({"프로그램"})
_KOREAN_PARTICLES = (
    "에서는", "에게는", "으로는", "에서", "에게", "으로",
    "부터", "까지", "에는", "에도", "보다", "이나", "해야", "할", "로",
    "은", "는", "을", "를", "이", "가", "의", "와", "과",
)
_HANGUL = re.compile(r"[가-힣]")
# Narrow, document-independent terminology equivalents. These extend a query
# but are never treated as additional independent evidence terms.
_TERM_ALIASES = {
    "엑셀": ("xls", "xlsx", "excel"),
    "재기동": ("재시작",),
    "재시작": ("재기동",),
}
_QUESTION_FILLER = _QUESTION_FILLER | frozenset({
    "차이", "차이점", "비교", "다른점", "있는지", "있나", "있나요",
    "하는", "상황", "할", "수", "어떤", "되나요",
})


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
    if len(terms) > 2:
        for generic in _GENERIC_CONTEXT_TERMS:
            terms.pop(generic, None)
    return list(terms.items())


def _term_fts(term: str, prefix: bool) -> str:
    """Quote both the original term and fixed aliases for FTS5."""
    options = [(term, prefix)] + [
        (alias, bool(_HANGUL.search(alias)) and len(alias) >= 2)
        for alias in _TERM_ALIASES.get(term, ())
    ]
    return " OR ".join(
        '"' + word.replace('"', '""') + '"' + ("*" if startswith else "")
        for word, startswith in options
    )


def _fts_query(question: str) -> str | None:
    """Quote user terms to prevent FTS syntax injection; allow safe prefixes."""
    terms = _query_terms(question)
    if not terms:
        return None
    return " OR ".join("(" + _term_fts(term, prefix) + ")" for term, prefix in terms)


def _matched_term_count(terms: list[tuple[str, bool]], content: str) -> int:
    """Count distinct *indexed word* matches, not arbitrary substrings."""
    words = set(_SEARCH_TOKENS.findall(content.casefold()))
    return sum(
        any(
            word == term or (prefix and word.startswith(term))
            or any(
                word == alias or (bool(_HANGUL.search(alias)) and word.startswith(alias))
                for alias in _TERM_ALIASES.get(term, ())
            )
            for word in words
        )
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


def _compound_at_word_start(text: str, compound: str) -> bool:
    """Only join adjacent whole words; never start inside another word.

    A Hangul query like 데이터 베이스 can match 데이터베이스, but cannot
    match the substring inside 빅데이터 베이스라인.
    """
    for line in text.casefold().splitlines():
        for phrase in re.split(r"[.,;:!?。]", line):
            words = _SEARCH_TOKENS.findall(phrase)
            for start in range(len(words)):
                joined = ""
                for word in words[start:start + 6]:
                    joined += word
                    if joined.startswith(compound):
                        suffix = joined[len(compound):]
                        if not suffix or suffix in _KOREAN_PARTICLES:
                            return True
                        break
                    if not compound.startswith(joined):
                        break
    return False


class QueryEmbedder(Protocol):
    def encode(self, text: str) -> list[float]: ...


def _semantic_hits(
    database: str | Path, *, product_id: str, query: str,
    requested: tuple[int, ...] | None, embedder: QueryEmbedder,
    min_similarity: float, limit: int,
) -> list[dict]:
    """Exact-model dense retrieval, bounded by source product and version."""
    with _database(database) as db:
        has_table = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='chunk_embeddings'"
        ).fetchone()
        if not has_table:
            return []
        meta = dict(db.execute("SELECT key,value FROM embedding_metadata").fetchall())
        dim = int(meta.get("dimensions", "0"))
        if dim < 16 or dim > 4096:
            return []
        question_vector = embedder.encode(meta.get("query_prefix", "") + query[:2000])
        if len(question_vector) != dim:
            raise ValueError("Query embedding dimension differs from knowledge index")
        scored: list[tuple[float, str, dict]] = []
        rows = db.execute("""
            SELECT d.document_id, d.title, d.source_path,
                   d.version_from, d.version_to,
                   c.chunk_id, c.section_title, c.content, c.page_from, c.page_to,
                   e.vector, e.dimensions
            FROM chunk_embeddings e
            JOIN chunks c ON c.chunk_id = e.chunk_id
            JOIN documents d ON d.document_id = c.document_id
            WHERE d.product_id = ?
        """, (product_id,))
        for row in rows:
            if not _version_applies(requested, row["version_from"], row["version_to"]):
                continue
            raw = row["vector"]
            if row["dimensions"] != dim or len(raw) != 4 * dim:
                raise ValueError("Invalid stored embedding vector")
            vector = struct.unpack("<" + "f" * dim, raw)
            cosine = sum(x * y for x, y in zip(question_vector, vector))
            if cosine < min_similarity:
                continue
            scored.append((-cosine, row["source_path"], {
                "document_id": row["document_id"],
                "chunk_id": row["chunk_id"],
                "title": row["title"],
                "section_title": row["section_title"],
                "excerpt": row["content"],
                "source_path": row["source_path"],
                "page_from": row["page_from"],
                "page_to": row["page_to"],
            }))
        scored.sort(key=lambda item: (item[0], item[1]))
        return [hit for _, _, hit in scored[:limit]]


def _original_compound_fallback(
    database: str | Path, *, product_id: str, terms: list[tuple[str, bool]],
    requested: tuple[int, ...] | None, limit: int,
) -> list[dict]:
    # Unicode61 indexes Korean sequences as whole words. A search written
    # "데이터 베이스" cannot find "데이터베이스", or vice versa, even when the
    # words are adjacent in the source. Use a narrow, opt-in fallback that
    # requires *all* meaningful Hangul terms in the same order and adjacency.
    # It is not an arbitrary infix search, synonym expansion or semantic match.
    if (len(terms) > 6 or not terms or
            not all(re.fullmatch(r"[가-힣]{2,}", term) for term, _ in terms)):
        return []
    compound = "".join(term for term, _ in terms)
    # A single short term is too broad for whitespace-insensitive matching.
    if len(terms) == 1 and len(compound) < 4:
        return []
    first = terms[0][0][:2]
    with _database(database) as db:
        candidates = db.execute("""
            SELECT d.document_id, d.title, d.source_path,
                   d.version_from, d.version_to,
                   c.chunk_id, c.section_title, c.content,
                   c.page_from, c.page_to
            FROM chunks c JOIN documents d ON d.document_id = c.document_id
            WHERE d.product_id = ?
              AND (instr(c.content, ?) > 0 OR instr(coalesce(c.section_title, ''), ?) > 0)
            ORDER BY d.source_path, c.sequence
        """, (product_id, first, first))
        fallback: list[dict] = []
        for row in candidates:
            if not _version_applies(requested, row["version_from"], row["version_to"]):
                continue
            original = (row["section_title"] or "") + "\n" + row["content"]
            if not _compound_at_word_start(original, compound):
                continue
            fallback.append({
                "document_id": row["document_id"],
                "chunk_id": row["chunk_id"],
                "title": row["title"],
                "section_title": row["section_title"],
                "excerpt": row["content"],
                "source_path": row["source_path"],
                "page_from": row["page_from"],
                "page_to": row["page_to"],
            })
            if len(fallback) >= limit:
                break
        return fallback


def _comparison_evidence(
    database: str | Path, *, product_id: str, query: str,
    terms: list[tuple[str, bool]], requested: tuple[int, ...] | None,
) -> list[dict]:
    """Fetch each side separately when a comparison spans multiple pages.

    Single-chunk co-occurrence tends to select table-of-contents pages.
    Only apply this to explicit, two-concept comparison questions, preserving
    the normal two-term evidence guard on all other searches.
    """
    if len(terms) != 2 or not re.search(r"차이|비교|다른\s*점", query):
        return []
    chosen: list[dict] = []
    seen: set[str] = set()
    with _database(database) as db:
        for term, prefix in terms:
            rows = db.execute("""
                SELECT d.document_id, d.title, d.source_path,
                       d.version_from, d.version_to,
                       c.chunk_id, c.section_title, c.content,
                       c.page_from, c.page_to,
                       bm25(chunks_fts) AS rank
                FROM chunks_fts
                JOIN chunks c ON c.id = chunks_fts.rowid
                JOIN documents d ON d.document_id = c.document_id
                WHERE chunks_fts MATCH ? AND d.product_id = ?
                ORDER BY rank ASC, d.source_path ASC, c.sequence ASC
                LIMIT 80
            """, (_term_fts(term, prefix), product_id)).fetchall()
            candidates = []
            for row in rows:
                if not _version_applies(requested, row["version_from"], row["version_to"]):
                    continue
                content = row["content"]
                if _matched_term_count([(term, prefix)], content) < 1:
                    continue
                is_contents = "목차" in content or (
                    len(re.findall(r"(?i)\bpage\s*\d+", content)) >= 3
                )
                candidates.append((
                    bool(is_contents),
                    -min(content.casefold().count(term), 10),
                    row["rank"],
                    {
                        "document_id": row["document_id"],
                        "chunk_id": row["chunk_id"],
                        "title": row["title"],
                        "section_title": row["section_title"],
                        "excerpt": content,
                        "source_path": row["source_path"],
                        "page_from": row["page_from"],
                        "page_to": row["page_to"],
                    },
                ))
            candidates.sort(key=lambda item: item[:3])
            for _, _, _, hit in candidates:
                if hit["chunk_id"] not in seen:
                    seen.add(hit["chunk_id"])
                    chosen.append(hit)
                    break
    # Only replace default search if BOTH sides have actual evidence.
    return chosen if len(chosen) == 2 else []

def search_documents(
    database: str | Path, *, product_id: str, query: str,
    version: str | None = None, limit: int = 10,
    embedder: QueryEmbedder | None = None, min_similarity: float = 0.72,
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
    if not isinstance(min_similarity, (int, float)) or not 0.0 < min_similarity <= 1.0:
        raise ValueError("min_similarity must be between 0 and 1")
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
    facets = _comparison_evidence(
        database, product_id=product_id, query=query,
        terms=terms, requested=requested,
    )
    if facets:
        return facets[:limit]
    # Prefer coverage of distinct query terms before FTS5 BM25 score.
    # SQL's stable path/sequence ordering remains the tiebreaker.
    ranked.sort(key=lambda hit: (-hit[0], hit[1]))
    primary = [hit for _, _, hit in ranked[:limit]]
    if not primary:
        # Preserve the established original-text Korean spacing recovery
        # before optional dense or LLM-generated search expansions.
        primary = _original_compound_fallback(
            database, product_id=product_id, terms=terms,
            requested=requested, limit=limit,
        )
    if len(primary) >= limit:
        return primary

    # Optional author-side LLM-generated question/keyword index. It is ONLY
    # a route to the original excerpt, never a source of factual answer text.
    # Legacy v1 databases lack this table and still work unchanged.
    seen = {hit["chunk_id"] for hit in primary}
    with _database(database) as db:
        exists = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='chunk_search_hints_fts'"
        ).fetchone()
        if exists:
            hints = db.execute("""
                SELECT d.document_id, d.title, d.source_path, d.version_from,
                       d.version_to, c.chunk_id, c.section_title, c.content,
                       c.page_from, c.page_to, h.hints
                FROM chunk_search_hints_fts AS f
                JOIN chunk_search_hints AS h ON h.rowid = f.rowid
                JOIN chunks AS c ON c.chunk_id = h.chunk_id
                JOIN documents AS d ON d.document_id = c.document_id
                WHERE chunk_search_hints_fts MATCH ? AND d.product_id = ?
                ORDER BY bm25(chunk_search_hints_fts), d.source_path
            """, (expression, product_id)).fetchall()
            for hint in hints:
                if hint["chunk_id"] in seen:
                    continue
                if not _version_applies(requested, hint["version_from"], hint["version_to"]):
                    continue
                # Generic one-word hints are weak evidence; require a
                # specific query or two independently matching concepts.
                n = _matched_term_count(terms, hint["hints"])
                if n < minimum_matches or (len(terms) == 1 and len(terms[0][0]) < 4):
                    continue
                primary.append({
                    "document_id": hint["document_id"],
                    "chunk_id": hint["chunk_id"],
                    "title": hint["title"],
                    "section_title": hint["section_title"],
                    "excerpt": hint["content"],  # never emit generated hints as evidence
                    "source_path": hint["source_path"],
                    "page_from": hint["page_from"],
                    "page_to": hint["page_to"],
                })
                seen.add(hint["chunk_id"])
                if len(primary) >= limit:
                    return primary
    if primary or embedder is None:
        # Common case: exact original/author-assisted retrieval needs no
        # additional model loading or embedding CPU work on Client PCs.
        return primary
    return _semantic_hits(
        database, product_id=product_id, query=query, requested=requested,
        embedder=embedder, min_similarity=min_similarity, limit=limit,
    )


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
