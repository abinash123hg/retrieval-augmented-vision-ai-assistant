# DocuLens

DocuLens is a local document reading and question-answering application.

Upload PDFs or images to ask questions in natural language and get grounded answers with page-level citations. If the answer is not supported by your documents, DocuLens will tell you instead of guessing.
## Overview
DocuLens is a document question-answering system. PDFs and images can be uploaded and processed to extract text, which can then be queried to produce natural-sounding answers with page-level citations of the source information. If a query cannot be answered with the documents provided, the model will refuse to guess.
The following functionality is implemented:

- PDF and image upload (PDF, PNG, JPG)
- Text extraction with page numbers
- OCR for scanned pages (Tesseract)
- Simple table extraction
- Local document search (FAISS + Ollama embeddings)
- Ollama-based grounded answer generation
- Page-level citations and evidence verification
- Refusal to answer when evidence is lacking
- Multi-document comparisons
- Report downloads

## Requirements

- Python 3.11 or newer
- Node.js 20 or newer
- Ollama running locally
- Models: `qwen2.5:1.5b` and `nomic-embed-text:latest`
- Tesseract OCR (for scanned documents): https://github.com/UB-Mannheim/tesseract/wiki

To start Ollama:

```bash
ollama serve
```

Then, pull the models (only once):

```bash
ollama pull qwen2.5:1.5b
ollama pull nomic-embed-text:latest
```

You can check the list of available models with:

```bash
ollama list
```

To start the backend:

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate    # Windows
# source .venv/bin/activate  # macOS/Linux
pip install -r requirements.txt
copy .env.example .env    # Windows (cp on macOS/Linux)
uvicorn app.main:app --reload --port 8000
```

The backend API is available at http://127.0.0.1:8000, with documentation at http://127.0.0.1:8000/docs.

To start the frontend:

```bash
cd frontend
npm install
npm run dev
```

The frontend will be available at http://localhost:5173 and will connect to the backend at http://127.0.0.1:8000.

To run tests:

```bash
cd backend
.venv\Scripts\activate
pytest
```

The `samples/` directory contains a `sample_report.pdf` (native text PDF) and `sample_invoice.png` (image requiring OCR) that can be used for quick testing.
The following documents are available in the `docs/` directory:

- `PRD.md`: Product Requirements Document
- `Architecture.md`: System architecture and data flow
- `Rules.md`: Project, answer, and safety rules
- `Phases.md`: Development phases
- `Design.md`: UI design specification
- `Memory.md`: Current project status

An important rule for the application is that it should never guess. If an answer is not supported by an uploaded document, it should clearly state:

"I could not find enough information in the uploaded documents to answer this confidently."

Every answer also displays the document name and page number of the evidence used, and draft answers are verified against the retrieved sections before being shown.