"""
config.py — single source of truth for all model names, dimensions, and service URLs.

Every other backend script imports from here instead of reading os.getenv() directly.
Values are read from the environment (or .env via python-dotenv) with safe defaults.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the project root (two levels up from this file: backend/ -> root)
_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env")

# ── Gemini API ──────────────────────────────────────────────────────────────
# The google-genai SDK uses GOOGLE_API_KEY.  GEMINI_API_KEY is a deprecated
# duplicate; we read only GOOGLE_API_KEY here and let the SDK pick it up.
GOOGLE_API_KEY: str = os.environ["GOOGLE_API_KEY"]   # raises KeyError if missing

# ── Model names ─────────────────────────────────────────────────────────────
# gemini-3.8-flash is confirmed present in models.list() as of 2026-10-07.
LLM_MODEL: str = os.getenv("LLM_MODEL", "gemini-3.8-flash")
FALLBACK_LLM_MODEL: str = os.getenv("FALLBACK_LLM_MODEL", "gemini-3.5-flash-lite")
EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "gemini-embedding-001")
EMBEDDING_DIM: int = 3072   # fixed for gemini-embedding-001; change here if model changes

# ── Qdrant ───────────────────────────────────────────────────────────────────
QDRANT_URL: str = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_COLLECTION: str = os.getenv("QDRANT_COLLECTION", "morpho_rag")

# ── Paths ────────────────────────────────────────────────────────────────────
ROOT: Path = _ROOT
DATA_DIR: Path = ROOT / "data"
PROCESSED_DIR: Path = DATA_DIR / "processed"
PDF_PATH: Path = DATA_DIR / "Northfield_Student_Academic_Policy_Handbook.pdf"
RECORDS_PATH: Path = PROCESSED_DIR / "records.jsonl"
CHUNKS_PATH: Path = PROCESSED_DIR / "chunks.jsonl"
EVAL_DIR: Path = ROOT / "eval"
ANSWER_KEY_PATH: Path = EVAL_DIR / "answer_key.json"
