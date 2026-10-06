# Morpho-RAG

A Retrieval-Augmented Generation (RAG) system with vector search powered by Qdrant.

## Project Structure

```text
Morpho-RAG/
├── backend/            # RAG pipeline, embeddings, vector search, and API server
├── frontend/           # Web client / UI interface
├── data/               # Source documents and knowledge base (local only, ignored in git)
├── eval/               # Evaluation benchmarks, test questions, and ground truth
├── .gitignore          # Git ignore rules for environments, data, and vector DB storage
└── README.md           # Project documentation
```

## Getting Started

### 1. Prerequisites

- Python 3.11+
- Node.js (for frontend, if applicable)
- Qdrant (local embedded or Docker instance)

### 2. Backend Setup

The virtual environment is configured inside `backend/venv`:

```powershell
# Activate virtual environment (Windows PowerShell)
.\backend\venv\Scripts\Activate.ps1

# Upgrade pip
python -m pip install --upgrade pip
```

### 3. Environment Variables

Create a `.env` file in the root or `backend/` directory (see `.gitignore`):

```env
OPENAI_API_KEY=your_openai_api_key
QDRANT_HOST=localhost
QDRANT_PORT=6333
```

### 4. Data & Document Ingestion

Place documents to be indexed into the `data/` directory.

### 5. Evaluation

Store evaluation questions, reference answers, and metrics inside `eval/`.
