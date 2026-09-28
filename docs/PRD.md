# DocuLens - Product Requirements Document

## 1. Project Overview

DocuLens is a document reading and question-answering application for PDFs, scanned documents and document images.

A user can upload one or more documents, ask questions in normal language, and receive answers based only on the uploaded content. The application will also show the page or section used for the answer.

The first version will focus on financial and business documents such as annual reports, invoices, policies and company reports.

## 2. Problem

People often spend a lot of time searching through long documents to find specific information.

This becomes more difficult when documents contain:

- Scanned pages.
- Tables.
- Multiple columns.
- Charts.
- Different formatting.
- Many pages of information.

DocuLens will make this information easier to find and understand.

## 3. Target Users

### Primary users

- Students reading research papers and reports.
- Employees reviewing business documents.
- Small business owners checking invoices and records.
- Researchers comparing multiple documents.
- Developers testing document-based question answering.

### First release user

The first release will focus on individual users using the application on a laptop.

## 4. Main Goals

- Allow users to upload PDF and image documents.
- Extract text from normal and scanned documents.
- Support questions about document content.
- Retrieve relevant pages and sections.
- Answer using only available document information.
- Show page numbers as evidence.
- Support multiple documents.
- Provide a simple and understandable interface.
- Generate a downloadable summary or answer report.

## 5. Main User Flow

1. The user opens the application.
2. The user uploads a document.
3. The application processes the document.
4. The application shows the document as ready.
5. The user asks a question.
6. The application finds the most relevant pages.
7. The application prepares an answer.
8. The application shows the answer and page references.
9. The user can ask another question or upload another document.

## 6. Required Features

### 6.1 Document upload

The application must allow users to upload:

- PDF files.
- PNG images.
- JPG images.

The application should show a clear error if:

- The file type is not supported.
- The file is empty.
- The file is too large.
- The file cannot be read.

### 6.2 Document processing

The application must:

- Read text from normal PDFs.
- Use OCR for scanned pages.
- Keep page numbers.
- Preserve useful headings.
- Detect tables where possible.
- Store the original uploaded document.
- Save extracted information for later questions.

### 6.3 Question answering

The user must be able to ask questions in normal language.

The answer should:

- Be based on the uploaded documents.
- Be written clearly.
- Mention when information is unavailable.
- Include page references.
- Avoid unsupported assumptions.
- Use tables or bullet points when useful.

### 6.4 Multiple documents

The user should be able to upload more than one document and ask questions such as:

- "What is common in these documents?"
- "Which document reports the higher revenue?"
- "Compare the policies in both files."
- "What changed between the two reports?"

### 6.5 Search and retrieval

The application must find relevant:

- Pages.
- Text sections.
- Tables.
- Document names.
- Headings.

The most relevant sources should appear with the answer.

### 6.6 Summary generation

The user should be able to request:

- Short summary.
- Detailed summary.
- Key points.
- Important numbers.
- Risks or issues mentioned in the document.

### 6.7 Report export

The application should allow users to download:

- Question.
- Answer.
- Source pages.
- Document name.
- Date and time.
- Optional summary.

## 7. Out of Scope for First Version

The first version will not include:

- User login.
- Payment system.
- Mobile application.
- Real-time collaboration.
- Automatic legal or medical advice.
- Training a large language model from scratch.
- Perfect understanding of every chart type.
- Automatic modification of uploaded documents.
- Public sharing of documents.

## 8. Non-Functional Requirements

### Performance

- Small documents should process within a reasonable time.
- Answers should be returned without unnecessary delay.
- The interface should show processing status.

### Reliability

- The application must not crash because of one invalid file.
- Processing errors must be shown clearly.
- The application must not silently ignore failed pages.

### Privacy

- Uploaded files should remain local during development.
- Files should not be exposed publicly.
- Temporary files should be deleted when no longer needed.
- Sensitive documents should not be sent to an external service without user awareness.

### Usability

- The interface should be understandable to a first-time user.
- Important actions should be visible.
- Error messages should explain what the user can do next.

## 9. Answer Quality Rules

An answer is considered acceptable when:

- It uses the correct document.
- It refers to the correct page.
- It answers the actual question.
- It does not add information absent from the document.
- It clearly says when the answer cannot be found.

## 10. Success Criteria

The first version will be successful if:

- A user can upload a normal PDF.
- A user can upload a scanned PDF.
- The application can answer questions from both types.
- Page references are displayed.
- Multiple documents can be compared.
- The user can download a report.
- The application handles invalid files clearly.
- The project can be started locally using documented instructions.

## 11. Example Questions

- What is the main purpose of this document?
- What was the total revenue?
- Which year had higher profit?
- What are the important risks?
- Summarize pages 5 to 10.
- Compare the two uploaded reports.
- Which page contains the information about expenses?
- Is the answer available in the uploaded document?

## 12. First Release

The first release will support:

- PDF upload.
- Image upload.
- Text extraction.
- OCR.
- Basic table reading.
- Question answering.
- Page references.
- Short summaries.
- React + FastAPI interface with local Ollama models.
- Local document storage.
