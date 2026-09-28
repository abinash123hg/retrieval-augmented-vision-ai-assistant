# DocuLens - Project Rules

## 1. General Rules

- Keep the application simple and understandable.
- Write code in small modules.
- Do not place the whole project in one file.
- Use clear names for files, functions and variables.
- Add type hints where practical.
- Keep user-facing messages simple.
- Do not add a feature unless it is required or clearly useful.

## 2. Technology Rules

Use:

- Python 3.11+ with FastAPI for the backend.
- React + Vite for the frontend.
- PyMuPDF and pdfplumber for PDF reading.
- Pillow for image handling.
- Tesseract (pytesseract) for scanned text.
- Ollama `nomic-embed-text:latest` for embeddings (`/api/embed`).
- Ollama `qwen2.5:1.5b` for answer generation (`/api/generate`).
- FAISS (faiss-cpu) for local vector search.
- ReportLab for downloadable reports.
- pytest for tests.
- Git for version control.

Avoid adding:

- Hardware components.
- Mobile application code.
- Kubernetes.
- Microservices.
- Complex cloud infrastructure.
- Multiple databases without a clear reason.
- Large frameworks that do not help the first version.

Model rule: do not replace `qwen2.5:1.5b` or `nomic-embed-text:latest` unless there is a clear technical reason and the user approves it. Never silently switch to another model.

## 3. Document Rules

- Keep the original uploaded file unchanged.
- Save page numbers with extracted content.
- Store document name with every extracted section.
- Do not mix content from different documents without recording the source.
- Mark whether content came from normal text extraction or OCR.
- Never silently discard a page that failed to process.

## 4. Answer Rules

- Answer questions using retrieved document content only.
- Include document name and page number.
- If the answer is not found, say exactly:
  "I could not find enough information in the uploaded documents to answer this confidently."
- Do not invent figures, names, dates or citations.
- Do not present guesses as facts.
- Do not use an unrelated document as evidence.
- Keep answers concise unless the user requests detail.
- Show calculations when numerical comparison is performed.
- Mention uncertainty when the source is unclear.
- Report conflicting values instead of silently selecting one.
- Verify the draft answer against the retrieved evidence; reject answers containing unsupported claims.
- Use deterministic generation settings where possible; keep temperature low.
- Do not expose internal prompts to the user.

## 5. Safety Rules

- Do not provide medical, legal or financial decisions as professional advice.
- If a document contains medical or legal information, describe the content but advise the user to consult a qualified professional for decisions.
- Do not expose private files.
- Do not log complete sensitive document content unnecessarily.
- Do not send documents to an external service — everything stays local (Ollama, FAISS, filesystem).
- Do not include secrets or API keys in source code.

## 6. Error Handling Rules

- Validate files before processing.
- Catch expected errors at the correct layer.
- Show useful error messages.
- Keep technical error details in logs, not in the main interface.
- Do not hide processing failures.
- Continue processing remaining pages when one page fails.
- Return an empty result instead of crashing when no relevant content is found.

## 7. Search Rules

- Store metadata with every searchable section.
- Keep the page number in search results.
- Start with vector search.
- Add keyword search only when it improves results.
- Do not return too many sections to the answer layer (top-k, score threshold, context character budget).
- Test retrieval using known questions and expected pages.

## 8. Code Rules

- Use functions that do one clear job.
- Avoid duplicated code.
- Keep configuration outside business logic.
- Do not hard-code file paths.
- Use environment variables for optional service settings.
- Write tests for important processing and retrieval functions.
- Do not remove working code without checking its purpose.

## 9. Change Rules

Before making a large change:

1. Explain what will change.
2. Identify affected files.
3. Check whether the change conflicts with this document.
4. Update the relevant documentation.
5. Test the change.

## 10. Completion Rules

A feature is complete only when:

- It works in the interface.
- Its errors are handled.
- Its main behavior has a test.
- Its documentation is updated.
- It does not break existing features.
