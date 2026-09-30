"""Local FAISS vector index with a JSON metadata sidecar.

Vectors are L2-normalized so inner product equals cosine similarity.
"""

import json
import threading
from pathlib import Path

import faiss
import numpy as np

from ..config import get_settings
from ..core.logging_config import get_logger

logger = get_logger(__name__)

_lock = threading.RLock()
_index: faiss.Index | None = None
_meta: list[dict] | None = None
_dimension: int | None = None


def _paths() -> tuple[Path, Path]:
    index_dir = get_settings().index_path
    return index_dir / "sections.faiss", index_dir / "sections_meta.json"


def _ensure_loaded() -> None:
    global _index, _meta, _dimension
    if _index is not None:
        return
    index_file, meta_file = _paths()
    if index_file.exists() and meta_file.exists():
        _index = faiss.read_index(str(index_file))
        _meta = json.loads(meta_file.read_text(encoding="utf-8"))
        _dimension = _index.d
    else:
        _index, _meta, _dimension = None, [], None


def _init_index(dimension: int) -> None:
    global _index, _dimension
    _index = faiss.IndexFlatIP(dimension)
    _dimension = dimension


def _persist() -> None:
    index_file, meta_file = _paths()
    index_file.parent.mkdir(parents=True, exist_ok=True)
    faiss.write_index(_index, str(index_file))
    meta_file.write_text(json.dumps(_meta, ensure_ascii=False), encoding="utf-8")


def _normalize(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return vectors / norms


def add_sections(sections: list[dict], embeddings: list[list[float]]) -> None:
    if not sections:
        return
    with _lock:
        _ensure_loaded()
        vectors = _normalize(np.array(embeddings, dtype="float32"))
        if _index is None:
            _init_index(vectors.shape[1])
        elif vectors.shape[1] != _dimension:
            raise ValueError("Embedding dimension changed; rebuild the index.")
        _index.add(vectors)
        # Keep the embedding in metadata so the index can be rebuilt after deletions.
        for section, embedding in zip(sections, embeddings):
            _meta.append({**section, "embedding": embedding})
        _persist()


def search(
    query_embedding: list[float], k: int = 8, document_ids: list[str] | None = None
) -> list[tuple[dict, float]]:
    with _lock:
        _ensure_loaded()
        if _index is None or _index.ntotal == 0 or not _meta:
            return []
        vector = _normalize(np.array([query_embedding], dtype="float32"))
        # When scoping to specific documents we must scan the whole index, otherwise
        # the k*5 pre-filter can be filled entirely by other documents and starve the
        # scoped result set. Unscoped searches keep the cheaper k*5 candidate window.
        fetch = _index.ntotal if document_ids else min(_index.ntotal, max(k * 5, k))
        scores, ids = _index.search(vector, fetch)
        results: list[tuple[dict, float]] = []
        for score, idx in zip(scores[0], ids[0]):
            if idx < 0:
                continue
            section = {k: v for k, v in _meta[idx].items() if k != "embedding"}
            if document_ids and section["document_id"] not in document_ids:
                continue
            results.append((section, float(score)))
            if len(results) >= k:
                break
        return results


def remove_document(document_id: str) -> None:
    with _lock:
        _ensure_loaded()
        if not _meta:
            return
        kept = [s for s in _meta if s["document_id"] != document_id]
        if len(kept) == len(_meta):
            return
        _rebuild_from(kept)


def _rebuild_from(sections: list[dict]) -> None:
    """Rebuild the index from metadata (each section carries its stored embedding)."""
    global _index, _meta, _dimension
    index_file, meta_file = _paths()
    if not sections:
        _index, _meta, _dimension = None, [], None
        index_file.unlink(missing_ok=True)
        meta_file.unlink(missing_ok=True)
        return
    vectors = _normalize(np.array([s["embedding"] for s in sections], dtype="float32"))
    _init_index(vectors.shape[1])
    _index.add(vectors)
    _meta = sections
    _persist()


def clear() -> None:
    global _index, _meta, _dimension
    with _lock:
        _index, _meta, _dimension = None, [], None
        index_file, meta_file = _paths()
        index_file.unlink(missing_ok=True)
        meta_file.unlink(missing_ok=True)


def count() -> int:
    with _lock:
        _ensure_loaded()
        return _index.ntotal if _index is not None else 0
