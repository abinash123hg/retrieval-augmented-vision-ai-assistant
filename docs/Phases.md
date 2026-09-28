# DocuLens - Development Phases

Coding order (from the build instruction):

```text
Phase 0:
- Create folders.
- Create backend health endpoint.
- Create frontend shell.
- Add documentation files.
- Add environment configuration.

Phase 1:
- Implement file upload.
- Validate PDF, PNG and JPG.
- Save files locally.
- Show uploaded documents in the frontend.

Phase 2:
- Implement PDF text extraction.
- Store page-level content.
- Show processing status.

Phase 3:
- Connect nomic-embed-text to /api/embed.
- Create FAISS index.
- Implement document retrieval.

Phase 4:
- Connect qwen2.5:1.5b to /api/generate.
- Implement grounded answers.
- Add page-level sources.

Phase 5:
- Add answer verification.
- Add refusal when evidence is insufficient.
- Add conflict detection.

Phase 6:
- Add OCR.
- Add basic table extraction.
- Add downloadable reports.
```

Do not skip testing. Do not build all phases in one step. After finishing a phase, update docs/Memory.md.

---

## Phase 0: Project Setup

Goal: project structure, health endpoint, frontend shell, docs, env config.

Completion: backend serves `GET /api/health`; frontend opens with the app shell.

## Phase 1: File Upload

Goal: user can upload PDF/PNG/JPG; validation errors are clear; files stored locally; frontend lists documents.

Completion: valid file uploads and appears in the list; invalid file produces a useful error.

## Phase 2: PDF Reading

Goal: extract page-level text from normal PDFs; store as JSON; show processing status.

Completion: extracted text visible per page; document status transitions to ready.

## Phase 3: Search Index

Goal: embeddings via Ollama `/api/embed`; FAISS index; retrieval by question with page references.

Completion: a question returns relevant sections with document name, page number and score.

## Phase 4: Grounded Question Answering

Goal: answers via Ollama `/api/generate` using only retrieved evidence; page-level sources; refusal message when not found.

Completion: chat answers document questions with sources and evidence status.

## Phase 5: Verification

Goal: verify draft answers against evidence; reject unsupported claims/numbers; detect conflicting sources.

Completion: verification block returned with every answer; unsupported answers refused.

## Phase 6: OCR, Tables, Reports

Goal: Tesseract OCR for scanned pages/images; basic table extraction with pdfplumber; downloadable reports.

Completion: scanned document is processed and answerable; report downloads with question, answer, evidence status, sources and time.

## Phase 7: Multi-Document Support

Goal: search across multiple documents; every result shows its source document; comparison questions work.

Completion: user can compare information from at least two documents.

## Phase 8: Interface Polish

Goal: apply Design.md fully — empty states, skeletons, toasts, badges, delete confirmation, responsive layout.

Completion: a first-time user can understand the interface without instructions.

## Phase 9: Testing and Packaging

Goal: pytest suite for validation/extraction/retrieval/verification; README with setup instructions; clean-environment check.

Completion: another person can install and run the project using the README.
