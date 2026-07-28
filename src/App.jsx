
import React, { useEffect, useRef, useState } from 'react';

const MAX_UPLOAD_FILES = 5;
const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;

// Shown before a key is entered (and if the live model list can't be fetched).
// The "-latest" aliases always resolve to a current model, so they never 404.
const FALLBACK_MODELS = [
  { id: 'gemini-flash-latest', label: 'Gemini Flash (latest)' },
  { id: 'gemini-flash-lite-latest', label: 'Gemini Flash-Lite (latest)' },
  { id: 'gemini-pro-latest', label: 'Gemini Pro (latest)' },
  { id: 'gemini-2.5-flash', label: 'Gemini 2.5 Flash' },
];

function getSessionId() {
  const existing = window.localStorage.getItem('rag_session_id');
  if (existing) return existing;
  const generated = `session-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
  window.localStorage.setItem('rag_session_id', generated);
  return generated;
}

function validatePdfFiles(files) {
  const selected = Array.from(files || []);
  if (selected.length === 0) return 'Select at least one PDF file.';
  if (selected.length > MAX_UPLOAD_FILES) return `Upload up to ${MAX_UPLOAD_FILES} PDF files at a time.`;

  const invalid = selected.find((file) => !file.name.toLowerCase().endsWith('.pdf') || (file.type && file.type !== 'application/pdf'));
  if (invalid) return 'Only PDF files can be uploaded.';

  const oversized = selected.find((file) => file.size > MAX_UPLOAD_BYTES);
  if (oversized) return `${oversized.name} exceeds the 10 MB upload limit.`;

  return '';
}

function App() {
  const [sessionId] = useState(getSessionId);
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [sampleQuestions, setSampleQuestions] = useState([]);
  const [indexStatus, setIndexStatus] = useState({ indexed: false, total_chunks: 0, files: [] });
  const [activeCitation, setActiveCitation] = useState(null);
  const [showSettingsKey, setShowSettingsKey] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState('');
  const [uploadSuccess, setUploadSuccess] = useState('');
  const [isDragging, setIsDragging] = useState(false);

  const [apiKey, setApiKey] = useState(() => window.localStorage.getItem('rag_api_key') || '');
  const [keyStatus, setKeyStatus] = useState('');
  const [model, setModel] = useState('gemini-2.5-flash');
  const [availableModels, setAvailableModels] = useState(FALLBACK_MODELS);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [mode, setMode] = useState('classic');
  const [topK, setTopK] = useState(5);
  const [useFilter, setUseFilter] = useState(true);
  const [useExpansion, setUseExpansion] = useState(true);

  const citationRefs = useRef({});
  const fileInputRef = useRef(null);

  useEffect(() => {
    fetchIndexStatus();
    fetchSampleQuestions();
    if (apiKey) fetchModels(apiKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Populate the model dropdown from the user's own key, so it never goes stale
  // as Google rotates models. Falls back to FALLBACK_MODELS on any failure.
  const fetchModels = async (key) => {
    const useKey = (key ?? apiKey).trim();
    if (!useKey) return; // no key yet -> keep the fallback list
    setModelsLoading(true);
    try {
      const res = await fetch('/api/models', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ api_key: useKey }),
      });
      const data = await res.json();
      if (res.ok && Array.isArray(data.models) && data.models.length) {
        setAvailableModels(data.models);
        // If the current selection is no longer offered, drop to the first available.
        setModel((current) =>
          data.models.some((m) => m.id === current) ? current : data.models[0].id,
        );
      }
    } catch (e) {
      console.error('Failed to load model list; using fallback', e);
    } finally {
      setModelsLoading(false);
    }
  };

  const sessionQuery = () => `session_id=${encodeURIComponent(sessionId)}`;

  const fetchIndexStatus = async () => {
    try {
      const res = await fetch(`/api/index-status?${sessionQuery()}`);
      const data = await res.json();
      setIndexStatus(data);
    } catch (e) {
      console.error('Failed to fetch indexing status', e);
    }
  };

  const fetchSampleQuestions = async () => {
    try {
      const res = await fetch(`/api/sample-questions?${sessionQuery()}`);
      const data = await res.json();
      setSampleQuestions(data);
    } catch (e) {
      console.error('Failed to fetch sample questions', e);
    }
  };

  const handlePdfUpload = async (files) => {
    setUploadError('');
    setUploadSuccess('');

    const validationError = validatePdfFiles(files);
    if (validationError) {
      setUploadError(validationError);
      return;
    }

    const formData = new FormData();
    formData.append('session_id', sessionId);
    Array.from(files).forEach((file) => formData.append('files', file));

    setUploading(true);
    try {
      const res = await fetch('/api/upload-pdfs', {
        method: 'POST',
        body: formData,
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Upload failed.');
      }

      const names = (data.uploaded_files || []).map((file) => file.name).join(', ');
      setUploadSuccess(`${names} indexed and ready for questions.`);
      if (fileInputRef.current) fileInputRef.current.value = '';
      await Promise.all([fetchIndexStatus(), fetchSampleQuestions()]);
    } catch (e) {
      setUploadError(e.message || 'Upload failed. Try another PDF.');
    } finally {
      setUploading(false);
      setIsDragging(false);
    }
  };

  const handleDrop = (event) => {
    event.preventDefault();
    event.stopPropagation();
    setIsDragging(false);
    handlePdfUpload(event.dataTransfer.files);
  };

  const handleSaveKey = async () => {
    const key = apiKey.trim();
    if (!key) {
      setKeyStatus('Enter a key first.');
      return;
    }
    // Model B: the key lives in THIS browser and is sent with each query.
    // It is never stored on the server (the serverless filesystem is read-only,
    // and a shared server key would leak between users on a public deployment).
    window.localStorage.setItem('rag_api_key', key);
    setKeyStatus('Saved in this browser — used for your queries.');
    fetchModels(key); // refresh the model list for this key
    // Optional: ask the backend to sanity-check the key shape (it does NOT store it).
    try {
      await fetch('/api/save-key', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ api_key: key }),
      });
    } catch (e) {
      // Non-fatal: the key still works client-side even if this ping fails.
      console.error('Key validation ping failed', e);
    }
  };

  const handleClearKey = () => {
    setApiKey('');
    window.localStorage.removeItem('rag_api_key');
    setKeyStatus('Key cleared from this browser.');
  };

  const handleSubmit = async (e, customQuery = null) => {
    if (e) e.preventDefault();
    const searchQuery = customQuery || query;
    if (!searchQuery.trim() || loading) return;

    setLoading(true);
    setResult(null);
    setActiveCitation(null);

    try {
      const res = await fetch('/api/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: searchQuery,
          session_id: sessionId,
          model,
          mode,
          top_k: topK,
          use_filter: useFilter,
          use_expansion: useExpansion,
          api_key: apiKey || undefined,
        }),
      });
      const data = await res.json();
      setResult(data);
    } catch (err) {
      console.error('RAG Query request failed', err);
      setResult({ error: 'Failed to communicate with RAG backend. Verify backend is running.' });
    } finally {
      setLoading(false);
    }
  };

  const handleSampleClick = (qText) => {
    setQuery(qText);
    handleSubmit(null, qText);
  };

  const handleCitationClick = (source, page) => {
    const cardId = `${source}_p${page}`;
    setActiveCitation(cardId);
    const element = citationRefs.current[cardId];
    if (element) element.scrollIntoView({ behavior: 'smooth', block: 'center' });
  };

  const renderAnswerWithCitations = (text) => {
    if (!text) return null;
    const citationRegex = /\[([a-zA-Z0-9\-. _]+),\s*(?:[pP]age\s*)?([0-9]+)\]/g;
    const parts = [];
    let lastIndex = 0;
    let match;

    while ((match = citationRegex.exec(text)) !== null) {
      if (match.index > lastIndex) parts.push(text.substring(lastIndex, match.index));
      const source = match[1].trim();
      const page = match[2];
      parts.push(
        <span
          key={match.index}
          className="citation-link"
          onClick={() => handleCitationClick(source, page)}
          title={`Click to view source: ${source}, Page ${page}`}
        >
          {match[0]}
        </span>,
      );
      lastIndex = citationRegex.lastIndex;
    }

    if (lastIndex < text.length) parts.push(text.substring(lastIndex));
    return parts.map((part, idx) => {
      if (typeof part !== 'string') return part;
      const lines = part.split('\n');
      return lines.map((line, lineIdx) => (
        <React.Fragment key={`${idx}-${lineIdx}`}>
          {line}
          {lineIdx < lines.length - 1 && <br />}
        </React.Fragment>
      ));
    });
  };

  return (
    <div className="app-container">
      <aside className="sidebar">
        <div className="brand-section">
          <div className="brand-logo">Sg</div>
          <div>
            <h1 className="brand-name">SgCare Retrieval</h1>
            <div className="brand-subtitle">RAG Pipeline Engine</div>
          </div>
        </div>

        <div className="upload-section">
          <span className="section-label">Upload PDFs</span>
          <div
            className={`upload-drop-zone ${isDragging ? 'dragging' : ''}`}
            data-testid="pdf-drop-zone"
            onDragOver={(event) => {
              event.preventDefault();
              setIsDragging(true);
            }}
            onDragLeave={() => setIsDragging(false)}
            onDrop={handleDrop}
          >
            <input
              ref={fileInputRef}
              id="pdf-upload-input"
              className="upload-input"
              type="file"
              accept="application/pdf,.pdf"
              multiple
              aria-label="Upload PDF files"
              onChange={(event) => handlePdfUpload(event.target.files)}
              disabled={uploading}
            />
            <label className="upload-label" htmlFor="pdf-upload-input">
              <span className="upload-icon">PDF</span>
              <span>{uploading ? 'Indexing PDFs...' : 'Drop PDFs here or choose files'}</span>
              <small>Session-only indexing, up to 5 files / 10 MB each.</small>
            </label>
          </div>
          {uploadError && (
            <div className="upload-message error" role="alert">
              {uploadError}
            </div>
          )}
          {uploadSuccess && <div className="upload-message success">{uploadSuccess}</div>}
        </div>

        <div className="nav-section document-section">
          <span className="section-label">Indexed Documents</span>
          <div className="document-list">
            {indexStatus.files.map((file) => (
              <div key={`${file.name}-${file.uploaded ? 'uploaded' : 'base'}`} className={`doc-card ${file.uploaded ? 'uploaded' : file.name.includes('briefing') ? 'orange' : ''}`}>
                <div className="doc-name" title={file.name}>{file.name}</div>
                <div className="doc-meta">
                  <span>{file.pages} pages</span>
                  <span className="doc-badge">{file.uploaded ? 'Uploaded' : file.size}</span>
                </div>
              </div>
            ))}
            {indexStatus.files.length === 0 && (
              <div className="loader-container compact-loader">
                <div className="spinner small-spinner"></div>
                <span>Extracting PDF text...</span>
              </div>
            )}
          </div>
        </div>

        <div className="settings-box">
          <span className="section-label">Pipeline Settings</span>

          <div className="setting-row">
            <label>Gemini API Key</label>
            <div className="setting-inline">
              <input
                type={showSettingsKey ? 'text' : 'password'}
                className="setting-input"
                placeholder="Paste your Gemini API key"
                value={apiKey}
                onChange={(e) => { setApiKey(e.target.value); setKeyStatus(''); }}
              />
              <button type="button" className="icon-btn" onClick={() => setShowSettingsKey(!showSettingsKey)} title="Toggle API key visibility">
                {showSettingsKey ? 'Hide' : 'Show'}
              </button>
            </div>
            <small className="setting-hint">
              Stored only in this browser and sent with each query. Get a key from Google AI Studio.
            </small>
            {apiKey && (
              <div className="setting-inline">
                <button type="button" className="alert-btn small-action" onClick={handleSaveKey}>
                  Save key
                </button>
                <button type="button" className="icon-btn" onClick={handleClearKey} title="Remove key from this browser">
                  Clear
                </button>
              </div>
            )}
            {keyStatus && <div className="upload-message success">{keyStatus}</div>}
          </div>

          <div className="setting-row">
            <label>Reasoning Mode</label>
            <select className="setting-select" value={mode} onChange={(e) => setMode(e.target.value)}>
              <option value="classic">Classic RAG (Strict Grounding)</option>
              <option value="auditor">Auditor Mode (Confidential Focus)</option>
              <option value="cot">Chain-of-Thought (Step Reasoning)</option>
            </select>
          </div>

          <div className="setting-row">
            <label>Gemini Model {modelsLoading ? '(updating…)' : ''}</label>
            <select className="setting-select" value={model} onChange={(e) => setModel(e.target.value)}>
              {availableModels.map((m) => (
                <option key={m.id} value={m.id}>{m.label}</option>
              ))}
            </select>
            <small className="setting-hint">
              {apiKey
                ? 'Live list from your key — retired models are dropped automatically.'
                : 'Save your API key to load the models it can call.'}
            </small>
          </div>

          <div className="setting-row">
            <label>Retrieve chunks (K)</label>
            <select className="setting-select" value={topK} onChange={(e) => setTopK(Number(e.target.value))}>
              <option value={3}>Top 3 pages</option>
              <option value={5}>Top 5 pages</option>
              <option value={7}>Top 7 pages</option>
              <option value={10}>Top 10 pages</option>
            </select>
          </div>

          <div className="toggle-container">
            <span>Query Expansion</span>
            <label className="switch">
              <input type="checkbox" checked={useExpansion} onChange={(e) => setUseExpansion(e.target.checked)} />
              <span className="slider"></span>
            </label>
          </div>

          <div className="toggle-container">
            <span>Relevance Filtering</span>
            <label className="switch">
              <input type="checkbox" checked={useFilter} onChange={(e) => setUseFilter(e.target.checked)} />
              <span className="slider"></span>
            </label>
          </div>
        </div>
      </aside>

      <main className="main-workspace">
        <header className="dashboard-header">
          <div className="header-title-container">
            <h1>Document Operations Workspace</h1>
            <p>Ask questions across shipped AAC documents and session-uploaded PDFs</p>
          </div>
          <div className="system-status">
            <span className="status-dot"></span>
            <span>{uploading ? 'Indexing Upload' : 'RAG Engine Ready'}</span>
          </div>
        </header>

        <div className="workspace-panels">
          <div className="query-panel">
            {!result && !loading && (
              <div className="welcome-hero">
                <div className="welcome-logo">PDF</div>
                <h2>Ask Any Indexed PDF</h2>
                <p>
                  Upload a new PDF or use the existing knowledgebase, then ask grounded questions with cited source pages.
                </p>

                <span className="section-label sample-heading">Suggested Inquiries</span>

                <div className="samples-grid">
                  {sampleQuestions.map((sq) => (
                    <button
                      type="button"
                      key={sq.id}
                      className="sample-question-card"
                      onClick={() => handleSampleClick(sq.question)}
                    >
                      <span className="sample-category">{sq.category}</span>
                      <span className="sample-title">{sq.question}</span>
                      <span className="sample-desc">{sq.description}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {loading && (
              <div className="loader-container">
                <div className="spinner"></div>
                <h3>Synthesizing response from indexed PDFs...</h3>
                <p className="loader-detail">Running retrieval, optional expansion, relevance filtering, and grounded generation.</p>
              </div>
            )}

            {result && !loading && (
              <div className="chat-output-container">
                {result.queries && result.queries.length > 1 && (
                  <div className="expanded-queries-box">
                    <div className="queries-title">Query Expansion</div>
                    <div className="queries-list">
                      {result.queries.map((q, idx) => (
                        <div key={q} className={`query-chip ${idx === 0 ? 'active' : ''}`}>
                          {idx === 0 ? 'Original: ' : 'Exp: '} {q}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {result.api_key_required && (
                  <div className="alert-banner">
                    <div className="alert-message">
                      <strong>API Key Required:</strong> The RAG engine retrieved {result.context?.length || 0} matching pages, but needs a Gemini API key to generate a finalized answer.
                    </div>
                  </div>
                )}

                {result.thought_process && (
                  <div className="thought-process-container">
                    <div className="thought-header">
                      <div className="thought-title">Reasoning Process</div>
                    </div>
                    <div className="thought-body">{result.thought_process}</div>
                  </div>
                )}

                {result.answer && (
                  <div className="rag-response-card">
                    <div className="response-header">
                      <div className="response-title-container">
                        <div className="response-icon">R</div>
                        <div>
                          <div className="response-title">Grounded Document Synthesis</div>
                          <div className="response-meta">Verified matching {result.context?.length || 0} cited pages</div>
                        </div>
                      </div>
                      <div className="response-meta">Model: <span>{result.model || model}</span></div>
                    </div>
                    <div className="response-body">{renderAnswerWithCitations(result.answer)}</div>
                  </div>
                )}

                {result.error && (
                  <div className="alert-banner error-banner">
                    <div className="alert-message error-text"><strong>Query Execution Error:</strong> {result.error}</div>
                  </div>
                )}
              </div>
            )}
          </div>

          <div className="search-input-panel">
            <form className="search-form" onSubmit={handleSubmit}>
              <input
                type="text"
                className="search-input"
                placeholder="Ask about indexed or uploaded PDFs..."
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                disabled={loading}
              />
              <button
                type="submit"
                className="search-submit-btn"
                disabled={!query.trim() || loading}
                title="Search knowledgebase"
              >
                Go
              </button>
            </form>
          </div>

          <div className="citations-panel">
            <div className="citations-panel-header">
              <h2 className="citations-panel-title">Cited Document Pages</h2>
              <p className="citations-panel-desc">
                {result && result.context && result.context.length > 0
                  ? 'Top retrieved pages evaluated by relevance filter'
                  : 'References will appear here after search'}
              </p>
            </div>

            <div className="citations-list">
              {result && result.context && result.context.map((c) => {
                const cardId = `${c.source}_p${c.page}`;
                const isOrange = c.source.includes('briefing');
                const isUploaded = indexStatus.files.some((file) => file.uploaded && file.name === c.source);
                const isActive = activeCitation === cardId;

                return (
                  <div
                    key={c.id}
                    ref={(el) => { citationRefs.current[cardId] = el; }}
                    className={`citation-card ${isOrange ? 'orange' : ''} ${isUploaded ? 'uploaded' : ''} ${isActive ? 'active' : ''}`}
                    onClick={() => setActiveCitation(isActive ? null : cardId)}
                  >
                    <div className="citation-header">
                      <div className="citation-doc" title={c.source}>{c.source}</div>
                      <div className="citation-page">Page {c.page}</div>
                    </div>
                    <div className="citation-snippet">{c.text}</div>
                  </div>
                );
              })}

              {(!result || !result.context || result.context.length === 0) && (
                <div className="empty-citations">
                  No active queries. Execute a search or click a sample question to retrieve context.
                </div>
              )}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}

export default App;
