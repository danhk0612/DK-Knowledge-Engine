"""T02 Knowledge Builder: local document extraction and SQLite FTS5 indexing.

This is an author-side tool. No runtime LLM, HTTP API, or internet access is used.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "1"
SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}
MAX_CHUNK_CHARS = 1200


@dataclass(frozen=True)
class Segment:
    text: str
    section_title: str | None
    page: int | None


@dataclass(frozen=True)
class DocumentSource:
    file: Path
    source_path: str
    product_id: str
    document_id: str
    title: str
    source_type: str
    version_from: str | None
    version_to: str | None
    language: str | None
    source_hash: str
    metadata_hash: str


def _hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object expected: {path}")
    return value


def _optional_text(obj: dict[str, Any], key: str) -> str | None:
    value = obj.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string or null")
    return value.strip()


def _required_text(obj: dict[str, Any], key: str) -> str:
    value = _optional_text(obj, key)
    if value is None:
        raise ValueError(f"{key} is required")
    return value


def _enumerate_sources(source_root: Path, default_product_id: str = "default") -> tuple[list[DocumentSource], list[Path]]:
    if not source_root.is_dir():
        raise ValueError(f"Source directory not found: {source_root}")
    root_resolved = source_root.resolve()
    if not default_product_id.strip():
        raise ValueError("Default product ID cannot be empty")
    # Preserve product-scoped trees already used by existing integrations.
    product_directories = {
        child.name for child in source_root.iterdir()
        if child.is_dir() and ((child / "manuals").is_dir() or (child / "rules").is_dir())
    }
    docs: list[DocumentSource] = []
    rules: list[Path] = []
    ids: set[str] = set()
    for path in sorted(source_root.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"Symbolic links are not supported in sources: {path}")
        if not path.is_file():
            continue
        if not path.resolve().is_relative_to(root_resolved):
            raise ValueError(f"File escapes the source root: {path}")
        relative = path.relative_to(source_root)
        if (path.suffix.lower() == ".json" and len(relative.parts) >= 3
                and relative.parts[0] in product_directories
                and "rules" in relative.parts[1:-1]
                and not path.name.endswith(".meta.json")):
            rules.append(path)
            continue
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        # Loose documents at the root or in arbitrary subfolders use the
        # administrator's selected product; legacy product trees remain scoped.
        product_id = (relative.parts[0]
                      if len(relative.parts) >= 2 and relative.parts[0] in product_directories
                      else default_product_id)
        source_path = relative.as_posix()
        sidecar = path.with_name(path.name + ".meta.json")
        meta = _load_json(sidecar) if sidecar.is_file() else {}
        allowed = {"document_id", "title", "version_from", "version_to", "language"}
        if set(meta) - allowed:
            raise ValueError(f"Unsupported metadata keys in {sidecar}: {sorted(set(meta)-allowed)}")
        document_id = _optional_text(meta, "document_id") or "doc-" + _hash_bytes(source_path.encode("utf-8"))[:24]
        if document_id in ids:
            raise ValueError(f"Duplicate document_id: {document_id}")
        ids.add(document_id)
        title = _optional_text(meta, "title") or path.stem
        version_from = _optional_text(meta, "version_from")
        version_to = _optional_text(meta, "version_to")
        language = _optional_text(meta, "language") or "ko"
        normalized = {"document_id": document_id, "title": title, "version_from": version_from,
                      "version_to": version_to, "language": language, "product_id": product_id}
        docs.append(DocumentSource(
            file=path, source_path=source_path, product_id=product_id,
            document_id=document_id, title=title,
            source_type=path.suffix.lower().lstrip("."),
            version_from=version_from, version_to=version_to, language=language,
            source_hash=_sha_file(path),
            metadata_hash=_hash_bytes(json.dumps(normalized, sort_keys=True, ensure_ascii=False).encode("utf-8")),
        ))
    return docs, rules


def _text_segments(text: str, *, markdown: bool = False, page: int | None = None) -> list[Segment]:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    blocks = re.split(r"\n\s*\n", text)
    result: list[Segment] = []
    section: str | None = None
    for block in blocks:
        for line in block.splitlines():
            if markdown and re.match(r"^#{1,6}\s+", line):
                section = re.sub(r"^#{1,6}\s+", "", line).strip() or section
        cleaned = block.strip()
        if cleaned:
            result.append(Segment(cleaned, section, page))
    return result


def _ocr_pdf_page(path: Path, page_number: int, *, tesseract: str,
                  pdftoppm: str, language: str) -> str:
    """Run author-side, offline OCR for one otherwise non-text PDF page.

    Both external executables must be installed by the author. Nothing is
    downloaded, installed or bundled into the user's Client package.
    """
    if not re.fullmatch(r"[A-Za-z0-9_+\-]+", language):
        raise ValueError("Invalid OCR language code")
    with tempfile.TemporaryDirectory(prefix="dk-ocr-") as temporary:
        prefix = Path(temporary) / "page"
        render = subprocess.run(
            [pdftoppm, "-f", str(page_number), "-l", str(page_number),
             "-singlefile", "-r", "200", "-png", str(path), str(prefix)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=120, check=False,
        )
        if render.returncode != 0 or not prefix.with_suffix(".png").is_file():
            raise ValueError(f"PDF page {page_number} render failed: {render.stderr[-300:]}")
        recognition = subprocess.run(
            [tesseract, str(prefix.with_suffix(".png")), "stdout", "-l", language],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=120, check=False,
        )
        if recognition.returncode != 0:
            raise ValueError(f"PDF page {page_number} OCR failed: {recognition.stderr[-300:]}")
        return recognition.stdout


def _extract(path: Path, *, pdf_layout: bool = False,
             ocr_scanned_pages: bool = False,
             tesseract: str = "tesseract", pdftoppm: str = "pdftoppm",
             ocr_language: str = "kor+eng") -> tuple[list[Segment], list[str]]:
    warnings: list[str] = []
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md"}:
        segments = _text_segments(path.read_text(encoding="utf-8-sig"), markdown=suffix == ".md")
    elif suffix == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        segments = []
        for page_number, page in enumerate(reader.pages, start=1):
            text = (page.extract_text(extraction_mode="layout")
                    if pdf_layout else page.extract_text()) or ""
            extracted = _text_segments(text, page=page_number)
            if not extracted and ocr_scanned_pages:
                text = _ocr_pdf_page(path, page_number, tesseract=tesseract,
                                     pdftoppm=pdftoppm, language=ocr_language)
                extracted = _text_segments(text, page=page_number)
                if extracted:
                    warnings.append(f"{path}: page {page_number} OCR text recovered")
            if not extracted:
                warnings.append(f"{path}: page {page_number} has no extractable text (possibly scanned)")
            segments.extend(extracted)
    elif suffix == ".docx":
        from docx import Document
        document = Document(str(path))
        segments = []
        section: str | None = None
        for block in document.iter_inner_content():
            if hasattr(block, "rows"):
                for row in block.rows:
                    cells = [cell.text.strip() for cell in row.cells]
                    if any(cells):
                        segments.append(Segment(" | ".join(cells), section, None))
            else:
                content = block.text.strip()
                if not content:
                    continue
                style = block.style.name if block.style is not None else ""
                if style.lower().startswith("heading") or style.startswith("제목"):
                    section = content
                segments.append(Segment(content, section, None))
    else:
        raise ValueError(f"Unsupported format: {path}")
    if not segments:
        raise ValueError(f"No extractable text in {path}; OCR or source correction is required")
    return segments, warnings


def _split_long(text: str, max_chars: int) -> list[str]:
    result: list[str] = []
    while len(text) > max_chars:
        idx = text.rfind(" ", max_chars // 2, max_chars)
        if idx < 1:
            idx = max_chars
        result.append(text[:idx].strip())
        text = text[idx:].strip()
    if text:
        result.append(text)
    return result


def _make_chunks(segments: list[Segment]) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    current = ""
    section: str | None = None
    page: int | None = None

    def flush() -> None:
        nonlocal current
        if current:
            chunks.append({"section_title": section, "content": current,
                           "page_from": page, "page_to": page, "sequence": len(chunks) + 1})
            current = ""

    for segment in segments:
        for part in _split_long(segment.text, MAX_CHUNK_CHARS):
            if current and (section != segment.section_title or page != segment.page or
                            len(current) + len(part) + 2 > MAX_CHUNK_CHARS):
                flush()
            if not current:
                section, page = segment.section_title, segment.page
                current = part
            else:
                current += "\n\n" + part
    flush()
    return chunks


SCHEMA = """
CREATE TABLE schema_info (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE documents (
    document_id TEXT PRIMARY KEY,
    product_id TEXT NOT NULL,
    title TEXT NOT NULL,
    source_path TEXT NOT NULL UNIQUE,
    source_type TEXT NOT NULL,
    version_from TEXT,
    version_to TEXT,
    language TEXT,
    source_hash TEXT NOT NULL,
    metadata_hash TEXT NOT NULL
);
CREATE TABLE chunks (
    id INTEGER PRIMARY KEY,
    chunk_id TEXT NOT NULL UNIQUE,
    document_id TEXT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    section_title TEXT,
    content TEXT NOT NULL,
    page_from INTEGER,
    page_to INTEGER,
    sequence INTEGER NOT NULL,
    UNIQUE(document_id, sequence)
);
CREATE VIRTUAL TABLE chunks_fts USING fts5(
    section_title, content, content='chunks', content_rowid='id', tokenize='unicode61'
);
CREATE TRIGGER chunks_ai AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts(rowid, section_title, content) VALUES (new.id, new.section_title, new.content);
END;
CREATE TRIGGER chunks_ad AFTER DELETE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, section_title, content)
    VALUES ('delete', old.id, old.section_title, old.content);
END;
CREATE TRIGGER chunks_au AFTER UPDATE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, section_title, content)
    VALUES ('delete', old.id, old.section_title, old.content);
    INSERT INTO chunks_fts(rowid, section_title, content) VALUES (new.id, new.section_title, new.content);
END;
CREATE TABLE help_rules (
    rule_id TEXT PRIMARY KEY,
    product_id TEXT NOT NULL,
    event_id TEXT,
    error_code TEXT,
    screen_id TEXT,
    version_from TEXT,
    version_to TEXT,
    document_id TEXT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    chunk_id TEXT REFERENCES chunks(chunk_id),
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    source_path TEXT NOT NULL
);
"""


def _prepare_schema(db: sqlite3.Connection) -> None:
    existing = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schema_info'").fetchone()
    if not existing:
        other = db.execute("SELECT name FROM sqlite_master WHERE type='table' LIMIT 1").fetchone()
        if other:
            raise ValueError("Existing database has no recognized schema_info table")
        db.executescript(SCHEMA)
        db.execute("INSERT INTO schema_info(key, value) VALUES('schema_version', ?)", (SCHEMA_VERSION,))
        db.execute("INSERT INTO schema_info(key, value) VALUES('tokenizer', 'unicode61')")
        db.commit()
        return
    row = db.execute("SELECT value FROM schema_info WHERE key='schema_version'").fetchone()
    if row is None or row[0] != SCHEMA_VERSION:
        raise ValueError(f"Unsupported knowledge DB schema version: {row[0] if row else None}")


def _parse_rule(path: Path, root: Path) -> dict[str, Any]:
    data = _load_json(path)
    allowed = {"rule_id", "product_id", "event_id", "error_code", "screen_id", "version_from", "version_to",
               "document_id", "chunk_id", "title", "content"}
    if set(data) - allowed:
        raise ValueError(f"Unsupported rule keys in {path}: {sorted(set(data)-allowed)}")
    rule = {key: _optional_text(data, key) for key in allowed}
    for key in ("rule_id", "product_id", "document_id", "title", "content"):
        rule[key] = _required_text(data, key)
    if rule["event_id"] is None and rule["error_code"] is None:
        raise ValueError(f"Rule needs event_id or error_code: {path}")
    if rule["product_id"] != path.relative_to(root).parts[0]:
        raise ValueError(f"Rule product_id differs from its product directory: {path}")
    rule["source_path"] = path.relative_to(root).as_posix()
    return rule


def _sync(db: sqlite3.Connection, docs: list[DocumentSource], rules: list[Path],
          root: Path, *, pdf_layout: bool = False, ocr_scanned_pages: bool = False,
          tesseract: str = "tesseract", pdftoppm: str = "pdftoppm",
          ocr_language: str = "kor+eng") -> dict[str, Any]:
    existing = {row["source_path"]: row for row in db.execute("SELECT * FROM documents")}
    seen = set()
    changes = {"added": 0, "updated": 0, "deleted": 0, "unchanged": 0, "chunks": 0,
               "rules": 0, "warnings": [], "quality": []}
    with db:
        for doc in docs:
            seen.add(doc.source_path)
            previous = existing.get(doc.source_path)
            if previous and previous["source_hash"] == doc.source_hash and previous["metadata_hash"] == doc.metadata_hash:
                changes["unchanged"] += 1
                continue
            segments, warnings = _extract(doc.file, pdf_layout=pdf_layout,
                                          ocr_scanned_pages=ocr_scanned_pages,
                                          tesseract=tesseract, pdftoppm=pdftoppm,
                                          ocr_language=ocr_language)
            changes["warnings"].extend(warnings)
            chunks = _make_chunks(segments)
            changes["quality"].append({
                "source_path": doc.source_path, "product_id": doc.product_id,
                "extracted_characters": sum(len(s.text) for s in segments),
                "chunks": len(chunks),
                "warnings": warnings,
            })
            if not chunks:
                raise ValueError(f"No chunks generated for {doc.source_path}")
            if previous:
                # Keep the document identity stable, but replace its old chunk contents.
                db.execute("DELETE FROM documents WHERE document_id=?", (previous["document_id"],))
                changes["updated"] += 1
            else:
                changes["added"] += 1
            db.execute("""INSERT INTO documents
                (document_id, product_id, title, source_path, source_type, version_from,
                 version_to, language, source_hash, metadata_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (doc.document_id, doc.product_id, doc.title, doc.source_path, doc.source_type,
                 doc.version_from, doc.version_to, doc.language, doc.source_hash, doc.metadata_hash))
            for chunk in chunks:
                db.execute("""INSERT INTO chunks
                    (chunk_id, document_id, section_title, content, page_from, page_to, sequence)
                    VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (f"{doc.document_id}:{chunk['sequence']:06d}", doc.document_id,
                     chunk["section_title"], chunk["content"], chunk["page_from"],
                     chunk["page_to"], chunk["sequence"]))
        for path, prev in existing.items():
            if path not in seen:
                db.execute("DELETE FROM documents WHERE document_id=?", (prev["document_id"],))
                changes["deleted"] += 1
        # Rules are a small author-side input set, revalidated against current documents.
        db.execute("DELETE FROM help_rules")
        seen_rules: set[str] = set()
        for rule_path in rules:
            rule = _parse_rule(rule_path, root)
            if rule["rule_id"] in seen_rules:
                raise ValueError(f"Duplicate rule_id: {rule['rule_id']}")
            seen_rules.add(rule["rule_id"])
            referenced = db.execute("SELECT product_id FROM documents WHERE document_id=?", (rule["document_id"],)).fetchone()
            if not referenced or referenced[0] != rule["product_id"]:
                raise ValueError(f"Rule references missing or cross-product document: {rule_path}")
            if rule["chunk_id"]:
                chunk = db.execute("SELECT document_id FROM chunks WHERE chunk_id=?", (rule["chunk_id"],)).fetchone()
                if not chunk or chunk[0] != rule["document_id"]:
                    raise ValueError(f"Rule references missing or unrelated chunk: {rule_path}")
            fields = ["rule_id", "product_id", "event_id", "error_code", "screen_id",
                      "version_from", "version_to", "document_id", "chunk_id", "title", "content", "source_path"]
            db.execute(f"INSERT INTO help_rules ({', '.join(fields)}) VALUES ({', '.join('?' for _ in fields)})",
                       tuple(rule[name] for name in fields))
        changes["chunks"] = db.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        changes["rules"] = db.execute("SELECT COUNT(*) FROM help_rules").fetchone()[0]
        db.execute("INSERT INTO chunks_fts(chunks_fts) VALUES('integrity-check')")
        if db.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("Foreign key verification failed")
    return changes


def build(source_root: Path, database_path: Path, *, rebuild: bool = False,
          default_product_id: str = "default", pdf_layout: bool = False,
          ocr_scanned_pages: bool = False, tesseract: str = "tesseract",
          pdftoppm: str = "pdftoppm", ocr_language: str = "kor+eng") -> dict[str, Any]:
    if (pdf_layout or ocr_scanned_pages) and not rebuild:
        raise ValueError("PDF extraction options require --rebuild to refresh existing documents")
    root = source_root.resolve()
    out = database_path.resolve()
    # A .db inside the source folder is safe: document enumeration ignores it.
    # Never let a DB output overwrite a supported source document.
    if out.is_relative_to(root) and out.suffix.lower() in SUPPORTED_EXTENSIONS:
        raise ValueError("Output database cannot overwrite a source document")
    if not root.is_dir():
        raise ValueError(f"Source directory not found: {source_root}")
    docs, rules = _enumerate_sources(root, default_product_id=default_product_id)
    out.parent.mkdir(parents=True, exist_ok=True)
    working = out
    temp: Path | None = None
    if rebuild or not out.exists():
        fd, name = tempfile.mkstemp(prefix=".knowledge-", suffix=".db", dir=out.parent)
        os.close(fd)
        temp = Path(name)
        working = temp
    try:
        with closing(sqlite3.connect(working)) as db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA journal_mode=DELETE")
            _prepare_schema(db)
            result = _sync(db, docs, rules, root, pdf_layout=pdf_layout,
                           ocr_scanned_pages=ocr_scanned_pages,
                           tesseract=tesseract, pdftoppm=pdftoppm,
                           ocr_language=ocr_language)
        if temp:
            os.replace(temp, out)
        return result
    finally:
        if temp and temp.exists():
            temp.unlink()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create/update an offline knowledge SQLite FTS5 database")
    parser.add_argument("--source", required=True, type=Path, help="Directory containing documents at any depth")
    parser.add_argument("--default-product-id", default="default", help="Product ID for documents outside product-specific folders")
    parser.add_argument("--database", required=True, type=Path, help="Output .db file (any location, without overwriting source documents)")
    parser.add_argument("--rebuild", action="store_true", help="Rebuild database from all source documents atomically")
    parser.add_argument("--pdf-layout", action="store_true", help="Use pypdf layout-mode extraction for complex text PDFs")
    parser.add_argument("--ocr-scanned-pages", action="store_true", help="Use external offline Poppler+Tesseract on pages with no extracted text")
    parser.add_argument("--tesseract", default="tesseract", help="Tesseract executable or PATH command")
    parser.add_argument("--pdftoppm", default="pdftoppm", help="Poppler pdftoppm executable or PATH command")
    parser.add_argument("--ocr-language", default="kor+eng", help="Installed Tesseract language data")
    parser.add_argument("--quality-report", type=Path, help="Optional JSON extraction/chunk quality report")
    args = parser.parse_args(argv)
    try:
        if args.ocr_scanned_pages:
            for program, command in (("Tesseract", args.tesseract), ("Poppler pdftoppm", args.pdftoppm)):
                if shutil.which(command) is None:
                    raise ValueError(f"{program} executable not found: {command}; install it on the authoring PC or supply its path")
        summary = build(args.source, args.database, rebuild=args.rebuild,
                        default_product_id=args.default_product_id,
                        pdf_layout=args.pdf_layout, ocr_scanned_pages=args.ocr_scanned_pages,
                        tesseract=args.tesseract, pdftoppm=args.pdftoppm,
                        ocr_language=args.ocr_language)
        visible_summary = dict(summary)
        if args.quality_report:
            report = args.quality_report.resolve()
            if report == args.database.resolve() or (
                    report.is_relative_to(args.source.resolve())
                    and report.suffix.lower() in SUPPORTED_EXTENSIONS):
                raise ValueError("Quality report cannot replace the database or a source document")
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
            visible_summary.pop("quality", None)
            visible_summary["quality_report"] = str(report)
    except (ValueError, OSError, sqlite3.Error, ImportError, json.JSONDecodeError,
            subprocess.TimeoutExpired) as exc:
        print(f"Knowledge Builder failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(visible_summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
