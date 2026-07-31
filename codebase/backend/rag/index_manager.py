"""Persistent lifecycle for the local VLearn Recall retrieval index.

The module deliberately contains no source text.  It fingerprints source files
and stores only sparse vector data plus a small document mapping under the
configured ``data/.rag-index`` directory.  The server supplies the document
loader and vector-index adapter at runtime, so raw source remains in memory
only.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


INDEX_SCHEMA_VERSION = "rag-index-v1"
VECTOR_FORMAT_VERSION = 1
VECTOR_FILE = "vectors.json"
MAPPING_FILE = "mapping.json"
MANIFEST_FILE = "manifest.json"
RAW_METADATA_KEYS = {"text", "context", "preview", "file_path", "raw_text", "snippet"}


def parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class NullVectorIndex:
    """Safe lexical-only fallback when vector index construction is unavailable."""

    def __init__(self, document_count: int) -> None:
        self.documents = [None] * max(0, document_count)

    def search(self, query: str) -> list[float]:
        del query
        return [0.0] * len(self.documents)


class RagIndexManager:
    """Detect, load and atomically rebuild a local retrieval index.

    ``build_index`` and the serializers are supplied by the application.  This
    keeps this lifecycle module independent from the source parser and avoids
    accidentally persisting the application's raw document dictionaries.
    """

    _build_lock = threading.Lock()

    def __init__(
        self,
        *,
        data_root: Path,
        index_dir: Path,
        mode: str = "persistent",
        auto_refresh: bool = True,
        embedding_model: str = "local-tfidf-char3-v1",
        chunking_version: str = "transcript-chunk-v1",
        normalization_version: str = "nfkc-tone-v2",
        index_schema_version: str = INDEX_SCHEMA_VERSION,
    ) -> None:
        self.data_root = Path(data_root).resolve()
        self.data_parent = self.data_root.parent
        self.index_dir = Path(index_dir).resolve()
        self.requested_mode = mode.strip().lower() if mode else "persistent"
        if self.requested_mode not in {"persistent", "memory"}:
            self.requested_mode = "persistent"
        self.auto_refresh = bool(auto_refresh)
        self.embedding_model = embedding_model
        self.chunking_version = chunking_version
        self.normalization_version = normalization_version
        self.index_schema_version = index_schema_version
        self.path_valid = self.index_dir == (self.data_parent / ".rag-index").resolve()
        self.path_error = "" if self.path_valid else "index_dir_outside_data_boundary"
        self.runtime_status: dict[str, Any] = self._base_status()

    def _base_status(self) -> dict[str, Any]:
        effective_mode = self.requested_mode if self.path_valid else "memory"
        status = {
            "index_mode": effective_mode,
            "requested_index_mode": self.requested_mode,
            "index_ready": False,
            "index_stale": False,
            "auto_refresh": self.auto_refresh,
            "embedding_model": self.embedding_model,
            "documents_loaded": 0,
            "last_indexed_at": None,
            "changed_files_detected": 0,
            "degraded": bool(self.path_error),
        }
        if self.path_error:
            status["fallback_reason"] = self.path_error
        return status

    def _config(self) -> dict[str, str]:
        return {
            "embedding_model": self.embedding_model,
            "chunking_version": self.chunking_version,
            "normalization_version": self.normalization_version,
            "index_schema_version": self.index_schema_version,
        }

    def scan_source_files(self) -> list[dict[str, str]]:
        """Return source fingerprints without reading source contents into output."""

        files: list[dict[str, str]] = []
        patterns = (("slide", "slides", "*.pdf"), ("transcript", "transcript", "transcript-*-clean.md"))
        for source_type, directory_name, pattern in patterns:
            directory = self.data_root / directory_name
            if not directory.exists():
                continue
            for path in sorted(directory.glob(pattern)):
                if not path.is_file():
                    continue
                try:
                    relative_path = path.relative_to(self.data_root).as_posix()
                    digest = self._sha256(path)
                except (OSError, ValueError):
                    continue
                files.append(
                    {
                        "relative_path": relative_path,
                        "sha256": digest,
                        "source_type": source_type,
                    }
                )
        return files

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    @property
    def manifest_path(self) -> Path:
        return self.index_dir / MANIFEST_FILE

    @property
    def vectors_path(self) -> Path:
        return self.index_dir / VECTOR_FILE

    @property
    def mapping_path(self) -> Path:
        return self.index_dir / MAPPING_FILE

    def _read_json(self, path: Path) -> dict[str, Any] | list[Any] | None:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return None
        return value

    def _read_manifest(self) -> dict[str, Any] | None:
        value = self._read_json(self.manifest_path)
        return value if isinstance(value, dict) else None

    @staticmethod
    def _file_map(files: list[dict[str, str]]) -> dict[str, tuple[str, str]]:
        return {
            item.get("relative_path", ""): (item.get("sha256", ""), item.get("source_type", ""))
            for item in files
            if item.get("relative_path")
        }

    def inspect(self) -> dict[str, Any]:
        """Inspect disk state; this does not build or load an index."""

        current_files = self.scan_source_files()
        manifest = self._read_manifest() if self.path_valid else None
        artifacts_present = bool(
            self.path_valid
            and self.manifest_path.is_file()
            and self.vectors_path.is_file()
            and self.mapping_path.is_file()
        )
        manifest_files = manifest.get("source_files", []) if manifest else []
        if not isinstance(manifest_files, list):
            manifest_files = []
        current_map = self._file_map(current_files)
        manifest_map = self._file_map([item for item in manifest_files if isinstance(item, dict)])
        changed_paths = set(current_map) ^ set(manifest_map)
        changed_paths.update(path for path in set(current_map) & set(manifest_map) if current_map[path] != manifest_map[path])
        config_matches = bool(manifest and manifest.get("config") == self._config())
        manifest_shape_ok = bool(
            manifest
            and isinstance(manifest.get("document_count"), int)
            and manifest.get("vector_file") == VECTOR_FILE
            and manifest.get("mapping_file") == MAPPING_FILE
        )
        ready = bool(artifacts_present and manifest_shape_ok)
        stale = not (ready and not changed_paths and config_matches)
        return {
            "index_ready": ready,
            "index_stale": stale,
            "changed_files_detected": len(changed_paths),
            "configuration_changed": not config_matches,
            "last_indexed_at": manifest.get("built_at") if manifest else None,
            "manifest": manifest,
            "current_files": current_files,
            "artifacts_present": artifacts_present,
        }

    def public_status(self) -> dict[str, Any]:
        """Return metadata safe for CLI/health output."""

        inspected = self.inspect()
        status = self._base_status()
        status.update(
            {
                "index_ready": inspected["index_ready"],
                "index_stale": inspected["index_stale"],
                "changed_files_detected": inspected["changed_files_detected"],
                "documents_loaded": (
                    inspected["manifest"].get("document_count", 0)
                    if isinstance(inspected.get("manifest"), dict)
                    else 0
                ),
                "last_indexed_at": inspected["last_indexed_at"],
            }
        )
        return status

    @staticmethod
    def _document_id(document: dict[str, Any], document_id_fn: Callable[[dict[str, Any]], str]) -> str:
        value = document_id_fn(document)
        if not value or any(character in value for character in "\r\n"):
            raise ValueError("invalid document id")
        return str(value)

    def _mapping_for(
        self,
        documents: list[dict[str, Any]],
        document_id_fn: Callable[[dict[str, Any]], str],
    ) -> list[dict[str, Any]]:
        mapping: list[dict[str, Any]] = []
        for document in documents:
            relative_path = str(document.get("relative_file_path", "")).replace("\\", "/")
            if (
                not relative_path
                or Path(relative_path).is_absolute()
                or relative_path.startswith("../")
                or ".." in Path(relative_path).parts
            ):
                raise ValueError("document mapping must use a relative data path")
            source_type = str(document.get("source_type", document.get("type", "")))
            if source_type not in {"slide", "transcript"}:
                raise ValueError("unsupported source type in mapping")
            item: dict[str, Any] = {
                "document_id": self._document_id(document, document_id_fn),
                "relative_file_path": relative_path,
                "source_type": source_type,
                "source_id": str(document.get("source_id", "")),
            }
            if document.get("page") is not None:
                item["page"] = int(document["page"])
            mapping.append(item)
        return mapping

    @staticmethod
    def _assert_clean_payload(value: Any, *, allowed_keys: set[str] | None = None) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key.lower() in RAW_METADATA_KEYS:
                    raise ValueError("raw source metadata is not allowed in persistent index")
                if allowed_keys is not None and key not in allowed_keys:
                    raise ValueError(f"unsupported persistent index field: {key}")
                RagIndexManager._assert_clean_payload(child)
        elif isinstance(value, list):
            for child in value:
                RagIndexManager._assert_clean_payload(child)

    def _manifest_for(self, source_files: list[dict[str, str]], document_count: int, built_at: str) -> dict[str, Any]:
        return {
            "index_schema_version": self.index_schema_version,
            "config": self._config(),
            "embedding_model": self.embedding_model,
            "chunking_version": self.chunking_version,
            "normalization_version": self.normalization_version,
            "source_root": self.data_root.name,
            "source_files": source_files,
            "document_count": document_count,
            "built_at": built_at,
            "vector_file": VECTOR_FILE,
            "mapping_file": MAPPING_FILE,
        }

    @staticmethod
    def _write_json(path: Path, value: Any) -> None:
        path.write_text(
            json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False),
            encoding="utf-8",
        )

    def _install_directory(self, temporary_dir: Path) -> None:
        """Install a prepared directory while retaining the old one on failure."""

        target = self.index_dir
        backup = self.data_parent / f".rag-index.backup-{uuid.uuid4().hex}"
        moved_old = False
        try:
            if target.exists():
                os.replace(target, backup)
                moved_old = True
            os.replace(temporary_dir, target)
        except Exception:
            if moved_old and not target.exists() and backup.exists():
                os.replace(backup, target)
            raise
        finally:
            if temporary_dir.exists():
                shutil.rmtree(temporary_dir, ignore_errors=True)
        if backup.exists():
            shutil.rmtree(backup, ignore_errors=True)

    def _persist(
        self,
        *,
        index: Any,
        documents: list[dict[str, Any]],
        source_files: list[dict[str, str]],
        serialize_index: Callable[[Any], dict[str, Any]],
        document_id_fn: Callable[[dict[str, Any]], str],
        extra_files: dict[str, Any] | None = None,
    ) -> str:
        if not self.path_valid:
            raise OSError(self.path_error or "invalid index path")

        vectors = serialize_index(index)
        if not isinstance(vectors, dict):
            raise ValueError("serialized vector index must be an object")
        self._assert_clean_payload(
            vectors,
            allowed_keys={
                "format_version",
                "idf",
                "vectors",
                "dense_model",
                "dense_dimensions",
                "dense_vectors",
            },
        )
        mapping = self._mapping_for(documents, document_id_fn)
        self._assert_clean_payload(
            mapping,
            allowed_keys={"document_id", "relative_file_path", "source_type", "source_id", "page"},
        )
        built_at = utc_now()
        manifest = self._manifest_for(source_files, len(documents), built_at)
        self._assert_clean_payload(manifest)

        temporary_dir = self.data_parent / f".rag-index.tmp-{uuid.uuid4().hex}"
        temporary_dir.mkdir(parents=False, exist_ok=False)
        try:
            self._write_json(temporary_dir / VECTOR_FILE, vectors)
            self._write_json(temporary_dir / MAPPING_FILE, mapping)
            self._write_json(temporary_dir / MANIFEST_FILE, manifest)
            for filename, value in (extra_files or {}).items():
                if not filename or Path(filename).name != filename or filename in {VECTOR_FILE, MAPPING_FILE, MANIFEST_FILE}:
                    raise ValueError("invalid persistent index extra file")
                self._assert_clean_payload(value)
                self._write_json(temporary_dir / filename, value)
            self._install_directory(temporary_dir)
        except Exception:
            if temporary_dir.exists():
                shutil.rmtree(temporary_dir, ignore_errors=True)
            raise
        return built_at

    def _load_persisted(
        self,
        *,
        documents: list[dict[str, Any]],
        deserialize_index: Callable[[list[dict[str, Any]], dict[str, Any]], Any],
        document_id_fn: Callable[[dict[str, Any]], str],
    ) -> Any:
        vectors = self._read_json(self.vectors_path)
        mapping = self._read_json(self.mapping_path)
        if not isinstance(vectors, dict) or not isinstance(mapping, list):
            raise ValueError("invalid persistent index files")
        expected_ids = [self._document_id(document, document_id_fn) for document in documents]
        stored_ids = [item.get("document_id") for item in mapping if isinstance(item, dict)]
        if stored_ids != expected_ids:
            raise ValueError("persistent index document mapping does not match current data")
        return deserialize_index(documents, vectors)

    def load_or_build(
        self,
        *,
        documents: list[dict[str, Any]],
        build_index: Callable[[list[dict[str, Any]]], Any],
        serialize_index: Callable[[Any], dict[str, Any]],
        deserialize_index: Callable[[list[dict[str, Any]], dict[str, Any]], Any],
        document_id_fn: Callable[[dict[str, Any]], str],
        force_rebuild: bool = False,
        extra_files: dict[str, Any] | None = None,
    ) -> tuple[Any, dict[str, Any]]:
        """Load unchanged index or build once for this process startup."""

        with self._build_lock:
            inspected = self.inspect()
            base = self._base_status()
            base.update(
                {
                    "documents_loaded": len(documents),
                    "index_stale": inspected["index_stale"],
                    "changed_files_detected": inspected["changed_files_detected"],
                    "last_indexed_at": inspected["last_indexed_at"],
                }
            )

            can_use_disk = (
                self.requested_mode == "persistent"
                and self.path_valid
                and inspected["index_ready"]
                and not inspected["index_stale"]
                and not force_rebuild
            )
            if can_use_disk:
                try:
                    index = self._load_persisted(
                        documents=documents,
                        deserialize_index=deserialize_index,
                        document_id_fn=document_id_fn,
                    )
                    base.update({"index_mode": "persistent", "index_ready": True, "index_stale": False})
                    self.runtime_status = base
                    return index, base
                except Exception:
                    base.update({"index_stale": True, "degraded": True, "fallback_reason": "persistent_index_load_failed"})

            if self.requested_mode == "persistent" and not self.auto_refresh and inspected["index_stale"] and not force_rebuild:
                try:
                    index = build_index(documents)
                except Exception as error:
                    base.update(
                        {
                            "index_mode": "memory",
                            "index_ready": False,
                            "index_stale": True,
                            "degraded": True,
                            "fallback_reason": f"memory_build_failed:{type(error).__name__}",
                        }
                    )
                    self.runtime_status = base
                    return NullVectorIndex(len(documents)), base
                base.update(
                    {
                        "index_mode": "memory",
                        "index_ready": True,
                        "index_stale": True,
                        "degraded": True,
                        "fallback_reason": "auto_refresh_disabled",
                    }
                )
                self.runtime_status = base
                return index, base

            try:
                index = build_index(documents)
            except Exception as error:
                try:
                    index = self._load_persisted(
                        documents=documents,
                        deserialize_index=deserialize_index,
                        document_id_fn=document_id_fn,
                    )
                    base.update(
                        {
                            "index_mode": "persistent",
                            "index_ready": True,
                            "index_stale": True,
                            "degraded": True,
                            "fallback_reason": f"rebuild_failed:{type(error).__name__}",
                        }
                    )
                    self.runtime_status = base
                    return index, base
                except Exception:
                    base.update(
                        {
                            "index_mode": "memory",
                            "index_ready": False,
                            "index_stale": True,
                            "degraded": True,
                            "fallback_reason": f"rebuild_failed:{type(error).__name__}",
                        }
                    )
                    self.runtime_status = base
                    return NullVectorIndex(len(documents)), base

            if self.requested_mode != "persistent" or not self.path_valid:
                base.update(
                    {
                        "index_mode": "memory",
                        "index_ready": True,
                        "index_stale": False,
                    }
                )
                self.runtime_status = base
                return index, base

            try:
                built_at = self._persist(
                    index=index,
                    documents=documents,
                    source_files=inspected["current_files"],
                    serialize_index=serialize_index,
                    document_id_fn=document_id_fn,
                    extra_files=extra_files,
                )
                base.update(
                    {
                        "index_mode": "persistent",
                        "index_ready": True,
                        "index_stale": False,
                        "changed_files_detected": 0,
                        "last_indexed_at": built_at,
                    }
                )
            except Exception as error:
                base.update(
                    {
                        "index_mode": "memory",
                        "index_ready": True,
                        "degraded": True,
                        "fallback_reason": f"persistent_write_failed:{type(error).__name__}",
                    }
                )
            self.runtime_status = base
            return index, base
