"""
retriever.py — Production Hybrid Retriever with Reciprocal Rank Fusion & FlashRank reranking.

Components:
  1. Dense vector search via Qdrant (Gemini gemini-embedding-001, RETRIEVAL_QUERY).
  2. Sparse lexical search via BM25 (rank-bm25 BM25Okapi).
  3. Reciprocal Rank Fusion (RRF) to merge dense + sparse rankings fairly.
  4. Cross-encoder neural reranking via FlashRank (ONNX CPU, ms-marco-TinyBERT-L-2-v2).

Usage:
    from retriever import HybridRetriever
    retriever = HybridRetriever()
    results = retriever.retrieve("What is the minimum attendance requirement?", top_k=5)
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

# Ensure backend imports work
sys.path.insert(0, str(Path(__file__).resolve().parent))

from flashrank import Ranker, RerankRequest
from google import genai
from google.genai import types
from qdrant_client import QdrantClient
from rank_bm25 import BM25Okapi

from config import (
    CHUNKS_PATH,
    EMBEDDING_MODEL,
    GOOGLE_API_KEY,
    QDRANT_COLLECTION,
    QDRANT_URL,
)


def _tokenize(text: str) -> list[str]:
    """Simple alphanumeric tokenizer for BM25."""
    return re.findall(r"\w+", text.lower())


class HybridRetriever:
    def __init__(
        self,
        qdrant_url: str = QDRANT_URL,
        collection_name: str = QDRANT_COLLECTION,
        chunks_path: Path = CHUNKS_PATH,
        embedding_model: str = EMBEDDING_MODEL,
        google_api_key: str = GOOGLE_API_KEY,
        rerank_model_name: str = "ms-marco-TinyBERT-L-2-v2",
    ) -> None:
        self.qdrant_url = qdrant_url
        self.collection_name = collection_name
        self.embedding_model = embedding_model

        # 1. Load chunks
        if not chunks_path.is_file():
            raise FileNotFoundError(f"Chunks file not found at {chunks_path}")
        self.chunks: list[dict[str, Any]] = []
        with open(chunks_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    self.chunks.append(json.loads(line))

        self.chunks_by_id: dict[str, dict[str, Any]] = {
            c["chunk_id"]: c for c in self.chunks
        }

        # 2. Initialize BM25 corpus index
        self.tokenized_corpus = [
            _tokenize(c.get("embed_text", c.get("display_text", "")))
            for c in self.chunks
        ]
        self.bm25 = BM25Okapi(self.tokenized_corpus)

        # 3. Connect to Qdrant & Gemini
        self.qc = QdrantClient(url=self.qdrant_url)
        self.gemini_client = genai.Client(api_key=google_api_key)

        # 4. Initialize FlashRank reranker
        self.ranker = Ranker(model_name=rerank_model_name)

    def dense_search(self, query: str, top_k: int = 20) -> list[dict[str, Any]]:
        """Dense semantic search in Qdrant using Gemini query embedding."""
        embed_resp = self.gemini_client.models.embed_content(
            model=self.embedding_model,
            contents=query,
            config=types.EmbedContentConfig(task_type="RETRIEVAL_QUERY"),
        )
        q_vec = embed_resp.embeddings[0].values

        response = self.qc.query_points(
            collection_name=self.collection_name,
            query=q_vec,
            limit=top_k,
        )

        results = []
        for rank, p in enumerate(response.points, start=1):
            chunk_id = p.payload.get("chunk_id")
            results.append({
                "chunk_id": chunk_id,
                "score": float(p.score),
                "rank": rank,
                "payload": p.payload,
            })
        return results

    def sparse_search(self, query: str, top_k: int = 20) -> list[dict[str, Any]]:
        """Sparse keyword search using BM25Okapi over chunk embed_text."""
        q_tokens = _tokenize(query)
        scores = self.bm25.get_scores(q_tokens)

        # Get indices of top_k highest scores
        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]

        results = []
        for rank, idx in enumerate(top_indices, start=1):
            score = float(scores[idx])
            chunk = self.chunks[idx]
            results.append({
                "chunk_id": chunk["chunk_id"],
                "score": score,
                "rank": rank,
                "payload": chunk,
            })
        return results

    def fuse_ranks(
        self,
        dense_results: list[dict[str, Any]],
        sparse_results: list[dict[str, Any]],
        k: int = 60,
    ) -> list[dict[str, Any]]:
        """Reciprocal Rank Fusion (RRF) combining dense and sparse results."""
        dense_ranks = {r["chunk_id"]: r["rank"] for r in dense_results}
        dense_scores = {r["chunk_id"]: r["score"] for r in dense_results}

        sparse_ranks = {r["chunk_id"]: r["rank"] for r in sparse_results}
        sparse_scores = {r["chunk_id"]: r["score"] for r in sparse_results}

        all_ids = set(dense_ranks.keys()) | set(sparse_ranks.keys())
        fused = []

        for cid in all_ids:
            d_rank = dense_ranks.get(cid, 1000)
            s_rank = sparse_ranks.get(cid, 1000)

            # Standard RRF formula: sum(1 / (k + rank))
            rrf_score = (1.0 / (k + d_rank)) + (1.0 / (k + s_rank))

            fused.append({
                "chunk_id": cid,
                "rrf_score": rrf_score,
                "dense_score": dense_scores.get(cid),
                "dense_rank": dense_ranks.get(cid),
                "sparse_score": sparse_scores.get(cid),
                "sparse_rank": sparse_ranks.get(cid),
                "payload": self.chunks_by_id[cid],
            })

        fused.sort(key=lambda x: x["rrf_score"], reverse=True)
        for rank, item in enumerate(fused, start=1):
            item["rrf_rank"] = rank
        return fused

    def rerank(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """Neural cross-encoder reranking via FlashRank."""
        if not candidates:
            return []

        passages = [
            {
                "id": c["chunk_id"],
                "text": c["payload"].get("embed_text", c["payload"].get("display_text", "")),
            }
            for c in candidates
        ]

        rerank_req = RerankRequest(query=query, passages=passages)
        reranked_results = self.ranker.rerank(rerank_req)

        # Map rerank scores back to candidates
        rerank_scores = {r["id"]: float(r["score"]) for r in reranked_results}

        enriched_candidates = []
        for c in candidates:
            cid = c["chunk_id"]
            if cid in rerank_scores:
                item = dict(c)
                item["rerank_score"] = rerank_scores[cid]
                enriched_candidates.append(item)

        enriched_candidates.sort(key=lambda x: x["rerank_score"], reverse=True)
        for rank, item in enumerate(enriched_candidates, start=1):
            item["final_rank"] = rank

        return enriched_candidates[:top_k]

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        dense_candidates: int = 20,
        sparse_candidates: int = 20,
        use_reranker: bool = True,
    ) -> list[dict[str, Any]]:
        """Full hybrid retrieval pipeline: Dense + Sparse -> RRF -> FlashRank -> Top-K."""
        # 1. Retrieve dense candidates from Qdrant
        dense_res = self.dense_search(query, top_k=dense_candidates)

        # 2. Retrieve sparse candidates from BM25
        sparse_res = self.sparse_search(query, top_k=sparse_candidates)

        # 3. Fuse ranks with RRF
        fused = self.fuse_ranks(dense_res, sparse_res, k=60)

        # 4. Rerank top candidates with FlashRank
        if use_reranker:
            # Take top 15 candidates into the cross-encoder
            candidates_to_rerank = fused[:15]
            final_results = self.rerank(query, candidates_to_rerank, top_k=top_k)
        else:
            final_results = fused[:top_k]
            for rank, item in enumerate(final_results, start=1):
                item["final_rank"] = rank

        return final_results
