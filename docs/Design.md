# DocuLens - Design Specification

## 1. Design Direction

DocuLens should look like a polished document workspace — calm, clean and trustworthy. Not a basic student form, not a complicated technical dashboard.

The design helps the user focus on: uploaded documents, processing status, questions, answers and source pages.

## 2. Theme

Light theme by default. Documents are easier to read on a light background; tables and page references stay clear; the app feels suitable for office and study use. A dark theme can be added later.

## 3. Colors

```text
Background:   #F8FAFC
Surface:      #FFFFFF
Primary:      #2563EB
Primary dark: #1D4ED8
Text:         #0F172A
Muted text:   #64748B
Border:       #E2E8F0
Success:      #16A34A
Warning:      #D97706
Error:        #DC2626
```

Primary is used for main buttons, active navigation, links and selected states. Surfaces (white) are used for document cards, answer panels, source panels and the upload area, with soft borders and rounded corners.

## 4. Typography

Clean sans-serif. Preferred order: Inter, Segoe UI, Arial, system sans-serif.

- Main title: 28–32 px
- Section title: 20–24 px
- Card title: 16–18 px
- Body text: 14–16 px
- Small metadata: 12–13 px

## 5. Layout

```text
┌─────────────────────────────────────────────┐
│ DocuLens                         Settings   │
├───────────────┬─────────────────────────────┤
│ Documents     │ Chat with your documents    │
│               │                             │
│ Upload files  │ Answer area                 │
│               │ Source pages                │
│ File cards    │                             │
│               │ Question input              │
└───────────────┴─────────────────────────────┘
```

- Top header: DocuLens name, short description, optional settings button.
- Left sidebar: upload area, document list, statuses, remove controls.
- Main panel: chat/question area, answers, source cards, question input.
- Right source panel on large screens where practical.

Empty state before any upload:

```text
Upload a document to begin.

You can ask questions about its text, tables and important sections.
```

## 6. Components

### UploadPanel

- Large drag-and-drop area + browse button.
- Accepted file types message (PDF, PNG, JPG) and size limit message.
- Upload progress indicator.

### DocumentCard

- File name, file size, page count, processing status badge, upload time, delete action (with confirmation).
- Statuses: Waiting, Processing, Ready, Partially processed, Failed.

### ChatWindow / ChatMessage

- Welcome message, previous questions preserved during the session.
- Answers with evidence status badge ("Supported", "Partially supported", "Not found", "Conflicting sources", "Low-quality source").
- Loading skeleton while answering.
- Copy answer button.

### SourceCard

- Document name, page number, section title, short excerpt, relevance indicator.
- Visually separate from the generated answer.

### QuestionInput

- Multiline input, Ask button, keyboard shortcut (Ctrl/Cmd+Enter).
- Disabled when no document is ready.

### SummaryPanel / ReportButton

- Summary options (short, detailed, key points).
- Download report button for the current answer.

## 7. Interaction Rules

- Buttons have clear labels; no icons without text for important actions.
- Disable Ask when no document is ready.
- Show progress during processing.
- Keep the question visible after answering.
- Preserve previous answers during the session.
- Confirm before deleting a document.
- Error toasts with actionable messages.

## 8. Accessibility

- Readable contrast; status never communicated by color alone.
- Text labels for icons; keyboard navigation where possible.
- Clear error messages; comfortable text size for long reading.

## 9. Writing Style

Direct and friendly:

- "Upload document." / "Processing document." / "Ask a question."
- "Answer not found in the uploaded files."
- "Sources used for this answer."

Avoid unnecessary technical terms, long system messages, vague errors like "Something went wrong", and overconfident language.

## 10. Responsive Behavior

Desktop-first. On smaller screens: move the sidebar above the main panel, keep cards readable, make buttons full-width where necessary, avoid horizontal scrolling.
