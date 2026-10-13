import numpy as np

from app.config import get_settings
from app.services import vector_store


def _embed(text: str) -> list[float]:
    vec = np.zeros(4, dtype="float32")
    for i, kw in enumerate(["revenue", "risk", "policy", "invoice"]):
        if kw in text.lower():
            vec[i] = 1.0
    if not vec.any():
        vec[0] = 0.01
    return vec.tolist()


def test_persist_leaves_no_temp_files_and_reloads():
    sections = [
        {
            "document_id": "d1",
            "document_name": "annual_report.pdf",
            "page_number": 2,
            "section_title": "Revenue",
            "content": "Total revenue was 500 million dollars.",
            "content_type": "text",
            "score": 0.8,
        }
    ]
    vector_store.add_sections(sections, [_embed(s["content"]) for s in sections])

    index_dir = get_settings().index_path
    leftovers = list(index_dir.glob("*.tmp"))
    assert leftovers == [], f"atomic persist must not leave temp files: {leftovers}"
    assert (index_dir / "sections.faiss").is_file()
    assert (index_dir / "sections_meta.json").is_file()

    # Force a cold reload from disk and confirm the section is retrievable.
    vector_store._index = None
    vector_store._meta = None
    vector_store._dimension = None
    results = vector_store.search(_embed("revenue"), k=3)
    assert results
    assert results[0][0]["document_name"] == "annual_report.pdf"
