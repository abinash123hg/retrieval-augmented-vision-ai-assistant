#!/usr/bin/env python3
"""Honest evaluation harness for the DocuLens grounded-RAG pipeline.

It runs the REAL pipeline end to end (embed -> FAISS retrieve -> IDF rerank ->
grounded answer -> numeric verify -> server-side cite) against the corpus in
evaluation/documents/ and the labelled questions in evaluation/questions.json.

Design rules (unchanged from the project's integrity policy):
- No new models or dependencies: it imports the existing backend services and
  uses the same Ollama models (nomic-embed-text + qwen2.5:3b).
- It runs against an ISOLATED data directory (evaluation/.evaldata) so it never
  touches the app's real uploads/index/registry.
- Ollama must be running (the same requirement as the app itself).
- It NEVER adjusts a number to reach a target. Every metric is whatever the real
  run produces; the corpus/questions are what make the score realistic, not the
  scoring code.
- The pure scoring helpers below have NO backend/Ollama dependency, so they are
  unit-tested offline in evaluation/test_scoring.py. Importing this module does
  not touch the environment or import the backend; that happens lazily in main().

Modes:
    (default)      every question is searched only inside its own document (scoped)
    --unscoped     every question is searched across ALL indexed documents
    --limit N      only run the first N questions (smoke test)
    --ocr-off      index the corpus with OCR preprocessing disabled (single run)
    --ablate       run a sweep of pipeline configurations and write a comparison

Metrics (each printed as correct/total next to the percentage):
- Retrieval Recall@K   : an expected page is present in the retrieved set
- MRR                  : mean reciprocal rank of the first expected-page hit
- Context precision@K  : fraction of retrieved sections on an expected page
- Answer accuracy      : strict correctness over ANSWERABLE questions only
- Answer precision     : of the questions it actually answered, how many were right
                         (a faithfulness proxy: "when it speaks, is it correct?")
- Citation/page accuracy: returned sources cite an expected page
- Refusal accuracy     : correct refusal over UNANSWERABLE questions
- False-refusal rate   : answerable questions that were wrongly refused
- Abstention matrix    : refusal precision / recall / F1 over the whole set
- Median per-question latency

Correctness is strict: every expected number must appear (comma-insensitive), at
least 80% of expected content words must appear, any per-question `forbidden`
string makes the answer wrong, and an answer that still leaks source-listing lines
or "Evidence Block" text is flagged wrong.

Results are written to evaluation/results/<timestamp>-<mode>/ and never overwrite
a previous run.

Usage:
    backend/.venv/Scripts/python.exe evaluation/evaluate.py
    backend/.venv/Scripts/python.exe evaluation/evaluate.py --unscoped
    backend/.venv/Scripts/python.exe evaluation/evaluate.py --limit 4      # smoke
    backend/.venv/Scripts/python.exe evaluation/evaluate.py --ablate
"""

from __future__ import annotations

import argparse
import contextlib
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
# Pure scoring helpers (stdlib only — unit-tested without Ollama).
# These signatures are depended on by evaluation/test_scoring.py; keep them stable.
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
# New pure helpers (also offline-testable). A multi-hop question may accept more
# than one page, so hits/citations are scored against a SET of acceptable pages
# while the single-page primitives above stay unchanged for the unit tests.
# ---------------------------------------------------------------------------
def acceptable_pages(question: dict) -> list:
    """Ordered list of pages that count as a correct retrieval/citation target."""
    pages = question.get("expected_pages")
    if pages:
        return list(pages)
    page = question.get("expected_page")
    return [page] if page is not None else []


def best_rank(sections: list[dict], expected_doc_id: str, pages: list) -> int:
    """1-based rank of the first retrieved section on any acceptable page, else 0."""
    ranks = [retrieval_hit(sections, expected_doc_id, p)[1] for p in pages]
    ranks = [r for r in ranks if r > 0]
    return min(ranks) if ranks else 0


def context_precision(sections: list[dict], expected_doc_id: str, pages: list) -> float:
    """Fraction of retrieved sections that land on an acceptable page."""
    if not sections:
        return 0.0
    on_target = sum(
        1
        for s in sections
        if s.get("document_id") == expected_doc_id and s.get("page_number") in pages
    )
    return on_target / len(sections)


def confusion(rows: list[dict]) -> dict:
    """Abstention confusion matrix with 'refused' as the positive class.

    TP = unanswerable & refused (correct refusal)
    FP = answerable   & refused (false refusal — coverage cost)
    FN = unanswerable & answered (should have refused)
    TN = answerable   & answered
    """
    tp = fp = fn = tn = 0
    for r in rows:
        refused = bool(r["refused"])
        if r["answerable"]:
            if refused:
                fp += 1
            else:
                tn += 1
        else:
            if refused:
                tp += 1
            else:
                fn += 1
    precision = frac(tp, tp + fp)
    recall = frac(tp, tp + fn)
    f1 = frac(2 * precision * recall, precision + recall) if (precision + recall) else 0.0
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "refusal_precision": round(precision, 4),
        "refusal_recall": round(recall, 4),
        "refusal_f1": round(f1, 4),
    }


# ---------------------------------------------------------------------------
# Ablation configurations. Each entry overrides only the listed knobs; anything
# omitted stays at the project default (gate 0.5, top_k 6, rerank w 0.4, numeric
# verification on, OCR preprocessing on). `ocr_off` needs a re-index.
# ---------------------------------------------------------------------------
ABLATIONS: list[dict] = [
    {"name": "baseline", "cfg": {}},
    {"name": "gate_off(min=0.0)", "cfg": {"min_score": 0.0}},
    {"name": "gate_high(min=0.6)", "cfg": {"min_score": 0.6}},
    {"name": "rerank_off(w=0.0)", "cfg": {"rerank_weight": 0.0}},
    {"name": "rerank_high(w=0.6)", "cfg": {"rerank_weight": 0.6}},
    {"name": "topk_3", "cfg": {"top_k": 3}},
    {"name": "topk_10", "cfg": {"top_k": 10}},
    {"name": "numeric_verify_off", "cfg": {"numeric_verify": False}},
    {"name": "ocr_preprocess_off", "cfg": {}, "ocr_off": True},
]


# ---------------------------------------------------------------------------
# Pipeline glue (backend-dependent) — imported lazily inside main().
# ---------------------------------------------------------------------------
def reset_eval_store(get_settings) -> None:
    import shutil

    if EVAL_DATA.exists():
        shutil.rmtree(EVAL_DATA, ignore_errors=True)
    get_settings().ensure_dirs()


def index_documents(
    pdf_service, ocr_off: bool = False, documents_dir: Path | None = None
) -> dict[str, str]:
    """Upload + process every file in ``documents_dir``. Returns {basename: document_id}.

    With ``ocr_off`` the OCR preprocessing chain is bypassed (identity) so the
    scanned/image evidence is whatever raw Tesseract reads — used only by the
    OCR ablation. The patch is restored before returning.
    """
    documents_dir = documents_dir or DOCUMENTS_DIR
    saved = None
    if ocr_off:
        saved = pdf_service.preprocess
        pdf_service.preprocess = lambda image: image
    try:
        name_to_id: dict[str, str] = {}
        for path in sorted(documents_dir.iterdir()):
            if path.suffix.lower() not in {".pdf", ".png", ".jpg", ".jpeg"}:
                continue
            document_id, _ = pdf_service.save_upload(path.name, path.read_bytes())
            pdf_service.process_document(document_id)
            record = pdf_service.get_document(document_id)
            name_to_id[path.name] = document_id
            print(
                f"  indexed {path.name:26s} id={document_id[:8]} "
                f"status={record.processing_status} pages={record.page_count} "
                f"ocr_pages={record.ocr_pages}"
            )
        return name_to_id
    finally:
        if saved is not None:
            pdf_service.preprocess = saved


@contextlib.contextmanager
def applied_cfg(rag_service, get_settings, cfg: dict):
    """Temporarily apply an ablation config to the live pipeline, then restore."""
    settings = get_settings()
    saved = {
        "top_k": settings.top_k_results,
        "min_score": settings.min_retrieval_score,
        "rerank_weight": rag_service.RERANK_WEIGHT,
        "verify": rag_service.verify,
    }
    if "top_k" in cfg:
        settings.top_k_results = cfg["top_k"]
    if "min_score" in cfg:
        settings.min_retrieval_score = cfg["min_score"]
    if "rerank_weight" in cfg:
        rag_service.RERANK_WEIGHT = cfg["rerank_weight"]
    if cfg.get("numeric_verify") is False:
        rag_service.verify = _make_lenient_verify(rag_service)
    try:
        yield
    finally:
        settings.top_k_results = saved["top_k"]
        settings.min_retrieval_score = saved["min_score"]
        rag_service.RERANK_WEIGHT = saved["rerank_weight"]
        rag_service.verify = saved["verify"]


def _make_lenient_verify(rag_service):
    """verify() with the numeric-grounding rejection removed (ablation only)."""

    def lenient_verify(answer: str, sections: list[dict]):
        if not answer.strip() or rag_service.is_refusal(answer):
            return "not_found", True, []
        warnings = []
        if any(s.get("content_type") == "ocr" for s in sections):
            warnings.append("Part of the evidence comes from OCR of a scanned page.")
        return "supported", True, warnings

    return lenient_verify


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


def run_questions(questions, name_to_id, rag_service, get_settings, unscoped, top_k):
    """Run every question through the live pipeline; return (rows, latencies)."""
    rows: list[dict] = []
    latencies: list[float] = []
    for q in questions:
        expected_doc_id = name_to_id.get(q["document"], "")
        scope = scope_for(q, name_to_id, unscoped=unscoped)
        pages = acceptable_pages(q)
        answerable = bool(q["answerable"])

        sections = rag_service.retrieve(
            q["question"], document_ids=scope or None, top_k=top_k
        )
        rank = best_rank(sections, expected_doc_id, pages)
        hit = rank > 0
        cprec = context_precision(sections, expected_doc_id, pages)

        start = time.time()
        response = rag_service.answer_question(q["question"], document_ids=scope or None)
        latency = time.time() - start
        latencies.append(latency)

        answer = response.answer
        refused = rag_service.is_refusal(answer)
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
            cite = any(citation_hit(response.sources, q["document"], p) for p in pages)
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
                "expected_pages": ";".join(str(p) for p in pages),
                "answerable": answerable,
                "retrieval_hit": hit if answerable else "",
                "retrieval_rank": rank if answerable else "",
                "context_precision": round(cprec, 3) if answerable else "",
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
            f"  [{flag}] Q{q['id']:<3d} ({q['category']:15s}) hit={hit} rank={rank} "
            f"refused={refused} {latency:.2f}s"
            + (f"  <- {'; '.join(reasons)}" if reasons else "")
        )
    return rows, latencies


def aggregate(rows, latencies, name_to_id, settings, top_k, mode, label="") -> dict:
    answerable_rows = [r for r in rows if r["answerable"]]
    unanswerable_rows = [r for r in rows if not r["answerable"]]
    page_known = [r for r in answerable_rows if r["expected_pages"] != ""]

    retrieval_correct = sum(1 for r in page_known if r["retrieval_hit"] is True)
    answer_correct = sum(1 for r in answerable_rows if r["answer_correct"] is True)
    citation_correct = sum(1 for r in page_known if r["citation_correct"] is True)
    refusal_correct = sum(1 for r in unanswerable_rows if r["refusal_correct"] is True)
    false_refusals = sum(1 for r in answerable_rows if r["refused"])
    answered = [r for r in answerable_rows if not r["refused"]]
    answered_correct = sum(1 for r in answered if r["answer_correct"] is True)

    rr_sum = sum(1.0 / r["retrieval_rank"] for r in page_known if r["retrieval_rank"])
    mrr = round(rr_sum / len(page_known), 4) if page_known else 0.0
    cp_vals = [r["context_precision"] for r in page_known if r["context_precision"] != ""]
    ctx_precision = round(sum(cp_vals) / len(cp_vals), 4) if cp_vals else 0.0

    metrics = {
        "retrieval_recall_at_k": metric(retrieval_correct, len(page_known)),
        "mrr": mrr,
        "context_precision_at_k": ctx_precision,
        "answer_accuracy": metric(answer_correct, len(answerable_rows)),
        "answer_precision": metric(answered_correct, len(answered)),
        "citation_page_accuracy": metric(citation_correct, len(page_known)),
        "refusal_accuracy": metric(refusal_correct, len(unanswerable_rows)),
        "false_refusal_rate": metric(false_refusals, len(answerable_rows)),
        "abstention": confusion(rows),
    }

    per_category: dict[str, dict] = {}
    for r in answerable_rows:
        cat = per_category.setdefault(r["category"], {"total": 0, "correct": 0})
        cat["total"] += 1
        cat["correct"] += int(r["answer_correct"] is True)

    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "label": label,
        "mode": mode,
        "chat_model": settings.ollama_chat_model,
        "embedding_model": settings.ollama_embed_model,
        "top_k": top_k,
        "min_retrieval_score": settings.min_retrieval_score,
        "rerank_weight": round(getattr(_RAG_REF, "RERANK_WEIGHT", 0.4), 3) if _RAG_REF else 0.4,
        "num_questions": len(rows),
        "num_answerable": len(answerable_rows),
        "num_unanswerable": len(unanswerable_rows),
        "documents": sorted(name_to_id),
        "median_latency_s": round(median(latencies), 3) if latencies else 0.0,
        "too_few_questions": len(rows) < 30,
        "metrics": metrics,
        "per_category": {
            c: {**v, "accuracy": round(frac(v["correct"], v["total"]), 4)}
            for c, v in per_category.items()
        },
    }


# Set by main() so aggregate() can report the live rerank weight under ablation.
_RAG_REF = None


def render_text(summary: dict, rows: list[dict]) -> str:
    m = summary["metrics"]

    def pct(x: dict) -> str:
        return f"{x['correct']}/{x['total']}  ({x['rate'] * 100:5.1f}%)"

    L: list[str] = []
    L.append("=" * 74)
    L.append(f"SUMMARY — {summary['label'] or summary['mode'].upper()}")
    L.append("=" * 74)
    L.append(f"  Chat model              : {summary['chat_model']}")
    L.append(f"  Embedding model         : {summary['embedding_model']}")
    L.append(
        f"  Settings                : top_k={summary['top_k']} "
        f"min_score={summary['min_retrieval_score']} rerank_w={summary['rerank_weight']}"
    )
    L.append(
        f"  Questions               : {summary['num_questions']} "
        f"({summary['num_answerable']} answerable, {summary['num_unanswerable']} unanswerable)"
    )
    L.append(f"  Documents indexed       : {len(summary['documents'])}")
    L.append(f"  Median per-question latency : {summary['median_latency_s']:.3f}s")
    L.append("-" * 74)
    L.append(f"  Retrieval Recall@{summary['top_k']}      : {pct(m['retrieval_recall_at_k'])}")
    L.append(f"  MRR                   : {m['mrr']:.3f}")
    L.append(f"  Context precision@{summary['top_k']}  : {m['context_precision_at_k']:.3f}")
    L.append(f"  Answer accuracy       : {pct(m['answer_accuracy'])}   [answerable only]")
    L.append(f"  Answer precision      : {pct(m['answer_precision'])}   [of those it answered]")
    L.append(f"  Citation/page accuracy: {pct(m['citation_page_accuracy'])}")
    L.append(f"  Refusal accuracy      : {pct(m['refusal_accuracy'])}   [unanswerable only]")
    L.append(f"  False-refusal rate    : {pct(m['false_refusal_rate'])}   [answerable refused]")
    a = m["abstention"]
    L.append(
        f"  Abstention (refusal)  : P={a['refusal_precision']:.3f} "
        f"R={a['refusal_recall']:.3f} F1={a['refusal_f1']:.3f}  "
        f"[TP={a['tp']} FP={a['fp']} FN={a['fn']} TN={a['tn']}]"
    )
    L.append("-" * 74)
    L.append("  Per-category answer accuracy (answerable only):")
    for cat, v in summary["per_category"].items():
        L.append(f"    {cat:18s} {v['correct']}/{v['total']}  ({v['accuracy'] * 100:.0f}%)")
    if summary["too_few_questions"]:
        L.append("-" * 74)
        L.append(
            "  WARNING: too few questions to be statistically meaningful "
            f"({summary['num_questions']} < 30)."
        )
    L.append("-" * 74)
    L.append("  Note: results depend on OCR quality and the small local model;")
    L.append("        they are a realistic snapshot, not a guaranteed benchmark.")
    L.append("=" * 74)
    return "\n".join(L)


def render_markdown(summary: dict) -> str:
    m = summary["metrics"]
    a = m["abstention"]

    def pct(x: dict) -> str:
        return f"{x['correct']}/{x['total']} ({x['rate'] * 100:.1f}%)"

    L: list[str] = []
    L.append(f"# DocuLens evaluation — {summary['label'] or summary['mode']}")
    L.append("")
    L.append(f"- Generated: {summary['generated_at']}")
    L.append(f"- Chat model: `{summary['chat_model']}` · Embedding: `{summary['embedding_model']}`")
    L.append(
        f"- Settings: top_k={summary['top_k']}, min_score={summary['min_retrieval_score']}, "
        f"rerank_w={summary['rerank_weight']}"
    )
    L.append(
        f"- Questions: {summary['num_questions']} "
        f"({summary['num_answerable']} answerable, {summary['num_unanswerable']} unanswerable) "
        f"over {len(summary['documents'])} documents"
    )
    L.append(f"- Median latency: {summary['median_latency_s']}s")
    L.append("")
    L.append("| Metric | Value |")
    L.append("| --- | --- |")
    L.append(f"| Retrieval Recall@{summary['top_k']} | {pct(m['retrieval_recall_at_k'])} |")
    L.append(f"| MRR | {m['mrr']:.3f} |")
    L.append(f"| Context precision@{summary['top_k']} | {m['context_precision_at_k']:.3f} |")
    L.append(f"| Answer accuracy (answerable) | {pct(m['answer_accuracy'])} |")
    L.append(f"| Answer precision (of answered) | {pct(m['answer_precision'])} |")
    L.append(f"| Citation page accuracy | {pct(m['citation_page_accuracy'])} |")
    L.append(f"| Refusal accuracy (unanswerable) | {pct(m['refusal_accuracy'])} |")
    L.append(f"| False-refusal rate | {pct(m['false_refusal_rate'])} |")
    L.append(
        f"| Abstention F1 (refusal) | {a['refusal_f1']:.3f} "
        f"(P={a['refusal_precision']:.3f}, R={a['refusal_recall']:.3f}) |"
    )
    L.append("")
    L.append("## Per-category answer accuracy (answerable only)")
    L.append("")
    L.append("| Category | Correct | Accuracy |")
    L.append("| --- | --- | --- |")
    for cat, v in summary["per_category"].items():
        L.append(f"| {cat} | {v['correct']}/{v['total']} | {v['accuracy'] * 100:.0f}% |")
    L.append("")
    return "\n".join(L)


def write_run(results_dir: Path, summary: dict, rows: list[dict]) -> None:
    with (results_dir / "evaluation_results.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    (results_dir / "evaluation_results.json").write_text(
        json.dumps({"summary": summary, "questions": rows}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    text = render_text(summary, rows)
    (results_dir / "summary.txt").write_text(text + "\n", encoding="utf-8")
    (results_dir / "summary.md").write_text(render_markdown(summary), encoding="utf-8")
    print("\n" + text)
    print(f"\n  Results written to {results_dir}")


def render_ablation_table(summaries: list[dict]) -> str:
    head = (
        "| Config | top_k | Recall@k | MRR | Answer acc | Answer prec | "
        "Citation | Refusal acc | False-refusal | Abstention F1 |\n"
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"
    )
    lines = ["# DocuLens ablation study", "", head]
    for s in summaries:
        m = s["metrics"]
        lines.append(
            f"| {s['label']} | {s['top_k']} "
            f"| {m['retrieval_recall_at_k']['rate'] * 100:.1f}% "
            f"| {m['mrr']:.3f} "
            f"| {m['answer_accuracy']['rate'] * 100:.1f}% "
            f"| {m['answer_precision']['rate'] * 100:.1f}% "
            f"| {m['citation_page_accuracy']['rate'] * 100:.1f}% "
            f"| {m['refusal_accuracy']['rate'] * 100:.1f}% "
            f"| {m['false_refusal_rate']['rate'] * 100:.1f}% "
            f"| {m['abstention']['refusal_f1']:.3f} |"
        )
    lines += [
        "",
        "Each row is a real run of the whole question set under one configuration; "
        "nothing is normalized or adjusted. `numeric_verify_off` shows the faithfulness "
        "guard's effect, `gate_*` shows the abstention gate's effect, `ocr_preprocess_off` "
        "shows the scan-rescue chain's effect.",
        "",
    ]
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="DocuLens evaluation harness")
    parser.add_argument(
        "--unscoped",
        action="store_true",
        help="search every indexed document for every question (default: scope to the "
        "question's own document)",
    )
    parser.add_argument("--limit", type=int, default=0, help="run only the first N questions")
    parser.add_argument(
        "--ocr-off",
        action="store_true",
        help="index the corpus with OCR preprocessing disabled (single run)",
    )
    parser.add_argument(
        "--ablate",
        action="store_true",
        help="run the configuration sweep and write a comparison table",
    )
    parser.add_argument(
        "--questions",
        default=str(QUESTIONS_FILE),
        help="path to the questions JSON (default: evaluation/questions.json)",
    )
    parser.add_argument(
        "--documents",
        default=str(DOCUMENTS_DIR),
        help="directory of documents to index (default: evaluation/documents)",
    )
    return parser


def main() -> int:
    global _RAG_REF
    args = build_parser().parse_args()
    mode = "unscoped" if args.unscoped else "scoped"

    # Isolate the data store BEFORE importing the backend config, which reads these
    # env vars once at import time (pydantic-settings: os.environ beats the .env file).
    import os

    for name, sub in (
        ("UPLOAD_DIR", "uploads"),
        ("PROCESSED_DIR", "processed"),
        ("INDEX_DIR", "indexes"),
    ):
        os.environ[name] = str(EVAL_DATA / sub)

    import sys

    sys.path.insert(0, str(BACKEND_DIR))
    from app import pdf_service, rag_service  # noqa: E402
    from app.config import get_settings  # noqa: E402

    _RAG_REF = rag_service

    print("=" * 74)
    print(f"DocuLens evaluation harness — mode: {mode.upper()}"
          + ("  [ABLATION SWEEP]" if args.ablate else ""))
    print("=" * 74)

    questions = json.loads(Path(args.questions).read_text(encoding="utf-8"))
    if args.limit > 0:
        questions = questions[: args.limit]
    settings = get_settings()
    documents_dir = Path(args.documents)

    print(f"\n[1/4] Preparing isolated data store at {EVAL_DATA}")
    reset_eval_store(get_settings)

    print(f"\n[2/4] Indexing {documents_dir}" + ("  [OCR preprocessing OFF]" if args.ocr_off else ""))
    t0 = time.time()
    name_to_id = index_documents(pdf_service, ocr_off=args.ocr_off, documents_dir=documents_dir)
    print(f"  done in {time.time() - t0:.1f}s — {len(name_to_id)} document(s)")
    if not name_to_id:
        print("No documents to index. Aborting.")
        return 1

    missing_docs = sorted({q["document"] for q in questions} - set(name_to_id))
    if missing_docs and not args.unscoped:
        print(f"  WARNING: question(s) reference un-indexed document(s): {missing_docs}")

    # ------------------------------- ABLATION -------------------------------
    if args.ablate:
        print(f"\n[3/4] Running ablation sweep over {len(questions)} questions")
        summaries: list[dict] = []
        root = unique_results_dir("ablate")
        normal_configs = [a for a in ABLATIONS if not a.get("ocr_off")]
        ocr_configs = [a for a in ABLATIONS if a.get("ocr_off")]

        def _run_one(abl: dict) -> None:
            cfg = abl["cfg"]
            with applied_cfg(rag_service, get_settings, cfg):
                top_k = get_settings().top_k_results
                print(f"\n  --- config: {abl['name']} (top_k={top_k}) ---")
                rows, lat = run_questions(
                    questions, name_to_id, rag_service, get_settings, args.unscoped, top_k
                )
            summary = aggregate(rows, lat, name_to_id, settings, top_k, mode, label=abl["name"])
            sub = root / re.sub(r"[^A-Za-z0-9_.-]+", "_", abl["name"])
            sub.mkdir(parents=True, exist_ok=True)
            write_run(sub, summary, rows)
            summaries.append(summary)

        for abl in normal_configs:
            _run_one(abl)
        if ocr_configs:
            print("\n  --- re-indexing with OCR preprocessing disabled ---")
            reset_eval_store(get_settings)
            name_to_id = index_documents(
                pdf_service, ocr_off=True, documents_dir=documents_dir
            )
            for abl in ocr_configs:
                _run_one(abl)

        table = render_ablation_table(summaries)
        (root / "comparison.md").write_text(table, encoding="utf-8")
        (root / "comparison.json").write_text(
            json.dumps(summaries, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print("\n" + table)
        print(f"\n  Ablation results written to {root}")
        return 0

    # ------------------------------- SINGLE RUN -----------------------------
    top_k = settings.top_k_results
    print(f"\n[3/4] Running {len(questions)} questions through the live pipeline (top_k={top_k})")
    rows, latencies = run_questions(
        questions, name_to_id, rag_service, get_settings, args.unscoped, top_k
    )
    summary = aggregate(rows, latencies, name_to_id, settings, top_k, mode)

    print("\n[4/4] Writing results")
    results_dir = unique_results_dir(mode + ("-ocroff" if args.ocr_off else ""))
    write_run(results_dir, summary, rows)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # surface a clear message (e.g. Ollama not running)
        print(f"\nEvaluation failed: {exc}")
        print("Is Ollama running with nomic-embed-text and qwen2.5:3b pulled?")
        raise SystemExit(1)
