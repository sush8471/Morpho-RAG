"""
main.py — Production FastAPI Application for Morpho-RAG.

Provides:
  1. GET /api/health — Health check verifying Qdrant & pipeline readiness.
  2. POST /api/chat — Standard JSON chat endpoint with grounded citations.
  3. POST /api/chat/stream — Real-time Server-Sent Events (SSE) streaming endpoint.
  4. GET /api/eval/summary — Evaluation transparency endpoint serving Phase 6 benchmarks.
  5. GET /api/document/info — Handbook metadata and amendment overview.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any, AsyncGenerator

# Ensure backend imports work
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from config import (
    ANSWER_KEY_PATH,
    CHUNKS_PATH,
    EVAL_REPORT_PATH,
    FALLBACK_LLM_MODEL,
    LLM_MODEL,
    QDRANT_COLLECTION,
    QDRANT_URL,
)
from generator import Citation, RAGGenerator
from retriever import HybridRetriever

# ── App Initialization ────────────────────────────────────────────────────────
app = FastAPI(
    title="Morpho-RAG API",
    description="Grounded Academic Policy Q&A with Strict Attributions and Zero-Hallucination Refusal.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows Next.js local frontend & dev tooling
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global generator instance (loads retriever, Qdrant client, and BM25 index on startup)
rag_generator: RAGGenerator | None = None


@app.on_event("startup")
def startup_event() -> None:
    global rag_generator
    print("[Startup] Initializing Morpho-RAG Generator & Retriever...")
    rag_generator = RAGGenerator()
    print("[Startup] Ready to serve queries.")


# ── Schemas ──────────────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Student question about policy handbook")
    top_k: int = Field(default=5, ge=1, le=10, description="Number of context chunks to retrieve")


class ChatResponse(BaseModel):
    query: str
    answer: str
    citations: list[Citation]
    refusal: bool
    model_used: str
    retrieved_chunks: list[dict[str, Any]]


# ── Endpoints ────────────────────────────────────────────────────────────────
@app.get("/api/health")
def health_check() -> dict[str, Any]:
    """Verify Qdrant connectivity and retriever health."""
    if rag_generator is None:
        raise HTTPException(status_code=503, detail="RAG pipeline not initialized")

    try:
        collections = rag_generator.retriever.qc.get_collections().collections
        exists = any(c.name == QDRANT_COLLECTION for c in collections)
        collection_info = rag_generator.retriever.qc.get_collection(QDRANT_COLLECTION)
        points_count = collection_info.points_count
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Qdrant connection error: {exc}")

    return {
        "status": "healthy",
        "qdrant_url": QDRANT_URL,
        "collection": QDRANT_COLLECTION,
        "collection_exists": exists,
        "indexed_chunks": points_count,
        "bm25_corpus_size": len(rag_generator.retriever.chunks),
        "primary_model": LLM_MODEL,
        "fallback_model": FALLBACK_LLM_MODEL,
    }


@app.get("/api/document/info")
def document_info() -> dict[str, Any]:
    """Return handbook metadata and amendment summary."""
    return {
        "document_name": "Northfield Institute of Technology - Student Academic Policy Handbook",
        "edition": "Edition 5.0",
        "total_pages": 41,
        "total_chunks": 160,
        "amendments": [
            {
                "id": "Amendment 1",
                "effective_date": "1 August 2025",
                "topic": "Re-evaluation fee amended from MRL 300 to MRL 500 per theory course.",
                "affected_section": "5.5.2",
            },
            {
                "id": "Amendment 2",
                "effective_date": "1 February 2026",
                "topic": "Late fee on tuition amended to MRL 500 per week (max MRL 3,000), superseding MRL 100 per day.",
                "affected_section": "7.2",
            },
        ],
    }


@app.get("/api/eval/summary")
def evaluation_summary() -> dict[str, Any]:
    """Expose verified Phase 6 evaluation benchmarks for frontend transparency."""
    if not EVAL_REPORT_PATH.exists():
        raise HTTPException(status_code=404, detail="Evaluation report not found")

    with open(EVAL_REPORT_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    return {
        "metadata": data.get("metadata", {}),
        "summary_metrics": data.get("summary_metrics", {}),
        "category_breakdown": data.get("category_breakdown", {}),
    }


@app.post("/api/chat", response_model=ChatResponse)
def chat_endpoint(req: ChatRequest) -> dict[str, Any]:
    """Synchronous grounded generation endpoint with structured JSON citations."""
    if rag_generator is None:
        raise HTTPException(status_code=503, detail="RAG pipeline not initialized")

    try:
        result = rag_generator.generate(query=req.query, top_k=req.top_k)
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Generation failed: {exc}")


@app.post("/api/chat/stream")
async def chat_stream_endpoint(req: ChatRequest) -> EventSourceResponse:
    """
    Streaming SSE endpoint.
    Emits progressive events:
      - 'status': current pipeline phase
      - 'retrieved': context chunks found
      - 'token': streaming text tokens of the answer
      - 'citations': structured citation objects
      - 'done': completion metadata and refusal state
    """
    if rag_generator is None:
        raise HTTPException(status_code=503, detail="RAG pipeline not initialized")

    async def event_generator() -> AsyncGenerator[dict[str, str], None]:
        # Stage 1: Retrieval
        yield {
            "event": "status",
            "data": json.dumps({"stage": "retrieval", "message": "Searching policy handbook passages..."}),
        }
        await asyncio.sleep(0.05)

        # Run retrieval in thread pool
        retrieved_chunks = await asyncio.to_thread(
            rag_generator.retriever.retrieve, req.query, req.top_k
        )

        # Emit retrieved context overview
        simple_chunks = [
            {
                "chunk_id": c["payload"].get("chunk_id"),
                "section_id": c["payload"].get("section_id"),
                "section_title": c["payload"].get("section_title"),
                "page_start": c["payload"].get("page_start"),
                "score": round(c.get("score", 0.0), 4),
            }
            for c in retrieved_chunks
        ]
        yield {
            "event": "retrieved",
            "data": json.dumps({"chunks": simple_chunks}),
        }

        # Stage 2: Synthesis
        yield {
            "event": "status",
            "data": json.dumps({"stage": "synthesis", "message": "Synthesizing policy answer with citations..."}),
        }
        await asyncio.sleep(0.05)

        # Generate grounded result without re-running retrieval
        result = await asyncio.to_thread(
            rag_generator.generate, req.query, req.top_k, retrieved_chunks
        )

        answer_text = result["answer"]
        citations = result["citations"]
        refusal = result["refusal"]
        model_used = result["model_used"]

        # Stream answer tokens smoothly in natural chunks
        words = answer_text.split(" ")
        chunk_size = 3
        for i in range(0, len(words), chunk_size):
            token_chunk = " ".join(words[i : i + chunk_size]) + " "
            yield {
                "event": "token",
                "data": json.dumps({"text": token_chunk}),
            }
            await asyncio.sleep(0.02)

        # Stage 3: Citations
        yield {
            "event": "citations",
            "data": json.dumps({"citations": citations}),
        }

        # Stage 4: Done
        yield {
            "event": "done",
            "data": json.dumps({
                "refusal": refusal,
                "model_used": model_used,
                "full_answer": answer_text,
            }),
        }

    return EventSourceResponse(event_generator())


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
