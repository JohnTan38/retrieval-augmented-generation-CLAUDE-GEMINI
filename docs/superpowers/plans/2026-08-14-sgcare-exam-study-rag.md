# SgCare SWK501 Exam-Study RAG Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the existing generic Vite PDF tool with a low-latency, citation-first SWK501 exam-study workspace that indexes exactly three fixed model-answer PDFs and deploys safely to the existing GitHub/Vercel application.

**Architecture:** A Next.js 16/React 19 Evidence Desk calls a same-origin FastAPI gateway. Offline Python ingestion creates a versioned gzip artifact containing page-aware chunks, BM25 statistics, and normalized Gemini embeddings; runtime retrieval fuses lexical and dense rankings in memory and streams grounded Gemini output with validated source markers.

**Tech Stack:** Next.js 16, React 19, TypeScript, Tailwind CSS, Motion, Lucide, React Markdown, FastAPI, Pydantic, Google GenAI SDK, PyMuPDF, Vitest, Testing Library, axe, pytest, Playwright, isolated RAG quality evaluation, Vercel Fluid Compute and Firewall.

**Spec:** `docs/superpowers/specs/2026-08-14-sgcare-exam-study-rag-design.md`

## Global Constraints

- Index exactly the three approved SWK501 PDFs: January 2025 (26 pages), July 2025 (36 pages), and January 2026 (27 pages), totaling 89 pages.
- Do not index the master prompt template or system-architecture prompt.
- Do not support visitor uploads, visitor API keys, model selection, retrieval controls, saved conversations, or chain-of-thought display.
- Keep `GEMINI_API_KEY` server-only; never print, serialize, expose, or commit it.
- Use the default Node/Python Fluid Compute runtime; do not add an Edge runtime declaration.
- Keep runtime retrieval project-owned and lightweight; do not add ChromaDB, LangChain, a cross-encoder, or an external vector database.
- Verify current Next.js and Google GenAI APIs from installed official docs/source before writing code that depends on them.
- Apply test-driven development: every production behavior begins with a failing focused test, then minimal implementation, then refactor under green tests.
- Enforce 100% statements, branches, functions, and lines for project-owned Python/TypeScript logic, excluding generated artifacts, framework/configuration entrypoints, declaration files, and CSS.
- Preserve the dirty `C:\Users\admin\rag` checkout; work only in the isolated `rag-upgrade` clone and branch `agent/sgcare-exam-study-rag`.
- Keep each commit scoped to one independently testable plan task.

## Planned File Structure

```text
app/
  error.tsx
  globals.css
  layout.tsx
  not-found.tsx
  page.tsx
api/
  index.py
backend/
  __init__.py
  app.py
  citation.py
  config.py
  gemini_client.py
  index_store.py
  models.py
  prompts.py
  retrieval.py
  service.py
components/
  AnswerSurface.tsx
  CorpusStrip.tsx
  EvidenceRibbon.tsx
  QueryComposer.tsx
  SourceCard.tsx
  StatusBanner.tsx
  StudyWorkspace.tsx
data/
  corpus-manifest.json
  index/
    swk501-v1.json.gz
docs/superpowers/
  plans/2026-08-14-sgcare-exam-study-rag.md
  specs/2026-08-14-sgcare-exam-study-rag-design.md
e2e/
  accessibility.spec.ts
  downloads.spec.ts
  production-smoke.spec.ts
  workspace.spec.ts
evaluation/
  golden-queries.json
  quality.py
  run_quality.py
ingestion/
  __init__.py
  __main__.py
  artifact.py
  chunker.py
  embeddings.py
  indexer.py
  manifest.py
  models.py
  parser.py
lib/
  api/stream.ts
  api/types.ts
  corpus.ts
  markdown.tsx
  sample-queries.ts
public/documents/
  swk501-Jan2025-evidence-based-model-answers.pdf
  swk501-July2025-deep-research-model-answers.pdf
  swk501-Jan2026-deep-research-model-answers.pdf
tests/
  backend/
  ingestion/
  retrieval/
  ui/
  conftest.py
eslint.config.mjs
next.config.ts
package.json
playwright.config.ts
postcss.config.mjs
pytest.ini
requirements-dev.txt
requirements-eval.txt
requirements.txt
tsconfig.json
vercel.json
vitest.config.ts
vitest.setup.ts
```

### Task 1: Clean Repository and Establish the Next.js Test Harness

**Files:**
- Modify: `.gitignore`
- Replace: `package.json`, `package-lock.json`, `tsconfig.json`, `vercel.json`
- Create: `app/layout.tsx`, `app/page.tsx`, `app/globals.css`, `components/StudyWorkspace.tsx`
- Create: `next.config.ts`, `postcss.config.mjs`, `eslint.config.mjs`, `vitest.config.ts`, `vitest.setup.ts`, `playwright.config.ts`
- Create: `tests/ui/app-shell.test.tsx`
- Remove from Git: `dist/**`, `node_modules/**`, `src/**`, `index.html`, `vite.config.js`, `vitest.config.js`, `vitest.setup.js`, obsolete `public/assets/**`, tracked Python caches and `backend/.env.local`

**Interfaces:**
- Produces: `StudyWorkspace(): JSX.Element`, the stable top-level client component used by `app/page.tsx`.
- Produces: npm scripts `dev`, `build`, `start`, `lint`, `typecheck`, `test`, `test:coverage`, `test:e2e`, `test:python`, `test:retrieval`, `test:quality`, and `check`.

- [ ] **Step 1: Remove tracked generated/secret-prone artifacts from the isolated clone**

Run explicit `git rm` commands only inside `C:\Users\admin\john-tan-presentation\rag-upgrade`:

```powershell
git rm -r --cached node_modules dist backend\__pycache__
git rm -r src public\assets
git rm index.html vite.config.js vitest.config.js vitest.setup.js backend\.env.local
```

Expected: the paths are staged for deletion in this feature branch; the original `C:\Users\admin\rag` worktree is unchanged.

- [ ] **Step 2: Expand `.gitignore` before any dependency installation**

Use this content:

```gitignore
node_modules/
.next/
dist/
coverage/
playwright-report/
test-results/
.pytest_cache/
.coverage
htmlcov/
__pycache__/
*.py[cod]
.env
.env.*
!.env.example
.vercel/
.superpowers/
tmp/
```

- [ ] **Step 3: Install the approved frontend and test dependencies**

Run:

```powershell
npm install next@^16 react@^19 react-dom@^19 lucide-react motion react-markdown remark-gfm rehype-sanitize tailwindcss @tailwindcss/postcss
npm install --save-dev typescript @types/node @types/react @types/react-dom eslint eslint-config-next vitest @vitest/coverage-v8 jsdom @testing-library/react @testing-library/jest-dom @testing-library/user-event @playwright/test @axe-core/playwright
```

Expected: `package-lock.json` pins the actual resolved versions.

- [ ] **Step 4: Read the installed Next.js guides before creating framework files**

Run:

```powershell
rg -n "App Router|Route Handlers|Streaming|headers|metadata|Server Components" node_modules\next\dist\docs
```

Read the matched official guides for App Router file conventions, Server/Client boundaries, metadata, error handling, and streaming. Record any version-specific constraints in the task notes before coding.

- [ ] **Step 5: Write the failing app-shell test**

Create `tests/ui/app-shell.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { StudyWorkspace } from '@/components/StudyWorkspace'

test('introduces the SWK501 evidence workspace without upload or key controls', () => {
  render(<StudyWorkspace />)

  expect(screen.getByRole('heading', { name: /sgcare study desk/i })).toBeVisible()
  expect(screen.getByText(/swk501 evidence workspace/i)).toBeVisible()
  expect(screen.queryByText(/upload pdf/i)).not.toBeInTheDocument()
  expect(screen.queryByLabelText(/api key/i)).not.toBeInTheDocument()
})
```

- [ ] **Step 6: Run the test and confirm the correct failure**

Run: `npm test -- tests/ui/app-shell.test.tsx`

Expected: FAIL because `@/components/StudyWorkspace` does not exist.

- [ ] **Step 7: Add the minimal Next.js app shell and test configuration**

Create `components/StudyWorkspace.tsx` with the exact initial contract:

```tsx
'use client'

export function StudyWorkspace() {
  return (
    <main>
      <h1>SgCare Study Desk</h1>
      <p>SWK501 evidence workspace</p>
    </main>
  )
}
```

Create `app/page.tsx` to render `StudyWorkspace`, `app/layout.tsx` with English metadata and optimized fonts, and the minimal CSS/config files required by the installed Next.js version. Configure Vitest aliases, jsdom, setup, and coverage exclusions exactly as approved by the spec.

- [ ] **Step 8: Run the narrow test and framework checks**

Run:

```powershell
npm test -- tests/ui/app-shell.test.tsx
npm run typecheck
npm run lint
```

Expected: the test passes; typecheck and lint exit 0.

- [ ] **Step 9: Commit the foundation**

```powershell
git add .gitignore package.json package-lock.json tsconfig.json next.config.ts postcss.config.mjs eslint.config.mjs vitest.config.ts vitest.setup.ts playwright.config.ts app components tests/ui/app-shell.test.tsx
git add -u
git commit -m "chore: establish clean Next.js workspace"
```

### Task 2: Add the Canonical Corpus Manifest and Verified Downloads

**Files:**
- Create: `public/documents/swk501-Jan2025-evidence-based-model-answers.pdf`
- Create: `public/documents/swk501-July2025-deep-research-model-answers.pdf`
- Create: `public/documents/swk501-Jan2026-deep-research-model-answers.pdf`
- Create: `data/corpus-manifest.json`
- Create: `ingestion/__init__.py`, `ingestion/models.py`, `ingestion/manifest.py`
- Create: `tests/ingestion/test_manifest.py`, `tests/conftest.py`
- Replace: `requirements.txt`, `requirements-dev.txt`, `pytest.ini`

**Interfaces:**
- Produces: `CorpusDocument` and `CorpusManifest` Pydantic models.
- Produces: `load_manifest(path: Path, documents_dir: Path) -> CorpusManifest`.
- Produces: manifest document IDs `jan-2025`, `jul-2025`, `jan-2026` and immutable download URLs.

- [ ] **Step 1: Copy the three approved PDFs into the isolated clone**

Run:

```powershell
New-Item -ItemType Directory -Force -Path public\documents | Out-Null
Copy-Item -LiteralPath 'C:\Users\admin\OneDrive\Documents\gdsw\swk501\swk501-jul-2025\swk501-Jan2025-evidence-based-model-answers.pdf' -Destination 'public\documents\swk501-Jan2025-evidence-based-model-answers.pdf'
Copy-Item -LiteralPath 'C:\Users\admin\OneDrive\Documents\gdsw\swk501\swk501-jul-2025\swk501-July2025-deep-research-model-answers.pdf' -Destination 'public\documents\swk501-July2025-deep-research-model-answers.pdf'
Copy-Item -LiteralPath 'C:\Users\admin\OneDrive\Documents\gdsw\swk501\swk501-jan-2026\swk501-Jan2026-deep-research-model-answers.pdf' -Destination 'public\documents\swk501-Jan2026-deep-research-model-answers.pdf'
```

Expected: only these three PDFs exist under `public/documents`.

- [ ] **Step 2: Install the approved Python runtime and test dependencies**

Set `requirements.txt` to:

```text
fastapi>=0.116,<1
pydantic>=2.11,<3
google-genai>=1.30,<2
pymupdf>=1.26,<2
uvicorn>=0.35,<1
```

Set `requirements-dev.txt` to:

```text
-r requirements.txt
httpx>=0.28,<1
pytest>=9,<10
pytest-asyncio>=1,<2
pytest-cov>=7,<8
```

Install with:

```powershell
python -m pip install -r requirements-dev.txt
```

- [ ] **Step 3: Write the failing manifest integrity test**

Create `tests/ingestion/test_manifest.py`:

```python
from pathlib import Path

import pytest

from ingestion.manifest import load_manifest


ROOT = Path(__file__).resolve().parents[2]


def test_manifest_contains_the_exact_approved_corpus():
    manifest = load_manifest(
        ROOT / "data" / "corpus-manifest.json",
        ROOT / "public" / "documents",
    )

    assert [doc.document_id for doc in manifest.documents] == [
        "jan-2025",
        "jul-2025",
        "jan-2026",
    ]
    assert [doc.pages for doc in manifest.documents] == [26, 36, 27]
    assert sum(doc.pages for doc in manifest.documents) == 89
    assert {doc.download_url for doc in manifest.documents} == {
        "/documents/swk501-Jan2025-evidence-based-model-answers.pdf",
        "/documents/swk501-July2025-deep-research-model-answers.pdf",
        "/documents/swk501-Jan2026-deep-research-model-answers.pdf",
    }


def test_manifest_rejects_a_checksum_mismatch(tmp_path: Path):
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        '{"schema_version":1,"corpus_version":"test","documents":['
        '{"document_id":"bad","filename":"bad.pdf","title":"Bad",'
        '"semester":"Test","pages":1,"sha256":"' + "0" * 64 + '",'
        '"download_url":"/documents/bad.pdf","topics":["test"]}]}',
        encoding="utf-8",
    )
    documents = tmp_path / "documents"
    documents.mkdir()
    (documents / "bad.pdf").write_bytes(b"%PDF-not-the-expected-file")

    with pytest.raises(ValueError, match="checksum"):
        load_manifest(manifest_path, documents)
```

- [ ] **Step 4: Run and verify the manifest test fails**

Run: `python -m pytest tests/ingestion/test_manifest.py -q`

Expected: FAIL because `ingestion.manifest` does not exist.

- [ ] **Step 5: Implement the manifest models, real SHA-256 values, and validation**

`CorpusDocument` must contain `document_id`, `filename`, `title`, `semester`, `pages`, `sha256`, `download_url`, and non-empty `topics`. `load_manifest` must reject duplicate IDs/filenames, unsafe filenames, extra or missing PDFs, checksum mismatch, and page-count mismatch. Populate the manifest with the three exact documents and checksums computed from the copied bytes.

- [ ] **Step 6: Run manifest and coverage checks**

Run:

```powershell
python -m pytest tests/ingestion/test_manifest.py --cov=ingestion.manifest --cov=ingestion.models --cov-report=term-missing --cov-fail-under=100
```

Expected: PASS with 100% coverage for the two implemented modules.

- [ ] **Step 7: Commit the canonical corpus**

```powershell
git add public/documents data/corpus-manifest.json ingestion tests/ingestion/test_manifest.py tests/conftest.py requirements.txt requirements-dev.txt pytest.ini
git commit -m "feat: add verified SWK501 corpus manifest"
```

### Task 3: Implement Page-Aware Parsing and Stable Semantic Chunking

**Files:**
- Create: `ingestion/parser.py`, `ingestion/chunker.py`
- Extend: `ingestion/models.py`
- Create: `tests/ingestion/test_parser.py`, `tests/ingestion/test_chunker.py`

**Interfaces:**
- Produces: `PageText(document_id: str, page: int, text: str)`.
- Produces: `ChunkRecord(chunk_id: str, document_id: str, filename: str, semester: str, page: int, text: str, topics: tuple[str, ...])`.
- Produces: `extract_pages(pdf_path: Path, document_id: str) -> list[PageText]`.
- Produces: `chunk_pages(document: CorpusDocument, pages: Sequence[PageText], target_words: int = 650, overlap_words: int = 90) -> list[ChunkRecord]`.

- [ ] **Step 1: Write failing parser tests**

```python
def test_extract_pages_preserves_one_based_page_numbers(corpus_paths):
    pages = extract_pages(corpus_paths["jan-2026"], "jan-2026")
    assert len(pages) == 27
    assert pages[0].page == 1
    assert pages[-1].page == 27
    assert "emotion" in " ".join(page.text.lower() for page in pages)


def test_extract_pages_rejects_an_empty_page(monkeypatch, tmp_path):
    monkeypatch.setattr(parser, "_read_pdf_pages", lambda _: [""])
    with pytest.raises(ValueError, match="extractable text"):
        extract_pages(tmp_path / "empty.pdf", "empty")
```

- [ ] **Step 2: Run parser tests and verify the missing-module failure**

Run: `python -m pytest tests/ingestion/test_parser.py -q`

Expected: FAIL because `ingestion.parser` is absent.

- [ ] **Step 3: Implement minimal page extraction and normalization**

Use PyMuPDF. Normalize repeated spaces and excessive blank lines, preserve meaningful paragraph boundaries, and reject missing/empty pages. Do not merge page content.

- [ ] **Step 4: Write failing chunking tests**

```python
def test_chunks_have_stable_ids_and_never_cross_pages(jan_2026_document, jan_2026_pages):
    first = chunk_pages(jan_2026_document, jan_2026_pages)
    second = chunk_pages(jan_2026_document, jan_2026_pages)

    assert [chunk.chunk_id for chunk in first] == [chunk.chunk_id for chunk in second]
    assert all(chunk.document_id == "jan-2026" for chunk in first)
    assert all(1 <= chunk.page <= 27 for chunk in first)
    assert all(chunk.text.strip() for chunk in first)


def test_adjacent_chunks_overlap_without_being_duplicates(document, long_page):
    chunks = chunk_pages(document, [long_page], target_words=120, overlap_words=20)
    assert len(chunks) > 1
    assert set(chunks[0].text.split()[-20:]) <= set(chunks[1].text.split()[:40])
    assert chunks[0].text != chunks[1].text
```

- [ ] **Step 5: Run chunking tests and verify failure**

Run: `python -m pytest tests/ingestion/test_chunker.py -q`

Expected: FAIL because `chunk_pages` is absent.

- [ ] **Step 6: Implement deterministic page-local chunking**

Prefer paragraph boundaries, fall back to sentence/word boundaries, target 650 words, overlap 90 words, and derive IDs as `sha256(corpus_version|document_id|page|ordinal|text)[:24]`. Keep every chunk within one PDF page so citations cannot drift.

- [ ] **Step 7: Run ingestion coverage**

Run:

```powershell
python -m pytest tests/ingestion/test_parser.py tests/ingestion/test_chunker.py --cov=ingestion --cov-report=term-missing --cov-fail-under=100
```

Expected: PASS at 100% for implemented ingestion logic.

- [ ] **Step 8: Commit parsing and chunking**

```powershell
git add ingestion tests/ingestion
git commit -m "feat: parse and chunk SWK501 sources"
```

### Task 4: Build the Versioned Hybrid Index Artifact

**Files:**
- Create: `ingestion/embeddings.py`, `ingestion/artifact.py`, `ingestion/indexer.py`, `ingestion/__main__.py`
- Create: `data/index/swk501-v1.json.gz`
- Create: `tests/ingestion/test_embeddings.py`, `tests/ingestion/test_artifact.py`, `tests/ingestion/test_indexer.py`

**Interfaces:**
- Consumes: `ChunkRecord` from Task 3.
- Produces: `Embedder.embed_documents(texts: Sequence[str]) -> list[list[float]]`.
- Produces: `IndexArtifact(schema_version, corpus_version, embedding_model, embedding_dimensions, documents, chunks, bm25)`.
- Produces: `build_index(manifest_path: Path, documents_dir: Path, output_path: Path, embedder: Embedder) -> IndexArtifact`.
- Produces CLI: `python -m ingestion --manifest data/corpus-manifest.json --documents public/documents --output data/index/swk501-v1.json.gz`.

- [ ] **Step 1: Write failing embedding and artifact tests**

```python
class FakeEmbedder:
    model = "fake-embedding"

    def embed_documents(self, texts):
        return [[float(len(text)), 1.0] for text in texts]


def test_build_index_writes_a_deterministic_gzip_artifact(tmp_path, corpus_manifest):
    first = tmp_path / "first.json.gz"
    second = tmp_path / "second.json.gz"

    one = build_index(corpus_manifest.path, corpus_manifest.documents_dir, first, FakeEmbedder())
    two = build_index(corpus_manifest.path, corpus_manifest.documents_dir, second, FakeEmbedder())

    assert one.model_dump(mode="json") == two.model_dump(mode="json")
    assert one.corpus_version == "swk501-v1"
    assert one.embedding_dimensions == 2
    assert len(one.documents) == 3
    assert first.read_bytes() == second.read_bytes()


def test_embedder_rejects_inconsistent_dimensions():
    with pytest.raises(ValueError, match="dimensions"):
        normalize_embeddings([[1.0, 0.0], [1.0]])
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m pytest tests/ingestion/test_embeddings.py tests/ingestion/test_artifact.py tests/ingestion/test_indexer.py -q`

Expected: FAIL because the artifact modules are absent.

- [ ] **Step 3: Implement batching, vector normalization, BM25 data, and deterministic gzip output**

The artifact must store normalized vectors, tokenized term frequencies, document frequencies, average document length, stable chunk records, document metadata, model ID, dimensions, schema version, and corpus version. Gzip output must set `mtime=0` and use stable JSON key ordering.

- [ ] **Step 4: Add the real Google embedder behind the `Embedder` protocol**

Read the installed `google-genai` package docs/source for current embedding calls. Send batches, use the retrieval-document task contract, validate response count/dimensions, retry only transient status codes with bounded backoff, and never log input text or the API key.

- [ ] **Step 5: Run unit coverage with the fake embedder**

Run:

```powershell
python -m pytest tests/ingestion --cov=ingestion --cov-report=term-missing --cov-fail-under=100
```

Expected: PASS at 100% for project-owned ingestion logic without a network call.

- [ ] **Step 6: Pull the server-managed environment locally without printing it**

Link the isolated clone to the existing `rag` Vercel project and pull development variables to ignored `.env.local`:

```powershell
vercel link --project rag --yes
vercel env pull .env.local --yes
```

Check only whether `GEMINI_API_KEY` is present; do not print its value.

- [ ] **Step 7: Build and validate the real index artifact**

Load the pulled key into the current process without printing it, run the index CLI, then remove it from the process:

```powershell
$geminiLine = Get-Content -LiteralPath '.env.local' | Where-Object { $_ -match '^GEMINI_API_KEY=' } | Select-Object -First 1
if (-not $geminiLine) { throw 'GEMINI_API_KEY is missing from .env.local' }
$env:GEMINI_API_KEY = $geminiLine.Substring('GEMINI_API_KEY='.Length).Trim().Trim('"')
python -m ingestion --manifest data/corpus-manifest.json --documents public/documents --output data/index/swk501-v1.json.gz
Remove-Item Env:GEMINI_API_KEY
```

Run an artifact inspection command that prints only corpus version, model ID, dimensions, document count, page count, and chunk count.

Expected: 3 documents, 89 pages, nonzero chunks, consistent embedding dimensions, and a valid `data/index/swk501-v1.json.gz`.

- [ ] **Step 8: Commit the index pipeline and artifact**

```powershell
git add ingestion tests/ingestion data/index/swk501-v1.json.gz
git commit -m "feat: build immutable hybrid corpus index"
```

### Task 5: Implement In-Memory Hybrid Retrieval and Golden Benchmarks

**Files:**
- Create: `backend/__init__.py`, `backend/models.py`, `backend/index_store.py`, `backend/retrieval.py`
- Create: `evaluation/golden-queries.json`
- Create: `tests/retrieval/test_index_store.py`, `tests/retrieval/test_bm25.py`, `tests/retrieval/test_fusion.py`, `tests/retrieval/test_golden_queries.py`

**Interfaces:**
- Consumes: `IndexArtifact` from Task 4.
- Produces: `SourceEvidence(source_id, chunk_id, document_id, filename, title, semester, page, excerpt, score, download_url)`.
- Produces: `IndexStore.load(path: Path) -> IndexStore`, cached once per warm process.
- Produces: `HybridRetriever.search(query: str, query_vector: Sequence[float] | None, top_k: int = 5) -> list[SourceEvidence]`.

- [ ] **Step 1: Write failing retrieval unit tests**

```python
def test_rrf_promotes_results_present_in_both_rankings():
    fused = reciprocal_rank_fusion(
        lexical=["a", "b", "c"],
        dense=["b", "d", "a"],
        k=60,
    )
    assert fused[0].chunk_id == "b"
    assert {item.chunk_id for item in fused[:2]} == {"a", "b"}


def test_hybrid_retriever_uses_lexical_results_when_vector_is_unavailable(index_store):
    results = HybridRetriever(index_store).search("Arnett emerging adulthood", None, top_k=3)
    assert len(results) == 3
    assert all(result.score > 0 for result in results)
```

- [ ] **Step 2: Run and verify retrieval tests fail**

Run: `python -m pytest tests/retrieval/test_index_store.py tests/retrieval/test_bm25.py tests/retrieval/test_fusion.py -q`

Expected: FAIL because backend retrieval modules do not exist.

- [ ] **Step 3: Implement safe artifact loading and project-owned BM25/cosine/RRF**

Reject unknown schema versions, checksum drift, dimension mismatch, empty artifacts, unsafe download URLs, and duplicate chunk IDs. BM25 tokenization must be deterministic and domain-aware. Dense similarity operates over normalized vectors. RRF uses `k=60`; diversity selection suppresses overlapping chunks from the same page before returning five sources.

- [ ] **Step 4: Add explicit golden queries for every major corpus domain**

`evaluation/golden-queries.json` must include at least these IDs and expected document IDs:

```json
[
  {"id":"max-ppct","query":"Apply Bronfenbrenner PPCT to Max's adolescent delinquency","expected_documents":["jan-2025"]},
  {"id":"tan-arnett","query":"How does Arnett emerging adulthood explain the Tan family?","expected_documents":["jul-2025"]},
  {"id":"multiple-intelligence","query":"Compare Gardner, Sternberg and traditional IQ","expected_documents":["jul-2025"]},
  {"id":"emotion-coaching","query":"Contrast emotion coaching and emotion dismissing for a two-year-old","expected_documents":["jan-2026"]},
  {"id":"marcia","query":"Explain Marcia identity status theory","expected_documents":["jan-2026"]},
  {"id":"cognitive-ageing","query":"Distinguish cognitive mechanics and pragmatics in ageing","expected_documents":["jan-2026"]},
  {"id":"baltes-soc","query":"Apply Baltes selection optimisation compensation to active ageing","expected_documents":["jan-2026"]}
]
```

Each record also stores at least one expected topic/page range derived from the actual artifact inspection.

- [ ] **Step 5: Write and run the failing golden benchmark**

The test embeds each golden query with a deterministic fixture vector or a committed query-vector fixture and asserts an expected document appears within the first three results. First run must fail until retrieval thresholds and domain token normalization are correct.

- [ ] **Step 6: Tune only retrieval constants, then run full retrieval coverage and timing**

Run:

```powershell
python -m pytest tests/retrieval --cov=backend.index_store --cov=backend.retrieval --cov=backend.models --cov-report=term-missing --cov-fail-under=100
python -m pytest tests/retrieval/test_golden_queries.py -q --durations=10
```

Expected: all golden queries pass; local hot retrieval remains within the benchmark budget recorded by the test on the current machine.

- [ ] **Step 7: Commit retrieval**

```powershell
git add backend evaluation/golden-queries.json tests/retrieval
git commit -m "feat: add low-latency hybrid retrieval"
```

### Task 6: Build the Secure FastAPI Streaming Gateway

**Files:**
- Create: `backend/config.py`, `backend/citation.py`, `backend/prompts.py`, `backend/gemini_client.py`, `backend/service.py`, `backend/app.py`
- Replace: `api/index.py`, `vercel.json`
- Create: `tests/backend/test_health.py`, `tests/backend/test_corpus.py`, `tests/backend/test_query_validation.py`, `tests/backend/test_streaming.py`, `tests/backend/test_failures.py`, `tests/backend/test_citations.py`, `tests/backend/test_security.py`

**Interfaces:**
- Consumes: `HybridRetriever` and `SourceEvidence` from Task 5.
- Produces: `QueryRequest(query: str)` with forbidden additional fields.
- Produces: `GeminiClient.embed_query(query: str) -> list[float]`.
- Produces: `GeminiClient.stream_answer(query: str, sources: Sequence[SourceEvidence]) -> AsyncIterator[str]`.
- Produces: `RagService.stream_query(query: str, request_id: str) -> AsyncIterator[ServerSentEvent]`.
- Produces routes `GET /api/health`, `GET /api/corpus`, and `POST /api/query`.

- [ ] **Step 1: Write failing health and corpus endpoint tests**

```python
def test_health_reports_the_ready_89_page_index(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {
        "ready": True,
        "schema_version": 1,
        "corpus_version": "swk501-v1",
        "documents": 3,
        "pages": 89,
    }


def test_corpus_exposes_three_safe_downloads(client):
    response = client.get("/api/corpus")
    assert response.status_code == 200
    documents = response.json()["documents"]
    assert len(documents) == 3
    assert all(doc["download_url"].startswith("/documents/") for doc in documents)
    assert all("sha256" in doc for doc in documents)
```

- [ ] **Step 2: Run endpoint tests and verify failure**

Run: `python -m pytest tests/backend/test_health.py tests/backend/test_corpus.py -q`

Expected: FAIL because `backend.app` is absent.

- [ ] **Step 3: Implement configuration, dependency injection, health, and corpus routes**

Configuration reads and validates server-only environment values lazily. App construction accepts injected index, retriever, and Gemini client so tests never need the network. Missing/invalid index makes health return `ready: false` and query return a safe 503.

- [ ] **Step 4: Write failing validation and streaming tests**

```python
def test_query_rejects_unknown_controls(client):
    response = client.post("/api/query", json={"query": "Arnett", "model": "attacker-choice"})
    assert response.status_code == 422


def test_query_streams_sources_before_tokens(client):
    with client.stream("POST", "/api/query", json={"query": "Explain Arnett"}) as response:
        events = list(parse_sse(response.iter_text()))

    assert response.headers["content-type"].startswith("text/event-stream")
    assert [event.name for event in events] == ["sources", "token", "token", "complete"]
    assert events[0].data["sources"][0]["source_id"] == "S1"
    assert events[-1].data["citation_valid"] is True
```

- [ ] **Step 5: Run the query tests and verify failure**

Run: `python -m pytest tests/backend/test_query_validation.py tests/backend/test_streaming.py -q`

Expected: FAIL because query behavior is not implemented.

- [ ] **Step 6: Implement the prompt, Gemini adapter, service, citation validation, and SSE route**

Use exact event names `sources`, `token`, `complete`, and `error`. Source IDs are assigned after final retrieval ordering. Validate citations with `\[S([1-9][0-9]*)\]` against supplied IDs. The system prompt enforces educational scope, evidence-only answering, Singapore-context evidence, nondeterminism, no diagnosis, no document/user instruction execution, and no hidden reasoning.

Read installed Google GenAI SDK docs/source before using streaming or cancellation APIs. The adapter uses one current pinned query-embedding model and one current pinned low-latency streaming generation model. It passes credentials through SDK configuration, not URLs, and maps provider errors to safe internal codes.

- [ ] **Step 7: Add failure, cancellation, secret, and sanitization tests**

Cover embedding fallback, weak evidence, generation timeout, provider failure after sources, disconnect cancellation, malformed JSON, incorrect content type, empty/oversized/control-character query, additional fields, missing key, and absence of secrets/provider payloads from responses and captured logs.

- [ ] **Step 8: Configure Vercel Python routing and security headers**

`api/index.py` exports the FastAPI app. `vercel.json` keeps the Python function in `sin1`, excludes tests/evaluation/source PDFs from its bundle when safe, and rewrites the backend route prefix without shadowing Next static assets. `next.config.ts` adds CSP, HSTS for production, `X-Content-Type-Options`, frame protection, referrer policy, and permissions policy.

- [ ] **Step 9: Run backend coverage and an SSE smoke request**

Run:

```powershell
python -m pytest tests/backend tests/retrieval --cov=backend --cov-report=term-missing --cov-fail-under=100
```

Start Uvicorn with test configuration, request `/api/health`, `/api/corpus`, and a mocked `/api/query` stream, then stop the process.

Expected: all tests pass at 100%; SSE ordering is sources-first.

- [ ] **Step 10: Commit the gateway**

```powershell
git add backend api vercel.json next.config.ts tests/backend
git commit -m "feat: stream grounded RAG responses"
```

### Task 7: Build the Evidence Desk Corpus and Initial Experience

**Files:**
- Create: `lib/api/types.ts`, `lib/corpus.ts`, `lib/sample-queries.ts`
- Create/modify: `components/CorpusStrip.tsx`, `components/QueryComposer.tsx`, `components/StatusBanner.tsx`, `components/StudyWorkspace.tsx`
- Modify: `app/page.tsx`, `app/layout.tsx`, `app/globals.css`
- Create: `tests/ui/corpus-strip.test.tsx`, `tests/ui/query-composer.test.tsx`, `tests/ui/initial-workspace.test.tsx`

**Interfaces:**
- Produces: TypeScript `CorpusDocument`, `CorpusResponse`, `SourceEvidence`, `StreamEvent`, and `WorkspaceState` types matching the API.
- Produces: `loadPublicCorpus(): CorpusDocument[]`, a server-only typed JSON-manifest reader used by `app/page.tsx`.
- Produces: `CorpusStrip({ documents }: { documents: CorpusDocument[] })`.
- Produces: `QueryComposer({ disabled, onSubmit }: QueryComposerProps)`.

- [ ] **Step 1: Write failing corpus and composer tests**

```tsx
test('shows and downloads the three semester documents', () => {
  render(<CorpusStrip documents={corpusFixture} />)
  expect(screen.getAllByRole('link', { name: /download/i })).toHaveLength(3)
  expect(screen.getByText('January 2025')).toBeVisible()
  expect(screen.getByText('July 2025')).toBeVisible()
  expect(screen.getByText('January 2026')).toBeVisible()
})


test('submits a trimmed study question and blocks empty input', async () => {
  const onSubmit = vi.fn()
  render(<QueryComposer disabled={false} onSubmit={onSubmit} />)
  const button = screen.getByRole('button', { name: /find evidence/i })
  expect(button).toBeDisabled()
  await userEvent.type(screen.getByRole('textbox'), '  Explain Arnett  ')
  await userEvent.click(button)
  expect(onSubmit).toHaveBeenCalledWith('Explain Arnett')
})
```

- [ ] **Step 2: Run and verify failing tests**

Run: `npm test -- tests/ui/corpus-strip.test.tsx tests/ui/query-composer.test.tsx tests/ui/initial-workspace.test.tsx`

Expected: FAIL because the components/types are absent.

- [ ] **Step 3: Implement the initial Evidence Desk components and server data fetch**

`app/page.tsx` reads corpus metadata server-side through `loadPublicCorpus()` and supplies it to `StudyWorkspace`; it must not issue a self-fetch during build. The initial client state contains the approved heading, 3-document/89-page readiness, semester cards, exact downloads, one prominent query composer, and curated sample queries. Remove every upload, API-key, model, reasoning, top-k, and pipeline-control surface.

- [ ] **Step 4: Implement the approved visual tokens and glass hierarchy**

Use CSS variables for Cloud `#F7FBFF`, Ink `#15243A`, Meridian teal `#0E7C7B`, Seminar blue `#5377DC`, Session amber `#F3B64A`, and muted text `#687891`. Restrict backdrop blur to navigation, answer, and evidence surfaces. Include visible focus rings, contrast-safe text, responsive typography, and `prefers-reduced-motion` rules.

- [ ] **Step 5: Run focused UI tests, typecheck, and lint**

Run:

```powershell
npm test -- tests/ui/corpus-strip.test.tsx tests/ui/query-composer.test.tsx tests/ui/initial-workspace.test.tsx
npm run typecheck
npm run lint
```

Expected: all exit 0.

- [ ] **Step 6: Commit the initial Evidence Desk**

```powershell
git add app components lib tests/ui
git commit -m "feat: create SWK501 Evidence Desk"
```

### Task 8: Add Streamed Answers, Citation Thread, and Evidence Ribbon

**Files:**
- Create: `lib/api/stream.ts`, `lib/markdown.tsx`
- Create: `components/AnswerSurface.tsx`, `components/EvidenceRibbon.tsx`, `components/SourceCard.tsx`
- Modify: `components/StudyWorkspace.tsx`, `components/QueryComposer.tsx`, `app/globals.css`
- Create: `tests/ui/stream-parser.test.ts`, `tests/ui/answer-surface.test.tsx`, `tests/ui/evidence-ribbon.test.tsx`, `tests/ui/workspace-flow.test.tsx`, `tests/ui/workspace-errors.test.tsx`

**Interfaces:**
- Produces: `parseEventStream(response: Response, signal?: AbortSignal) -> AsyncGenerator<StreamEvent>`.
- Produces: `AnswerSurface({ answer, citedSourceIds, status }: AnswerSurfaceProps)`.
- Produces: `EvidenceRibbon({ sources, activeSourceId, onSelect }: EvidenceRibbonProps)`.
- Produces: `StudyWorkspace` state machine `idle | retrieving | streaming | complete | no-evidence | degraded | rate-limited | provider-error | offline | cancelled`.

- [ ] **Step 1: Write the failing stream parser test**

```ts
test('parses events split across arbitrary network chunks', async () => {
  const response = responseFromChunks([
    'event: sources\ndata: {"sources":[{"source_id":"S1"}]}\n',
    '\nevent: token\ndata: {"delta":"Arnett"}\n\n',
    'event: complete\ndata: {"citation_valid":true}\n\n',
  ])

  const events = []
  for await (const event of parseEventStream(response)) events.push(event)

  expect(events.map((event) => event.type)).toEqual(['sources', 'token', 'complete'])
})
```

- [ ] **Step 2: Run and verify parser failure**

Run: `npm test -- tests/ui/stream-parser.test.ts`

Expected: FAIL because `parseEventStream` is absent.

- [ ] **Step 3: Implement the defensive streaming parser**

Handle UTF-8 boundaries, comments/heartbeats, multi-line data, incomplete terminal chunks, unknown events, invalid JSON, response errors, aborts, and missing body. Unknown events are ignored; protocol errors produce a typed safe client error.

- [ ] **Step 4: Write failing answer/evidence interaction tests**

```tsx
test('citation activation focuses the matching source and exposes its exact page link', async () => {
  render(<CompletedWorkspaceFixture />)
  await userEvent.click(screen.getByRole('button', { name: /source s1/i }))

  const source = screen.getByTestId('source-S1')
  expect(source).toHaveAttribute('data-active', 'true')
  expect(within(source).getByRole('link', { name: /open exact page/i })).toHaveAttribute(
    'href',
    '/documents/swk501-July2025-deep-research-model-answers.pdf#page=9',
  )
})
```

- [ ] **Step 5: Run and verify component failures**

Run: `npm test -- tests/ui/answer-surface.test.tsx tests/ui/evidence-ribbon.test.tsx tests/ui/workspace-flow.test.tsx tests/ui/workspace-errors.test.tsx`

Expected: FAIL because streamed workspace components are absent.

- [ ] **Step 6: Implement the workspace state machine and source-first rendering**

Post only `{ query }`; process `sources` before `token`; retain sources on generation failure; concatenate token deltas; validate completion metadata; abort prior requests when starting a new query; provide retry and cancel actions; announce state changes in a polite live region. Do not render raw HTML.

- [ ] **Step 7: Implement sanitized Markdown and citation controls**

Use React Markdown, GFM, and an explicit sanitize schema. Convert only `[S<number>]` markers that exist in the current source set into accessible citation buttons. Unknown markers remain text and show an integrity warning when completion says citations are invalid.

- [ ] **Step 8: Implement the responsive evidence ribbon and mobile bottom sheet**

Desktop shows ranked glass source cards. Mobile uses an accessible labelled dialog/sheet, traps focus while open, restores focus on close, and responds to Escape. Activating a citation scrolls/focuses its source card without unexpected page navigation.

- [ ] **Step 9: Run UI coverage, typecheck, and lint**

Run:

```powershell
npm run test:coverage
npm run typecheck
npm run lint
```

Expected: 100% for project-owned TypeScript logic under the approved exclusions; all checks exit 0.

- [ ] **Step 10: Commit the complete interactive workspace**

```powershell
git add app components lib tests/ui
git commit -m "feat: connect citations to streamed evidence"
```

### Task 9: Add Accessibility, End-to-End, Download, and Quality Evaluation Suites

**Files:**
- Create: `app/error.tsx`, `app/not-found.tsx`
- Create: `e2e/workspace.spec.ts`, `e2e/downloads.spec.ts`, `e2e/accessibility.spec.ts`, `e2e/production-smoke.spec.ts`
- Create: `evaluation/quality.py`, `evaluation/run_quality.py`, `requirements-eval.txt`
- Create: `tests/ui/accessibility.test.tsx`, `tests/ui/error-boundary.test.tsx`, `tests/test_quality.py`
- Modify: `package.json`, `playwright.config.ts`, `pytest.ini`

**Interfaces:**
- Produces: `QualityReport(faithfulness, answer_relevance, context_precision, citation_validity)`.
- Produces: `assert_quality_thresholds(report: QualityReport) -> None`.
- Produces: tagged commands for deterministic E2E, live backend smoke, production smoke, and live quality evaluation.

- [ ] **Step 1: Write failing quality-threshold tests**

```python
def test_quality_thresholds_accept_the_required_floor():
    assert_quality_thresholds(QualityReport(
        faithfulness=0.85,
        answer_relevance=0.80,
        context_precision=0.80,
        citation_validity=1.0,
    ))


@pytest.mark.parametrize("field,value", [
    ("faithfulness", 0.849),
    ("answer_relevance", 0.799),
    ("context_precision", 0.799),
    ("citation_validity", 0.999),
])
def test_quality_thresholds_reject_below_floor(field, value):
    report = QualityReport(0.85, 0.80, 0.80, 1.0).model_copy(update={field: value})
    with pytest.raises(AssertionError, match=field):
        assert_quality_thresholds(report)
```

- [ ] **Step 2: Run and verify quality-test failure**

Run: `python -m pytest tests/test_quality.py -q`

Expected: FAIL because evaluation modules are absent.

- [ ] **Step 3: Implement deterministic quality types and the isolated live evaluator**

Keep threshold logic dependency-light. Set `requirements-eval.txt` to:

```text
-r requirements-dev.txt
datasets>=4,<5
ragas>=0.3,<1
```

The live runner loads the seven golden queries, calls the deployed/local RAG endpoint, evaluates faithfulness, answer relevance, context precision, and citation validity, writes a JSON report without keys/full prompts, and exits nonzero below threshold. Read the installed RAGAS docs/source before adapting samples into the current API.

- [ ] **Step 4: Write failing Playwright flows before final UI fixes**

`e2e/workspace.spec.ts` must assert:

```ts
test('streams a cited answer and focuses exact evidence', async ({ page }) => {
  await installMockSse(page, fixtures.tanArnett)
  await page.goto('/')
  await page.getByRole('textbox').fill('How does Arnett apply to the Tan family?')
  await page.getByRole('button', { name: /find evidence/i }).click()
  await expect(page.getByText(/evidence-backed response/i)).toBeVisible()
  await page.getByRole('button', { name: /source s1/i }).click()
  await expect(page.getByTestId('source-S1')).toHaveAttribute('data-active', 'true')
})
```

Downloads tests verify all three responses are PDFs and their SHA-256 hashes match the manifest. Accessibility tests run axe on initial, streaming, complete, error, and mobile-sheet states and exercise keyboard-only focus order. Production smoke is tagged and read-only except for one known Gemini query.

- [ ] **Step 5: Run Playwright and observe missing/incorrect behavior**

Run: `npm run test:e2e`

Expected: any remaining accessibility, focus, download, responsive, or error-state gaps fail with specific assertions.

- [ ] **Step 6: Make the minimal UI/error changes required by the failing tests**

Add `error.tsx`, `not-found.tsx`, any missing focus restoration, live-region copy, download attributes, and responsive behavior. Do not add unrelated features.

- [ ] **Step 7: Run all deterministic quality gates**

Run:

```powershell
npm run test:coverage
python -m pytest --cov=ingestion --cov=backend --cov=evaluation.quality --cov-report=term-missing --cov-fail-under=100
npm run typecheck
npm run lint
npm run test:e2e
```

Expected: all deterministic suites pass and project-owned logic meets 100% coverage.

- [ ] **Step 8: Run the live quality evaluation with the server-managed key**

Install `requirements-eval.txt` outside the production bundle, run the local production server and `python -m evaluation.run_quality --base-url http://127.0.0.1:3000 --output output/quality-report.json`.

Expected: faithfulness >= 0.85, answer relevance >= 0.80, context precision >= 0.80, citation validity = 1.00.

- [ ] **Step 9: Commit evaluation and E2E coverage**

```powershell
git add app e2e evaluation tests package.json package-lock.json playwright.config.ts pytest.ini requirements-eval.txt
git commit -m "test: cover SgCare production flows"
```

### Task 10: Run Full Verification and Perform the Code-Quality Reviews

**Files:**
- Review: all files changed since `b42b26f`
- Modify only when a test-first review fix is required.

**Interfaces:**
- Consumes: every prior task output.
- Produces: a clean verification record and a findings-first review with zero unresolved defects.

- [ ] **Step 1: Verify the repository contains no tracked secrets or generated dependency/build output**

Run:

```powershell
git ls-files | rg "(^|/)(node_modules|dist|\.next|__pycache__|\.env)"
git grep -n -I -E "AIza[0-9A-Za-z_-]{20,}|GEMINI_API_KEY=.+|PRIVATE KEY"
```

Expected: both scans return no tracked secret/generated-path finding. Investigate any match without printing secret values.

- [ ] **Step 2: Run corpus and artifact integrity checks**

Run the manifest validator and index inspector.

Expected: 3 documents, 89 pages, correct SHA-256 values, valid schema/model dimensions, nonzero chunks, and all public downloads present.

- [ ] **Step 3: Run the complete fresh verification command set**

Run:

```powershell
npm ci
python -m pip install -r requirements-dev.txt
python -m pytest --cov=ingestion --cov=backend --cov=evaluation.quality --cov-report=term-missing --cov-fail-under=100
npm run test:coverage
npm run typecheck
npm run lint
npm run build
```

Start `npm run start`, run Playwright, corpus downloads, health, stream, and live query smoke tests against production mode, then stop it. Start `npm run dev`, run the development smoke subset, then stop it.

Expected: every command exits 0 with no warnings that indicate correctness, security, or accessibility defects.

- [ ] **Step 4: Review the implementation against the approved spec line by line**

Create an internal checklist for all 15 spec sections. Confirm every in-scope behavior has code and a test, and every out-of-scope behavior is absent. Record any gap as a finding rather than a completion claim.

- [ ] **Step 5: Perform findings-first code, security, performance, and test reviews**

Inspect `git diff b42b26f...HEAD` and nearby call sites for correctness, regression, input validation, async cancellation, secret handling, prompt injection, Markdown safety, citation integrity, retrieval quality, cold-start cost, bundle contents, loading/empty/error/success states, mobile behavior, and weak tests.

For each confirmed defect: write a failing regression test, run it to verify RED, implement the minimal fix, run GREEN, and rerun the relevant complete suite.

- [ ] **Step 6: Run final diff and whitespace checks, then commit review fixes**

```powershell
git diff --check
git status -sb
```

If fixes were needed:

```powershell
git add backend ingestion app components lib tests e2e evaluation
git commit -m "fix: address final quality review"
```

Expected: only intended files remain changed; no unresolved review finding remains.

### Task 11: Publish the Draft PR, Verify Preview, Deploy Production, and Stage Firewall Controls

**Files:**
- No application file changes expected.
- External outputs: GitHub branch/PR, Vercel preview and production deployments, staged Vercel Firewall draft.

**Interfaces:**
- Consumes: verified branch from Task 10.
- Produces: pushed branch, draft PR, preview URL, production URL, and staged log-only firewall rule awaiting user publication.

- [ ] **Step 1: Re-run the full pre-publish verification gate**

Run the same complete deterministic command set from Task 10 immediately before push. Run `git status -sb` and `git log --oneline --decorate -10`.

Expected: fresh all-green evidence and a clean intended branch.

- [ ] **Step 2: Push the feature branch to the existing GitHub remote**

```powershell
git push -u origin agent/sgcare-exam-study-rag
```

Expected: the remote branch exists in `JohnTan38/retrieval-augmented-generation-CLAUDE-GEMINI`.

- [ ] **Step 3: Open a draft pull request through the connected GitHub integration**

Use repository `JohnTan38/retrieval-augmented-generation-CLAUDE-GEMINI`, head `agent/sgcare-exam-study-rag`, and the remote default branch as base. The PR body must summarize the Evidence Desk migration, fixed corpus/index architecture, server-side Gemini security, tests/coverage/evaluation, deployment plan, and verification commands.

Expected: a draft PR URL.

- [ ] **Step 4: Create a Vercel preview deployment**

Run from the linked isolated clone:

```powershell
vercel deploy . -y
```

Use a 10-minute timeout. Do not use `--prod` yet.

Expected: a preview URL with the correct linked `rag` project.

- [ ] **Step 5: Run preview smoke and Playwright tests**

Run the tagged preview suite against the preview URL. Verify health, corpus metadata, all three PDF downloads/checksums, one live query, streamed citations, mobile layout, keyboard flow, and axe checks.

Expected: 100% of preview smoke assertions pass.

- [ ] **Step 6: Stage a log-only Vercel Firewall rule**

Inspect current firewall state first:

```powershell
vercel firewall overview --json
vercel firewall rules list --expand --json
```

Stage a custom rule matching production `POST` requests whose path is `/api/query`, with a generous initial threshold and `log` action. Inspect it and run `vercel firewall diff`. Do not publish it.

Expected: a reviewed draft that records likely abusive query rates without blocking users. Provide the filtered firewall traffic URL and ask the user to publish/review it through the staged rollout before later enforcement.

- [ ] **Step 7: Deploy the verified build to production**

Because the user explicitly requested production deployment, run:

```powershell
vercel deploy . --prod -y
```

Use a 10-minute timeout.

Expected: the existing production application receives the verified deployment.

- [ ] **Step 8: Run production smoke tests**

Run only read-safe smoke tests plus one known live Gemini query. Verify the production title, 3-document/89-page health, downloads/checksums, answer stream, valid citation mapping, security headers, and responsive UI.

Expected: all production smoke assertions pass.

- [ ] **Step 9: Update the draft PR with deployment evidence**

Add preview/production URLs, verification results, coverage totals, quality scores, and the note that firewall enforcement remains staged for user review. Keep the PR draft unless the user explicitly requests ready-for-review status.

- [ ] **Step 10: Report final delivery state**

Report branch, commits, PR URL, preview URL, production URL, exact verification commands/results, live quality scores, firewall draft status, and any residual external dependency risk. Do not claim completion without fresh evidence from Steps 1, 5, and 8.
