import {
  ChatResponse,
  Citation,
  DocumentInfo,
  EvalSummary,
  HealthInfo,
  RetrievedChunk,
} from "./types";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function fetchHealth(): Promise<HealthInfo> {
  const res = await fetch(`${API_BASE_URL}/api/health`, {
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`Health check failed with status ${res.status}`);
  }
  return res.json();
}

export async function fetchDocumentInfo(): Promise<DocumentInfo> {
  const res = await fetch(`${API_BASE_URL}/api/document/info`, {
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`Document info fetch failed with status ${res.status}`);
  }
  return res.json();
}

export async function fetchEvalSummary(): Promise<EvalSummary> {
  const res = await fetch(`${API_BASE_URL}/api/eval/summary`, {
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`Evaluation summary fetch failed with status ${res.status}`);
  }
  return res.json();
}

export async function sendChatSync(
  query: string,
  top_k = 5
): Promise<ChatResponse> {
  const res = await fetch(`${API_BASE_URL}/api/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ query, top_k }),
  });

  if (!res.ok) {
    const errorText = await res.text();
    throw new Error(`Chat request failed: ${res.status} - ${errorText}`);
  }

  return res.json();
}

export interface StreamCallbacks {
  onStatus?: (stage: string, message: string) => void;
  onRetrieved?: (chunks: RetrievedChunk[]) => void;
  onToken?: (token: string) => void;
  onCitations?: (citations: Citation[]) => void;
  onDone?: (refusal: boolean, modelUsed: string, fullAnswer: string) => void;
  onError?: (error: Error) => void;
}

export async function streamChat(
  query: string,
  top_k = 5,
  callbacks: StreamCallbacks,
  signal?: AbortSignal
): Promise<void> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/chat/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
      },
      body: JSON.stringify({ query, top_k }),
      signal,
    });

    if (!res.ok) {
      const errText = await res.text();
      throw new Error(`Stream request failed with status ${res.status}: ${errText}`);
    }

    if (!res.body) {
      throw new Error("Response body is empty.");
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      let currentEvent = "message";

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed) {
          currentEvent = "message";
          continue;
        }

        if (trimmed.startsWith("event:")) {
          currentEvent = trimmed.slice(6).trim();
        } else if (trimmed.startsWith("data:")) {
          const rawData = trimmed.slice(5).trim();
          try {
            const parsed = JSON.parse(rawData);

            switch (currentEvent) {
              case "status":
                callbacks.onStatus?.(parsed.stage || "processing", parsed.message || "");
                break;
              case "retrieved":
                callbacks.onRetrieved?.(parsed.chunks || []);
                break;
              case "token":
                callbacks.onToken?.(parsed.text || "");
                break;
              case "citations":
                callbacks.onCitations?.(parsed.citations || []);
                break;
              case "done":
                callbacks.onDone?.(
                  Boolean(parsed.refusal),
                  parsed.model_used || "Unknown",
                  parsed.full_answer || ""
                );
                break;
            }
          } catch {
            // raw text token fallback
            if (currentEvent === "token") {
              callbacks.onToken?.(rawData);
            }
          }
        }
      }
    }
  } catch (err: unknown) {
    if (signal?.aborted) {
      return;
    }
    const errorObj = err instanceof Error ? err : new Error(String(err));
    callbacks.onError?.(errorObj);
    throw errorObj;
  }
}
