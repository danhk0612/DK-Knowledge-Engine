"""Standalone author-side Builder CLI (Windows PyInstaller entrypoint).

No LLM, localhost API, network server or user-side modules are imported.
"""
from builder.knowledge_builder import main

if __name__ == "__main__":
    raise SystemExit(main())
