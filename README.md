# DocuLens

DocuLens is a local document reading and question-answering application.

Upload PDFs or images, ask questions in normal language, and get grounded answers with page-level citations. If the answer is not in your documents, DocuLens says so instead of guessing.

## Main Features

- PDF and image upload (PDF, PNG, JPG).
- Text extraction with page numbers.
- OCR for scanned pages (Tesseract).
- Basic table extraction.
- Local document search (FAISS + Ollama embeddings).
- Ollama-based grounded answer generation.
- Page-level citations and evidence verification.
- Refusal when evidence is insufficient.
- Multi-document comparison.
- Downloadable reports.

## Requirements

- Python 3.11 or newer.
- Node.js 20 or newer.
- Ollama running locally.
- Models: `qwen2.5:1.5b` and `nomic-embed-text:latest`.
- Tesseract OCR (for scanned documents): https://github.com/UB-Mannheim/tesseract/wiki

## Start Ollama

```bash
ollama serve
```

Pull the models (once):

```bash
ollama pull qwen2.5:1.5b
ollama pull nomic-embed-text:latest
```

Check models:

```bash
ollama list
```

## Start Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux
pip install -r requirements.txt
copy .env.example .env        # Windows (cp on macOS/Linux)
uvicorn app.main:app --reload --port 8000
```

Backend API: http://127.0.0.1:8000
API documentation: http://127.0.0.1:8000/docs

## Start Frontend

Open another terminal:

```bash
cd frontend
npm install
npm run dev
```

The frontend runs at http://localhost:5173 and talks to the backend at http://127.0.0.1:8000.

## Run Tests

```bash
cd backend
.venv\Scripts\activate
pytest
```

## Sample Documents

`samples/` contains `sample_report.pdf` (native text PDF) and `sample_invoice.png` (image requiring OCR) for quick testing.

## Project Documentation

See `docs/`:

- `PRD.md` — product requirements.
- `Architecture.md` — system design and data flow.
- `Rules.md` — project, answer and safety rules.
- `Phases.md` — development phases.
- `Design.md` — UI design specification.
- `Memory.md` — current project status.

## Important Accuracy Rule

The application must not guess. If an answer is not supported by an uploaded document, it must clearly say:

> "I could not find enough information in the uploaded documents to answer this confidently."

Every answer shows the document name and page number of the evidence used, and draft answers are verified against the retrieved sections before being shown.
