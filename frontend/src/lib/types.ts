export interface Citation {
  chunk_id?: string;
  section_id: string;
  section_title?: string;
  page: number;
  quote?: string;
  verbatim_quote?: string;
}

export interface RetrievedChunk {
  chunk_id?: string;
  section_id?: string;
  section_title?: string;
  page_start?: number;
  score?: number;
  text?: string;
}

export interface ChatResponse {
  query: string;
  answer: string;
  citations: Citation[];
  refusal: boolean;
  model_used: string;
  retrieved_chunks: RetrievedChunk[];
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  refusal?: boolean;
  modelUsed?: string;
  retrievedChunks?: RetrievedChunk[];
  status?: string;
  isStreaming?: boolean;
  timestamp: string;
}

export interface HealthInfo {
  status: string;
  qdrant_url: string;
  collection: string;
  collection_exists: boolean;
  indexed_chunks: number;
  bm25_corpus_size: number;
  primary_model: string;
  fallback_model: string;
}

export interface Amendment {
  id: string;
  effective_date: string;
  topic: string;
  affected_section: string;
}

export interface DocumentInfo {
  document_name: string;
  edition: string;
  total_pages: number;
  total_chunks: number;
  amendments: Amendment[];
}

export interface CategoryMetric {
  count: number;
  hit_at_5?: number;
  section_recall?: number;
  factual_correctness?: number;
  refusal_rate?: number;
  factual_score?: number;
}

export interface ConfusionMatrix {
  TP: number;
  FP: number;
  TN: number;
  FN: number;
}

export interface EvalSummary {
  metadata: {
    generated_at: string;
    llm_model: string;
    judge_model: string;
    total_questions: number;
    answerable_count: number;
    unanswerable_count: number;
  };
  summary_metrics: {
    retrieval: {
      section_hit_at_5: number;
      mean_section_recall: number;
    };
    generation: {
      mean_factual_correctness: number;
      exact_or_correct_pct: number;
      verdict_distribution: {
        EXACT_MATCH: number;
        INCORRECT: number;
        CORRECT: number;
      };
    };
    citations: {
      total_citations_evaluated: number;
      citation_grounding_rate: number;
      quote_veracity_rate: number;
    };
    refusal: {
      confusion_matrix: ConfusionMatrix;
      precision: number;
      recall: number;
      f1_score: number;
    };
  };
  category_breakdown: Record<string, CategoryMetric>;
}
