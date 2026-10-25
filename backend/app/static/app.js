/* ==========================================================================
   DocuLens front-end — vanilla JS rewrite of the previous React app.
   Same behaviour, same API calls, same look. No build step, no dependencies.
   All dynamic text is HTML-escaped before insertion (the old JSX did this
   automatically; here it is explicit).
   ========================================================================== */
(function () {
  'use strict';

  // ---------------------------------------------------------------- constants
  var STORAGE_KEY = 'doculens.chat.messages';
  var POLL_INTERVAL_MS = 2500;
  var MAX_POLL_MS = 10 * 60 * 1000;
  var ACCEPTED_EXTENSIONS = ['pdf', 'png', 'jpg', 'jpeg'];
  var MAX_FILE_BYTES = 25 * 1024 * 1024;
  var MAX_SOURCES = 2;
  var ANSWERABLE_STATUSES = ['ready', 'partially_processed'];
  var ACTIVE_STATUSES = ['waiting', 'processing'];
  var EXAMPLE_QUESTIONS = [
    'What is the main purpose of this document?',
    'What was the total revenue?',
    'What are the important risks?',
    'Summarize this document.'
  ];
  var STATUS_META = {
    waiting: { label: 'Waiting', cls: 'waiting' },
    processing: { label: 'Processing', cls: 'processing' },
    ready: { label: 'Ready', cls: 'ready' },
    partially_processed: { label: 'Partially processed', cls: 'partial' },
    failed: { label: 'Failed', cls: 'failed' }
  };
  var STATUS_TEXT = {
    waiting: 'Waiting in queue…',
    processing: 'Extracting text… Building search index…'
  };
  var IMAGE_EXTENSIONS = ['png', 'jpg', 'jpeg'];

  // -------------------------------------------------------------------- state
  var health = null;
  var documents = [];
  var messages = loadMessages();
  var selectedDocId = '';
  var chatLoading = false;
  var uploads = [];
  var expandedKeys = Object.create(null); // "msgId:index" -> true
  var copiedKey = null;
  var confirmingDeleteId = null;
  var pollDeadline = null;
  var pollTimer = null;
  var uploadSeq = 0;
  var msgSeq = 0;
  var toastSeq = 0;

  // summary panel state
  var summaryActiveMode = null;
  var summaryText = null;
  var summaryNotice = null;
  var summaryError = null;
  var summaryLoading = false;

  // ------------------------------------------------------------------- dom refs
  var el = {};
  function cacheDom() {
    el.health = document.getElementById('health');
    el.uploadZone = document.getElementById('upload-zone');
    el.browseBtn = document.getElementById('browse-btn');
    el.fileInput = document.getElementById('file-input');
    el.uploadList = document.getElementById('upload-list');
    el.docCount = document.getElementById('doc-count');
    el.documentsContainer = document.getElementById('documents-container');
    el.summaryPanel = document.getElementById('summary-panel');
    el.summaryDoc = document.getElementById('summary-doc');
    el.summaryBody = document.getElementById('summary-body');
    el.summaryButtons = document.querySelectorAll('.summary-btn');
    el.chatMessages = document.getElementById('chat-messages');
    el.docScopeWrap = document.getElementById('doc-scope-wrap');
    el.docScopeSelect = document.getElementById('doc-scope-select');
    el.questionInput = document.getElementById('question-input');
    el.askBtn = document.getElementById('ask-btn');
    el.toastContainer = document.getElementById('toast-container');
  }

  // ------------------------------------------------------------------- icons
  function svg(size, body) {
    return (
      '<svg width="' + size + '" height="' + size + '" viewBox="0 0 24 24" fill="none" ' +
      'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
      body + '</svg>'
    );
  }
  var ICON = {
    fileText: function (s) { return svg(s, '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M9 13h6"/><path d="M9 17h6"/>'); },
    fileImage: function (s) { return svg(s, '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><circle cx="9.5" cy="12.5" r="1.5"/><path d="m20 16-3.5-3.5L10 19"/>'); },
    alert: function (s) { return svg(s, '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4"/><path d="M12 17h.01"/>'); },
    check: function (s) { return svg(s, '<path d="M20 6 9 17l-5-5"/>'); },
    x: function (s) { return svg(s, '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>'); },
    trash: function (s) { return svg(s, '<path d="M3 6h18"/><path d="M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/><path d="M10 11v6"/><path d="M14 11v6"/>'); },
    chevronDown: function (s) { return svg(s, '<path d="m6 9 6 6 6-6"/>'); },
    chevronUp: function (s) { return svg(s, '<path d="m18 15-6-6-6 6"/>'); },
    copy: function (s) { return svg(s, '<rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>'); },
    checkCircle: function (s) { return svg(s, '<circle cx="12" cy="12" r="9"/><path d="m8.5 12.5 2.5 2.5 4.5-5"/>'); },
    xCircle: function (s) { return svg(s, '<circle cx="12" cy="12" r="9"/><path d="m15 9-6 6"/><path d="m9 9 6 6"/>'); },
    fileSearch: function (s) { return svg(s, '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h6"/><path d="M14 2v6h6"/><circle cx="16" cy="15" r="3"/><path d="m20.5 19.5 1.5 1.5"/>'); }
  };

  // ------------------------------------------------------------------ helpers
  function escapeHtml(value) {
    if (value === null || value === undefined) return '';
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }
  function includes(arr, v) { return arr.indexOf(v) !== -1; }
  function nextMsgId() { msgSeq += 1; return 'msg-' + Date.now() + '-' + msgSeq; }
  function extensionOf(name) {
    var parts = String(name).toLowerCase().split('.');
    return parts.length > 1 ? parts[parts.length - 1] : '';
  }
  function formatBytes(bytes) {
    if (bytes == null || isNaN(bytes)) return '';
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
  }
  function formatRelativeTime(iso) {
    if (!iso) return '';
    var then = new Date(iso);
    if (isNaN(then.getTime())) return '';
    var minutes = Math.floor((Date.now() - then.getTime()) / 60000);
    if (minutes < 1) return 'just now';
    if (minutes < 60) return minutes + ' min ago';
    var hours = Math.floor(minutes / 60);
    if (hours < 24) return hours + ' hr' + (hours > 1 ? 's' : '') + ' ago';
    var days = Math.floor(hours / 24);
    if (days < 7) return days + ' day' + (days > 1 ? 's' : '') + ' ago';
    return then.toLocaleDateString();
  }
  function errorDetail(err, fallback) {
    return (err && err.detail) || fallback;
  }
  function isImageDoc(doc) {
    var type = String(doc.file_type || '').toLowerCase();
    var name = String(doc.file_name || '').toLowerCase();
    return IMAGE_EXTENSIONS.some(function (ext) {
      return type.indexOf(ext) !== -1 || name.endsWith('.' + ext);
    });
  }
  function hasReadyDocument() {
    return documents.some(function (d) { return includes(ANSWERABLE_STATUSES, d.processing_status); });
  }
  function answerableDocs() {
    return documents.filter(function (d) { return includes(ANSWERABLE_STATUSES, d.processing_status); });
  }
  function scopeOf(message) {
    var ids = message.documentIds || [];
    return ids.length === 1 ? ids[0] : 'all';
  }
  function currentScope() { return selectedDocId || 'all'; }
  function visibleMessages() {
    var scope = currentScope();
    return messages.filter(function (m) { return scopeOf(m) === scope; });
  }

  // ------------------------------------------------------- message persistence
  function loadMessages() {
    try {
      var raw = sessionStorage.getItem(STORAGE_KEY);
      if (!raw) return [];
      var parsed = JSON.parse(raw);
      if (!Array.isArray(parsed)) return [];
      return parsed.filter(function (m) { return m && Array.isArray(m.documentIds); });
    } catch (e) {
      return [];
    }
  }
  function saveMessages() {
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(messages));
    } catch (e) {
      /* best-effort */
    }
  }

  // --------------------------------------------------------------------- api
  function parseError(res, bodyText) {
    var detail = null;
    try { detail = JSON.parse(bodyText).detail; } catch (e) { detail = null; }
    var err = new Error('HTTP ' + res.status);
    err.detail = typeof detail === 'string' ? detail : null;
    err.status = res.status;
    return err;
  }
  function apiGet(path) {
    return fetch('/api' + path).then(function (res) {
      return res.text().then(function (body) {
        if (!res.ok) throw parseError(res, body);
        return body ? JSON.parse(body) : null;
      });
    });
  }
  function apiPost(path, payload) {
    return fetch('/api' + path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    }).then(function (res) {
      return res.text().then(function (body) {
        if (!res.ok) throw parseError(res, body);
        return body ? JSON.parse(body) : null;
      });
    });
  }
  function apiDelete(path) {
    return fetch('/api' + path, { method: 'DELETE' }).then(function (res) {
      return res.text().then(function (body) {
        if (!res.ok) throw parseError(res, body);
        return body ? JSON.parse(body) : null;
      });
    });
  }
  function uploadFile(file, onProgress) {
    return new Promise(function (resolve, reject) {
      var form = new FormData();
      form.append('file', file);
      var xhr = new XMLHttpRequest();
      xhr.open('POST', '/api/documents/upload');
      xhr.upload.onprogress = function (e) {
        if (e.lengthComputable && onProgress) onProgress(Math.round((e.loaded / e.total) * 100));
      };
      xhr.onload = function () {
        if (xhr.status >= 200 && xhr.status < 300) {
          try { resolve(JSON.parse(xhr.responseText)); } catch (e) { resolve(null); }
        } else {
          var detail = null;
          try { detail = JSON.parse(xhr.responseText).detail; } catch (e) { detail = null; }
          var err = new Error('HTTP ' + xhr.status);
          err.detail = typeof detail === 'string' ? detail : null;
          reject(err);
        }
      };
      xhr.onerror = function () { reject(new Error('network')); };
      xhr.send(form);
    });
  }

  // ------------------------------------------------------------------- toasts
  function showToast(message, type) {
    type = type || 'error';
    toastSeq += 1;
    var id = 'toast-' + toastSeq;
    var node = document.createElement('div');
    node.className = 'toast toast-' + type;
    node.setAttribute('data-toast', id);
    node.innerHTML =
      (type === 'success' ? ICON.checkCircle(18) : ICON.xCircle(18)) +
      '<span class="toast-message">' + escapeHtml(message) + '</span>' +
      '<button type="button" class="toast-close" data-dismiss="' + id + '" aria-label="Dismiss notification">' + ICON.x(14) + '</button>';
    el.toastContainer.appendChild(node);
    setTimeout(function () { dismissToast(id); }, 5000);
  }
  function dismissToast(id) {
    var node = el.toastContainer.querySelector('[data-toast="' + id + '"]');
    if (node && node.parentNode) node.parentNode.removeChild(node);
  }

  // ------------------------------------------------------------------- health
  function renderHealth() {
    var html;
    if (!health || health.status === 'loading') {
      el.health.title = 'Checking backend status…';
      html = '<span class="health-dot health-dot-loading" aria-hidden="true"></span><span class="health-label">Checking…</span>';
    } else if (!health.ollama || health.status === 'unreachable') {
      el.health.title = 'Ollama or the backend is not available — answers will fail until it is running.';
      var label = health.status === 'unreachable' ? 'Backend offline' : 'Ollama unavailable';
      html = '<span class="health-dot health-dot-bad" aria-hidden="true"></span><span class="health-label">' + escapeHtml(label) + '</span>';
    } else {
      el.health.title = 'Chat model: ' + (health.chat_model || 'unknown') + '\nEmbedding model: ' + (health.embedding_model || 'unknown');
      html = '<span class="health-dot health-dot-ok" aria-hidden="true"></span><span class="health-label">Ollama connected</span>';
    }
    el.health.innerHTML = html;
  }
  function fetchHealth() {
    apiGet('/health')
      .then(function (data) { health = data; renderHealth(); })
      .catch(function () { health = { status: 'unreachable', ollama: false }; renderHealth(); });
  }

  // ---------------------------------------------------------------- documents
  function processingStatusHtml(doc) {
    var text = STATUS_TEXT[doc.processing_status] || 'Processing…';
    var ocr = doc.ocr_pages || 0;
    var suffix = ocr > 0 ? ' (' + ocr + ' OCR page' + (ocr > 1 ? 's' : '') + ')' : '';
    return '<p class="processing-status"><span class="spinner" aria-hidden="true"></span><span>' +
      escapeHtml(text + suffix) + '</span></p>';
  }
  function docCardHtml(doc) {
    var meta = STATUS_META[doc.processing_status] || { label: doc.processing_status, cls: 'waiting' };
    var icon = isImageDoc(doc) ? ICON.fileImage(20) : ICON.fileText(20);
    var confirming = confirmingDeleteId === doc.id;
    var side;
    if (!confirming) {
      side = '<button type="button" class="icon-btn icon-btn-danger" data-delete="' + escapeHtml(doc.id) +
        '" aria-label="Delete ' + escapeHtml(doc.file_name) + '" title="Delete document">' + ICON.trash(15) + '</button>';
    } else {
      side = '<span class="confirm-row">' +
        '<button type="button" class="icon-btn icon-btn-danger" data-confirm-delete="' + escapeHtml(doc.id) +
        '" aria-label="Confirm delete" title="Confirm delete">' + ICON.check(15) + '</button>' +
        '<button type="button" class="icon-btn" data-cancel-delete="' + escapeHtml(doc.id) +
        '" aria-label="Cancel delete" title="Cancel">' + ICON.x(15) + '</button>' +
        '</span>';
    }
    var metaBits = '<span>' + escapeHtml(formatBytes(doc.file_size)) + '</span>';
    if (doc.page_count != null) metaBits += '<span>' + escapeHtml(doc.page_count) + ' pages</span>';
    metaBits += '<span>' + escapeHtml(formatRelativeTime(doc.upload_time)) + '</span>';
    var errorLine = (doc.processing_status === 'failed' && doc.error_message)
      ? '<p class="doc-card-error">' + ICON.alert(13) + ' ' + escapeHtml(doc.error_message) + '</p>'
      : '';
    var processing = (doc.processing_status === 'waiting' || doc.processing_status === 'processing')
      ? processingStatusHtml(doc)
      : '';
    return '<article class="doc-card">' +
      '<span class="doc-card-icon" aria-hidden="true">' + icon + '</span>' +
      '<div class="doc-card-body">' +
        '<p class="doc-card-name" title="' + escapeHtml(doc.file_name) + '">' + escapeHtml(doc.file_name) + '</p>' +
        '<p class="doc-card-meta">' + metaBits + '</p>' +
        errorLine + processing +
      '</div>' +
      '<div class="doc-card-side">' +
        '<span class="badge badge-' + meta.cls + '"><span class="badge-dot" aria-hidden="true"></span>' + escapeHtml(meta.label) + '</span>' +
        side +
      '</div>' +
      '</article>';
  }
  function renderDocuments() {
    el.docCount.textContent = String(documents.length);
    if (documents.length === 0) {
      el.documentsContainer.innerHTML = '<p class="sidebar-empty">No documents yet.</p>';
      return;
    }
    el.documentsContainer.innerHTML =
      '<div class="document-list">' + documents.map(docCardHtml).join('') + '</div>';
  }

  function refreshDocuments(silent) {
    return apiGet('/documents')
      .then(function (data) {
        documents = data.documents || [];
        afterDocumentsChanged();
      })
      .catch(function (err) {
        if (!silent) showToast(errorDetail(err, 'Could not load the document list. Is the backend running?'), 'error');
      });
  }
  function afterDocumentsChanged() {
    // Drop the selection if the chosen document is gone or no longer answerable.
    var answerable = answerableDocs();
    if (selectedDocId && !answerable.some(function (d) { return d.id === selectedDocId; })) {
      selectedDocId = '';
    }
    renderDocuments();
    renderScope();
    renderSummaryPanel();
    updateAskButton();
    // Only redraw the chat region when it is showing the empty-state / chips
    // (no messages in scope); an active conversation is left untouched so its
    // scroll position and expanded sources survive background polling.
    if (visibleMessages().length === 0) renderChat(false);
    maybeSchedulePoll();
  }

  function maybeSchedulePoll() {
    var hasActive = documents.some(function (d) { return includes(ACTIVE_STATUSES, d.processing_status); });
    if (!hasActive) {
      pollDeadline = null;
      if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
      return;
    }
    if (pollDeadline === null) pollDeadline = Date.now() + MAX_POLL_MS;
    if (pollTimer) return;
    pollTimer = setInterval(function () {
      if (Date.now() >= pollDeadline) {
        clearInterval(pollTimer);
        pollTimer = null;
        pollDeadline = null;
        showToast('Document processing is taking longer than expected. Refresh to check its status.', 'error');
        return;
      }
      refreshDocuments(true);
    }, POLL_INTERVAL_MS);
  }

  // ------------------------------------------------------------------- uploads
  function renderUploads() {
    if (uploads.length === 0) { el.uploadList.innerHTML = ''; return; }
    el.uploadList.innerHTML = uploads.map(function (u) {
      var stateHtml = '';
      if (u.state === 'done') stateHtml = '<span class="upload-item-state ok">' + ICON.checkCircle(14) + ' Done</span>';
      else if (u.state === 'error') stateHtml = '<span class="upload-item-state bad">' + ICON.xCircle(14) + ' Failed</span>';
      else stateHtml = '<span class="upload-item-state">' + escapeHtml(u.progress) + '%</span>';
      var bar = u.state === 'uploading'
        ? '<div class="upload-progress" role="progressbar" aria-valuenow="' + escapeHtml(u.progress) +
          '" aria-valuemin="0" aria-valuemax="100"><div class="upload-progress-bar" style="width:' + escapeHtml(u.progress) + '%"></div></div>'
        : '';
      return '<li class="upload-item"><div class="upload-item-row">' +
        '<span class="upload-item-name" title="' + escapeHtml(u.name) + '">' + escapeHtml(u.name) + '</span>' +
        stateHtml + '</div>' + bar + '</li>';
    }).join('');
  }
  function findUpload(key) {
    for (var i = 0; i < uploads.length; i++) if (uploads[i].key === key) return uploads[i];
    return null;
  }
  function handleFiles(fileList) {
    var files = Array.prototype.slice.call(fileList || []);
    files.reduce(function (chain, file) {
      return chain.then(function () { return uploadOne(file); });
    }, Promise.resolve());
  }
  function uploadOne(file) {
    uploadSeq += 1;
    var key = file.name + '-' + file.size + '-' + Date.now() + '-' + uploadSeq + '-' + Math.random();
    if (!includes(ACCEPTED_EXTENSIONS, extensionOf(file.name))) {
      showToast('"' + file.name + '" is not supported. Accepted: PDF, PNG, JPG.', 'error');
      return Promise.resolve();
    }
    if (file.size > MAX_FILE_BYTES) {
      showToast('"' + file.name + '" is larger than 25 MB.', 'error');
      return Promise.resolve();
    }
    if (file.size === 0) {
      showToast('"' + file.name + '" is empty.', 'error');
      return Promise.resolve();
    }
    uploads.push({ key: key, name: file.name, progress: 0, state: 'uploading' });
    renderUploads();
    function dismiss() {
      setTimeout(function () {
        uploads = uploads.filter(function (u) { return u.key !== key; });
        renderUploads();
      }, 4000);
    }
    return uploadFile(file, function (pct) {
      var u = findUpload(key);
      if (u) { u.progress = pct; renderUploads(); }
    })
      .then(function () {
        var u = findUpload(key);
        if (u) { u.state = 'done'; u.progress = 100; }
        renderUploads();
        showToast('"' + file.name + '" uploaded', 'success');
        return refreshDocuments(true).then(dismiss);
      })
      .catch(function (err) {
        var detail = errorDetail(err, 'Upload of "' + file.name + '" failed.');
        var u = findUpload(key);
        if (u) { u.state = 'error'; u.error = detail; }
        renderUploads();
        showToast(detail, 'error');
        dismiss();
      });
  }

  // -------------------------------------------------------------------- chat
  function emptyStateHtml() {
    return '<div class="empty-state"><span class="empty-icon" aria-hidden="true">' + ICON.fileSearch(40) + '</span>' +
      '<h2 class="empty-title">Upload a document to begin.</h2>' +
      '<p class="empty-text">You can ask questions about its text, tables and important sections.</p></div>';
  }
  function chipsHtml() {
    var chips = EXAMPLE_QUESTIONS.map(function (q) {
      return '<button type="button" class="chip" data-chip="' + escapeHtml(q) + '">' + escapeHtml(q) + '</button>';
    }).join('');
    return '<div class="chips-block"><p class="chips-heading">Try asking:</p><div class="chips">' + chips + '</div></div>';
  }
  function sourceCardHtml(msgId, source, index) {
    var key = msgId + ':' + index;
    var expanded = !!expandedKeys[key];
    var section = source.section
      ? '<p class="source-section">' + escapeHtml(source.section) + '</p>'
      : '';
    var toggle = expanded
      ? ICON.chevronUp(13) + ' Show less'
      : ICON.chevronDown(13) + ' Show more';
    return '<article class="source-card">' +
      '<div class="source-card-header">' +
        '<span class="source-doc">' + ICON.fileText(14) + escapeHtml(source.document_name) + '</span>' +
        '<span class="source-page">Page ' + escapeHtml(source.page_number) + '</span>' +
      '</div>' + section +
      '<p class="source-excerpt' + (expanded ? ' expanded' : '') + '" data-toggle="' + escapeHtml(key) +
        '" role="button" tabindex="0" title="' + (expanded ? 'Click to collapse' : 'Click to expand') + '">' +
        escapeHtml(source.excerpt) + '</p>' +
      '<button type="button" class="source-toggle" data-toggle="' + escapeHtml(key) + '" aria-expanded="' + expanded + '">' + toggle + '</button>' +
      '</article>';
  }
  function messageHtml(m) {
    if (m.role === 'user') {
      return '<div class="chat-row chat-row-user"><p class="chat-bubble-user">' + escapeHtml(m.text) + '</p></div>';
    }
    var sources = (m.sources || []).slice(0, MAX_SOURCES);
    var copied = copiedKey === m.id;
    var copyBtn = '<button type="button" class="btn btn-quiet copy-btn" data-copy="' + escapeHtml(m.id) +
      '" title="Copy answer to clipboard">' + (copied ? ICON.check(14) : ICON.copy(14)) +
      (copied ? 'Copied' : 'Copy answer') + '</button>';
    var sourcesBlock = sources.length > 0
      ? '<div class="sources-block"><h3 class="sources-heading">Sources used for this answer</h3>' +
        sources.map(function (s, i) { return sourceCardHtml(m.id, s, i); }).join('') + '</div>'
      : '';
    return '<div class="chat-row chat-row-assistant"><div class="chat-msg">' +
      '<p class="answer-text">' + escapeHtml(m.text) + '</p>' +
      '<div class="chat-msg-footer">' + copyBtn + '</div>' +
      sourcesBlock +
      '</div></div>';
  }
  function loadingHtml() {
    return '<div class="chat-msg" aria-label="Loading answer" aria-busy="true"><div class="skeleton-msg">' +
      '<div class="skeleton-line" style="width:90%"></div>' +
      '<div class="skeleton-line" style="width:75%"></div>' +
      '<div class="skeleton-line" style="width:60%"></div>' +
      '</div></div>';
  }
  function renderChat(scrollToBottom) {
    var vm = visibleMessages();
    var html = '';
    if (vm.length === 0 && documents.length === 0) html += emptyStateHtml();
    if (vm.length === 0 && !chatLoading && hasReadyDocument()) html += chipsHtml();
    html += vm.map(messageHtml).join('');
    if (chatLoading) html += loadingHtml();
    el.chatMessages.innerHTML = html;
    if (scrollToBottom) {
      el.chatMessages.scrollTo({ top: el.chatMessages.scrollHeight, behavior: 'smooth' });
    }
  }
  function appendMessage(message) {
    messages.push(message);
    saveMessages();
    renderChat(true);
  }
  function setChatLoading(value) {
    chatLoading = value;
    renderChat(true);
    updateAskButton();
  }
  function removeMessagesForDocument(documentId) {
    if (!documentId) return;
    var before = messages.length;
    messages = messages.filter(function (m) {
      return (m.documentIds || []).indexOf(documentId) === -1;
    });
    if (messages.length !== before) saveMessages();
  }

  function ask(question) {
    var scope = selectedDocId ? [selectedDocId] : [];
    appendMessage({
      id: nextMsgId(), role: 'user', text: question, documentIds: scope,
      createdAt: new Date().toISOString()
    });
    setChatLoading(true);
    apiPost('/chat', { question: question, document_ids: scope })
      .then(function (data) {
        appendMessage({
          id: nextMsgId(), role: 'assistant', question: question, text: data.answer,
          documentIds: scope, evidenceStatus: data.evidence_status,
          sources: (data.sources || []).slice(0, MAX_SOURCES),
          verification: data.verification || null,
          createdAt: data.created_at || new Date().toISOString()
        });
      })
      .catch(function (err) {
        showToast(errorDetail(err, 'The answer service could not be reached. Please try again.'), 'error');
      })
      .then(function () {
        setChatLoading(false);
      });
  }
  function submitQuestion() {
    var text = el.questionInput.value.trim();
    if (!text || chatLoading || !hasReadyDocument()) return;
    ask(text);
    el.questionInput.value = '';
    updateAskButton();
  }

  // ------------------------------------------------------------- scope select
  function renderScope() {
    var answerable = answerableDocs();
    if (answerable.length === 0) {
      el.docScopeWrap.hidden = true;
      return;
    }
    el.docScopeWrap.hidden = false;
    var options = '<option value="">All documents</option>' + answerable.map(function (d) {
      return '<option value="' + escapeHtml(d.id) + '">' + escapeHtml(d.file_name) + '</option>';
    }).join('');
    el.docScopeSelect.innerHTML = options;
    el.docScopeSelect.value = selectedDocId;
    el.docScopeSelect.disabled = chatLoading;
  }

  function updateAskButton() {
    var empty = el.questionInput.value.trim().length === 0;
    var ready = hasReadyDocument();
    var disabled = empty || chatLoading || !ready;
    el.askBtn.disabled = disabled;
    var reason = '';
    if (chatLoading) reason = 'Waiting for the current answer to finish…';
    else if (!ready) reason = 'Ask is available once a document finishes processing.';
    else if (empty) reason = 'Type a question first.';
    el.askBtn.title = reason || 'Ask (Ctrl+Enter)';
  }

  // ------------------------------------------------------------------ summary
  function summaryEligibleDoc() {
    for (var i = 0; i < documents.length; i++) {
      if (includes(ANSWERABLE_STATUSES, documents[i].processing_status)) return documents[i];
    }
    return null;
  }
  function renderSummaryPanel() {
    var doc = summaryEligibleDoc();
    if (!doc) { el.summaryPanel.hidden = true; return; }
    el.summaryPanel.hidden = false;
    el.summaryDoc.textContent = doc.file_name;
    el.summaryDoc.title = doc.file_name;
    Array.prototype.forEach.call(el.summaryButtons, function (btn) {
      btn.classList.toggle('active', btn.getAttribute('data-mode') === summaryActiveMode);
      btn.disabled = summaryLoading;
    });
    var body = '';
    if (summaryLoading) {
      body = '<div class="skeleton-msg summary-skeleton" aria-label="Loading summary">' +
        '<div class="skeleton-line" style="width:95%"></div>' +
        '<div class="skeleton-line" style="width:80%"></div>' +
        '<div class="skeleton-line" style="width:65%"></div></div>';
    } else if (summaryError) {
      body = '<p class="summary-error">' + escapeHtml(summaryError) + '</p>';
    } else if (summaryText) {
      var notice = summaryNotice ? '<p class="summary-notice" role="status">' + escapeHtml(summaryNotice) + '</p>' : '';
      body = '<div class="summary-card">' + notice + '<p class="summary-text">' + escapeHtml(summaryText) + '</p></div>';
    }
    el.summaryBody.innerHTML = body;
  }
  function loadSummary(mode) {
    var doc = summaryEligibleDoc();
    if (!doc) return;
    summaryActiveMode = mode;
    summaryLoading = true;
    summaryError = null;
    renderSummaryPanel();
    apiGet('/documents/' + encodeURIComponent(doc.id) + '/summary?mode=' + encodeURIComponent(mode))
      .then(function (data) {
        summaryText = data.summary;
        summaryNotice = data.warning || (data.truncated ? 'Summary covers only the first part of this document.' : null);
      })
      .catch(function (err) {
        summaryText = null;
        summaryNotice = null;
        summaryError = errorDetail(err, 'Could not generate the summary.');
      })
      .then(function () {
        summaryLoading = false;
        renderSummaryPanel();
      });
  }

  // --------------------------------------------------------------- delete flow
  function handleDelete(id) {
    confirmingDeleteId = id;
    renderDocuments();
    apiDelete('/documents/' + encodeURIComponent(id))
      .then(function () {
        return refreshDocuments(true);
      })
      .then(function () {
        removeMessagesForDocument(id);
        if (selectedDocId === id) selectedDocId = '';
        renderScope();
        renderChat(false);
        showToast('Document deleted', 'success');
      })
      .catch(function (err) {
        showToast(errorDetail(err, 'Could not delete the document.'), 'error');
      })
      .then(function () {
        confirmingDeleteId = null;
        renderDocuments();
      });
  }

  // ------------------------------------------------------------------ events
  function wireEvents() {
    // health is fetched on init; upload zone
    el.uploadZone.addEventListener('click', function () { el.fileInput.click(); });
    el.uploadZone.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); el.fileInput.click(); }
    });
    el.browseBtn.addEventListener('click', function (e) { e.stopPropagation(); el.fileInput.click(); });
    el.uploadZone.addEventListener('dragover', function (e) { e.preventDefault(); el.uploadZone.classList.add('dragging'); });
    el.uploadZone.addEventListener('dragleave', function () { el.uploadZone.classList.remove('dragging'); });
    el.uploadZone.addEventListener('drop', function (e) {
      e.preventDefault();
      el.uploadZone.classList.remove('dragging');
      handleFiles(e.dataTransfer.files);
    });
    el.fileInput.addEventListener('change', function (e) {
      handleFiles(e.target.files);
      e.target.value = '';
    });

    // documents: delete / confirm / cancel (delegated)
    el.documentsContainer.addEventListener('click', function (e) {
      var del = e.target.closest('[data-delete]');
      var confirm = e.target.closest('[data-confirm-delete]');
      var cancel = e.target.closest('[data-cancel-delete]');
      if (del) { confirmingDeleteId = del.getAttribute('data-delete'); renderDocuments(); return; }
      if (confirm) { handleDelete(confirm.getAttribute('data-confirm-delete')); return; }
      if (cancel) { confirmingDeleteId = null; renderDocuments(); return; }
    });

    // summary mode buttons
    Array.prototype.forEach.call(el.summaryButtons, function (btn) {
      btn.addEventListener('click', function () { loadSummary(btn.getAttribute('data-mode')); });
    });

    // scope select
    el.docScopeSelect.addEventListener('change', function () {
      selectedDocId = el.docScopeSelect.value;
      renderChat(true);
    });

    // question input
    el.questionInput.addEventListener('input', updateAskButton);
    el.questionInput.addEventListener('keydown', function (e) {
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { e.preventDefault(); submitQuestion(); }
    });
    el.askBtn.addEventListener('click', submitQuestion);

    // chat region: chips, copy, source expand (delegated)
    el.chatMessages.addEventListener('click', function (e) {
      var chip = e.target.closest('[data-chip]');
      if (chip) { el.questionInput.value = chip.getAttribute('data-chip'); updateAskButton(); el.questionInput.focus(); return; }
      var copy = e.target.closest('[data-copy]');
      if (copy) { doCopy(copy.getAttribute('data-copy')); return; }
      var toggle = e.target.closest('[data-toggle]');
      if (toggle) { toggleSource(toggle.getAttribute('data-toggle')); return; }
    });
    el.chatMessages.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.key === ' ') {
        var toggle = e.target.closest && e.target.closest('[data-toggle]');
        if (toggle && toggle.classList.contains('source-excerpt')) {
          e.preventDefault();
          toggleSource(toggle.getAttribute('data-toggle'));
        }
      }
    });

    // toasts: dismiss (delegated)
    el.toastContainer.addEventListener('click', function (e) {
      var btn = e.target.closest('[data-dismiss]');
      if (btn) dismissToast(btn.getAttribute('data-dismiss'));
    });
  }
  function doCopy(msgId) {
    var msg = null;
    for (var i = 0; i < messages.length; i++) if (messages[i].id === msgId) { msg = messages[i]; break; }
    if (!msg) return;
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(msg.text)
        .then(function () {
          copiedKey = msgId;
          renderChat(false);
          setTimeout(function () {
            if (copiedKey === msgId) { copiedKey = null; renderChat(false); }
          }, 2000);
        })
        .catch(function () { showToast('Could not copy to the clipboard.', 'error'); });
    } else {
      showToast('Could not copy to the clipboard.', 'error');
    }
  }
  function toggleSource(key) {
    if (expandedKeys[key]) delete expandedKeys[key];
    else expandedKeys[key] = true;
    renderChat(false);
  }

  // -------------------------------------------------------------------- init
  function init() {
    cacheDom();
    renderHealth();
    renderDocuments();
    renderScope();
    renderChat(false);
    updateAskButton();
    wireEvents();
    fetchHealth();
    refreshDocuments(false);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
