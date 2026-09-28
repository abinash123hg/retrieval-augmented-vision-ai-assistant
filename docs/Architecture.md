# DocuLens - Architecture

## 1. Architecture Overview

DocuLens is a local full-stack application.

- Frontend: React + Vite (desktop-first document workspace UI).
- Backend: FastAPI (Python), multi-file service architecture.
- Models: local Ollama (`qwen2.5:1.5b` for answers, `nomic-embed-text:latest` for embeddings).
- Search: local FAISS vector index.
- Storage: local filesystem (uploads, processed JSON, indexes, reports).

All document processing and inference stays on the local machine.

## 2. Main Flow

```text
User uploads document
        |
        v
File validation (type, size, readability)
        |
        v
PDF and image processing
        |
        v
Text extraction (PyMuPDF / pdfplumber) and OCR (Tesseract) for scanned pages
        |
        v
Basic table extraction
        |
        v
Page and section preparation (cleaning, chunking, metadata)
        |
        v
Embeddings via Ollama /api/embed (nomic-embed-text:latest)
        |
        v
Local FAISS vector index
        |
        v
User asks a question
        |
        v
Question embedded, relevant sections retrieved
        |
        v
Grounded answer generated via Ollama /api/generate (qwen2.5:1.5b)
        |
        v
Answer verified against retrieved evidence
        |
        v
Answer, evidence status and page-level sources returned
```

## 3. Application Layers

### 3.1 Frontend (React + Vite)

Responsibilities:

- Drag-and-drop file upload with progress.
- Document cards with processing status.
- Chat-style question/answer area.
- Source citation cards with page references.
- Evidence status badge.
- Summary panel.
- Report download.
- Empty, loading and error states.

### 3.2 API layer (FastAPI)

Routes:

- `GET /api/health` — app, Ollama and model availability.
- `POST /api/documents/upload` — multipart upload.
- `GET /api/documents` — list documents.
- `GET /api/documents/{id}` — document status.
- `DELETE /api/documents/{id}` — remove document and its data.
- `POST /api/chat` — ask a question, get grounded answer + sources.
- `POST /api/reports` — generate downloadable report (PDF/Markdown).
- `GET /api/reports/{report_id}/download` — download a generated report.

### 3.3 Document processing services

- `file_service.py` — validation and local storage of uploads.
- `pdf_service.py` — page-level text extraction with PyMuPDF; falls back to OCR for pages with little/no text.
- `ocr_service.py` — Tesseract OCR for scanned pages and images; marks output as OCR-derived.
- `table_service.py` — basic table detection with pdfplumber; tables stored as separate sections.

### 3.4 Content preparation services

- `chunk_service.py` — cleaning and splitting page text into sections with metadata (document name, page number, section title, content type).
- `embedding_service.py` — embeddings through Ollama `/api/embed`.
- `vector_store.py` — FAISS index persistence per store, with metadata sidecar JSON.

### 3.5 Answer layer

- `retrieval_service.py` — embed the question, FAISS search, score threshold, top-k, multi-document filtering.
- `ollama_service.py` — connection check, model availability, embedding and generation calls with clear errors.
- `answer_service.py` — builds the grounded prompt (required prompt from the spec), parses Answer / Evidence status / Sources.
- `verification_service.py` — checks the draft answer against retrieved evidence; rejects unsupported numbers/claims; detects conflicts.
- `citation_service.py` — assembles page-level source citations from retrieved sections only. Never invents pages.

### 3.6 Report layer

- `report_service.py` — builds a downloadable report (question, answer, evidence status, sources with pages and excerpts, date/time) using ReportLab.

## 4. Folder Structure

```text
doculens/
├── README.md
├── .gitignore
├── docker-compose.yml
├── docs/
│   ├── PRD.md
│   ├── Architecture.md
│   ├── Rules.md
│   ├── Phases.md
│   ├── Design.md
│   └── Memory.md
├── backend/
│   ├── requirements.txt
│   ├── .env.example
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── api/ (health, documents, chat, reports)
│   │   ├── core/ (errors, logging_config, security)
│   │   ├── models/ (schemas)
│   │   ├── services/ (see 3.3–3.6)
│   │   └── data/ (uploads, processed, indexes, reports)
│   └── tests/
└── frontend/
    ├── package.json
    ├── vite.config.js
    ├── index.html
    └── src/ (components, hooks, api, styles, utils)
```

## 5. Data Storage

- Uploaded files stored under `app/data/uploads/`.
- Extracted page/section content stored as JSON under `app/data/processed/`.
- Document registry (metadata) stored as JSON under `app/data/processed/documents.json`.
- FAISS indexes under `app/data/indexes/`.
- Generated reports under `app/data/reports/`.
- Configuration from environment variables (`.env`), see `.env.example`.

## 6. Main Data Objects

### Document

```text
id, file_name, file_type, file_size, page_count,
upload_time, processing_status, error_message
```

Statuses: `waiting | processing | ready | partially_processed | failed`

### Page

```text
document_id, page_number, text, ocr_used, tables_found
```

### Content Section

```text
id, document_id, document_name, page_number, section_title,
content, content_type (text | table | ocr)
```

### Answer

```text
question, answer, evidence_status, sources[], verification, created_at
```

## 7. Error Flow

```text
Invalid file
    → 400 with user-friendly message, no processing started

Ollama not running / model missing
    → health endpoint reports it; chat returns clear error:
      "Required Ollama model is not available. Please check the local Ollama model list."

OCR failure on a page
    → page recorded as failed, processing continues, document marked partially_processed

No relevant content
    → refusal answer: "I could not find enough information in the uploaded
      documents to answer this confidently."

Answer service failure
    → 502/500 with temporary error message, uploaded documents remain available
```

## 8. Local Development

Backend:

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Ollama must be running (`ollama serve`) with `qwen2.5:1.5b` and `nomic-embed-text:latest` pulled.
