"""
generator.py — Grounded Generation with Citations & Amendments for Morpho-RAG.

Features:
  1. Dense + Sparse Hybrid Retrieval via HybridRetriever.
  2. Strict context grounding: answers exclusively from retrieved chunks.
  3. Explicit refusal: refuses when the question cannot be answered from the document.
  4. Precise citations: chunk_id, section_id, page number, and quote.
  5. Policy resolution: respects amendments (superseding rules) and exceptions.
  6. Structured Pydantic schema with Gemini structured JSON output.
  7. Primary model (gemini-3.8-flash) with automatic fallback (gemini-3.5-flash-lite).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

# Ensure backend imports work
sys.path.insert(0, str(Path(__file__).resolve().parent))

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from config import (
    FALLBACK_LLM_MODEL,
    GOOGLE_API_KEY,
    LLM_MODEL,
)
from retriever import HybridRetriever


class Citation(BaseModel):
    chunk_id: str = Field(description="The ID of the cited chunk, e.g. chk0024")
    section_id: str = Field(description="The section number cited, e.g. 3.1 or 5.5.2")
    page: int = Field(description="The page number where the fact appears")
    quote: str = Field(description="A brief verbatim snippet from the chunk supporting the claim")


class RAGResponse(BaseModel):
    answer: str = Field(description="Comprehensive, factual answer grounded strictly in the context passages.")
    citations: list[Citation] = Field(description="List of exact chunk citations supporting the answer.")
    refusal: bool = Field(description="Set to true if the context does not contain sufficient information to answer.")


SYSTEM_INSTRUCTION = """You are the authoritative Academic Policy Assistant for Northfield Institute of Technology.
Your duty is to answer student questions based EXCLUSIVELY on the provided policy handbook context passages below.

STRICT INSTRUCTIONS:
1. Grounding & Zero Hallucination:
   - Answer ONLY using facts directly stated in the supplied context passages.
   - Do NOT use outside knowledge or assume unstated rules.
   - If the provided context does NOT contain enough information to answer the question, set refusal=true, answer="This information is not found in the Student Academic Policy Handbook.", and set citations to an empty list.

2. Citations:
   - For every factual statement, populate the 'citations' list with the exact chunk_id, section_id, page number, and supporting quote.
   - Also include natural inline section references in the answer where helpful, e.g. (Section 3.1, p. 8).

3. Handling Amendments:
   - If a chunk contains an [AMENDMENT] or notes that a rule was amended, the amended rule takes precedence over earlier rules.
   - Explicitly state the amendment and its effective date in your answer.

4. Handling Exceptions:
   - When an [EXCEPTION] or condonation rule applies, state the general rule first, then clearly present the exception conditions, approvals needed, and any fees.

5. Tone:
   - Direct, objective, helpful, and academically precise.
"""


class RAGGenerator:
    def __init__(
        self,
        retriever: HybridRetriever | None = None,
        model_name: str = LLM_MODEL,
        fallback_model: str = FALLBACK_LLM_MODEL,
        google_api_key: str = GOOGLE_API_KEY,
    ) -> None:
        self.retriever = retriever or HybridRetriever()
        self.model_name = model_name
        self.fallback_model = fallback_model
        self.client = genai.Client(api_key=google_api_key)

    def format_context(self, chunks: list[dict[str, Any]]) -> str:
        """Format retrieved chunks into structured context blocks."""
        blocks = []
        for rank, c in enumerate(chunks, start=1):
            p = c["payload"]
            cid = p.get("chunk_id", f"chk_{rank}")
            sec_id = p.get("section_id", "Unknown")
            sec_title = p.get("section_title", "")
            p_start = p.get("page_start", 0)
            p_end = p.get("page_end", 0)
            page_str = f"p. {p_start}" if p_start == p_end else f"pp. {p_start}-{p_end}"

            # Use embed_text as it contains full hierarchical context & amendment tags
            content = p.get("embed_text", p.get("display_text", ""))

            header = f"--- [CHUNK {cid} | Section {sec_id}: {sec_title} | {page_str}] ---"
            blocks.append(f"{header}\n{content}")
        return "\n\n".join(blocks)

    def generate(
        self,
        query: str,
        top_k: int = 5,
        retrieved_chunks: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Retrieve relevant chunks and generate a grounded, cited answer."""
        # 1. Retrieve candidates if not provided
        if retrieved_chunks is None:
            retrieved_chunks = self.retriever.retrieve(query, top_k=top_k)

        # 2. Format context
        context_str = self.format_context(retrieved_chunks)

        # 3. Build user prompt
        user_prompt = f"""Context Passages from Handbook:
{context_str}

Student Question:
{query}

Provide a grounded, cited answer following your system instructions:"""

        # 4. Generate with structured JSON output
        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            response_schema=RAGResponse,
            temperature=0.0,
        )

        response_text = ""
        model_used = self.model_name
        try:
            resp = self.client.models.generate_content(
                model=self.model_name,
                contents=user_prompt,
                config=config,
            )
            response_text = resp.text
        except Exception as exc:
            print(f"[WARN] Primary model {self.model_name} failed ({exc}). Retrying with {self.fallback_model}...")
            model_used = self.fallback_model
            resp = self.client.models.generate_content(
                model=self.fallback_model,
                contents=user_prompt,
                config=config,
            )
            response_text = resp.text

        # 5. Parse response
        parsed = json.loads(response_text)

        # Build section_title and section metadata lookup from retrieved_chunks
        sec_title_map: dict[str, str] = {}
        for c in retrieved_chunks:
            p = c.get("payload", {})
            if p.get("section_id") and p.get("section_title"):
                sec_title_map[p["section_id"]] = p["section_title"]
            if p.get("chunk_id") and p.get("section_title"):
                sec_title_map[p["chunk_id"]] = p["section_title"]

        raw_citations = parsed.get("citations", [])
        enriched_citations = []
        for cit in raw_citations:
            chk_id = cit.get("chunk_id", "")
            sec_id = cit.get("section_id", "")
            quote_str = cit.get("quote", "")
            title = (
                sec_title_map.get(sec_id)
                or sec_title_map.get(chk_id)
                or f"Section {sec_id}"
            )
            enriched_citations.append({
                "chunk_id": chk_id,
                "section_id": sec_id,
                "section_title": title,
                "page": cit.get("page", 1),
                "quote": quote_str,
                "verbatim_quote": quote_str,
            })

        return {
            "query": query,
            "answer": parsed.get("answer", ""),
            "citations": enriched_citations,
            "refusal": parsed.get("refusal", False),
            "model_used": model_used,
            "retrieved_chunks": retrieved_chunks,
        }

