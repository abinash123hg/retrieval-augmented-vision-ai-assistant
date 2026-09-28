"""Verification of draft answers against retrieved evidence.

Rules enforced here (from docs/Rules.md):
- Refusal is detected and reported as not_found.
- Numbers in the answer must appear in the evidence.
- Model-reported conflicts are surfaced, never silently resolved.
"""

import re

REFUSAL_SENTENCE = (
    "I could not find enough information in the uploaded documents to answer this confidently."
)
_REFUSAL_MARKER = "could not find enough information"

_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?%?")

STATUS_MAP = {
    "supported": "supported",
    "partially supported": "partially_supported",
    "partially-supported": "partially_supported",
    "not found": "not_found",
    "conflicting sources": "conflicting_sources",
    "conflicting": "conflicting_sources",
    "low-quality source": "low_quality_source",
    "low quality source": "low_quality_source",
}


def normalize_number(token: str) -> str:
    return token.replace(",", "")


def is_refusal(answer: str) -> bool:
    return _REFUSAL_MARKER.lower() in answer.lower()


def _numbers_in(text: str) -> set[str]:
    return {normalize_number(m) for m in _NUMBER.findall(text)}


def map_evidence_status(raw: str) -> str:
    key = raw.strip().lower().rstrip(".")
    return STATUS_MAP.get(key, "partially_supported")


def verify(answer: str, model_status: str, sections: list[dict]) -> tuple[str, bool, list[str]]:
    """Return (evidence_status, passed, warnings)."""
    warnings: list[str] = []

    if is_refusal(answer):
        return "not_found", True, warnings

    status = map_evidence_status(model_status)
    evidence_text = " ".join(s.get("content", "") for s in sections)
    evidence_numbers = _numbers_in(evidence_text)
    answer_numbers = _numbers_in(answer)

    # Page numbers cited in the answer are allowed to come from source metadata.
    allowed = set(evidence_numbers)
    for section in sections:
        allowed.add(str(section.get("page_number", "")))

    unsupported = {n for n in answer_numbers if n not in allowed and len(n) > 1}
    if unsupported:
        sample = ", ".join(sorted(unsupported)[:5])
        warnings.append(
            f"These values in the draft answer were not found in the retrieved evidence: {sample}."
        )
        if status == "supported":
            status = "partially_supported"

    if status == "conflicting_sources":
        warnings.append(
            "The documents contain conflicting values for this question. Both are reported."
        )

    if any(s.get("content_type") == "ocr" for s in sections) and status == "supported":
        warnings.append("Part of the evidence comes from OCR of a scanned page; values may contain recognition errors.")

    passed = status in {"supported", "partially_supported", "conflicting_sources", "low_quality_source"}
    return status, passed, warnings
