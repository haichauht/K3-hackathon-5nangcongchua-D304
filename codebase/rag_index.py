"""CLI and backwards-compatible exports for the persisted RAG index."""

from __future__ import annotations

import argparse
import json

from backend.config import SETTINGS
from backend.rag.index_manager import NullVectorIndex, RagIndexManager, parse_bool
from backend.rag.retriever import rag_index_build, rag_index_status


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage the VLearn local RAG index.")
    parser.add_argument("command", choices=("build", "status"), nargs="?", default="status")
    parser.add_argument("--force", action="store_true", help="Rebuild even if the index is current.")
    args = parser.parse_args()

    result = (
        rag_index_build(force_rebuild=args.force)
        if args.command == "build"
        else rag_index_status()
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()


__all__ = [
    "NullVectorIndex",
    "RagIndexManager",
    "SETTINGS",
    "main",
    "parse_bool",
]
