#!/usr/bin/env python3
"""Honest evaluation harness for the DocuLens RAG pipeline.

It runs the REAL pipeline end to end (embed -> FAISS retrieve -> rerank ->
grounded answer -> verify -> cite) against the corpus in evaluation/documents/
and the questions in evaluation/questions.json.

Design notes:
- No new models or dependencies: it imports the existing backend services and
  uses the same Ollama models (nomic-embed-text + qwen2.5:3b).
- It runs against an ISOLATED data directory (evaluation/.evaldata) so it never
  touches the app's real uploads/index/registry.
- Ollama must be running (the same requirement as the app itself).
- The pure scoring functions below have NO backend/Ollama dependency, so they can
  be unit-tested offline (see evaluation/test_scoring.py). Importing this module
  does not touch the environment or import the backend; that happens in main().

Modes:
    (default)  every question is searched only inside its own document (scoped)
    --unscoped every question is searched across ALL indexed documents

Metrics (each printed as correct/total next to the percentage):
- Retrieval Recall@K      : expected page present in the retrieved set (answerable,
                            known page)
- Answer accuracy         : strict correctness over ANSWERABLE questions only
- Citation/page accuracy  : returned sources cite the expected page (answerable,
                            known page)
- Refusal accuracy        : correct refusal over UNANSWERABLE questions
- False-refusal rate      : answerable questions that were wrongly refused
- Median per-question latency

Correctness is strict: every expected number must appear (comma-insensitive),
at least 80% of expected content words must appear, any per-question `forbidden`
string makes the answer wrong, and an answer that still leaks source-listing
lines or "Evidence Block" text is flagged wrong.

Results are written to evaluation/results/<timestamp>-<mode>/ and never overwrite
a previous run.

Usage:
    backend/.venv/Scripts/python.exe evaluation/evaluate.py
    backend/.venv/Scripts/python.exe evaluation/evaluate.py --unscoped
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import time
from pathlib import Path
from statistics import median

# ---------------------------------------------------------------------------
# Paths (no side effects at import time).
# ---------------------------------------------------------------------------
EVAL_DIR = Path(__file__).resolve().parent
REPO_ROOT = EVAL_DIR.parent
BACKEND_DIR = REPO_ROOT / "backend"
EVAL_DATA = EVAL_DIR / ".evaldata"

DOCUMENTS_DIR = EVAL_DIR / "documents"
QUESTIONS_FILE = EVAL_DIR / "questions.json"
RESULTS_DIR = EVAL_DIR / "results"

# ---------------------------------------------------------------------------
# Pure scoring helpers (stdlib only — unit-testable without Ollama).
# ---------------------------------------------------------------------------
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?%?")
_STOPWORDS = frozenset(
    """a an and are as at be by for from had has have how i in is it its of on or
    that the this to was were what when where which who why will with you your
    did does do total""".split()
)

# At least this fraction of the expected content words must appear in the answer.
CONTENT_WORD_THRESHOLD = 0.8

# An answer that still shows internal scaffolding is treated as wrong.
_LEAK_RE = re.compile(
    r"evidence\s+block|\[\s*source\s*\d+\s*\]|sources used for this answer", re.IGNORECASE
)
_CITATION_LINE_RE = re.compile(r"^\s*[*•\-]\s+.*\bpage\s*\d+\b", re.IGNORECASE)


def normalize_number(token: str) -> str:
    return token.replace(",", "")


def numbers_in(text: str) -> set[str]:
    """Numeric claims in a string, comma-normalized (e.g. '8,450' -> '8450')."""
    return {normalize_number(m) for m in _NUMBER_RE.findall(text or "")}


def content_words(text: str) -> set[str]:
    """Lowercased content tokens for the word-overlap check.

    Stopwords, single characters and pure-number tokens are removed: numbers are
    verified exactly and separately by ``numbers_in`` (and comma formatting like
    '8,450' tokenizes differently from '8450'), so they must not also drive the
    word-overlap ratio.
    """
    if not text:
        return set()
    return {
        t
        for t in _TOKEN_RE.findall(text.lower())
        if len(t) > 1 and t not in _STOPWORDS and not t.isdigit()
    }


def has_source_leak(answer: str) -> bool:
    """True if the answer still contains source-listing lines or 'Evidence Block' text."""
    if not answer:
        return False
    if _LEAK_RE.search(answer):
        return True
    return any(_CITATION_LINE_RE.match(line) for line in answer.splitlines())


def answer_is_correct(
    expected: str, answer: str, forbidden: list[str] | None = None
) -> tuple[bool, list[str], float]:
    """Strict grounded-answer correctness.

    Returns (correct, reasons, content_word_overlap). ``reasons`` is empty when
    the answer is correct; otherwise it lists every rule the answer broke.
    """
    reasons: list[str] = []

    expected_numbers = numbers_in(expected)
    answer_numbers = numbers_in(answer)
    missing_numbers = sorted(expected_numbers - answer_numbers)
    if missing_numbers:
        reasons.append("missing expected number(s): " + ", ".join(missing_numbers))

    expected_words = content_words(expected)
    answer_words = content_words(answer)
    overlap = (len(expected_words & answer_words) / len(expected_words)) if expected_words else 1.0
    if expected_words and overlap < CONTENT_WORD_THRESHOLD:
        reasons.append(
            f"content-word overlap {overlap:.0%} < {CONTENT_WORD_THRESHOLD:.0%}"
        )

    for bad in forbidden or []:
        if bad and bad.lower() in (answer or "").lower():
            reasons.append(f"contains forbidden string {bad!r}")

    return (not reasons), reasons, overlap


def retrieval_hit(sections: list[dict], expected_doc_id: str, expected_page) -> tuple[bool, int]:
    """Return (hit, rank); rank is the 1-based position of the expected page, 0 if absent."""
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


def scope_for(question: dict, name_to_id: dict[str, str], unscoped: bool = False):
    """Document ids to search for a question, or None to search everything."""
    if unscoped:
        return None
    if question.get("category") == "multi_document":
        return list(name_to_id.values())
    doc_id = name_to_id.get(question["document"])
    return [doc_id] if doc_id else []


def frac(numerator: int, denominator: int) -> float:
    return (numerator / denominator) if denominator else 0.0


def metric(correct: int, total: int) -> dict:
    return {"correct": correct, "total": total, "rate": round(frac(correct, total), 4)}


# ---------------------------------------------------------------------------
# Pipeline (backend-dependent) — imported lazily inside main().
# ---------------------------------------------------------------------------
def reset_eval_store(get_settings) -> None:
    import shutil

    if EVAL_DATA.exists():
        shutil.rmtree(EVAL_DATA, ignore_errors=True)
    get_settings().ensure_dirs()


def index_documents(file_service) -> dict[str, str]:
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
            f"  indexed {path.name:28s} id={document_id[:8]} "
            f"status={record.processing_status} pages={record.page_count}"
        )
    return name_to_id


def unique_results_dir(mode: str) -> Path:
    """results/<timestamp>-<mode>/, never colliding with an existing run."""
    stamp = time.strftime("%Y%m%d-%H%M%S")
    candidate = RESULTS_DIR / f"{stamp}-{mode}"
    n = 1
    while candidate.exists():
        candidate = RESULTS_DIR / f"{stamp}-{mode}-{n}"
        n += 1
    candidate.mkdir(parents=True, exist_ok=True)
    return candidate


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="DocuLens evaluation harness")
    parser.add_argument(
        "--unscoped",
        action="store_true",
        help="search every indexed document for every question (default: scope to the "
        "question's own document)",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    mode = "unscoped" if args.unscoped else "scoped"

    # Isolate the data store BEFORE importing the backend config, which reads these
    # env vars once at import time.
    import os

    for name, sub in (
        ("UPLOAD_DIR", "uploads"),
        ("PROCESSED_DIR", "processed"),
        ("INDEX_DIR", "indexes"),
        ("REPORT_DIR", "reports"),
    ):
        os.environ[name] = str(EVAL_DATA / sub)

    import sys

    sys.path.insert(0, str(BACKEND_DIR))
    from app.config import get_settings  # noqa: E402
    from app.services import (  # noqa: E402
        answer_service,
        file_service,
        retrieval_service,
        verification_service,
    )

    print("=" * 72)
    print(f"DocuLens evaluation harness — mode: {mode.upper()}")
    print("=" * 72)

    questions = json.loads(QUESTIONS_FILE.read_text(encoding="utf-8"))
    settings = get_settings()
    top_k = settings.top_k_results

    print(f"\n[1/4] Preparing isolated data store at {EVAL_DATA}")
    reset_eval_store(get_settings)

    print(f"\n[2/4] Indexing {DOCUMENTS_DIR} (Recall@K uses top_k={top_k})")
    t0 = time.time()
    name_to_id = index_documents(file_service)
    print(f"  done in {time.time() - t0:.1f}s — {len(name_to_id)} document(s)")
    if not name_to_id:
        print("No documents to index. Aborting.")
        return 1

    missing_docs = sorted({q["document"] for q in questions} - set(name_to_id))
    if missing_docs and not args.unscoped:
        print(f"  WARNING: question(s) reference un-indexed document(s): {missing_docs}")

    print(f"\n[3/4] Running {len(questions)} questions through the live pipeline")
    rows: list[dict] = []
    latencies: list[float] = []
    for q in questions:
        expected_doc_id = name_to_id.get(q["document"], "")
        scope = scope_for(q, name_to_id, unscoped=args.unscoped)
        expected_page = q.get("expected_page")
        answerable = bool(q["answerable"])

        sections = retrieval_service.retrieve(
            q["question"], document_ids=scope or None, top_k=top_k
        )
        hit, rank = retrieval_hit(sections, expected_doc_id, expected_page)

        start = time.time()
        response = answer_service.answer_question(q["question"], document_ids=scope or None)
        latency = time.time() - start
        latencies.append(latency)

        answer = response.answer
        refused = verification_service.is_refusal(answer)
        leak = has_source_leak(answer)
        reasons: list[str] = []

        if answerable:
            if refused:
                correct = False
                reasons.append("model refused an answerable question (false refusal)")
            else:
                correct, reasons, _ = answer_is_correct(
                    q["expected_answer"], answer, q.get("forbidden")
                )
                if leak:
                    correct = False
                    reasons.append("answer leaks source-listing / 'Evidence Block' text")
            cite = citation_hit(response.sources, q["document"], expected_page)
            row_correct = correct
            refusal_correct = not refused
            citation_correct = cite
        else:
            refusal_correct = refused
            if not refused:
                reasons.append("answered an unanswerable question (should have refused)")
            row_correct = refused
            citation_correct = None

        rows.append(
            {
                "id": q["id"],
                "category": q["category"],
                "document": q["document"],
                "question": q["question"],
                "expected_answer": q["expected_answer"] or "",
                "expected_page": expected_page if expected_page is not None else "",
                "answerable": answerable,
                "retrieval_hit": hit if answerable else "",
                "retrieval_rank": rank if answerable else "",
                "model_answer": answer,
                "refused": refused,
                "source_leak": leak,
                "answer_correct": row_correct if answerable else "",
                "refusal_correct": refusal_correct,
                "citation_correct": "" if citation_correct is None else citation_correct,
                "cited_pages": ";".join(str(s.page_number) for s in response.sources),
                "evidence_status": response.evidence_status,
                "latency_s": round(latency, 3),
                "failure_reasons": " | ".join(reasons),
            }
        )
        flag = "OK " if row_correct else "MISS"
        print(
            f"  [{flag}] Q{q['id']:<3d} ({q['category']:15s}) hit={hit} "
            f"refused={refused} {latency:.2f}s"
            + (f"  <- {'; '.join(reasons)}" if reasons else "")
        )

    # ------------------------- aggregate metrics -------------------------
    answerable_rows = [r for r in rows if r["answerable"]]
    unanswerable_rows = [r for r in rows if not r["answerable"]]
    page_known = [r for r in answerable_rows if r["expected_page"] != ""]

    retrieval_correct = sum(1 for r in page_known if r["retrieval_hit"] is True)
    answer_correct = sum(1 for r in answerable_rows if r["answer_correct"] is True)
    citation_correct = sum(1 for r in page_known if r["citation_correct"] is True)
    refusal_correct = sum(1 for r in unanswerable_rows if r["refusal_correct"] is True)
    false_refusals = sum(1 for r in answerable_rows if r["refused"])

    metrics = {
        "retrieval_recall_at_k": metric(retrieval_correct, len(page_known)),
        "answer_accuracy": metric(answer_correct, len(answerable_rows)),
        "citation_page_accuracy": metric(citation_correct, len(page_known)),
        "refusal_accuracy": metric(refusal_correct, len(unanswerable_rows)),
        "false_refusal_rate": metric(false_refusals, len(answerable_rows)),
    }

    per_category: dict[str, dict] = {}
    for r in answerable_rows:
        cat = per_category.setdefault(r["category"], {"total": 0, "correct": 0})
        cat["total"] += 1
        cat["correct"] += int(r["answer_correct"] is True)

    median_latency = round(median(latencies), 3) if latencies else 0.0
    too_few = len(rows) < 30

    summary = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "mode": mode,
        "chat_model": settings.ollama_chat_model,
        "embedding_model": settings.ollama_embed_model,
        "top_k": top_k,
        "num_questions": len(rows),
        "num_answerable": len(answerable_rows),
        "num_unanswerable": len(unanswerable_rows),
        "documents": sorted(name_to_id),
        "median_latency_s": median_latency,
        "too_few_questions": too_few,
        "metrics": metrics,
        "per_category": {
            c: {**v, "accuracy": round(frac(v["correct"], v["total"]), 4)}
            for c, v in per_category.items()
        },
    }

    # ----------------------------- report --------------------------------
    def pct(m: dict) -> str:
        return f"{m['correct']}/{m['total']}  ({m['rate'] * 100:5.1f}%)"

    lines: list[str] = []
    lines.append("=" * 72)
    lines.append(f"SUMMARY — mode: {mode.upper()}")
    lines.append("=" * 72)
    lines.append(f"  Chat model              : {summary['chat_model']}")
    lines.append(f"  Embedding model         : {summary['embedding_model']}")
    lines.append(f"  Questions               : {len(rows)} "
                 f"({len(answerable_rows)} answerable, {len(unanswerable_rows)} unanswerable)")
    lines.append(f"  Documents indexed       : {len(name_to_id)}")
    lines.append(f"  Median per-question latency : {median_latency:.3f}s")
    lines.append("-" * 72)
    lines.append(f"  Retrieval Recall@{top_k}      : {pct(metrics['retrieval_recall_at_k'])}")
    lines.append(f"  Answer accuracy       : {pct(metrics['answer_accuracy'])}   [answerable only]")
    lines.append(f"  Citation/page accuracy: {pct(metrics['citation_page_accuracy'])}")
    lines.append(f"  Refusal accuracy      : {pct(metrics['refusal_accuracy'])}   [unanswerable only]")
    lines.append(f"  False-refusal rate    : {pct(metrics['false_refusal_rate'])}   [answerable refused]")
    lines.append("-" * 72)
    lines.append("  Per-category answer accuracy (answerable only):")
    for cat, v in summary["per_category"].items():
        lines.append(f"    {cat:18s} {v['correct']}/{v['total']}  ({v['accuracy'] * 100:.0f}%)")
    if too_few:
        lines.append("-" * 72)
        lines.append("  WARNING: too few questions to be statistically meaningful "
                     f"({len(rows)} < 30).")
    lines.append("-" * 72)
    lines.append("  Note: results depend on OCR quality and the small local model;")
    lines.append("        they are a realistic snapshot, not a guaranteed benchmark.")
    lines.append("=" * 72)

    report_text = "\n".join(lines)
    print("\n[4/4] Writing results")
    print(report_text)

    results_dir = unique_results_dir(mode)
    csv_path = results_dir / "evaluation_results.csv"
    json_path = results_dir / "evaluation_results.json"
    txt_path = results_dir / "summary.txt"

    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    json_path.write_text(
        json.dumps({"summary": summary, "questions": rows}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    txt_path.write_text(report_text + "\n", encoding="utf-8")
    print(f"\n  Results written to {results_dir}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # surface a clear message (e.g. Ollama not running)
        print(f"\nEvaluation failed: {exc}")
        print("Is Ollama running with nomic-embed-text and qwen2.5:3b pulled?")
        raise SystemExit(1)
