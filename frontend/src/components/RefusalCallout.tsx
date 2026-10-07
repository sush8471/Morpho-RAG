"use client";

import React from "react";
import { AlertTriangle, ArrowRight } from "lucide-react";

interface RefusalCalloutProps {
  answerText: string;
  onSelectSuggestion?: (query: string) => void;
}

export const RefusalCallout: React.FC<RefusalCalloutProps> = ({
  answerText,
  onSelectSuggestion,
}) => {
  const suggestions = [
    {
      label: "Attendance threshold",
      query: "What is the minimum attendance required to appear for end-semester exams?",
    },
    {
      label: "Re-evaluation fee",
      query: "How much is the fee for answer script re-evaluation?",
    },
    {
      label: "Grading & SGPA scale",
      query: "How is SGPA calculated and which grade indicates course failure?",
    },
  ];

  return (
    <div
      style={{
        padding: "16px",
        borderRadius: "var(--radius-sm)",
        backgroundColor: "rgba(245, 158, 11, 0.08)",
        border: "1px solid rgba(245, 158, 11, 0.22)",
        display: "flex",
        flexDirection: "column",
        gap: "12px",
      }}
    >
      <div style={{ display: "flex", alignItems: "flex-start", gap: "10px" }}>
        <AlertTriangle
          size={16}
          color="var(--warning)"
          style={{ flexShrink: 0, marginTop: "2px" }}
        />
        <div style={{ flex: 1 }}>
          <div
            style={{
              fontSize: "13px",
              fontWeight: 600,
              color: "var(--warning)",
              marginBottom: "4px",
            }}
          >
            Outside policy scope
          </div>
          <div
            style={{
              fontSize: "14px",
              lineHeight: 1.55,
              color: "var(--text-primary)",
            }}
          >
            {answerText}
          </div>
        </div>
      </div>

      {/* Suggestion chips to steer back to in-scope topics */}
      <div
        style={{
          borderTop: "1px solid rgba(245, 158, 11, 0.16)",
          paddingTop: "10px",
          display: "flex",
          flexDirection: "column",
          gap: "8px",
        }}
      >
        <span
          style={{
            fontSize: "12px",
            color: "var(--text-muted)",
          }}
        >
          In-scope handbook topics you can explore:
        </span>
        <div style={{ display: "flex", flexWrap: "wrap", gap: "6px" }}>
          {suggestions.map((item, idx) => (
            <button
              key={idx}
              type="button"
              onClick={() => onSelectSuggestion?.(item.query)}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "5px",
                padding: "4px 10px",
                borderRadius: "var(--radius-sm)",
                backgroundColor: "var(--surface-1)",
                border: "1px solid var(--border)",
                fontSize: "12px",
                color: "var(--text-secondary)",
                cursor: onSelectSuggestion ? "pointer" : "default",
                transition: "border-color 0.15s ease, color 0.15s ease",
              }}
              onMouseEnter={(e) => {
                if (onSelectSuggestion) {
                  e.currentTarget.style.borderColor = "var(--accent)";
                  e.currentTarget.style.color = "var(--text-primary)";
                }
              }}
              onMouseLeave={(e) => {
                if (onSelectSuggestion) {
                  e.currentTarget.style.borderColor = "var(--border)";
                  e.currentTarget.style.color = "var(--text-secondary)";
                }
              }}
            >
              <span>{item.label}</span>
              <ArrowRight size={11} color="var(--text-muted)" />
            </button>
          ))}
        </div>
      </div>
    </div>
  );
};
