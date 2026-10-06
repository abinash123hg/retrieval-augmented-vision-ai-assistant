#!/usr/bin/env python3
"""Lightweight evaluation harness for the DocuLens RAG pipeline.

It runs the REAL pipeline end to end (embed -> FAISS retrieve -> rerank ->
grounded answer -> verify -> cite) against the small sample corpus in
evaluation/documents/ and the questions in evaluation/questions.json.

Design notes:
- No new models or dependencies: it imports the existing backend services and
  uses the same Ollama models (nomic-embed-text + qwen2.5:3b).
- It runs against an ISOLATED data directory (evaluation/.evaldata) so it never
  touches the app's real uploads/index/registry.
- Ollama must be running (the same requirement as the app itself).

Metrics reported:
- Retrieval Recall@K   : did the expected document page appear in retrieved set
- Answer correctness   : keyword/number overlap vs the expected answer
- Citation/page accuracy: did the returned sources cite the expected page
- Refusal accuracy     : correct refusal on unanswerable questions
- Overall summary + per-category breakdown

Usage:
    backend/.venv/Scripts/python.exe evaluation/evaluate.py
"""

from __future__ import annotations

import csv
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths and data isolation. These env vars MUST be set before importing the
# backend config (pydantic-settings reads them and they override backend/.env).
# ---------------------------------------------------------------------------
EVAL_DIR = Path(__file__).resolve().parent
REPO_ROOT = EVAL_DIR.parent
BACKEND_DIR = REPO_ROOT / "backend"
EVAL_DATA = EVAL_DIR / ".evaldata"

DOCUMENTS_DIR = EVAL_DIR / "documents"
QUESTIONS_FILE = EVAL_DIR / "questions.json"
RESULTS_DIR = EVAL_DIR / "results"

for name, sub in (
    ("UPLOAD_DIR", "uploads"),
    ("PROCESSED_DIR", "processed"),
    ("INDEX_DIR", "indexes"),
    ("REPORT_DIR", "reports"),
):
    os.environ[name] = str(EVAL_DATA / sub)

sys.path.insert(0, str(BACKEND_DIR))

# Now it is safe to import backend modules.
from app.config import get_settings  # noqa: E402
from app.services import (  # noqa: E402
    answer_service,
    file_service,
    retrieval_service,
    verification_service,
)

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    """a an and are as at be by for from had has have how i in is it its of on or
    that the this to was were what when where which who why will with you your
    total was were did does do""".split()
)


def norm_tokens(text: str) -> set[str]:
    if not text:
        return set()
    return {t for t in _TOKEN_RE.findall(text.lower()) if len(t) > 1 and t not in _STOPWORDS}


def numeric_tokens(tokens: set[str]) -> set[str]:
    return {t for t in tokens if any(c.isdigit() for c in t)}


def answer_is_correct(expected: str, answer: str) -> bool:
    """Keyword-overlap correctness: expected content words largely present and
    every expected number reproduced exactly."""
    expected_tokens = norm_tokens(expected)
    answer_tokens = norm_tokens(answer)
    if not expected_tokens:
        return False
    overlap = len(expected_tokens & answer_tokens) / len(expected_tokens)
    exp_numbers = numeric_tokens(expected_tokens)
    numbers_ok = exp_numbers.issubset(answer_tokens)
    return overlap >= 0.5 and numbers_ok


def reset_eval_store() -> None:
    if EVAL_DATA.exists():
        shutil.rmtree(EVAL_DATA, ignore_errors=True)
    get_settings().ensure_dirs()


def index_documents() -> dict[str, str]:
    """Upload + process every file in documents/. Returns {basename: document_id}."""
    name_to_id: dict[str, str] = {}
    for path in sorted(DOCUMENTS_DIR.iterdir()):
        if path.suffix.lower() not in {".pdf", ".png", ".jpg", ".jpeg"}:
            continue
        document_id, _ = file_service.save_upload(path.name, path.read_bytes())
        file_service.process_document(document_id)
        record = file_service.get_document(document_id)
        name_to_id[path.name] = document_id
        print(
            f"  indexed {path.name:24s} id={document_id[:8]} "
            f"status={record.processing_status} pages={record.page_count}"
        )
    return name_to_id


def scope_for(question: dict, name_to_id: dict[str, str]) -> list[str]:
    if question.get("category") == "multi_document":
        return list(name_to_id.values())
    doc_id = name_to_id.get(question["document"])
    return [doc_id] if doc_id else []


def retrieval_hit(sections: list[dict], expected_doc_id: str, expected_page) -> tuple[bool, int]:
    """Return (hit, rank) — rank is 1-based position of the expected page, 0 if absent."""
    if expected_page is None:
        return False, 0
    for rank, sec in enumerate(sections, start=1):
        if sec.get("document_id") == expected_doc_id and sec.get("page_number") == expected_page:
            return True, rank
    return False, 0


def citation_hit(sources, expected_doc_name: str, expected_page) -> bool:
    if expected_page is None:
        return False
    stem = Path(expected_doc_name).stem.lower()
    for src in sources:
        if src.page_number == expected_page and stem in src.document_name.lower():
            return True
    return False


def main() -> int:
    print("=" * 68)
    print("DocuLens evaluation harness")
    print("=" * 68)

    questions = json.loads(QUESTIONS_FILE.read_text(encoding="utf-8"))
    settings = get_settings()
    top_k = settings.top_k_results

    print(f"\n[1/4] Preparing isolated data store at {EVAL_DATA}")
    reset_eval_store()

    print(f"\n[2/4] Indexing {DOCUMENTS_DIR} (Recall@K uses top_k={top_k})")
    t0 = time.time()
    name_to_id = index_documents()
    print(f"  done in {time.time() - t0:.1f}s — {len(name_to_id)} document(s)")
    if not name_to_id:
        print("No documents to index. Aborting.")
        return 1

    print(f"\n[3/4] Running {len(questions)} questions through the live pipeline")
    rows = []
    for q in questions:
        expected_doc_id = name_to_id.get(q["document"], "")
        scope = scope_for(q, name_to_id)

        sections = retrieval_service.retrieve(q["question"], document_ids=scope or None, top_k=top_k)
        hit, rank = retrieval_hit(sections, expected_doc_id, q.get("expected_page"))

        response = answer_service.answer_question(q["question"], document_ids=scope or None)
        answer = response.answer
        refused = verification_service.is_refusal(answer)

        if q["answerable"]:
            correct = (not refused) and answer_is_correct(q["expected_answer"], answer)
            refusal_correct = not refused
            cite_correct = citation_hit(response.sources, q["document"], q.get("expected_page"))
        else:
            correct = refused
            refusal_correct = refused
            cite_correct = None  # citations not applicable to unanswerable questions

        rows.append(
            {
                "id": q["id"],
                "category": q["category"],
                "document": q["document"],
                "question": q["question"],
                "expected_answer": q["expected_answer"] or "",
                "expected_page": q["expected_page"] if q["expected_page"] is not None else "",
                "answerable": q["answerable"],
                "retrieval_hit": hit if q["answerable"] else "",
                "retrieval_rank": rank if q["answerable"] else "",
                "model_answer": answer,
                "refused": refused,
                "answer_correct": correct,
                "refusal_correct": refusal_correct,
                "citation_correct": "" if cite_correct is None else cite_correct,
                "cited_pages": ";".join(str(s.page_number) for s in response.sources),
                "evidence_status": response.evidence_status,
            }
        )
        flag = "OK " if correct else "MISS"
        print(f"  [{flag}] Q{q['id']:<2d} ({q['category']:14s}) hit={hit} refused={refused}")

    # ------------------------- aggregate metrics -------------------------
    answerable = [r for r in rows if r["answerable"]]
    unanswerable = [r for r in rows if not r["answerable"]]
    page_known = [r for r in answerable if r["expected_page"] != ""]

    def rate(items, key):
        vals = [r for r in items if isinstance(r[key], bool)]
        return (sum(1 for r in vals if r[key]) / len(vals)) if vals else 0.0

    retrieval_recall = rate(page_known, "retrieval_hit")
    answer_accuracy = rate(rows, "answer_correct")
    citation_accuracy = rate(page_known, "citation_correct")
    refusal_accuracy = rate(unanswerable, "refusal_correct")

    per_category = {}
    for r in rows:
        cat = per_category.setdefault(r["category"], {"total": 0, "answer_correct": 0})
        cat["total"] += 1
        cat["answer_correct"] += int(bool(r["answer_correct"]))

    summary = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "chat_model": settings.ollama_chat_model,
        "embedding_model": settings.ollama_embed_model,
        "num_questions": len(rows),
        "num_answerable": len(answerable),
        "num_unanswerable": len(unanswerable),
        "top_k": top_k,
        "documents": sorted(name_to_id),
        "metrics": {
            "retrieval_recall_at_k": round(retrieval_recall, 4),
            "answer_accuracy": round(answer_accuracy, 4),
            "citation_page_accuracy": round(citation_accuracy, 4),
            "refusal_accuracy": round(refusal_accuracy, 4),
        },
        "per_category": {
            c: {
                "total": v["total"],
                "answer_correct": v["answer_correct"],
                "accuracy": round(v["answer_correct"] / v["total"], 4) if v["total"] else 0.0,
            }
            for c, v in per_category.items()
        },
    }

    print(f"\n[4/4] Writing results to {RESULTS_DIR}")
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = RESULTS_DIR / "evaluation_results.csv"
    json_path = RESULTS_DIR / "evaluation_results.json"

    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    json_path.write_text(
        json.dumps({"summary": summary, "questions": rows}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("\n" + "=" * 68)
    print("SUMMARY")
    print("=" * 68)
    print(f"  Chat model            : {summary['chat_model']}")
    print(f"  Embedding model       : {summary['embedding_model']}")
    m = summary["metrics"]
    print(f"  Retrieval Recall@{top_k}    : {m['retrieval_recall_at_k'] * 100:5.1f}%")
    print(f"  Answer accuracy       : {m['answer_accuracy'] * 100:5.1f}%")
    print(f"  Citation/page accuracy: {m['citation_page_accuracy'] * 100:5.1f}%")
    print(f"  Refusal accuracy      : {m['refusal_accuracy'] * 100:5.1f}%")
    print("\n  Per-category answer accuracy:")
    for cat, v in summary["per_category"].items():
        print(f"    {cat:16s} {v['answer_correct']}/{v['total']}  ({v['accuracy'] * 100:.0f}%)")
    print("\n  Note: results depend on OCR quality and the small local model;")
    print("        they are a realistic snapshot, not a guaranteed benchmark.")
    print("=" * 68)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # surface a clear message (e.g. Ollama not running)
        print(f"\nEvaluation failed: {exc}")
        print("Is Ollama running with nomic-embed-text and qwen2.5:3b pulled?")
        raise SystemExit(1)
