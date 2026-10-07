# Morpho-RAG

A RAG (Retrieval-Augmented Generation) chatbot that answers questions from a single policy document with cited sources (section + page), refuses when the answer is not in the document, and handles amendments and exceptions correctly.

**This is a learning project.** The goal is to understand every step of the RAG pipeline, not just to ship a product.

## Project Structure

```text
Morpho-RAG/
├── backend/            # RAG pipeline, embeddings, vector search, and API server
│   ├── config.py       # Single source of truth for model names, URLs, paths
│   ├── phase1_ingest.py  # PDF -> structured records (PyMuPDF)
│   ├── phase1_verify.py  # Verify ingest output against the PDF
│   ├── phase2_chunk.py   # Records -> chunks (with section-path prefix)
│   ├── phase2_verify.py  # Verify chunk coverage and needle presence
│   ├── requirements.txt  # Pinned Python dependencies
│   └── smoke_test.py     # Quick Qdrant connectivity check
├── frontend/           # Next.js chat UI (Phase 7)
├── data/               # Source PDF and processed output (gitignored)
│   └── processed/      # records.jsonl, chunks.jsonl, sections.json, ...
├── eval/               # Answer key and evaluation scripts
├── qdrant_storage/     # Qdrant on-disk storage (gitignored)
└── .env.example        # Environment variable template
```

## Stack

| Component | Technology |
|---|---|
| PDF parsing | PyMuPDF (pymupdf 1.28+) |
| Embeddings | Gemini embedding-001 (3072 dims, free tier) |
| Vector DB | Qdrant (Docker, localhost:6333) |
| Sparse retrieval | rank-bm25 (Phase 4) |
| Reranker | bge-reranker-base via sentence-transformers (Phase 4) |
| Generation | Gemini 3.8 Flash (free tier) |
| API | FastAPI + Uvicorn (Phase 7) |
| Frontend | Next.js + Tailwind, streaming citations (Phase 7) |

## Setup

### 1. Prerequisites

- Python 3.11+
- Docker Desktop (for Qdrant)
- A Google AI Studio API key — **`GOOGLE_API_KEY` only** (the SDK does not use `GEMINI_API_KEY`)

### 2. Clone and create the virtual environment

```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 3. Environment variables

Copy `.env.example` to `.env` and fill in your key:

```env
GOOGLE_API_KEY=your_key_here
QDRANT_URL=http://localhost:6333
```

### 4. Start Qdrant

```powershell
docker run -d --name qdrant -p 6333:6333 -p 6334:6334 `
  -v "${PWD}\qdrant_storage:/qdrant/storage" qdrant/qdrant
```

If the container already exists: `docker start qdrant`

### 5. Verify Qdrant is running

```powershell
python backend/smoke_test.py
```

### 6. Run Phase 1 (PDF ingestion)

```powershell
python backend/phase1_ingest.py
python backend/phase1_verify.py   # should show 49 PASS, 0 FAIL
```

### 7. Run Phase 2 (chunking)

```powershell
python backend/phase2_chunk.py
python backend/phase2_verify.py   # should show all PASS
```

## Document

The test document is a **fictional, AI-generated** 41-page student academic policy handbook (`data/Northfield_Student_Academic_Policy_Handbook.pdf`). It is safe to publish. It deliberately contains amendments, exceptions, cross-references, and topics that are absent (parking, cafeteria, sports, alumni) to test refusal behaviour.

## Evaluation

`eval/answer_key.json` contains 30 answerable questions (simple fact, table lookup, multi-section, exception, amendment) and 6 unanswerable ones. It is never placed in `data/` and is never indexed.

## Known limitations

- Free-tier Gemini API: rate limits apply; the ingest scripts include backoff (Phase 3+).
- No dedicated GPU: the bge-reranker-base model runs on CPU (adequate for this scale).
- Single-document scope: the pipeline is not designed for multi-document retrieval.
