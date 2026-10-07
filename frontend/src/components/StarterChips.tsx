"use client";

import React from "react";
import { ArrowUpRight } from "lucide-react";

interface StarterChipsProps {
  onSelectQuery: (query: string) => void;
  disabled?: boolean;
}

interface ChipItem {
  title: string;
  query: string;
  tag: string;
  isAmendment?: boolean;
  isRefusal?: boolean;
}

export const StarterChips: React.FC<StarterChipsProps> = ({ onSelectQuery, disabled }) => {
  const chips: ChipItem[] = [
    {
      title: "Minimum attendance required to sit for end-term exams",
      query: "What is the minimum attendance required to appear for end-semester exams?",
      tag: "§ 3.1",
    },
    {
      title: "Answer script re-evaluation fee and deadline",
      query: "How much is the fee for answer script re-evaluation?",
      tag: "amendment 1 · MRL 500",
      isAmendment: true,
    },
    {
      title: "Late tuition fee penalty calculation and cap",
      query: "What is the penalty for late payment of tuition fees?",
      tag: "amendment 2 · MRL 500/wk",
      isAmendment: true,
    },
    {
      title: "SGPA formula and failing course grade designation",
      query: "How is SGPA calculated and which grade indicates course failure?",
      tag: "§ 4.3 & 4.5",
    },
    {
      title: "Campus car parking lot location and rules",
      query: "Where is the student car parking lot located on campus?",
      tag: "out-of-scope test",
      isRefusal: true,
    },
  ];

  return (
    <div style={{ marginTop: "16px", marginBottom: "16px" }}>
      <div
        style={{
          fontSize: "12px",
          color: "var(--text-muted)",
          fontFamily: "var(--font-mono)",
          marginBottom: "10px",
        }}
      >
        suggested policy questions
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
          gap: "8px",
        }}
      >
        {chips.map((chip, idx) => (
          <button
            key={idx}
            type="button"
            disabled={disabled}
            onClick={() => onSelectQuery(chip.query)}
            style={{
              display: "flex",
              flexDirection: "column",
              justifyContent: "space-between",
              alignItems: "flex-start",
              gap: "8px",
              padding: "12px 14px",
              borderRadius: "var(--radius-sm)",
              backgroundColor: "var(--surface-1)",
              border: "1px solid var(--border)",
              color: "var(--text-primary)",
              textAlign: "left",
              cursor: disabled ? "not-allowed" : "pointer",
              transition: "border-color 0.15s ease, background-color 0.15s ease",
            }}
            onMouseEnter={(e) => {
              if (!disabled) {
                e.currentTarget.style.borderColor = "var(--border-strong)";
                e.currentTarget.style.backgroundColor = "var(--surface-2)";
              }
            }}
            onMouseLeave={(e) => {
              if (!disabled) {
                e.currentTarget.style.borderColor = "var(--border)";
                e.currentTarget.style.backgroundColor = "var(--surface-1)";
              }
            }}
          >
            <div
              style={{
                display: "flex",
                alignItems: "flex-start",
                justifyContent: "space-between",
                width: "100%",
                gap: "8px",
              }}
            >
              <span
                style={{
                  fontSize: "13px",
                  lineHeight: 1.45,
                  color: "var(--text-primary)",
                  fontWeight: 500,
                }}
              >
                {chip.title}
              </span>
              <ArrowUpRight
                size={14}
                color="var(--text-muted)"
                style={{ flexShrink: 0, marginTop: "2px" }}
              />
            </div>

            <div
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: "11px",
                color: chip.isRefusal
                  ? "var(--text-muted)"
                  : chip.isAmendment
                  ? "var(--warning)"
                  : "var(--accent)",
              }}
            >
              [{chip.tag}]
            </div>
          </button>
        ))}
      </div>
    </div>
  );
};
