# DocuLens - Project Memory

## Current Status

All build phases completed and verified end-to-end (backend + frontend + Ollama pipeline).
Phases 0–9 from Phases.md are done, including the coding-order phases 0–6 from the build instruction.

## Completed Work

- Project structure, docs (PRD, Architecture, Rules, Phases, Design), README, .gitignore, docker-compose.yml.
- FastAPI backend: health, upload with validation, PDF text extraction (PyMuPDF), OCR fallback (Tesseract), image OCR, table extraction (pdfplumber), chunking with metadata, Ollama embeddings (/api/embed, nomic-embed-text), FAISS index with persistence, retrieval with score threshold, grounded answers (/api/generate, qwen2.5:1.5b), evidence verification, refusal on insufficient evidence, page-level citations, summaries (short/detailed/key_points), PDF reports (ReportLab), document delete with index rebuild.
- React + Vite frontend: app shell with Ollama health pill, drag-and-drop upload with progress, document cards with status badges, polling, chat window with example-question chips, evidence status badge, verification warnings, source cards with relevance, copy answer, report download, summary panel, delete confirmation, toasts, skeletons, responsive layout.
- Tests: 30 pytest tests passing (health, file validation, PDF/OCR extraction, chunking, retrieval, verification, citations, response parsing).
- Live verification: uploaded a generated PDF and an OCR invoice image; questions answered with correct page sources; unanswerable question refused with the exact refusal sentence; report PDF downloaded through the frontend proxy.

## Current Files

- backend/app — full service architecture per Architecture.md.
- frontend/src — components per Design.md.
- samples/ — sample_report.pdf and sample_invoice.png for quick testing.

## Decisions

- Stack: FastAPI backend + React/Vite frontend (superseded the earlier Streamlit plan).
- Ollama models: qwen2.5:1.5b (answers), nomic-embed-text:latest (embeddings). Never switched silently.
- sentence-transformers/scikit-learn intentionally NOT installed — embeddings come from Ollama, keeping the install light.
- FAISS index stores embeddings in its JSON metadata sidecar so the index can be rebuilt after document deletion.
- Chat answers use temperature 0 for determinism.
- Verification flags numbers in answers that don't appear in retrieved evidence and downgrades "supported" to "partially_supported".
- Heading detection in chunking is strict (ALL-CAPS or Title Case only) with a whole-page fallback so no page content is ever dropped.

## Known Problems

- OCR quality depends on scan resolution; small default-font images misread some characters (expected).
- Table extraction is basic (pdfplumber grid tables only).
- Browser-based UI verification was structural (accessibility tree); a visual pass on an open browser is still worth doing.

## Next Task

Optional polish: visual UI review, demo screenshots for README, evaluation document set (Phase 9 stretch).
