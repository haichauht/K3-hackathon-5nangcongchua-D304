from __future__ import annotations

import json
from pathlib import Path

from backend.rag.index_manager import RagIndexManager


class FakeIndex:
    def __init__(self, documents: list[dict]) -> None:
        self.document_ids = [item["document_id"] for item in documents]

    def search(self, query: str) -> list[float]:
        del query
        return [0.0] * len(self.document_ids)


def make_document(document_id: str, relative_path: str, source_type: str, source_id: str) -> dict:
    return {
        "document_id": document_id,
        "relative_file_path": relative_path,
        "source_type": source_type,
        "source_id": source_id,
        "page": 1 if source_type == "slide" else None,
    }


def adapter():
    calls = {"build": 0}

    def build(documents: list[dict]) -> FakeIndex:
        calls["build"] += 1
        return FakeIndex(documents)

    def serialize(index: FakeIndex) -> dict:
        return {
            "format_version": 1,
            "idf": {"w:demo": 1.0},
            "vectors": [{f"w:{item}": 1.0} for item in index.document_ids],
        }

    def deserialize(documents: list[dict], payload: dict) -> FakeIndex:
        assert payload["format_version"] == 1
        return FakeIndex(documents)

    return calls, build, serialize, deserialize


def manager_for(tmp_path: Path, *, embedding_model: str = "test-model") -> RagIndexManager:
    data_root = tmp_path / "data" / "vlearn-pack"
    (data_root / "slides").mkdir(parents=True, exist_ok=True)
    (data_root / "transcript").mkdir(parents=True, exist_ok=True)
    return RagIndexManager(
        data_root=data_root,
        index_dir=data_root.parent / ".rag-index",
        mode="persistent",
        auto_refresh=True,
        embedding_model=embedding_model,
    )


def test_first_build_and_restart_load_without_rebuild(tmp_path: Path) -> None:
    manager = manager_for(tmp_path)
    data_root = tmp_path / "data" / "vlearn-pack"
    (data_root / "slides" / "deck.pdf").write_bytes(b"slide source")
    (data_root / "transcript" / "transcript-01-clean.md").write_text("transcript source", encoding="utf-8")
    documents = [
        make_document("slide:deck.pdf#page=1", "slides/deck.pdf", "slide", "deck.pdf#page=1"),
        make_document("transcript:[T01-001]", "transcript/transcript-01-clean.md", "transcript", "[T01-001]"),
    ]
    calls, build, serialize, deserialize = adapter()

    _, first_status = manager.load_or_build(
        documents=documents,
        build_index=build,
        serialize_index=serialize,
        deserialize_index=deserialize,
        document_id_fn=lambda item: item["document_id"],
        extra_files={
            "vision_cache.json": {
                "schema_version": "slide-vision-cache-v1",
                "entries": {
                    "slides/deck.pdf#page=1": {
                        "pdf_relative_path": "slides/deck.pdf",
                        "page": 1,
                        "pdf_sha256": "hash",
                        "prompt_hash": "prompt",
                        "model": "gpt-5",
                        "status": "ok",
                        "result": {
                            "title": "Diagram",
                            "visual_summary": "A visible diagram",
                            "important_labels": [],
                            "relationships": [],
                            "uncertain_details": [],
                        },
                    }
                },
            }
        },
    )
    assert first_status["index_mode"] == "persistent"
    assert first_status["index_ready"] is True
    assert first_status["index_stale"] is False
    assert calls["build"] == 1

    index_dir = data_root.parent / ".rag-index"
    assert {path.name for path in index_dir.iterdir()} == {
        "manifest.json",
        "mapping.json",
        "vectors.json",
        "vision_cache.json",
    }
    manifest_text = (index_dir / "manifest.json").read_text(encoding="utf-8")
    mapping_text = (index_dir / "mapping.json").read_text(encoding="utf-8")
    vectors_text = (index_dir / "vectors.json").read_text(encoding="utf-8")
    vision_text = (index_dir / "vision_cache.json").read_text(encoding="utf-8")
    assert "transcript source" not in manifest_text + mapping_text + vectors_text + vision_text
    assert '"file_path"' not in manifest_text + mapping_text + vectors_text + vision_text

    restarted = manager_for(tmp_path)
    restart_calls, restart_build, _, restart_deserialize = adapter()
    _, restart_status = restarted.load_or_build(
        documents=documents,
        build_index=restart_build,
        serialize_index=serialize,
        deserialize_index=restart_deserialize,
        document_id_fn=lambda item: item["document_id"],
    )
    assert restart_status["index_mode"] == "persistent"
    assert restart_status["index_stale"] is False
    assert restart_calls["build"] == 0


def test_add_edit_delete_and_config_change_trigger_refresh(tmp_path: Path) -> None:
    manager = manager_for(tmp_path)
    data_root = tmp_path / "data" / "vlearn-pack"
    slide_path = data_root / "slides" / "deck.pdf"
    transcript_path = data_root / "transcript" / "transcript-01-clean.md"
    slide_path.write_bytes(b"slide source")
    transcript_path.write_text("transcript source", encoding="utf-8")
    base_docs = [
        make_document("slide:deck.pdf#page=1", "slides/deck.pdf", "slide", "deck.pdf#page=1"),
        make_document("transcript:[T01-001]", "transcript/transcript-01-clean.md", "transcript", "[T01-001]"),
    ]
    calls, build, serialize, deserialize = adapter()
    manager.load_or_build(
        documents=base_docs,
        build_index=build,
        serialize_index=serialize,
        deserialize_index=deserialize,
        document_id_fn=lambda item: item["document_id"],
    )

    new_path = data_root / "transcript" / "transcript-02-clean.md"
    new_path.write_text("new source", encoding="utf-8")
    changed_docs = base_docs + [
        make_document("transcript:[T02-001]", "transcript/transcript-02-clean.md", "transcript", "[T02-001]")
    ]
    assert manager.inspect()["index_stale"] is True
    assert manager.inspect()["changed_files_detected"] == 1
    manager.load_or_build(
        documents=changed_docs,
        build_index=build,
        serialize_index=serialize,
        deserialize_index=deserialize,
        document_id_fn=lambda item: item["document_id"],
    )
    assert calls["build"] == 2

    new_path.write_text("edited source", encoding="utf-8")
    assert manager.inspect()["index_stale"] is True
    assert manager.inspect()["changed_files_detected"] == 1

    new_path.unlink()
    assert manager.inspect()["index_stale"] is True
    assert manager.inspect()["changed_files_detected"] == 1

    changed_model = manager_for(tmp_path, embedding_model="changed-model")
    assert changed_model.inspect()["index_stale"] is True
    assert changed_model.inspect()["configuration_changed"] is True


def test_atomic_failure_keeps_previous_index_and_falls_back_to_memory(tmp_path: Path, monkeypatch) -> None:
    manager = manager_for(tmp_path)
    data_root = tmp_path / "data" / "vlearn-pack"
    (data_root / "slides" / "deck.pdf").write_bytes(b"slide source")
    documents = [make_document("slide:deck.pdf#page=1", "slides/deck.pdf", "slide", "deck.pdf#page=1")]
    calls, build, serialize, deserialize = adapter()
    manager.load_or_build(
        documents=documents,
        build_index=build,
        serialize_index=serialize,
        deserialize_index=deserialize,
        document_id_fn=lambda item: item["document_id"],
    )
    manifest_path = data_root.parent / ".rag-index" / "manifest.json"
    old_manifest = manifest_path.read_text(encoding="utf-8")

    def fail_install(temporary_dir: Path) -> None:
        raise OSError("simulated install failure")

    monkeypatch.setattr(manager, "_install_directory", fail_install)
    _, status = manager.load_or_build(
        documents=documents,
        build_index=build,
        serialize_index=serialize,
        deserialize_index=deserialize,
        document_id_fn=lambda item: item["document_id"],
        force_rebuild=True,
    )
    assert status["index_mode"] == "memory"
    assert status["index_ready"] is True
    assert status["degraded"] is True
    assert manifest_path.read_text(encoding="utf-8") == old_manifest
    assert calls["build"] == 2


def test_invalid_index_path_never_writes_outside_data_boundary(tmp_path: Path) -> None:
    data_root = tmp_path / "data" / "vlearn-pack"
    (data_root / "slides").mkdir(parents=True)
    manager = RagIndexManager(
        data_root=data_root,
        index_dir=tmp_path / "outside-index",
        mode="persistent",
        auto_refresh=True,
    )
    calls, build, serialize, deserialize = adapter()
    documents = [make_document("slide:deck.pdf#page=1", "slides/deck.pdf", "slide", "deck.pdf#page=1")]
    _, status = manager.load_or_build(
        documents=documents,
        build_index=build,
        serialize_index=serialize,
        deserialize_index=deserialize,
        document_id_fn=lambda item: item["document_id"],
    )
    assert status["index_mode"] == "memory"
    assert status["fallback_reason"] == "index_dir_outside_data_boundary"
    assert not (tmp_path / "outside-index").exists()
