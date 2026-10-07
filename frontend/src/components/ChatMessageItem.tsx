"use client";

import React, { useState } from "react";
import { Layers, ChevronDown, ChevronUp } from "lucide-react";
import { ChatMessage, Citation } from "@/lib/types";
import { CitationBadge } from "./CitationBadge";
import { AmendmentBanner } from "./AmendmentBanner";
import { RefusalCallout } from "./RefusalCallout";

interface ChatMessageItemProps {
  message: ChatMessage;
  onSelectCitation: (citation: Citation) => void;
  onSelectQuery?: (query: string) => void;
}

export const ChatMessageItem: React.FC<ChatMessageItemProps> = ({
  message,
  onSelectCitation,
  onSelectQuery,
}) => {
  const [showChunks, setShowChunks] = useState(false);
  const isUser = message.role === "user";

  if (isUser) {
    return (
      <div
        className="animate-fade"
        style={{
          display: "flex",
          justifyContent: "flex-end",
          marginBottom: "20px",
          width: "100%",
        }}
      >
        <div
          style={{
            maxWidth: "76%",
            backgroundColor: "rgba(255, 255, 255, 0.06)",
            border: "1px solid var(--border)",
            borderRadius: "16px 4px 16px 16px",
            padding: "14px 18px",
            color: "var(--text-primary)",
            fontSize: "15px",
            lineHeight: 1.6,
          }}
        >
          <div>{message.content}</div>
          {message.timestamp && (
            <div
              className="tabular-nums"
              style={{
                fontSize: "11px",
                color: "var(--text-muted)",
                textAlign: "right",
                marginTop: "6px",
              }}
            >
              {message.timestamp}
            </div>
          )}
        </div>
      </div>
    );
  }

  // Assistant message — left-aligned, no avatar card, conversation is the interface
  return (
    <div
      className="animate-fade"
      style={{
        display: "flex",
        justifyContent: "flex-start",
        marginBottom: "24px",
        width: "100%",
      }}
    >
      <div
        style={{
          maxWidth: "88%",
          width: "100%",
          backgroundColor: "var(--surface-1)",
          border: "1px solid var(--border)",
          borderRadius: "4px 16px 16px 16px",
          padding: "18px 20px",
          display: "flex",
          flexDirection: "column",
          gap: "12px",
        }}
      >
        {/* Streaming status line (if searching/retrieving) */}
        {message.isStreaming && message.status && (
          <div
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "7px",
              fontSize: "12px",
              color: "var(--accent)",
              fontFamily: "var(--font-mono)",
            }}
          >
            <span
              style={{
                width: "6px",
                height: "6px",
                borderRadius: "50%",
                backgroundColor: "var(--accent)",
                display: "inline-block",
              }}
            />
            <span>{message.status}</span>
          </div>
        )}

        {/* Refusal state or assistant prose */}
        {message.refusal ? (
          <RefusalCallout
            answerText={message.content}
            onSelectSuggestion={onSelectQuery}
          />
        ) : (
          <div
            style={{
              fontSize: "15px",
              lineHeight: 1.6,
              color: "var(--text-primary)",
              whiteSpace: "pre-wrap",
            }}
          >
            {message.content}
            {message.isStreaming && <span className="streaming-caret" />}
          </div>
        )}

        {/* Active amendment callout if applicable */}
        {message.citations && message.citations.length > 0 && !message.refusal && (
          <AmendmentBanner citations={message.citations} />
        )}

        {/* Inline citation pills */}
        {message.citations && message.citations.length > 0 && (
          <div
            style={{
              marginTop: "4px",
              paddingTop: "12px",
              borderTop: "1px solid var(--border)",
              display: "flex",
              flexDirection: "column",
              gap: "8px",
            }}
          >
            <div
              style={{
                fontSize: "12px",
                color: "var(--text-muted)",
                fontFamily: "var(--font-mono)",
              }}
            >
              grounded policy citations
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "6px" }}>
              {message.citations.map((c, i) => (
                <CitationBadge
                  key={i}
                  citation={c}
                  index={i}
                  onClick={onSelectCitation}
                />
              ))}
            </div>
          </div>
        )}

        {/* Optional retrieved context chunks */}
        {message.retrievedChunks && message.retrievedChunks.length > 0 && (
          <div style={{ marginTop: "4px" }}>
            <button
              onClick={() => setShowChunks(!showChunks)}
              type="button"
              style={{
                background: "transparent",
                border: "none",
                display: "flex",
                alignItems: "center",
                gap: "6px",
                fontSize: "12px",
                color: "var(--text-muted)",
                fontFamily: "var(--font-mono)",
                cursor: "pointer",
                padding: "2px 0",
              }}
            >
              <Layers size={13} />
              <span>
                retrieved context ({message.retrievedChunks.length} chunks)
              </span>
              {showChunks ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
            </button>

            {showChunks && (
              <div
                className="animate-fade"
                style={{
                  marginTop: "8px",
                  display: "flex",
                  flexDirection: "column",
                  gap: "6px",
                }}
              >
                {message.retrievedChunks.map((chunk, idx) => (
                  <div
                    key={idx}
                    style={{
                      padding: "10px 12px",
                      borderRadius: "var(--radius-sm)",
                      backgroundColor: "var(--surface-2)",
                      border: "1px solid var(--border)",
                      fontSize: "12px",
                      color: "var(--text-secondary)",
                    }}
                  >
                    <div
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        fontFamily: "var(--font-mono)",
                        color: "var(--accent)",
                        marginBottom: "3px",
                      }}
                    >
                      <span className="tabular-nums">
                        rank #{idx + 1} · §{chunk.section_id} (p. {chunk.page_start})
                      </span>
                      {chunk.score !== undefined && (
                        <span className="tabular-nums" style={{ color: "var(--text-muted)" }}>
                          score: {Number(chunk.score).toFixed(3)}
                        </span>
                      )}
                    </div>
                    <div style={{ fontWeight: 500, color: "var(--text-primary)" }}>
                      {chunk.section_title}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
