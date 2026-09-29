"""Verification of draft answers against retrieved evidence.

Lightweight grounding validator (safest behavior: uncertain evidence -> refusal):
- A refusal from the model is reported as not_found.
- Every multi-digit number in the answer must appear in the evidence text or
  match a cited page number; otherwise the answer is rejected (not_found) so
  the caller replaces it with the exact refusal sentence.
"""

import re

REFUSAL_SENTENCE = (
    "I could not find enough information in the uploaded documents to answer this confidently."
)
_REFUSAL_MARKER = "could not find enough information"

_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?%?")


def normalize_number(token: str) -> str:
    return token.replace(",", "")


def is_refusal(answer: str) -> bool:
    return _REFUSAL_MARKER.lower() in answer.lower()


def _numbers_in(text: str) -> set[str]:
    return {normalize_number(m) for m in _NUMBER.findall(text)}


def verify(answer: str, sections: list[dict]) -> tuple[str, bool, list[str]]:
    """Return (evidence_status, passed, warnings).

    'not_found' means the draft answer must be replaced with the refusal
    sentence — either the model refused, or it produced claims that are not
    grounded in the retrieved evidence.
    """
    warnings: list[str] = []

    if not answer.strip() or is_refusal(answer):
        return "not_found", True, warnings

    evidence_text = " ".join(
        " ".join(filter(None, [s.get("content", ""), s.get("section_title") or ""]))
        for s in sections
    )
    allowed = _numbers_in(evidence_text)
    for section in sections:
        allowed.add(str(section.get("page_number", "")))

    answer_numbers = _numbers_in(answer)
    unsupported = {n for n in answer_numbers if n not in allowed and len(n) > 1}
    if unsupported:
        sample = ", ".join(sorted(unsupported)[:5])
        warnings.append(
            f"Draft answer rejected: values not found in the retrieved evidence: {sample}."
        )
        return "not_found", True, warnings

    if any(s.get("content_type") == "ocr" for s in sections):
        warnings.append("Part of the evidence comes from OCR of a scanned page.")

    return "supported", True, warnings
